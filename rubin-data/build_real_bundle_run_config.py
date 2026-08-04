#!/usr/bin/env python3
"""
Assemble the run-time files needed to execute a real v0.2 QuantumGraph export
bundle (qgraph_manifest.json + quanta.jsonl + edges.jsonl, from
qgraph_exporter.py) through cg-sim + libRubinDispatcherPlugin.so:

  clustering.json  - one cluster per task label, using that task's real
                      dimensions from the manifest (schema section 5)
  site_info.json   - a copy of the base topology with every genuinely
                      external input (produced by no quantum in this graph,
                      e.g. raw calibration products) pre-registered at
                      --raw-site, since core resolves input file locations
                      once at t=0 (see generate_campaign.py's
                      build_site_info(), which this generalizes from an
                      in-memory synthetic qgraph to a real streaming bundle)
  rubin_dag_config.json - Custom_Parameters pointed at the manifest and the
                      files above

This does not fit real resource models or build a campaign.json -- it is a
structural smoke-test harness for validating that a real rc2_subset export
loads and DAG-orders correctly, not a production run configuration.

Usage:
    python build_real_bundle_run_config.py \\
        --manifest $PSCRATCH/cgsim-rubin/artifacts/.../qgraph_manifest.json \\
        --site-info rubin-data/site_info.json \\
        --raw-site Base \\
        --default-site USDF \\
        --dispatcher-plugin .../libRubinDispatcherPlugin.so \\
        --out-dir $PSCRATCH/cgsim-rubin/artifacts/.../run_config
"""

import argparse
import json
import os


def load_bundle(manifest_path):
    with open(manifest_path) as f:
        manifest = json.load(f)
    bundle_dir = os.path.dirname(os.path.abspath(manifest_path))
    quanta = []
    with open(os.path.join(bundle_dir, manifest["quanta_file"])) as f:
        for line in f:
            line = line.strip()
            if line:
                quanta.append(json.loads(line))
    return manifest, quanta


def build_clustering(manifest, request_memory_mb, request_cpus):
    clusters = []
    for task in manifest["tasks"]:
        clusters.append({
            "name": f"{task['label']}_full",
            "task_labels": [task["label"]],
            "dimensions": task["dimensions"],
            "equal_dimensions": [],
            "max_quanta": None,
            "request_memory_mb": request_memory_mb,
            "request_cpus": request_cpus,
        })
    return {
        "schema_version": "0.2",
        "method": "dimension",
        "clusters": clusters,
        "overhead": {"pipetask_init_s": None, "final_job_s": None, "per_quantum_startup_s": None},
        "wms_retry": {"max_retries": 3, "memory_multiplier": None},
    }


def build_site_info(quanta, raw_site, base_site_info_path, default_bytes):
    with open(base_site_info_path) as f:
        site_info = json.load(f)
    if raw_site not in site_info:
        raise ValueError(f"--raw-site {raw_site!r} not found in {base_site_info_path} "
                          f"(available: {sorted(site_info)})")

    produced = {out["dataset_type"] for q in quanta for out in q["outputs"]}
    files = site_info[raw_site].setdefault("files", [])
    n = 0
    for q in quanta:
        for inp in q["inputs"]:
            if inp["dataset_type"] in produced:
                continue
            bytes_est = inp["bytes_est"] if inp["bytes_est"] is not None else default_bytes
            files.append([f"{inp['dataset_type']}_q{q['qid']}", bytes_est])
            n += 1
    return site_info, n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, help="path to qgraph_manifest.json")
    ap.add_argument("--site-info", required=True, help="base site_info.json to copy (e.g. rubin-data/site_info.json)")
    ap.add_argument("--raw-site", default="Base", help="netzone where external inputs are pre-registered")
    ap.add_argument("--default-site", default="USDF", help="netzone where cluster jobs run")
    ap.add_argument("--dispatcher-plugin", required=True, help="path to libRubinDispatcherPlugin.so")
    ap.add_argument("--sites-connection-info", required=True, help="path to site_conn_info.json")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--request-memory-mb", type=int, default=4096)
    ap.add_argument("--request-cpus", type=int, default=1)
    ap.add_argument("--default-bytes", type=int, default=100_000_000,
                     help="fallback size for inputs with a null bytes_est")
    ap.add_argument("--output-db", default="/tmp/rubin_real_bundle_output.db")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    manifest, quanta = load_bundle(args.manifest)

    clustering = build_clustering(manifest, args.request_memory_mb, args.request_cpus)
    clustering_path = os.path.join(args.out_dir, "clustering.json")
    with open(clustering_path, "w") as f:
        json.dump(clustering, f, indent=2)

    site_info, n_external = build_site_info(quanta, args.raw_site, args.site_info, args.default_bytes)
    site_info_path = os.path.join(args.out_dir, "site_info.json")
    with open(site_info_path, "w") as f:
        json.dump(site_info, f, indent=2)

    config = {
        "Grid_Name": "Rubin-Data-Facilities",
        "Sites_Information": site_info_path,
        "Sites_Connection_Information": os.path.abspath(args.sites_connection_info),
        "Dispatcher_Plugin": os.path.abspath(args.dispatcher_plugin),
        "Limited_Sites": [],
        "Custom_Parameters": {
            "qgraph_file": os.path.abspath(args.manifest),
            "clustering_file": clustering_path,
            "default_site": args.default_site,
            "output_file": args.output_db,
        },
    }
    config_path = os.path.join(args.out_dir, "rubin_dag_config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"wrote {clustering_path} ({len(clustering['clusters'])} clusters)")
    print(f"wrote {site_info_path} ({n_external} external input files pre-registered at {args.raw_site!r})")
    print(f"wrote {config_path}")


if __name__ == "__main__":
    main()
