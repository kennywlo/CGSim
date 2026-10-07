#!/usr/bin/env python3
"""Convert an lsst/drp_pipe BPS clustering YAML into a rubin_campaign_schema v0.2 clustering.json.

The BPS `cluster:` section (ctrl_bps dimension_clustering) lists, per cluster, the pipetasks bundled
into one job and the dimensions that define a job. This follows `includeConfigs`, so passing the
per-instrument file (e.g. bps/clustering/HSC/DRP-RC2-clustering.yaml) works. A drp_pipe git tag or
ref (e.g. w.2025.41) selects the version a given campaign ran with.

Optionally, --bundle applies the clustering to a real QuantumGraph bundle (qgraph_manifest.json)
and prints jobs and quanta per job for each cluster. That check is independent of the C++ plugin.

Semantics encoded in clustering.json (ctrl_bps dimension_clustering, as understood here):
  dimensions            quanta of the listed tasks with the same values form one job
  equal_dimensions      [a, b] pairs: dimension a of one task is the same data ID value as dimension b
                        of another (e.g. visit == exposure, so isr and calibrateImage cluster together)
  partition_dimensions  extra dimensions that split a cluster into separate jobs; with
  partition_max_clusters  recorded but not enforced (the caps are well above typical cluster counts)
Tasks not named by any cluster run as one job per quantum, labelled by the task.
"""
import argparse
import collections
import json
import os
import re
import subprocess
import sys

import yaml

DRP_PIPE_DIR_VAR = "${DRP_PIPE_DIR}/"


class Source:
    """Reads files from a drp_pipe checkout, optionally at a git ref."""

    def __init__(self, root, ref=None):
        self.root, self.ref = os.path.abspath(os.path.expanduser(root)), ref

    def read(self, relpath):
        if self.ref:
            return subprocess.run(["git", "-C", self.root, "show", f"{self.ref}:{relpath}"],
                                  check=True, capture_output=True, text=True).stdout
        with open(os.path.join(self.root, relpath)) as f:
            return f.read()

    def load(self, relpath, seen=None):
        """Load a BPS YAML, merging `includeConfigs` (included files first, this file overrides)."""
        seen = seen or set()
        if relpath in seen:
            raise ValueError(f"includeConfigs loop at {relpath}")
        seen.add(relpath)
        doc = yaml.safe_load(self.read(relpath)) or {}
        merged = {}
        for inc in doc.pop("includeConfigs", []) or []:
            if not inc.startswith(DRP_PIPE_DIR_VAR):
                raise ValueError(f"unsupported include {inc!r} in {relpath}")
            merged = deep_merge(merged, self.load(inc[len(DRP_PIPE_DIR_VAR):], seen))
        return deep_merge(merged, doc)


def deep_merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def split_list(value):
    return [x.strip() for x in str(value).split(",") if x.strip()] if value else []


def build(clustering_doc, resources_doc):
    pipetask_mem = {t: v.get("requestMemory") for t, v in (resources_doc or {}).get("pipetask", {}).items()
                    if isinstance(v, dict)}
    clusters = []
    for name, spec in clustering_doc["cluster"].items():
        tasks = split_list(spec["pipetasks"])
        equal = [pair.split(":") for pair in split_list(spec.get("equalDimensions"))]
        mem = [pipetask_mem[t] for t in tasks if pipetask_mem.get(t)]
        clusters.append({
            "name": name,
            "task_labels": tasks,
            "dimensions": split_list(spec["dimensions"]),
            "equal_dimensions": equal,
            "partition_dimensions": split_list(spec.get("partitionDimensions")),
            "partition_max_clusters": spec.get("partitionMaxClusters"),
            "max_quanta": spec.get("clusterMaxQuanta"),
            "request_memory_mb": max(mem) if mem else None,
            "request_cpus": 1,
        })
    return {
        "schema_version": "0.2",
        "method": "dimension",
        "algorithm": clustering_doc.get("clusterAlgorithm"),
        "clusters": clusters,
        "overhead": {"pipetask_init_s": None, "final_job_s": None, "per_quantum_startup_s": None},
        "wms_retry": {"max_retries": 3, "memory_multiplier": None},
    }


def dim_value(data_id, dim, equal):
    if dim in data_id:
        return data_id[dim]
    for a, b in equal:
        if dim == a and b in data_id:
            return data_id[b]
        if dim == b and a in data_id:
            return data_id[a]
    return None


def cluster_key(q, clustering):
    for spec in clustering["clusters"]:
        if q["task"] in spec["task_labels"]:
            dims = spec["dimensions"] + [d for d in spec["partition_dimensions"] if d not in spec["dimensions"]]
            return (spec["name"],) + tuple(json.dumps(dim_value(q["data_id"], d, spec["equal_dimensions"])) for d in dims)
    return ("sq_" + q["task"], q["qid"])


def check_bundle(manifest_path, clustering):
    with open(manifest_path) as f:
        manifest = json.load(f)
    bundle_dir = os.path.dirname(os.path.abspath(manifest_path))
    jobs = collections.defaultdict(list)
    with open(os.path.join(bundle_dir, manifest["quanta_file"])) as f:
        for line in f:
            q = json.loads(line)
            jobs[cluster_key(q, clustering)].append(q["task"])
    per = collections.defaultdict(list)
    for key, tasks in jobs.items():
        per[key[0]].append(len(tasks))
    nq = sum(len(t) for t in jobs.values())
    print(f"\n{nq} quanta -> {len(jobs)} jobs ({nq / len(jobs):.2f} quanta per job on average)")
    print(f"{'cluster / unclustered task':42s} {'jobs':>6s} {'quanta/job':>12s}")
    named = {c["name"] for c in clustering["clusters"]}
    for name in sorted(per, key=lambda n: (n not in named, n)):
        sizes = per[name]
        if name.startswith("sq_"):
            continue
        print(f"{name:42s} {len(sizes):6d} {min(sizes):>6d}..{max(sizes):<5d}")
    uncl = {n: len(s) for n, s in per.items() if n.startswith("sq_")}
    print(f"unclustered tasks: {len(uncl)} tasks, {sum(uncl.values())} single-quantum jobs")
    return len(jobs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yaml", required=True,
                    help="clustering YAML path relative to the drp_pipe root, e.g. bps/clustering/HSC/DRP-RC2-clustering.yaml")
    ap.add_argument("--resources", action="append", default=[],
                    help="resources YAML(s) relative to the drp_pipe root, e.g. bps/resources/HSC/DRP-RC2.yaml "
                         "(cluster request_memory_mb = max over its member tasks; assumption, not verified against ctrl_bps)")
    ap.add_argument("--drp-pipe-dir", default="~/llm-apps/app/drp_pipe")
    ap.add_argument("--ref", help="drp_pipe git ref/tag, e.g. w.2025.41 (default: working tree)")
    ap.add_argument("--out", help="write clustering.json here")
    ap.add_argument("--bundle", help="qgraph_manifest.json: report jobs and quanta per job")
    args = ap.parse_args()

    src = Source(args.drp_pipe_dir, args.ref)
    resources = {}
    for r in args.resources:
        resources = deep_merge(resources, src.load(r))
    clustering = build(src.load(args.yaml), resources)
    rev = subprocess.run(["git", "-C", src.root, "rev-parse", "--short", args.ref or "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    clustering["provenance"] = {"source": "lsst/drp_pipe", "yaml": args.yaml, "resources": args.resources,
                                "ref": args.ref or "working tree", "commit": rev,
                                "memory_rule": "max over member tasks (assumption)"}
    if args.out:
        with open(args.out, "w") as f:
            json.dump(clustering, f, indent=2)
        print(f"wrote {args.out}: {len(clustering['clusters'])} clusters from {args.yaml} @ {args.ref or 'working tree'} ({rev})")
    if args.bundle:
        check_bundle(args.bundle, clustering)
    elif not args.out:
        json.dump(clustering, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
