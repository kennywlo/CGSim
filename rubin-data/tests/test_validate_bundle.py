"""
Unit tests for validate_bundle.py against hand-built bundles.

Pure standard library -- no LSST environment required, so these run in any
CI context. See test_qgraph_exporter.py for the tests against the real
rc2_subset QuantumGraph, which do require an activated LSST stack.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import validate_bundle  # noqa: E402

VALID_PROVENANCE = {
    "qgraph_uuid": "1785815689.7669582-812339",
    "qgraph_path": "/fake/central_six_step1_9813.qgraph",
    "butler_repo": "/fake/SMALL_HSC",
    "butler_config": "/fake/SMALL_HSC/butler.yaml",
    "rc2_subset_commit": "432ea10",
    "instrument": "HSC",
    "pinned": {
        "lsst_release": "w_2026_31",
        "lsst_distrib": "g00e868bf88+c1824e70d0",
        "pipe_base": "g954f02917a+aa127417cf",
        "ctrl_bps": "ge3e32f3943+dd41cd23f8",
        "drp_pipe": "gc6b104cb6d+dad5072d3c",
        "obs_subaru": "g4db92921ce+973196f922",
    },
    "exported_at": "2026-08-04T00:00:00+00:00",
    "sanitized": False,
}

VALID_TASKS = [
    {"label": "isr", "class": "lsst.ip.isr.isrTask.IsrTask", "dimensions": ["detector", "exposure"],
     "resource_key": "isr:HSC"},
    {"label": "calibrateImage", "class": "lsst.pipe.tasks.calibrateImage.CalibrateImageTask",
     "dimensions": ["detector", "exposure"], "resource_key": "calibrateImage:HSC"},
]


def _write_bundle(tmp_path, quanta, edges, manifest_overrides=None, counts=None):
    quanta_path = tmp_path / "quanta.jsonl"
    edges_path = tmp_path / "edges.jsonl"
    with open(quanta_path, "w") as f:
        for rec in quanta:
            f.write(json.dumps(rec) + "\n")
    with open(edges_path, "w") as f:
        for rec in edges:
            f.write(json.dumps(rec) + "\n")

    manifest = {
        "schema_version": "0.2",
        "provenance": VALID_PROVENANCE,
        "tasks": VALID_TASKS,
        "quanta_file": "quanta.jsonl",
        "edges_file": "edges.jsonl",
        "counts": counts or {"quanta": len(quanta), "edges": len(edges),
                              "dataset_types": 2, "tasks": 2},
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    manifest_path = tmp_path / "qgraph_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)
    return str(manifest_path)


def _quantum(qid, task="isr"):
    return {
        "schema_version": "0.2", "record_type": "quantum", "qid": qid, "task": task,
        "data_id": {"detector": 1, "exposure": 100 + qid, "instrument": "HSC"},
        "inputs": [{"dataset_type": "raw", "n": 1, "bytes_est": None}],
        "outputs": [{"dataset_type": "postISRCCD", "n": 1, "bytes_est": None}],
        "source_node_id": f"node-{qid}",
    }


def _edge(producer, consumer, dataset_type="postISRCCD"):
    return {"schema_version": "0.2", "record_type": "edge", "producer_qid": producer,
            "consumer_qid": consumer, "dataset_type": dataset_type}


def test_valid_bundle_passes(tmp_path):
    quanta = [_quantum(1), _quantum(2, task="calibrateImage")]
    edges = [_edge(1, 2)]
    manifest_path = _write_bundle(tmp_path, quanta, edges)
    assert validate_bundle.validate(manifest_path) == []


def test_missing_manifest_file(tmp_path):
    errors = validate_bundle.validate(str(tmp_path / "does_not_exist.json"))
    assert len(errors) == 1
    assert "does not exist" in errors[0]


def test_wrong_schema_version(tmp_path):
    manifest_path = _write_bundle(tmp_path, [_quantum(1)], [],
                                   manifest_overrides={"schema_version": "0.1"})
    errors = validate_bundle.validate(manifest_path)
    assert any("schema_version" in e for e in errors)


def test_missing_provenance_key(tmp_path):
    bad_provenance = dict(VALID_PROVENANCE)
    del bad_provenance["qgraph_uuid"]
    manifest_path = _write_bundle(tmp_path, [_quantum(1)], [],
                                   manifest_overrides={"provenance": bad_provenance})
    errors = validate_bundle.validate(manifest_path)
    assert any("qgraph_uuid" in e for e in errors)


def test_missing_pinned_revision(tmp_path):
    bad_provenance = json.loads(json.dumps(VALID_PROVENANCE))
    del bad_provenance["pinned"]["pipe_base"]
    manifest_path = _write_bundle(tmp_path, [_quantum(1)], [],
                                   manifest_overrides={"provenance": bad_provenance})
    errors = validate_bundle.validate(manifest_path)
    assert any("pipe_base" in e for e in errors)


def test_duplicate_qid_detected(tmp_path):
    quanta = [_quantum(1), _quantum(1)]
    manifest_path = _write_bundle(tmp_path, quanta, [])
    errors = validate_bundle.validate(manifest_path)
    assert any("duplicate qid" in e for e in errors)


def test_non_integer_qid_detected(tmp_path):
    quanta = [_quantum(1)]
    quanta[0]["qid"] = "1"
    manifest_path = _write_bundle(tmp_path, quanta, [])
    errors = validate_bundle.validate(manifest_path)
    assert any("not an int" in e for e in errors)


def test_dangling_edge_reference_detected(tmp_path):
    quanta = [_quantum(1)]
    edges = [_edge(1, 999)]
    manifest_path = _write_bundle(tmp_path, quanta, edges, counts={"quanta": 1, "edges": 1})
    errors = validate_bundle.validate(manifest_path)
    assert any("999" in e and "not present" in e for e in errors)


def test_self_edge_detected(tmp_path):
    quanta = [_quantum(1)]
    edges = [_edge(1, 1)]
    manifest_path = _write_bundle(tmp_path, quanta, edges, counts={"quanta": 1, "edges": 1})
    errors = validate_bundle.validate(manifest_path)
    assert any("self-edge" in e for e in errors)


def test_duplicate_logical_edge_detected(tmp_path):
    quanta = [_quantum(1), _quantum(2, task="calibrateImage")]
    edges = [_edge(1, 2), _edge(1, 2)]
    manifest_path = _write_bundle(tmp_path, quanta, edges, counts={"quanta": 2, "edges": 2})
    errors = validate_bundle.validate(manifest_path)
    assert any("duplicate logical edge" in e for e in errors)


def test_task_not_declared_in_manifest(tmp_path):
    quanta = [_quantum(1, task="notARealTask")]
    manifest_path = _write_bundle(tmp_path, quanta, [])
    errors = validate_bundle.validate(manifest_path)
    assert any("notARealTask" in e for e in errors)


def test_count_mismatch_detected(tmp_path):
    quanta = [_quantum(1)]
    manifest_path = _write_bundle(tmp_path, quanta, [], counts={"quanta": 5, "edges": 0,
                                                                  "dataset_types": 2, "tasks": 2})
    errors = validate_bundle.validate(manifest_path)
    assert any("counts.quanta" in e for e in errors)


def test_referenced_files_missing(tmp_path):
    manifest = {
        "schema_version": "0.2", "provenance": VALID_PROVENANCE, "tasks": VALID_TASKS,
        "quanta_file": "does_not_exist.jsonl", "edges_file": "edges.jsonl",
        "counts": {"quanta": 0, "edges": 0, "dataset_types": 0, "tasks": 0},
    }
    manifest_path = tmp_path / "qgraph_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f)
    errors = validate_bundle.validate(str(manifest_path))
    assert any("does not exist" in e for e in errors)


def test_cli_exit_codes(tmp_path):
    good_dir = tmp_path / "good"
    good_dir.mkdir()
    quanta = [_quantum(1), _quantum(2, task="calibrateImage")]
    good_manifest = _write_bundle(good_dir, quanta, [_edge(1, 2)])
    assert validate_bundle.main([good_manifest]) == 0

    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    bad_manifest = _write_bundle(bad_dir, [_quantum(1), _quantum(1)], [])
    assert validate_bundle.main([bad_manifest]) == 1
