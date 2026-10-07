"""
ScenarioConfigGenerator — generate Rubin QGraph scenario configs for CGSim datagen.

Each scenario runs one synthetic Rubin DRP campaign (rubin-data/generate_campaign.py:
schema-v0.2 qgraph + clustering + resources + campaign files) through the rubin-plugin
on the baseline 5-site topology, with targeted overrides (reduced site capacity,
network throttling, disk throttling, workload size) so that the resulting EVENTS
databases exercise different operational patterns for AskPanDA SFT/GRPO.

Each scenario picks the site that runs the campaign (`site`) and the site where the
raw inputs are pre-registered (`raw_site`), so link and capacity overrides sit on the
path the workload actually uses.

Output layout:
  <output_dir>/
    manifest.json                  — index of all scenario configs
    <scenario_name>/
      qgraph_export.json, clustering.json, resources.json, campaign.json
      site_info.json               — baseline topology + overrides + raw inputs
      site_conn_info.json
      config.json                  — ready to pass to cg-sim -c

Usage:
  python ScenarioConfigGenerator.py \\
      --output-dir $PSCRATCH/cgsim-scenarios \\
      --dispatch-plugin ~/llm-apps/app/CGSim/dispatch_plugins/rubin-plugin/build/libRubinDispatcherPlugin.so
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ============================================================
# Baseline network (the topology itself comes from rubin-data/site_info.json
# via generate_campaign.py)
# ============================================================

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
    site: str = "USDF"          # site that runs the campaign
    raw_site: str = "Base"      # site where raw inputs are pre-registered
    visits: int = 20
    detectors: int = 9
    patches: int = 4
    site_overrides: dict[str, SiteOverride] = field(default_factory=dict)
    conn_overrides: dict[str, ConnOverride] = field(default_factory=dict)


SCENARIOS: dict[str, ScenarioSpec] = {
    "baseline": ScenarioSpec(
        description="Nominal Rubin 5-site grid operation",
    ),
    "usdf_degraded": ScenarioSpec(
        description="USDF compute halved at 300 visits — hardware failure or planned maintenance",
        visits=300,
        site_overrides={"USDF": SiteOverride(cpu_units_multiplier=0.5)},
    ),
    "base_degraded": ScenarioSpec(
        description="Base site compute halved — prompt processing bottleneck",
        site="Base", raw_site="Summit",
        site_overrides={"Base": SiteOverride(cpu_units_multiplier=0.5)},
    ),
    "frdf_offline": ScenarioSpec(
        description="FrDF network links throttled to 10 Mbps — site network partition",
        site="FrDF",
        conn_overrides={
            "Base:FrDF":  ConnOverride(bandwidth="10Mbps"),
            "USDF:FrDF":  ConnOverride(bandwidth="10Mbps"),
            "FrDF:UKDF":  ConnOverride(bandwidth="10Mbps"),
            "Summit:FrDF": ConnOverride(bandwidth="10Mbps"),
        },
    ),
    "summit_link_bottleneck": ScenarioSpec(
        description="Summit uplinks throttled to 1 Gbps — mountain network degradation",
        raw_site="Summit",
        conn_overrides={
            "Summit:Base":  ConnOverride(bandwidth="1Gbps"),
            "Summit:USDF":  ConnOverride(bandwidth="1Gbps"),
            "Summit:FrDF":  ConnOverride(bandwidth="1Gbps"),
            "Summit:UKDF":  ConnOverride(bandwidth="1Gbps"),
        },
    ),
    "transatlantic_congested": ScenarioSpec(
        description="All transatlantic links at 2 Gbps — intercontinental congestion",
        site="FrDF", raw_site="USDF",
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
        description="Heavy coadd burst — 12 patches per visit (DRP reprocessing campaign)",
        patches=12,
    ),
    "high_load": ScenarioSpec(
        description="Grid oversubscribed at 20% capacity, 100 visits — resource contention and scheduling retries",
        visits=100,
        site_overrides={
            "Base": SiteOverride(cpu_units_multiplier=0.2),
            "USDF": SiteOverride(cpu_units_multiplier=0.2),
            "FrDF": SiteOverride(cpu_units_multiplier=0.2),
            "UKDF": SiteOverride(cpu_units_multiplier=0.2),
        },
    ),
}


# ============================================================
# Config generation helpers
# ============================================================

_SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPT_DIR.parents[2]
GENERATE_CAMPAIGN = REPO_ROOT / "rubin-data" / "generate_campaign.py"


def apply_site_overrides(site_info: dict, overrides: dict[str, SiteOverride]) -> dict:
    for site_name, ov in overrides.items():
        site = site_info[site_name]
        storage = int(int(site["SITE_PROPERTIES"]["storage_capacity_bytes"]) * ov.storage_multiplier)
        site["SITE_PROPERTIES"]["storage_capacity_bytes"] = str(storage)
        site["storage"] = f"{storage}B"
        for cl in site["CPUInfo"]:
            cl["units"] = max(1, int(cl["units"] * ov.cpu_units_multiplier))
            for disk in cl["disks"]:
                if ov.disk_read_bw:  disk["read_bw"] = ov.disk_read_bw
                if ov.disk_write_bw: disk["write_bw"] = ov.disk_write_bw
    return site_info


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


def write_scenario(
    name: str,
    spec: ScenarioSpec,
    scenario_dir: Path,
    dispatch_plugin: str,
    seed: int,
) -> dict[str, str]:
    scenario_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [sys.executable, str(GENERATE_CAMPAIGN),
         "--visits", str(spec.visits), "--detectors", str(spec.detectors),
         "--patches", str(spec.patches), "--site", spec.site,
         "--raw-site", spec.raw_site, "--seed", str(seed),
         "--out-dir", str(scenario_dir)],
        check=True, stdout=subprocess.DEVNULL)

    site_info_path = scenario_dir / "site_info.json"
    conn_info_path = scenario_dir / "site_conn_info.json"
    config_path    = scenario_dir / "config.json"

    site_info = apply_site_overrides(json.loads(site_info_path.read_text()), spec.site_overrides)
    site_info_path.write_text(json.dumps(site_info, indent=2))
    conn_info_path.write_text(json.dumps(build_conn_info(BASELINE_CONNECTIONS, spec.conn_overrides), indent=2))

    # one cluster job per (visit, detector) sfp + (patch, visit) warp + one coadd per patch
    num_jobs = spec.visits * spec.detectors + spec.patches * spec.visits + spec.patches

    config = {
        "Grid_Name": f"Rubin-{name}",
        "Sites_Information": str(site_info_path.resolve()),
        "Sites_Connection_Information": str(conn_info_path.resolve()),
        "Plugin": dispatch_plugin,
        "Limited_Sites": [],
        "Custom_Parameters": {
            "qgraph_file": str((scenario_dir / "qgraph_export.json").resolve()),
            "clustering_file": str((scenario_dir / "clustering.json").resolve()),
            "campaign_file": str((scenario_dir / "campaign.json").resolve()),
            "resources_file": str((scenario_dir / "resources.json").resolve()),
            "default_site": spec.site,
            "output_file": f"/tmp/rubin_{name}.db",
        },
    }
    config_path.write_text(json.dumps(config, indent=4))

    print(f"  [{name}] {num_jobs} cluster jobs at {spec.site} (raw at {spec.raw_site}) → {scenario_dir}")
    return {
        "name": name,
        "description": spec.description,
        "config": str(config_path.resolve()),
        "output_db": config["Custom_Parameters"]["output_file"],
        "num_jobs": num_jobs,
    }


# ============================================================
# Main
# ============================================================

DEFAULT_DISPATCH_PLUGIN = str(
    REPO_ROOT / "dispatch_plugins" / "rubin-plugin" / "build" / "libRubinDispatcherPlugin.so")

DEFAULT_OUTPUT_DIR = REPO_ROOT / "rubin-data" / "scenarios"


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate CGSim scenario config variants")
    ap.add_argument(
        "--output-dir", default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory to write scenarios into (default: {DEFAULT_OUTPUT_DIR})",
    )
    ap.add_argument(
        "--dispatch-plugin", default=DEFAULT_DISPATCH_PLUGIN,
        help="Absolute path to libRubinDispatcherPlugin.so",
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
