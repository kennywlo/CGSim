#!/usr/bin/env python3
"""
Stream a real LSST QuantumGraph into the rubin_campaign_schema v0.2 bundle
(qgraph_manifest.json, quanta.jsonl, edges.jsonl -- schema section 4 in
LLM-Interface/rubin_campaign_schema_v0.2.md).

Requires an activated LSST Science Pipelines environment (lsst.pipe.base and
lsst.daf.butler importable). On Perlmutter:

    export LSST_RELEASE_DIR=/cvmfs/sw.lsst.eu/almalinux-x86_64/lsst_distrib/w_2026_31
    source "$LSST_RELEASE_DIR/loadLSST.bash"
    setup lsst_distrib
    setup obs_subaru

Usage:
    python qgraph_exporter.py \\
        --qgraph /path/to/graph.qgraph \\
        --repo /path/to/butler_repo \\
        --out-dir /path/to/output \\
        --rc2-commit 432ea10

Design notes (see LLM-Interface/rubin_campaign_schema_v0.2.md section 4):
  - qid assignment is deterministic: nodes are sorted by their QuantumGraph
    nodeId (a UUID) before qids are assigned, so repeated exports of the same
    graph produce identical qid numbering.
  - Records are written incrementally as each node is visited. The only
    additional in-memory state is a compact id->qid index and a
    DatasetRef.id -> (producer_qid, dataset_type) index used to find edges;
    neither duplicates the QuantumGraph itself as a second JSON structure.
  - Dependency edges are derived by matching each consumer's input
    DatasetRefs against the DatasetRefs every earlier-seen quantum produced
    as outputs (matched by DatasetRef.id, i.e. the same physical dataset),
    not by walking QuantumGraph.graph.edges directly. Identical
    (producer_qid, consumer_qid, dataset_type) triples are deduplicated.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SCHEMA_VERSION = "0.2"

# Recorded once here so every export carries the same pinned provenance
# regardless of caller. See LLM-Interface/TODO.md "Kenny: Perlmutter
# readiness" and perlmutter-env.txt / lsst-products.txt for how these were
# established.
PINNED_PRODUCTS = {
    "lsst_release": "w_2026_31",
    "lsst_distrib": "g00e868bf88+c1824e70d0",
    "pipe_base": "g954f02917a+aa127417cf",
    "ctrl_bps": "ge3e32f3943+dd41cd23f8",
    "drp_pipe": "gc6b104cb6d+dad5072d3c",
    "obs_subaru": "g4db92921ce+973196f922",
}


def _git_commit(path):
    """Best-effort git commit lookup for provenance; None if unavailable."""
    directory = path if os.path.isdir(path) else os.path.dirname(path)
    try:
        out = subprocess.check_output(
            ["git", "-C", directory, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        )
        return out.strip()
    except Exception:
        return None


def load_quantum_graph(qgraph_path, repo):
    """Load a QuantumGraph, working around older serialization formats.

    Current pipe_base (w_2026_31) defaults QuantumGraph.loadUri to
    minimumVersion=3 and expects the DimensionUniverse to be embedded in the
    file. Format-version-1 graphs need an explicit universe (pulled from the
    target Butler repo) and a lowered minimumVersion -- see
    qgraph-inspection.txt for the exact tracebacks this fallback chain was
    derived from.

    Graphs old enough to have been pickled before the
    lsst.daf.butler.core -> lsst.daf.butler module reorg (and the loss of
    the custom unpickleInstanceMethod reducer for bound methods) cannot be
    recovered by any loadUri argument; this function does not attempt a
    pickle-compatibility shim for that case and instead raises with a clear
    message pointing at regenerating the graph via `pipetask qgraph` against
    the current stack.

    Returns (qgraph, load_notes) where load_notes lists which fallback path
    was used, for inclusion in export provenance.
    """
    from lsst.daf.butler import Butler
    from lsst.pipe.base import QuantumGraph

    notes = []
    try:
        return QuantumGraph.loadUri(qgraph_path), notes
    except Exception as exc:
        notes.append(f"default loadUri failed: {exc!r}")

    butler = Butler(repo)
    try:
        qgraph = QuantumGraph.loadUri(
            qgraph_path, universe=butler.dimensions, minimumVersion=1
        )
        notes.append("loaded with minimumVersion=1 and explicit universe=Butler(repo).dimensions")
        return qgraph, notes
    except Exception as exc:
        notes.append(f"minimumVersion=1 fallback failed: {exc!r}")
        raise RuntimeError(
            f"Could not load QuantumGraph at {qgraph_path!r} under the "
            "current pipe_base/daf_butler. If this is a pre-2022-era graph, "
            "it may be pickled with a lsst.daf.butler.core module layout "
            "and an unpickleInstanceMethod reducer that no longer exist in "
            "any form (not just moved) -- regenerate it instead with "
            "`pipetask qgraph` against the currently activated stack. "
            f"Fallback attempts: {notes}"
        ) from exc


def sanitize_value(value, salt):
    digest = hashlib.sha256(f"{salt}:{value!r}".encode()).hexdigest()[:12]
    return f"anon_{digest}"


def sanitize_data_id(data_id, salt, exempt_keys=("instrument", "band", "physical_filter", "skymap")):
    """Hash data ID values that could identify unreleased data.

    Public HSC rc2_subset identifiers are not proprietary (RDO-013 v1.2.5
    DPOL-520) and may remain visible by default -- this is opt-in via
    --sanitize, for use against unreleased commissioning/LSSTCam exports.
    """
    return {
        k: (v if k in exempt_keys else sanitize_value(v, salt))
        for k, v in data_id.items()
    }


def _dataset_type_name(dataset_type):
    return getattr(dataset_type, "name", str(dataset_type))


def _summarize_refs(mapping, dataset_types_seen):
    """mapping: DatasetType -> Sequence[DatasetRef]."""
    summaries = []
    for dataset_type, refs in mapping.items():
        name = _dataset_type_name(dataset_type)
        refs = list(refs)
        dataset_types_seen.add(name)
        summaries.append({"dataset_type": name, "n": len(refs), "bytes_est": None})
    return summaries


def _sorted_nodes(qgraph):
    """Deterministic node order for reproducible qid assignment."""
    return sorted(qgraph.graph.nodes, key=lambda n: str(n.nodeId))


def export(qgraph, out_dir, *, rc2_commit, repo, qgraph_path, sanitize, salt,
           pinned=PINNED_PRODUCTS):
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "qgraph_manifest.json")
    quanta_path = os.path.join(out_dir, "quanta.jsonl")
    edges_path = os.path.join(out_dir, "edges.jsonl")

    nodes = _sorted_nodes(qgraph)
    qid_of = {node.nodeId: i + 1 for i, node in enumerate(nodes)}

    tasks_seen = {}
    dataset_types_seen = set()
    producer_of_ref = {}  # DatasetRef.id -> (producer_qid, dataset_type_name)
    instrument = None

    with open(quanta_path, "w") as qf:
        for node in nodes:
            quantum = node.quantum
            task = node.taskDef
            qid = qid_of[node.nodeId]
            label = getattr(task, "label", None)
            data_id = dict(quantum.dataId.mapping)
            if instrument is None:
                instrument = data_id.get("instrument")

            if label not in tasks_seen:
                tasks_seen[label] = {
                    "label": label,
                    "class": getattr(task, "taskName", None),
                    "dimensions": sorted(data_id.keys()),
                    "resource_key": f"{label}:{data_id.get('instrument', instrument or 'UNKNOWN')}",
                }

            out_data_id = sanitize_data_id(data_id, salt) if sanitize else data_id
            inputs = _summarize_refs(quantum.inputs, dataset_types_seen)
            outputs = _summarize_refs(quantum.outputs, dataset_types_seen)

            for dataset_type, refs in quantum.outputs.items():
                name = _dataset_type_name(dataset_type)
                for ref in refs:
                    ref_id = getattr(ref, "id", None)
                    if ref_id is not None:
                        producer_of_ref[ref_id] = (qid, name)

            qf.write(json.dumps({
                "schema_version": SCHEMA_VERSION,
                "record_type": "quantum",
                "qid": qid,
                "task": label,
                "data_id": out_data_id,
                "inputs": inputs,
                "outputs": outputs,
                "source_node_id": str(node.nodeId),
            }) + "\n")

    seen_edges = set()
    edge_count = 0
    with open(edges_path, "w") as ef:
        for node in nodes:
            consumer_qid = qid_of[node.nodeId]
            for dataset_type, refs in node.quantum.inputs.items():
                for ref in refs:
                    ref_id = getattr(ref, "id", None)
                    if ref_id is None:
                        continue
                    producer = producer_of_ref.get(ref_id)
                    if producer is None:
                        continue  # produced outside this graph (e.g. raw/calib)
                    producer_qid, dataset_type_name = producer
                    key = (producer_qid, consumer_qid, dataset_type_name)
                    if key in seen_edges:
                        continue
                    seen_edges.add(key)
                    edge_count += 1
                    ef.write(json.dumps({
                        "schema_version": SCHEMA_VERSION,
                        "record_type": "edge",
                        "producer_qid": producer_qid,
                        "consumer_qid": consumer_qid,
                        "dataset_type": dataset_type_name,
                    }) + "\n")

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "provenance": {
            "qgraph_uuid": str(qgraph.graphID),
            "qgraph_path": os.path.abspath(qgraph_path),
            "butler_repo": os.path.abspath(repo),
            "butler_config": os.path.join(os.path.abspath(repo), "butler.yaml"),
            "rc2_subset_commit": rc2_commit,
            "instrument": instrument,
            "pinned": pinned,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "sanitized": bool(sanitize),
        },
        "tasks": sorted(tasks_seen.values(), key=lambda t: t["label"]),
        "quanta_file": "quanta.jsonl",
        "edges_file": "edges.jsonl",
        "counts": {
            "quanta": len(nodes),
            "edges": edge_count,
            "dataset_types": len(dataset_types_seen),
            "tasks": len(tasks_seen),
        },
    }
    with open(manifest_path, "w") as mf:
        json.dump(manifest, mf, indent=2, sort_keys=True)

    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qgraph", required=True, help="path to a saved QuantumGraph (.qgraph/.qg)")
    ap.add_argument("--repo", required=True, help="Butler repository root (e.g. rc2_subset/SMALL_HSC)")
    ap.add_argument("--out-dir", required=True, help="output directory for the v0.2 bundle")
    ap.add_argument("--rc2-commit", default=None,
                     help="git commit of the rc2_subset checkout providing --repo/--qgraph "
                          "(auto-detected via git if omitted)")
    ap.add_argument("--sanitize", action="store_true",
                     help="hash non-dimension data ID values; not needed for public rc2_subset")
    ap.add_argument("--salt", default="cgsim-rubin", help="salt for --sanitize hashing")
    args = ap.parse_args(argv)

    qgraph, load_notes = load_quantum_graph(args.qgraph, args.repo)
    for note in load_notes:
        print(f"[load] {note}", file=sys.stderr)

    rc2_commit = args.rc2_commit or _git_commit(args.qgraph)

    manifest = export(
        qgraph, args.out_dir,
        rc2_commit=rc2_commit, repo=args.repo, qgraph_path=args.qgraph,
        sanitize=args.sanitize, salt=args.salt,
    )
    print(json.dumps(manifest["counts"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
