#!/usr/bin/env python3
"""
Generate CGSim input files for Rubin Observatory workflows.

Sites:
  - Summit  : Cerro Pachón, Chile (telescope)
  - Base    : La Serena, Chile (prompt processing)
  - USDF    : SLAC, CA (primary data facility)
  - FrDF    : CC-IN2P3, Lyon, France (backup + processing)
  - UKDF    : RAL/IRIS, UK (additional processing)

Network (published Rubin specs + WLCG estimates):
  Summit <-> Base  : 100 Gbps, 1ms
  Base   <-> USDF  : 100 Gbps, 95ms   (Rubin long-haul network, Chile->CA)
  Base   <-> FrDF  : 10 Gbps,  160ms  (Chile->France)
  USDF   <-> FrDF  : 10 Gbps,  130ms  (CA->France transatlantic)
  USDF   <-> UKDF  : 10 Gbps,  120ms  (CA->UK transatlantic)
  FrDF   <-> UKDF  : 1 Gbps,   20ms   (France->UK)
"""

import json
import csv
import random
import math
import os

random.seed(42)
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Site definitions
# ---------------------------------------------------------------------------
#
# speed: FLOPS per core (SimGrid host speed)
# GFLOPS property: used by dispatcher as flops = GFLOPS * cpu_time * cores
# storage_capacity_bytes: total online disk capacity
# disk read/write bw: Lustre/GPFS typical sustained throughput per node
#
SITES = {
    "Summit": {
        "description": "Cerro Pachon summit site - camera readout buffer only",
        "storage_capacity_bytes": 10 * 10**12,   # 10 TB buffer
        "GFLOPS": 3,
        "cpu_clusters": [
            {
                "units": 8,
                "cores": 32,
                "speed": 3.2e9,
                "BW_CPU": "10GBps",
                "LAT_CPU": "1us",
                "disk_name": "SUMMIT_DISK",
                "disk_read_bw": "2GBps",
                "disk_write_bw": "2GBps",
            }
        ],
    },
    "Base": {
        "description": "La Serena base facility - prompt processing and alert distribution",
        "storage_capacity_bytes": 200 * 10**12,  # 200 TB
        "GFLOPS": 3,
        "cpu_clusters": [
            {
                "units": 50,
                "cores": 32,
                "speed": 3.2e9,
                "BW_CPU": "10GBps",
                "LAT_CPU": "1us",
                "disk_name": "BASE_DISK",
                "disk_read_bw": "5GBps",
                "disk_write_bw": "5GBps",
            }
        ],
    },
    "USDF": {
        "description": "SLAC US Data Facility - primary archive and DRP processing",
        "storage_capacity_bytes": 5 * 10**15,    # 5 PB online disk
        "GFLOPS": 3,
        "cpu_clusters": [
            {
                "units": 300,
                "cores": 32,
                "speed": 3.2e9,
                "BW_CPU": "10GBps",
                "LAT_CPU": "1us",
                "disk_name": "USDF_DISK",
                "disk_read_bw": "10GBps",
                "disk_write_bw": "10GBps",
            }
        ],
    },
    "FrDF": {
        "description": "CC-IN2P3 French Data Facility - backup archive and reprocessing",
        "storage_capacity_bytes": 2 * 10**15,    # 2 PB online disk
        "GFLOPS": 3,
        "cpu_clusters": [
            {
                "units": 150,
                "cores": 32,
                "speed": 3.2e9,
                "BW_CPU": "10GBps",
                "LAT_CPU": "1us",
                "disk_name": "FrDF_DISK",
                "disk_read_bw": "10GBps",
                "disk_write_bw": "10GBps",
            }
        ],
    },
    "UKDF": {
        "description": "RAL/IRIS UK Data Facility - additional processing capacity",
        "storage_capacity_bytes": 1 * 10**15,    # 1 PB online disk
        "GFLOPS": 3,
        "cpu_clusters": [
            {
                "units": 60,
                "cores": 32,
                "speed": 3.2e9,
                "BW_CPU": "10GBps",
                "LAT_CPU": "1us",
                "disk_name": "UKDF_DISK",
                "disk_read_bw": "10GBps",
                "disk_write_bw": "10GBps",
            }
        ],
    },
}

# ---------------------------------------------------------------------------
# Network connections
# bandwidth strings: SimGrid accepts "Gbps" (bits/s) or "GBps" (bytes/s)
# latency strings:   SimGrid accepts "ms", "us", "ns"
# ---------------------------------------------------------------------------
CONNECTIONS = {
    # Direct links (published Rubin specs)
    "Summit:Base": {"bandwidth": "100Gbps", "latency": "1ms"},
    "Base:USDF":   {"bandwidth": "100Gbps", "latency": "95ms"},
    "Base:FrDF":   {"bandwidth": "10Gbps",  "latency": "160ms"},
    "USDF:FrDF":   {"bandwidth": "10Gbps",  "latency": "130ms"},
    "USDF:UKDF":   {"bandwidth": "10Gbps",  "latency": "120ms"},
    "FrDF:UKDF":   {"bandwidth": "1Gbps",   "latency": "20ms"},
    # Indirect paths — SimGrid FullZone requires explicit pairwise routes.
    # Bandwidth = bottleneck of physical path; latency = sum of hops.
    "Summit:USDF": {"bandwidth": "100Gbps", "latency": "96ms"},   # via Base
    "Summit:FrDF": {"bandwidth": "10Gbps",  "latency": "161ms"},  # via Base
    "Summit:UKDF": {"bandwidth": "10Gbps",  "latency": "216ms"},  # via Base+USDF
    "Base:UKDF":   {"bandwidth": "10Gbps",  "latency": "215ms"},  # via USDF
}

# ---------------------------------------------------------------------------
# Synthetic Rubin job workload
#
# Job types reflect the Rubin Science Pipelines task graph:
#   1. Prompt (ISR + detection per CCD, runs at Base)
#   2. Single-frame calibration (runs at USDF)
#   3. Coadd/template building (runs at USDF or FrDF)
#   4. Difference imaging (runs at USDF)
#   5. Forced photometry / catalog (runs at USDF or FrDF)
#
# cpu_consumption_time: seconds of CPU time
# input file sizes: ~40 MB per raw CCD, ~100 MB per calibrated exp
# output file sizes: fraction of input
# ---------------------------------------------------------------------------
COMPUTE_SITES = ["Base", "USDF", "FrDF", "UKDF"]
SITE_WEIGHTS  = [0.15, 0.55, 0.20, 0.10]   # probability weights

JOB_TYPES = [
    {
        "name": "Prompt_ISR",
        "site_weights": [0.85, 0.10, 0.03, 0.02],
        "cores": 1,
        "cpu_time_mean": 30,     # seconds
        "cpu_time_std": 10,
        "n_input_files_range": (1, 1),
        "input_file_size_mean": 42 * 10**6,   # 42 MB per CCD
        "input_file_size_std":  5  * 10**6,
        "n_output_files_range": (1, 2),
        "output_size_fraction": 0.9,
    },
    {
        "name": "SingleFrame_Cal",
        "site_weights": [0.05, 0.70, 0.15, 0.10],
        "cores": 4,
        "cpu_time_mean": 120,
        "cpu_time_std": 40,
        "n_input_files_range": (1, 3),
        "input_file_size_mean": 100 * 10**6,
        "input_file_size_std":  20  * 10**6,
        "n_output_files_range": (1, 3),
        "output_size_fraction": 1.1,
    },
    {
        "name": "Coadd",
        "site_weights": [0.02, 0.55, 0.28, 0.15],
        "cores": 8,
        "cpu_time_mean": 600,
        "cpu_time_std": 200,
        "n_input_files_range": (10, 50),
        "input_file_size_mean": 100 * 10**6,
        "input_file_size_std":  20  * 10**6,
        "n_output_files_range": (1, 4),
        "output_size_fraction": 0.5,
    },
    {
        "name": "DiffImaging",
        "site_weights": [0.05, 0.65, 0.20, 0.10],
        "cores": 4,
        "cpu_time_mean": 180,
        "cpu_time_std": 60,
        "n_input_files_range": (2, 4),
        "input_file_size_mean": 100 * 10**6,
        "input_file_size_std":  20  * 10**6,
        "n_output_files_range": (1, 2),
        "output_size_fraction": 0.3,
    },
    {
        "name": "ForcedPhotom",
        "site_weights": [0.02, 0.58, 0.25, 0.15],
        "cores": 8,
        "cpu_time_mean": 300,
        "cpu_time_std": 100,
        "n_input_files_range": (5, 20),
        "input_file_size_mean": 50 * 10**6,
        "input_file_size_std":  10 * 10**6,
        "n_output_files_range": (1, 3),
        "output_size_fraction": 0.2,
    },
]

# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def build_site_info():
    out = {}
    for site_name, cfg in SITES.items():
        clusters = []
        for cl in cfg["cpu_clusters"]:
            clusters.append({
                "units": cl["units"],
                "cores": cl["cores"],
                "speed": cl["speed"],
                "BW_CPU": cl["BW_CPU"],
                "LAT_CPU": cl["LAT_CPU"],
                "properties": [],
                "disks": [
                    {
                        "name": cl["disk_name"],
                        "read_bw":  cl["disk_read_bw"],
                        "write_bw": cl["disk_write_bw"],
                    }
                ],
            })

        out[site_name] = {
            "SITE_PROPERTIES": {
                "storage_capacity_bytes": str(cfg["storage_capacity_bytes"]),
                "GFLOPS": str(cfg["GFLOPS"]),
                "description": cfg["description"],
            },
            "CPUInfo": clusters,
            "files": [],
        }
    return out


def build_site_conn_info():
    return CONNECTIONS


def lognormal_sample(mean, std, min_val=1):
    """Sample from a log-normal with given approximate mean and std."""
    if std <= 0:
        return max(int(mean), min_val)
    sigma2 = math.log(1 + (std / mean) ** 2)
    mu = math.log(mean) - sigma2 / 2
    val = random.lognormvariate(mu, math.sqrt(sigma2))
    return max(int(val), min_val)


# Source site for each job type's input files — where the data lives before processing
SOURCE_SITE = {
    "Prompt_ISR":     "Summit",   # raw images come from the telescope
    "SingleFrame_Cal": "Base",    # ISR outputs live at Base
    "Coadd":           "USDF",    # calibrated exposures archived at USDF
    "DiffImaging":     "USDF",
    "ForcedPhotom":    "USDF",
}


def build_jobs_csv(n_jobs=500):
    rows = []
    # files_by_site: {site_name: {filename: size}} — accumulated for site_info registration
    files_by_site = {s: {} for s in SITES}
    job_type_weights = [0.40, 0.25, 0.15, 0.12, 0.08]

    for job_id in range(1, n_jobs + 1):
        jtype = random.choices(JOB_TYPES, weights=job_type_weights)[0]

        site = random.choices(COMPUTE_SITES, weights=jtype["site_weights"])[0]
        cores = jtype["cores"]
        cpu_time = lognormal_sample(jtype["cpu_time_mean"], jtype["cpu_time_std"], 1)

        n_in = random.randint(*jtype["n_input_files_range"])
        input_files = {}
        total_input_bytes = 0
        src_site = SOURCE_SITE[jtype["name"]]

        for f in range(n_in):
            size = lognormal_sample(
                jtype["input_file_size_mean"], jtype["input_file_size_std"], 1024
            )
            fname = f"lsst_{jtype['name']}_{job_id}_{f:04d}.fits"
            input_files[fname] = size
            total_input_bytes += size
            files_by_site[src_site][fname] = size

        n_out = random.randint(*jtype["n_output_files_range"])
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


# ---------------------------------------------------------------------------
# Write files
# ---------------------------------------------------------------------------

def main():
    # Generate jobs first to collect which files need to be registered at each site
    jobs, files_by_site = build_jobs_csv(n_jobs=500)

    # Build site_info with pre-registered input files
    site_info = build_site_info()
    for site_name, files in files_by_site.items():
        total_file_bytes = sum(files.values())
        capacity = int(site_info[site_name]["SITE_PROPERTIES"]["storage_capacity_bytes"])
        if total_file_bytes > capacity:
            raise RuntimeError(
                f"Site {site_name}: input files ({total_file_bytes/1e12:.2f} TB) "
                f"exceed capacity ({capacity/1e12:.2f} TB)"
            )
        site_info[site_name]["files"] = [[name, size] for name, size in files.items()]
        print(f"  {site_name}: registered {len(files)} files "
              f"({total_file_bytes/1e9:.1f} GB / {capacity/1e12:.1f} TB)")

    path = os.path.join(OUT_DIR, "site_info.json")
    with open(path, "w") as f:
        json.dump(site_info, f, indent=2)
    print(f"Written: {path}")

    conn_info = build_site_conn_info()
    path = os.path.join(OUT_DIR, "site_conn_info.json")
    with open(path, "w") as f:
        json.dump(conn_info, f, indent=2)
    print(f"Written: {path}")

    path = os.path.join(OUT_DIR, "jobs.csv")
    fieldnames = ["pandaid", "computingsite", "cpuconsumptiontime", "corecount",
                  "noutputdatafiles", "outputfilebytes", "files_info"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(jobs)
    print(f"Written: {path}  ({len(jobs)} jobs)")


if __name__ == "__main__":
    main()
