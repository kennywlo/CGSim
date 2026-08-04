"""
Integration tests for qgraph_exporter.py against a real rc2_subset
QuantumGraph -- not synthetic data.

Requires an activated LSST Science Pipelines environment. On Perlmutter:

    export LSST_RELEASE_DIR=/cvmfs/sw.lsst.eu/almalinux-x86_64/lsst_distrib/w_2026_31
    source "$LSST_RELEASE_DIR/loadLSST.bash"
    setup lsst_distrib
    setup obs_subaru
    python -m pytest CGSim/rubin-data/tests/test_qgraph_exporter.py -v

Fixture selection: the spec target is rc2_subset's committed
central_six_coadd_9813.qgraph. That file was pickled in 2021 (see
`git log -- central_six_coadd_9813.qgraph`) by a daf_butler old enough to
predate the lsst.daf.butler.core module reorg *and* to rely on a custom
unpickleInstanceMethod reducer that no longer exists in any form under
w_2026_31 -- see qgraph-inspection.txt for the exact traceback and
qgraph_exporter.load_quantum_graph's docstring for the fallback chain that
was tried (default loadUri, minimumVersion=1 + explicit universe, and a
bounded module-alias shim investigation that got past three missing
submodules before hitting the unrecoverable pickle reducer). Because that
break is a genuine format incompatibility with no fix short of an old-era
stack, these tests fall back to a graph freshly rebuilt from the *same real*
rc2_subset Butler repo via `pipetask qgraph` (nightlyStep1, tract-unconstrained,
720 real quanta) if the original file isn't loadable. See README.md for the
exact rebuild command.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qgraph_exporter  # noqa: E402
import validate_bundle  # noqa: E402

pytest.importorskip("lsst.pipe.base", reason="requires an activated LSST Science Pipelines environment")

RC2_ROOT = os.environ.get("RC2_ROOT", os.path.expanduser("~/llm-apps/app/rc2_subset"))
RC2_REPO = os.environ.get("RC2_REPO", os.path.join(RC2_ROOT, "SMALL_HSC"))
ORIGINAL_QGRAPH = os.path.join(RC2_ROOT, "central_six_coadd_9813.qgraph")
FALLBACK_QGRAPH = os.environ.get(
    "RUBIN_TEST_QGRAPH_FALLBACK",
    os.path.join(os.environ.get("PSCRATCH", "/tmp"), "cgsim-rubin/artifacts/central_six_step1_9813.qgraph"),
)


def _rc2_commit():
    try:
        out = subprocess.check_output(
            ["git", "-C", RC2_ROOT, "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True,
        )
        return out.strip()
    except Exception:
        return None


def _resolve_test_qgraph():
    if os.path.isfile(ORIGINAL_QGRAPH):
        try:
            qgraph_exporter.load_quantum_graph(ORIGINAL_QGRAPH, RC2_REPO)
            return ORIGINAL_QGRAPH
        except Exception:
            pass
    if os.path.isfile(FALLBACK_QGRAPH):
        return FALLBACK_QGRAPH
    return None


@pytest.fixture(scope="module")
def qgraph_path():
    path = _resolve_test_qgraph()
    if path is None:
        pytest.skip(
            "no loadable real QuantumGraph fixture found; tried "
            f"{ORIGINAL_QGRAPH} (unloadable under the current stack, see module "
            f"docstring) and {FALLBACK_QGRAPH} (not yet built). Rebuild with: "
            "pipetask qgraph -b $RC2_REPO -i HSC/RC2_subset/defaults "
            "-o u/$USER/RC2_subset/qgraph_regen_step1 "
            "-p $DRP_PIPE_DIR/pipelines/HSC/DRP-RC2_subset.yaml#nightlyStep1 "
            "-q $FALLBACK_QGRAPH"
        )
    return path


@pytest.fixture(scope="module")
def loaded_qgraph(qgraph_path):
    qgraph, _notes = qgraph_exporter.load_quantum_graph(qgraph_path, RC2_REPO)
    return qgraph


def _export(tmp_path, name, qgraph_path, loaded_qgraph):
    out_dir = tmp_path / name
    manifest = qgraph_exporter.export(
        loaded_qgraph, str(out_dir),
        rc2_commit=_rc2_commit(), repo=RC2_REPO, qgraph_path=qgraph_path,
        sanitize=False, salt="test",
    )
    return out_dir, manifest


def test_every_node_appears_exactly_once(tmp_path, qgraph_path, loaded_qgraph):
    out_dir, manifest = _export(tmp_path, "bundle", qgraph_path, loaded_qgraph)

    qids, node_ids = [], []
    with open(out_dir / "quanta.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            qids.append(rec["qid"])
            node_ids.append(rec["source_node_id"])

    n_nodes = loaded_qgraph.graph.number_of_nodes()
    assert len(qids) == n_nodes == manifest["counts"]["quanta"]
    assert len(set(qids)) == n_nodes, "duplicate qid emitted"
    assert len(set(node_ids)) == n_nodes, "duplicate source QuantumGraph node emitted"
    assert {str(n.nodeId) for n in loaded_qgraph.graph.nodes} == set(node_ids)
    assert all(isinstance(q, int) for q in qids)
    assert set(qids) == set(range(1, n_nodes + 1)), "qids are not a dense 1..N assignment"


def test_edges_reference_existing_qids_and_agree_with_graph_topology(tmp_path, qgraph_path, loaded_qgraph):
    out_dir, _manifest = _export(tmp_path, "bundle", qgraph_path, loaded_qgraph)

    nodes = qgraph_exporter._sorted_nodes(loaded_qgraph)
    qid_of_node = {n.nodeId: i + 1 for i, n in enumerate(nodes)}

    qids = set()
    with open(out_dir / "quanta.jsonl") as f:
        for line in f:
            qids.add(json.loads(line)["qid"])

    graph_pairs = {
        (qid_of_node[parent.nodeId], qid_of_node[child.nodeId])
        for parent, child in loaded_qgraph.graph.edges
    }

    emitted_pairs = set()
    n_edges = 0
    with open(out_dir / "edges.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            n_edges += 1
            assert rec["producer_qid"] in qids
            assert rec["consumer_qid"] in qids
            emitted_pairs.add((rec["producer_qid"], rec["consumer_qid"]))

    assert n_edges > 0
    assert emitted_pairs <= graph_pairs, (
        f"emitted edges not present in QuantumGraph.graph: {emitted_pairs - graph_pairs}"
    )


def test_edge_dataset_types_grounded_in_shared_dataset_refs(tmp_path, qgraph_path, loaded_qgraph):
    out_dir, _manifest = _export(tmp_path, "bundle", qgraph_path, loaded_qgraph)

    nodes = qgraph_exporter._sorted_nodes(loaded_qgraph)
    node_of_qid = {i + 1: n for i, n in enumerate(nodes)}

    checked = 0
    with open(out_dir / "edges.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            producer_node = node_of_qid[rec["producer_qid"]]
            consumer_node = node_of_qid[rec["consumer_qid"]]
            producer_output_ids = {
                getattr(ref, "id", None)
                for refs in producer_node.quantum.outputs.values()
                for ref in refs
            }
            consumer_input_ids = {
                getattr(ref, "id", None)
                for refs in consumer_node.quantum.inputs.values()
                for ref in refs
            }
            assert producer_output_ids & consumer_input_ids, (
                f"edge {rec['producer_qid']}->{rec['consumer_qid']} "
                f"({rec['dataset_type']}) has no shared DatasetRef"
            )
            checked += 1
    assert checked > 0


def test_validator_passes_on_real_export(tmp_path, qgraph_path, loaded_qgraph):
    out_dir, _manifest = _export(tmp_path, "bundle", qgraph_path, loaded_qgraph)
    errors = validate_bundle.validate(str(out_dir / "qgraph_manifest.json"))
    assert errors == []


def test_repeated_export_is_structurally_deterministic(tmp_path, qgraph_path, loaded_qgraph):
    def _records(path):
        with open(path) as f:
            return [json.loads(line) for line in f]

    out1, _ = _export(tmp_path, "run1", qgraph_path, loaded_qgraph)
    out2, _ = _export(tmp_path, "run2", qgraph_path, loaded_qgraph)

    assert _records(out1 / "quanta.jsonl") == _records(out2 / "quanta.jsonl")
    assert _records(out1 / "edges.jsonl") == _records(out2 / "edges.jsonl")

    with open(out1 / "qgraph_manifest.json") as f:
        m1 = json.load(f)
    with open(out2 / "qgraph_manifest.json") as f:
        m2 = json.load(f)
    m1["provenance"].pop("exported_at")
    m2["provenance"].pop("exported_at")
    assert m1 == m2


def test_provenance_carries_pinned_revisions_and_rc2_commit(tmp_path, qgraph_path, loaded_qgraph):
    _out_dir, manifest = _export(tmp_path, "bundle", qgraph_path, loaded_qgraph)
    pinned = manifest["provenance"]["pinned"]
    assert pinned == {
        "lsst_release": "w_2026_31",
        "lsst_distrib": "g00e868bf88+c1824e70d0",
        "pipe_base": "g954f02917a+aa127417cf",
        "ctrl_bps": "ge3e32f3943+dd41cd23f8",
        "drp_pipe": "gc6b104cb6d+dad5072d3c",
        "obs_subaru": "g4db92921ce+973196f922",
    }
    assert manifest["provenance"]["qgraph_uuid"] == str(loaded_qgraph.graphID)
    assert manifest["provenance"]["butler_repo"] == os.path.abspath(RC2_REPO)
    assert manifest["provenance"]["butler_config"] == os.path.join(os.path.abspath(RC2_REPO), "butler.yaml")
    if _rc2_commit():
        assert manifest["provenance"]["rc2_subset_commit"] == _rc2_commit()


def test_sanitize_hashes_non_dimension_fields_but_keeps_instrument_band(tmp_path, qgraph_path, loaded_qgraph):
    out_dir = tmp_path / "sanitized"
    qgraph_exporter.export(
        loaded_qgraph, str(out_dir),
        rc2_commit=_rc2_commit(), repo=RC2_REPO, qgraph_path=qgraph_path,
        sanitize=True, salt="test-salt",
    )
    with open(out_dir / "quanta.jsonl") as f:
        first = json.loads(f.readline())
    data_id = first["data_id"]
    if "instrument" in data_id:
        assert data_id["instrument"] == "HSC"
    for key, value in data_id.items():
        if key in ("instrument", "band", "physical_filter", "skymap"):
            continue
        assert isinstance(value, str) and value.startswith("anon_"), (
            f"expected {key}={value!r} to be sanitized"
        )
