"""
ScenarioConfigGenerator — generate CGSim config variants for failure-mode coverage.

Each scenario starts from the baseline Rubin 5-site topology and applies targeted
overrides (reduced site capacity, network throttling, shifted job mix) so that the
resulting EVENTS databases exercise different operational patterns for AskPanDA SFT.

Output layout:
  <output_dir>/
    manifest.json                  — index of all scenario configs
    <scenario_name>/
      site_info.json
      site_conn_info.json
      jobs.csv
      config.json                  — ready to pass to cg-sim -c

Usage:
  python ScenarioConfigGenerator.py \\
      --output-dir $PSCRATCH/cgsim-scenarios \\
      --dispatch-plugin ~/llm-apps/app/CGSim/dispatch_plugins/simple-test-plugin/build/libSimpleDispatcherPlugin.so
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ============================================================
# Baseline topology (mirrors rubin-data/generate.py)
# ============================================================

BASELINE_SITES: dict[str, Any] = {
    "Summit": {
        "description": "Cerro Pachon summit site - camera readout buffer only",
        "storage_capacity_bytes": 10 * 10**12,
        "GFLOPS": 3,
        "cpu_clusters": [
            {"units": 8,   "cores": 32, "speed": 3.2e9,
             "BW_CPU": "10GBps", "LAT_CPU": "1us",
             "disk_name": "SUMMIT_DISK", "disk_read_bw": "2GBps", "disk_write_bw": "2GBps"},
        ],
    },
    "Base": {
        "description": "La Serena base facility - prompt processing and alert distribution",
        "storage_capacity_bytes": 200 * 10**12,
        "GFLOPS": 3,
        "cpu_clusters": [
            {"units": 50,  "cores": 32, "speed": 3.2e9,
             "BW_CPU": "10GBps", "LAT_CPU": "1us",
             "disk_name": "BASE_DISK", "disk_read_bw": "5GBps", "disk_write_bw": "5GBps"},
        ],
    },
    "USDF": {
        "description": "SLAC US Data Facility - primary archive and DRP processing",
        "storage_capacity_bytes": 5 * 10**15,
        "GFLOPS": 3,
        "cpu_clusters": [
            {"units": 300, "cores": 32, "speed": 3.2e9,
             "BW_CPU": "10GBps", "LAT_CPU": "1us",
             "disk_name": "USDF_DISK", "disk_read_bw": "10GBps", "disk_write_bw": "10GBps"},
        ],
    },
    "FrDF": {
        "description": "CC-IN2P3 French Data Facility - backup archive and reprocessing",
        "storage_capacity_bytes": 2 * 10**15,
        "GFLOPS": 3,
        "cpu_clusters": [
            {"units": 150, "cores": 32, "speed": 3.2e9,
             "BW_CPU": "10GBps", "LAT_CPU": "1us",
             "disk_name": "FrDF_DISK", "disk_read_bw": "10GBps", "disk_write_bw": "10GBps"},
        ],
    },
    "UKDF": {
        "description": "RAL/IRIS UK Data Facility - additional processing capacity",
        "storage_capacity_bytes": 1 * 10**15,
        "GFLOPS": 3,
        "cpu_clusters": [
            {"units": 60,  "cores": 32, "speed": 3.2e9,
             "BW_CPU": "10GBps", "LAT_CPU": "1us",
             "disk_name": "UKDF_DISK", "disk_read_bw": "10GBps", "disk_write_bw": "10GBps"},
        ],
    },
}

BASELINE_CONNECTIONS: dict[str, dict[str, str]] = {
    "Summit:Base":  {"bandwidth": "100Gbps", "latency": "1ms"},
    "Base:USDF":    {"bandwidth": "100Gbps", "latency": "95ms"},
    "Base:FrDF":    {"bandwidth": "10Gbps",  "latency": "160ms"},
    "USDF:FrDF":    {"bandwidth": "10Gbps",  "latency": "130ms"},
    "USDF:UKDF":    {"bandwidth": "10Gbps",  "latency": "120ms"},
    "FrDF:UKDF":    {"bandwidth": "10Gbps",  "latency": "20ms"},
    "Summit:USDF":  {"bandwidth": "100Gbps", "latency": "96ms"},
    "Summit:FrDF":  {"bandwidth": "10Gbps",  "latency": "161ms"},
    "Summit:UKDF":  {"bandwidth": "10Gbps",  "latency": "216ms"},
    "Base:UKDF":    {"bandwidth": "10Gbps",  "latency": "215ms"},
}

BASELINE_JOB_TYPES = [
    {
        "name": "Prompt_ISR",
        "site_weights": [0.85, 0.10, 0.03, 0.02],
        "cores": 1,
        "cpu_time_mean": 90,  "cpu_time_std": 20,
        "n_input_files_range": (1, 1),
        "input_file_size_mean": 80 * 10**6, "input_file_size_std": 8 * 10**6,
        "n_output_files_range": (1, 2),
        "output_size_fraction": 0.9,
    },
    {
        "name": "SingleFrame_Cal",
        "site_weights": [0.05, 0.70, 0.15, 0.10],
        "cores": 4,
        "cpu_time_mean": 420, "cpu_time_std": 100,
        "n_input_files_range": (1, 3),
        "input_file_size_mean": 100 * 10**6, "input_file_size_std": 20 * 10**6,
        "n_output_files_range": (1, 3),
        "output_size_fraction": 1.1,
    },
    {
        "name": "Coadd",
        "site_weights": [0.02, 0.55, 0.28, 0.15],
        "cores": 8,
        "cpu_time_mean": 3600, "cpu_time_std": 1000,
        "n_input_files_range": (10, 50),
        "input_file_size_mean": 100 * 10**6, "input_file_size_std": 20 * 10**6,
        "n_output_files_range": (1, 4),
        "output_size_fraction": 0.5,
    },
    {
        "name": "DiffImaging",
        "site_weights": [0.05, 0.65, 0.20, 0.10],
        "cores": 4,
        "cpu_time_mean": 600, "cpu_time_std": 150,
        "n_input_files_range": (2, 4),
        "input_file_size_mean": 100 * 10**6, "input_file_size_std": 20 * 10**6,
        "n_output_files_range": (1, 2),
        "output_size_fraction": 0.3,
    },
    {
        "name": "ForcedPhotom",
        "site_weights": [0.02, 0.58, 0.25, 0.15],
        "cores": 8,
        "cpu_time_mean": 900, "cpu_time_std": 250,
        "n_input_files_range": (5, 20),
        "input_file_size_mean": 50 * 10**6, "input_file_size_std": 10 * 10**6,
        "n_output_files_range": (1, 3),
        "output_size_fraction": 0.2,
    },
]

COMPUTE_SITES = ["Base", "USDF", "FrDF", "UKDF"]

SOURCE_SITE = {
    "Prompt_ISR":     "Summit",
    "SingleFrame_Cal": "Base",
    "Coadd":           "USDF",
    "DiffImaging":     "USDF",
    "ForcedPhotom":    "USDF",
}

BASELINE_JOB_TYPE_WEIGHTS = [0.40, 0.25, 0.15, 0.12, 0.08]


# ============================================================
# Scenario specs
# ============================================================

@dataclass
class SiteOverride:
    cpu_units_multiplier: float = 1.0
    storage_multiplier: float = 1.0
    disk_read_bw: str | None = None
    disk_write_bw: str | None = None


@dataclass
class ConnOverride:
    bandwidth: str | None = None
    latency: str | None = None


@dataclass
class ScenarioSpec:
    description: str
    site_overrides: dict[str, SiteOverride] = field(default_factory=dict)
    conn_overrides: dict[str, ConnOverride] = field(default_factory=dict)
    num_jobs: int = 1000
    job_type_weights: list[float] | None = None


SCENARIOS: dict[str, ScenarioSpec] = {
    "baseline": ScenarioSpec(
        description="Nominal Rubin 5-site grid operation",
    ),
    "usdf_degraded": ScenarioSpec(
        description="USDF compute halved — hardware failure or planned maintenance",
        site_overrides={"USDF": SiteOverride(cpu_units_multiplier=0.5)},
    ),
    "base_degraded": ScenarioSpec(
        description="Base site compute halved — prompt processing bottleneck",
        site_overrides={"Base": SiteOverride(cpu_units_multiplier=0.5)},
    ),
    "frdf_offline": ScenarioSpec(
        description="FrDF network links throttled to 10 Mbps — site network partition",
        conn_overrides={
            "Base:FrDF":  ConnOverride(bandwidth="10Mbps"),
            "USDF:FrDF":  ConnOverride(bandwidth="10Mbps"),
            "FrDF:UKDF":  ConnOverride(bandwidth="10Mbps"),
            "Summit:FrDF": ConnOverride(bandwidth="10Mbps"),
        },
    ),
    "summit_link_bottleneck": ScenarioSpec(
        description="Summit uplinks throttled to 1 Gbps — mountain network degradation",
        conn_overrides={
            "Summit:Base":  ConnOverride(bandwidth="1Gbps"),
            "Summit:USDF":  ConnOverride(bandwidth="1Gbps"),
            "Summit:FrDF":  ConnOverride(bandwidth="1Gbps"),
            "Summit:UKDF":  ConnOverride(bandwidth="1Gbps"),
        },
    ),
    "transatlantic_congested": ScenarioSpec(
        description="All transatlantic links at 2 Gbps — intercontinental congestion",
        conn_overrides={
            "Base:USDF":  ConnOverride(bandwidth="2Gbps"),
            "Base:FrDF":  ConnOverride(bandwidth="2Gbps"),
            "USDF:FrDF":  ConnOverride(bandwidth="2Gbps"),
            "USDF:UKDF":  ConnOverride(bandwidth="2Gbps"),
            "Summit:USDF": ConnOverride(bandwidth="2Gbps"),
        },
    ),
    "usdf_storage_throttled": ScenarioSpec(
        description="USDF disk I/O throttled to 1 GBps — storage system degradation",
        site_overrides={"USDF": SiteOverride(disk_read_bw="1GBps", disk_write_bw="1GBps")},
    ),
    "high_coadd_burst": ScenarioSpec(
        description="Heavy Coadd/ForcedPhotom burst — DRP reprocessing campaign",
        # Shift weight toward compute-heavy jobs
        job_type_weights=[0.10, 0.15, 0.45, 0.15, 0.15],
    ),
    "high_load": ScenarioSpec(
        description="Grid oversubscribed at 20% capacity — resource contention and scheduling retries",
        site_overrides={
            "Base": SiteOverride(cpu_units_multiplier=0.2),
            "USDF": SiteOverride(cpu_units_multiplier=0.2),
            "FrDF": SiteOverride(cpu_units_multiplier=0.2),
            "UKDF": SiteOverride(cpu_units_multiplier=0.2),
        },
        num_jobs=1500,
    ),
}


# ============================================================
# Config generation helpers
# ============================================================

def lognormal_sample(rng: random.Random, mean: float, std: float, min_val: int = 1) -> int:
    if std <= 0:
        return max(int(mean), min_val)
    sigma2 = math.log(1 + (std / mean) ** 2)
    mu = math.log(mean) - sigma2 / 2
    return max(int(rng.lognormvariate(mu, math.sqrt(sigma2))), min_val)


def build_site_info(
    sites: dict[str, Any],
    files_by_site: dict[str, dict[str, int]],
    overrides: dict[str, SiteOverride],
) -> dict[str, Any]:
    out = {}
    for site_name, cfg in sites.items():
        ov = overrides.get(site_name, SiteOverride())
        storage = int(cfg["storage_capacity_bytes"] * ov.storage_multiplier)
        clusters = []
        for cl in cfg["cpu_clusters"]:
            units = max(1, int(cl["units"] * ov.cpu_units_multiplier))
            clusters.append({
                "units": units,
                "cores": cl["cores"],
                "speed": cl["speed"],
                "BW_CPU": cl["BW_CPU"],
                "LAT_CPU": cl["LAT_CPU"],
                "properties": [],
                "disks": [{
                    "name": cl["disk_name"],
                    "read_bw":  ov.disk_read_bw  or cl["disk_read_bw"],
                    "write_bw": ov.disk_write_bw or cl["disk_write_bw"],
                }],
            })
        registered = [[name, size] for name, size in files_by_site.get(site_name, {}).items()]
        out[site_name] = {
            "SITE_PROPERTIES": {
                "storage_capacity_bytes": str(storage),
                "GFLOPS": str(cfg["GFLOPS"]),
                "description": cfg["description"],
            },
            "CPUInfo": clusters,
            "files": registered,
        }
    return out


def build_conn_info(
    connections: dict[str, dict[str, str]],
    overrides: dict[str, ConnOverride],
) -> dict[str, dict[str, str]]:
    out = {}
    for link, vals in connections.items():
        ov = overrides.get(link)
        out[link] = {
            "bandwidth": ov.bandwidth if ov and ov.bandwidth else vals["bandwidth"],
            "latency":   ov.latency   if ov and ov.latency   else vals["latency"],
        }
    return out


def build_jobs(
    rng: random.Random,
    n_jobs: int,
    job_type_weights: list[float],
    job_types: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    files_by_site: dict[str, dict[str, int]] = {s: {} for s in BASELINE_SITES}
    rows = []
    for job_id in range(1, n_jobs + 1):
        jtype = rng.choices(job_types, weights=job_type_weights)[0]
        site = rng.choices(COMPUTE_SITES, weights=jtype["site_weights"])[0]
        cores = jtype["cores"]
        cpu_time = lognormal_sample(rng, jtype["cpu_time_mean"], jtype["cpu_time_std"])
        n_in = rng.randint(*jtype["n_input_files_range"])
        input_files: dict[str, int] = {}
        total_input_bytes = 0
        src_site = SOURCE_SITE[jtype["name"]]
        for f in range(n_in):
            size = lognormal_sample(rng, jtype["input_file_size_mean"], jtype["input_file_size_std"], 1024)
            fname = f"lsst_{jtype['name']}_{job_id}_{f:04d}.fits"
            input_files[fname] = size
            total_input_bytes += size
            files_by_site[src_site][fname] = size
        n_out = rng.randint(*jtype["n_output_files_range"])
        total_output_bytes = int(total_input_bytes * jtype["output_size_fraction"])
        files_info_str = "{" + ",".join(f'"{k}":{v}' for k, v in input_files.items()) + "}"
        rows.append({
            "pandaid": job_id,
            "computingsite": site,
            "cpuconsumptiontime": cpu_time,
            "corecount": cores,
            "noutputdatafiles": n_out,
            "outputfilebytes": total_output_bytes,
            "files_info": files_info_str,
        })
    return rows, files_by_site


def write_scenario(
    name: str,
    spec: ScenarioSpec,
    scenario_dir: Path,
    dispatch_plugin: str,
    seed: int,
) -> dict[str, str]:
    scenario_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    job_weights = spec.job_type_weights or BASELINE_JOB_TYPE_WEIGHTS
    jobs, files_by_site = build_jobs(rng, spec.num_jobs, job_weights, BASELINE_JOB_TYPES)

    site_info = build_site_info(BASELINE_SITES, files_by_site, spec.site_overrides)
    conn_info = build_conn_info(BASELINE_CONNECTIONS, spec.conn_overrides)

    site_info_path = scenario_dir / "site_info.json"
    conn_info_path = scenario_dir / "site_conn_info.json"
    jobs_csv_path  = scenario_dir / "jobs.csv"
    config_path    = scenario_dir / "config.json"

    site_info_path.write_text(json.dumps(site_info, indent=2))
    conn_info_path.write_text(json.dumps(conn_info, indent=2))

    fieldnames = ["pandaid", "computingsite", "cpuconsumptiontime", "corecount",
                  "noutputdatafiles", "outputfilebytes", "files_info"]
    with jobs_csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(jobs)

    config = {
        "Grid_Name": f"Rubin-{name}",
        "Sites_Information": str(site_info_path.resolve()),
        "Sites_Connection_Information": str(conn_info_path.resolve()),
        "Dispatcher_Plugin": dispatch_plugin,
        "Limited_Sites": [],
        "Custom_Parameters": {
            "Num_of_Jobs": "-1",
            "jobs_file": str(jobs_csv_path.resolve()),
            "output_file": f"/tmp/rubin_{name}.db",
        },
    }
    config_path.write_text(json.dumps(config, indent=4))

    print(f"  [{name}] {spec.num_jobs} jobs → {scenario_dir}")
    return {
        "name": name,
        "description": spec.description,
        "config": str(config_path.resolve()),
        "output_db": config["Custom_Parameters"]["output_file"],
        "num_jobs": spec.num_jobs,
    }


# ============================================================
# Main
# ============================================================

DEFAULT_DISPATCH_PLUGIN = (
    str(Path.home() / "llm-apps/app/CGSim/dispatch_plugins"
        "/simple-test-plugin/build/libSimpleDispatcherPlugin.so")
)

_SCRIPT_DIR = Path(__file__).parent
DEFAULT_OUTPUT_DIR = _SCRIPT_DIR.parent.parent / "rubin-data" / "scenarios"


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate CGSim scenario config variants")
    ap.add_argument(
        "--output-dir", default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory to write scenarios into (default: {DEFAULT_OUTPUT_DIR})",
    )
    ap.add_argument(
        "--dispatch-plugin", default=DEFAULT_DISPATCH_PLUGIN,
        help="Absolute path to libSimpleDispatcherPlugin.so",
    )
    ap.add_argument(
        "--scenarios", nargs="+", default=list(SCENARIOS.keys()),
        choices=list(SCENARIOS.keys()),
        help="Which scenarios to generate (default: all)",
    )
    args = ap.parse_args()

    if not Path(args.dispatch_plugin).exists():
        print(f"WARNING: dispatch plugin not found: {args.dispatch_plugin}", file=sys.stderr)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i, name in enumerate(args.scenarios):
        spec = SCENARIOS[name]
        entry = write_scenario(
            name=name,
            spec=spec,
            scenario_dir=output_dir / name,
            dispatch_plugin=args.dispatch_plugin,
            seed=42 + i,
        )
        manifest.append(entry)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote manifest: {manifest_path}  ({len(manifest)} scenarios)")


if __name__ == "__main__":
    main()
