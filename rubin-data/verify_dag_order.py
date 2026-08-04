#!/usr/bin/env python3
"""
Verify DAG-gated execution ordering in a rubin-plugin EVENTS db.

Recomputes the cluster DAG exactly the way the plugin does (same cluster keys,
same sorted-key -> jobid assignment starting at 1000), then checks that every
child job's first ExecutionStart is >= the max ExecutionEnd of all its parents.

Usage:
  verify_dag_order.py <events.db> [--qgraph qgraph_export.json] [--clustering clustering.json]

Defaults assume campaign-demo/ next to this script.
"""

import argparse
import json
import os
import sqlite3
import sys


def load_qgraph_bundle(path):
    """Load either the monolithic qgraph_export.json test-fixture format
    (top-level quanta/edges arrays, as generate_campaign.py produces) or a
    real v0.2 streaming bundle: a qgraph_manifest.json whose quanta_file/
    edges_file point at quanta.jsonl/edges.jsonl (see
    LLM-Interface/rubin_campaign_schema_v0.2.md section 4 and
    rubin-data/qgraph_exporter.py), resolved relative to the manifest's own
    directory. Mirrors QGRAPH_WORKLOAD::load_qgraph_bundle in the C++ plugin.
    """
    with open(path) as f:
        top = json.load(f)
    if "quanta" in top and "edges" in top:
        return top
    if "quanta_file" not in top or "edges_file" not in top:
        raise ValueError(
            f"{path} has neither inline quanta/edges nor quanta_file/edges_file "
            "-- not a recognized qgraph bundle format"
        )
    bundle_dir = os.path.dirname(os.path.abspath(path))

    def _read_jsonl(rel_path):
        records = []
        with open(os.path.join(bundle_dir, rel_path)) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    top["quanta"] = _read_jsonl(top["quanta_file"])
    top["edges"] = _read_jsonl(top["edges_file"])
    return top


def cluster_key(quantum, clustering):
    for spec in clustering["clusters"]:
        if quantum["task"] in spec["task_labels"]:
            key = spec["name"]
            for dim in spec["dimensions"]:
                key += "_" + json.dumps(quantum["data_id"][dim])
            return key
    return f"sq_{quantum['task']}_{quantum['qid']}"


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--qgraph", default=os.path.join(here, "campaign-demo/qgraph_export.json"))
    ap.add_argument("--clustering", default=os.path.join(here, "campaign-demo/clustering.json"))
    args = ap.parse_args()

    qgraph = load_qgraph_bundle(args.qgraph)
    with open(args.clustering) as f:
        clustering = json.load(f)

    cluster_of = {q["qid"]: cluster_key(q, clustering) for q in qgraph["quanta"]}
    # std::map iteration order == python sorted() for these ASCII keys
    jobid_of = {key: 1000 + i for i, key in enumerate(sorted(set(cluster_of.values())))}

    dag_edges = set()
    for e in qgraph["edges"]:
        p = jobid_of[cluster_of[e["producer_qid"]]]
        c = jobid_of[cluster_of[e["consumer_qid"]]]
        if p != c:
            dag_edges.add((p, c))

    db = sqlite3.connect(args.db)
    starts, ends = {}, {}
    for jid, t in db.execute(
            "SELECT JOB_ID, MIN(TIME) FROM EVENTS "
            "WHERE EVENT='JobExecution' AND STATE='Started' GROUP BY JOB_ID"):
        starts[int(jid)] = t
    for jid, t in db.execute(
            "SELECT JOB_ID, MAX(TIME) FROM EVENTS "
            "WHERE EVENT='JobExecution' AND STATE='Finished' GROUP BY JOB_ID"):
        ends[int(jid)] = t

    missing = [j for j in jobid_of.values() if j not in starts or j not in ends]
    violations = []
    for p, c in sorted(dag_edges):
        if p in ends and c in starts and starts[c] < ends[p]:
            violations.append((p, c, starts[c], ends[p]))

    print(f"clusters: {len(jobid_of)}  dag edges: {len(dag_edges)}  "
          f"executed: {len(starts)}")
    if missing:
        print(f"WARNING: {len(missing)} jobs missing execution events "
              f"(first few: {missing[:5]})")
    if violations:
        print(f"FAIL: {len(violations)} ordering violations")
        for p, c, cs, pe in violations[:10]:
            print(f"  child {c} started {cs:.6f} before parent {p} ended {pe:.6f}")
        sys.exit(1)
    print("OK: every child started at/after its last parent's end")


if __name__ == "__main__":
    main()
