#!/usr/bin/env python3
"""
Generate synthetic rubin_campaign_schema v0.2 instance files for the
rubin-plugin scaffold (see LLM-Interface/rubin_campaign_schema_v0.2.md).

Emits into --out-dir (default: rubin-data/campaign-demo/):
  campaign.json       - minimal campaign graph, one step / one group (schema section 2)
  qgraph_export.json  - quanta + dataset edges for a DRP-like pipeline (section 4)
  clustering.json     - clustering overlay (section 5)
  resources.json      - per-task lognorm resource models (section 6)

Demo pipeline (single qgraph, chains + fan-in so the DAG gate is exercised):
  isr -> characterizeImage -> calibrate      per (visit, detector)
  calibrate -> makeWarp                      per (patch, visit), fan-in over detectors
  makeWarp  -> assembleCoadd                 per patch, fan-in over visits

This is a structural stand-in, not an astronomically faithful qgraph: the real
exporter (schema section 4) replaces this file's output without touching the plugin.
"""

import argparse
import json
import random
import uuid

SCHEMA_VERSION = "0.2"
INSTRUMENT = "LSSTCam"

TASKS = [
    {"label": "isr",              "class": "lsst.ip.isr.IsrTask",                        "dimensions": ["visit", "detector"]},
    {"label": "characterizeImage","class": "lsst.pipe.tasks.characterizeImage.CharacterizeImageTask", "dimensions": ["visit", "detector"]},
    {"label": "calibrate",        "class": "lsst.pipe.tasks.calibrate.CalibrateTask",    "dimensions": ["visit", "detector"]},
    {"label": "makeWarp",         "class": "lsst.pipe.tasks.makeWarp.MakeWarpTask",      "dimensions": ["tract", "patch", "visit"]},
    {"label": "assembleCoadd",    "class": "lsst.pipe.tasks.assembleCoadd.AssembleCoaddTask", "dimensions": ["tract", "patch", "band"]},
]

# Rough per-copy output sizes in bytes, used for bytes_est
DATASET_BYTES = {
    "raw":         2_000_000_000,
    "postISRCCD":  2_000_000_000,
    "icSrc":         50_000_000,
    "calexp":     1_500_000_000,
    "deepCoadd_directWarp": 800_000_000,
    "deepCoadd":  1_000_000_000,
}

# scipy lognorm convention: params = [shape(sigma), loc, scale]
RESOURCE_MODELS = {
    "isr":              {"cpu_s": [0.4, 0.0, 30.0],  "wall_s": [0.4, 0.0, 35.0],  "max_rss_mb": [0.3, 0.0, 2000.0]},
    "characterizeImage":{"cpu_s": [0.5, 0.0, 60.0],  "wall_s": [0.5, 0.0, 70.0],  "max_rss_mb": [0.3, 0.0, 2500.0]},
    "calibrate":        {"cpu_s": [0.5, 0.0, 90.0],  "wall_s": [0.5, 0.0, 100.0], "max_rss_mb": [0.3, 0.0, 3000.0]},
    "makeWarp":         {"cpu_s": [0.6, 0.0, 120.0], "wall_s": [0.6, 0.0, 140.0], "max_rss_mb": [0.4, 0.0, 3500.0]},
    "assembleCoadd":    {"cpu_s": [0.7, 0.0, 300.0], "wall_s": [0.7, 0.0, 340.0], "max_rss_mb": [0.4, 0.0, 6000.0]},
}


def build_qgraph(visits, detectors, patches, group_id, campaign_name):
    tract = 0
    band = "i"
    quanta, edges = [], []
    qid = 0
    calexp_qid = {}   # (visit, detector) -> calibrate qid
    warp_qid = {}     # (patch, visit)    -> makeWarp qid

    # Round-robin detector -> patch mapping (structural stand-in for sky geometry)
    patch_detectors = {p: [d for d in range(detectors) if d % patches == p] for p in range(patches)}

    for v in range(visits):
        for d in range(detectors):
            data_id = {"visit": v, "detector": d, "band": band}
            qid += 1; isr = qid
            quanta.append({"qid": isr, "task": "isr", "data_id": data_id,
                           "inputs":  [{"dataset_type": "raw", "n": 1, "bytes_est": DATASET_BYTES["raw"]}],
                           "outputs": [{"dataset_type": "postISRCCD", "n": 1, "bytes_est": DATASET_BYTES["postISRCCD"]}]})
            qid += 1; char = qid
            quanta.append({"qid": char, "task": "characterizeImage", "data_id": data_id,
                           "inputs":  [{"dataset_type": "postISRCCD", "n": 1, "bytes_est": DATASET_BYTES["postISRCCD"]}],
                           "outputs": [{"dataset_type": "icSrc", "n": 1, "bytes_est": DATASET_BYTES["icSrc"]}]})
            qid += 1; cal = qid
            quanta.append({"qid": cal, "task": "calibrate", "data_id": data_id,
                           "inputs":  [{"dataset_type": "icSrc", "n": 1, "bytes_est": DATASET_BYTES["icSrc"]}],
                           "outputs": [{"dataset_type": "calexp", "n": 1, "bytes_est": DATASET_BYTES["calexp"]}]})
            calexp_qid[(v, d)] = cal
            edges.append({"producer_qid": isr,  "consumer_qid": char, "dataset_type": "postISRCCD"})
            edges.append({"producer_qid": char, "consumer_qid": cal,  "dataset_type": "icSrc"})

    for p in range(patches):
        for v in range(visits):
            qid += 1; warp = qid
            quanta.append({"qid": warp, "task": "makeWarp",
                           "data_id": {"tract": tract, "patch": p, "visit": v},
                           "inputs":  [{"dataset_type": "calexp", "n": len(patch_detectors[p]), "bytes_est": DATASET_BYTES["calexp"]}],
                           "outputs": [{"dataset_type": "deepCoadd_directWarp", "n": 1, "bytes_est": DATASET_BYTES["deepCoadd_directWarp"]}]})
            warp_qid[(p, v)] = warp
            for d in patch_detectors[p]:
                edges.append({"producer_qid": calexp_qid[(v, d)], "consumer_qid": warp, "dataset_type": "calexp"})

    for p in range(patches):
        qid += 1; coadd = qid
        quanta.append({"qid": coadd, "task": "assembleCoadd",
                       "data_id": {"tract": tract, "patch": p, "band": band},
                       "inputs":  [{"dataset_type": "deepCoadd_directWarp", "n": visits, "bytes_est": DATASET_BYTES["deepCoadd_directWarp"]}],
                       "outputs": [{"dataset_type": "deepCoadd", "n": 1, "bytes_est": DATASET_BYTES["deepCoadd"]}]})
        for v in range(visits):
            edges.append({"producer_qid": warp_qid[(p, v)], "consumer_qid": coadd, "dataset_type": "deepCoadd_directWarp"})

    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": {
            "lsst_distrib": "synthetic",
            "qgraph_uuid": str(uuid.uuid4()),
            "campaign": campaign_name,
            "group_id": group_id,
            "rescue_of": None,
            "pipeline_yaml": "synthetic://generate_campaign.py",
            "input_collections": ["synthetic/raw"],
            "output_run": "u/synthetic/demo",
            "instrument": INSTRUMENT,
        },
        "tasks": [dict(t, resource_key=f"{t['label']}:{INSTRUMENT}") for t in TASKS],
        "quanta": quanta,
        "edges": edges,
    }


def build_campaign(name, site, group_id, qgraph_uuid, visits):
    ids = {k: str(uuid.uuid4()) for k in ("start", "step", "group", "collect", "end")}
    ids["group"] = group_id
    nodes = [
        {"id": ids["start"],   "kind": "start",          "name": "START",   "configuration": {}},
        {"id": ids["step"],    "kind": "step",           "name": "step_demo",
         "configuration": {"splitter": {"split_by": "null"}}},
        {"id": ids["group"],   "kind": "group",          "name": "step_demo_g0",
         "configuration": {"predicate": f"instrument='{INSTRUMENT}' AND visit < {visits}",
                           "wms": "panda", "site": site, "qgraph_ref": qgraph_uuid}},
        {"id": ids["collect"], "kind": "collect_groups", "name": "step_demo_collect", "configuration": {}},
        {"id": ids["end"],     "kind": "end",            "name": "END",     "configuration": {}},
    ]
    order = ["start", "step", "group", "collect", "end"]
    edges = [{"source": ids[a], "target": ids[b]} for a, b in zip(order, order[1:])]
    return {
        "schema_version": SCHEMA_VERSION,
        "campaign": {
            "name": name,
            "provenance": {"lsst_distrib": "synthetic", "drp_pipe_ref": "synthetic",
                           "pipeline_yaml": "synthetic://generate_campaign.py", "source": "synthetic"},
            "nodes": nodes,
            "edges": edges,
        },
    }


def build_clustering():
    return {
        "schema_version": SCHEMA_VERSION,
        "method": "user_labeled",
        "clusters": [
            {"name": "sfp_visit_detector", "task_labels": ["isr", "characterizeImage", "calibrate"],
             "dimensions": ["visit", "detector"], "equal_dimensions": [], "max_quanta": None,
             "request_memory_mb": 4096, "request_cpus": 4},
            {"name": "warp_patch_visit", "task_labels": ["makeWarp"],
             "dimensions": ["tract", "patch", "visit"], "equal_dimensions": [], "max_quanta": None,
             "request_memory_mb": 4096, "request_cpus": 2},
            {"name": "coadd_patch", "task_labels": ["assembleCoadd"],
             "dimensions": ["tract", "patch", "band"], "equal_dimensions": [], "max_quanta": None,
             "request_memory_mb": 8192, "request_cpus": 4},
        ],
        "overhead": {"pipetask_init_s": None, "final_job_s": None, "per_quantum_startup_s": None},
        "wms_retry": {"max_retries": 3, "memory_multiplier": None},
    }


def build_resources(n_quanta):
    models = {}
    for label, dists in RESOURCE_MODELS.items():
        models[f"{label}:{INSTRUMENT}"] = {
            k: {"dist": "lognorm", "params": v} for k, v in dists.items()
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "provenance": {"fit_source": "synthetic", "campaign": "demo",
                       "n_samples": n_quanta, "lsst_distrib_versions": ["synthetic"],
                       "fit_inputs": []},
        "models": models,
        "dataset_types": {
            name: {"bytes": {"dist": "lognorm", "params": [0.2, 0.0, float(size)]}}
            for name, size in DATASET_BYTES.items()
        },
    }


def build_site_info(qgraph, raw_site, base_site_info_path):
    """Copy site_info.json with this qgraph's external inputs (raw) pre-registered
    at raw_site. Required because core resolves every job's input file locations
    once at t=0 (util/job_executor.cpp -> FileManager::request_file_location);
    files not registered before the run make FileManager throw."""
    with open(base_site_info_path) as f:
        site_info = json.load(f)

    produced = {out["dataset_type"] for q in qgraph["quanta"] for out in q["outputs"]}
    files = site_info[raw_site].setdefault("files", [])
    n = 0
    for q in qgraph["quanta"]:
        for inp in q["inputs"]:
            if inp["dataset_type"] in produced:
                continue
            files.append([f"{inp['dataset_type']}_q{q['qid']}", inp["bytes_est"]])
            n += 1
    return site_info, n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--visits", type=int, default=20)
    ap.add_argument("--detectors", type=int, default=9)
    ap.add_argument("--patches", type=int, default=4)
    ap.add_argument("--site", default="USDF", help="SimGrid netzone name from site_info.json")
    ap.add_argument("--raw-site", default="Base", help="site where external inputs (raw) are pre-registered")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    random.seed(args.seed)
    import os
    out_dir = args.out_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "campaign-demo")
    os.makedirs(out_dir, exist_ok=True)

    campaign_name = "synthetic_demo_dp"
    group_id = str(uuid.uuid4())

    qgraph = build_qgraph(args.visits, args.detectors, args.patches, group_id, campaign_name)
    campaign = build_campaign(campaign_name, args.site, group_id,
                              qgraph["provenance"]["qgraph_uuid"], args.visits)
    clustering = build_clustering()
    resources = build_resources(len(qgraph["quanta"]))
    site_info, n_raw = build_site_info(
        qgraph, args.raw_site,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "site_info.json"))

    for fname, obj in [("campaign.json", campaign), ("qgraph_export.json", qgraph),
                       ("clustering.json", clustering), ("resources.json", resources),
                       ("site_info.json", site_info)]:
        path = os.path.join(out_dir, fname)
        with open(path, "w") as f:
            json.dump(obj, f, indent=2)
        print(f"wrote {path}")

    n_sfp = args.visits * args.detectors
    n_warp = args.patches * args.visits
    print(f"\nquanta: {len(qgraph['quanta'])}  edges: {len(qgraph['edges'])}")
    print(f"expected clusters (WMS jobs): {n_sfp} sfp + {n_warp} warp + {args.patches} coadd "
          f"= {n_sfp + n_warp + args.patches}")


if __name__ == "__main__":
    main()
