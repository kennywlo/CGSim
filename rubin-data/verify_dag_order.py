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

    with open(args.qgraph) as f:
        qgraph = json.load(f)
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
