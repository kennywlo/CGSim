# Rubin Campaign & QuantumGraph Schema for CGSim — v0.2

**Purpose.** A simulator-ingestible representation of Rubin DRP workload structure, extracted from authoritative sources: the `cm-service` v2 state machine (lsst-dm/cm-service@67bb63a), `ctrl_bps` semantics, RTN-101, RTN-001 §2.1.4, and the production PanDA/Rucio records in `rubinobs-opensearch` at USDF (reference dump: `opensearch_reference/`). Consumers: the CGSim Rubin plugin (Raees), the qgraph/log extraction pipelines at USDF (Kenny), and the AskPanDA training pipeline (§10).

**Design rules.**
1. Quanta are atomic. Clustering, grouping, and campaign structure are *overlays* in separate files, so any layer can be varied as a simulation policy knob without regenerating the layers below.
2. Workload representation (§1–7) and simulator output (§10) are separate schemas. The output side must round-trip into the OpenSearch PanDA job-record schema so simulated traces are drop-in training data for AskPanDA.

All files carry `"schema_version": "0.2"`. The canonical distribution format everywhere is `{"dist": "lognorm", "params": [...]}`.

## 1. The five-level hierarchy

From `cm-service` `LevelEnum` plus the quantum level beneath it:

| Level | Term | Meaning | Typical cardinality |
|---|---|---|---|
| 1 | `campaign` | Full processing campaign (DP2, DR1) | 1 |
| 2 | `step` | Part of a campaign finished before moving on | ~7–10 |
| 3 | `group` | Parallel subset of data within a step | 10s–100s per step |
| 4 | `job` | One BPS workflow = one submission = one QuantumGraph | 1 per group (plus rescues) |
| 5 | *(quantum)* | One task invocation on one data ID | ~10⁴ per job |

Below level 5, BPS **clustering** aggregates quanta into WMS (PanDA) jobs — an overlay (§5), since it lives in the submit YAML, not the qgraph. Jobs are not serialized in `campaign.json`: the primary job is implied 1:1 per group; a **rescue** is generated in-simulator as a subset qgraph over unexecuted quanta, linked via `rescue_of` (§4).

## 2. Campaign graph: `campaign.json` (levels 1–3)

cm-service represents a campaign as a validated directed graph START→END. Node kinds (`ManifestKind`): `start`, `end`, `step`, `group`, `collect_groups` (fan-in), `breakpoint` (explicit pause; descendant of RTN-001 "sequence points").

Steps spawn groups via splitters (`SplitterEnum`): `null` (step = one group, no other fields), `values` (enumerate `values[]`), `query` (butler dimension query; uses `dataset`, `min_groups`, `max_size`). Each resulting predicate becomes a group; each group builds one qgraph and one BPS submission. **This is the generative model for synthetic campaigns** — sample (instrument, N visits, N tracts), apply the drp_pipe step template and splitters, get a realistic campaign DAG with no production data.

```json
{
  "schema_version": "0.2",
  "campaign": {
    "name": "string",
    "provenance": {"lsst_distrib": "w_2026_XX", "drp_pipe_ref": "git-sha",
                   "pipeline_yaml": "path#subset", "source": "cm-service|synthetic|manual"},
    "nodes": [
      {"id": "uuid", "kind": "start|step|group|collect_groups|breakpoint|end", "name": "step1",
       "configuration": {
         "splitter": {"split_by": "null|values|query", "values": ["..."],
                      "dataset": "raw", "min_groups": 0, "max_size": 0},
         "predicate": "instrument='LSSTCam' AND visit IN (...)",
         "wms": "panda|htcondor|bash",
         "site": "usdf|in2p3|lanc|ral",
         "qgraph_ref": "uuid-or-path-or-null"}}
    ],
    "edges": [{"source": "uuid", "target": "uuid"}]
  }
}
```

Configuration by kind — `step`: `splitter` only; `group`: `predicate`, `wms`, `site`, `qgraph_ref`; others: none. `site` per group is the multi-site knob (RTN-101: qgraphs are generated at the facility that processes the data). `qgraph_ref` is the join key to §4.

## 3. Lifecycle states (all element levels)

One ordered vocabulary (`StatusEnum`) shared by campaign, step, group, job:

```
overdue(-6)  failed(-5)  rejected(-4)  blocked(-3)  paused(-2)  rescuable(-1)
waiting(0) → ready(1) → prepared(2) → running(3) → reviewable(4) → accepted(5) → rescued(6)
```

Terminal-success = `>= accepted` (includes `rescued`); bad = `<= rejected`. Campaign transitions: `paused ⇄ running`, `running → accepted` (guarded), `reject/force: * → rejected/accepted`; campaign status = worst-case of active nodes. CM polls the WMS per group/job and maps `WmsStates` → StatusEnum; `blocked` = held/unready in the WMS — queue starvation, driven by *requested* resources against queue caps (§5, §9).

The plugin emits per-element state-transition events with timestamps in exactly this vocabulary, so simulated traces join cleanly with cm-service activity logs and OpenSearch-derived production traces.

## 4. Quantum level: `qgraph_export.json`

One file per BPS submission (including rescues), produced by the exporter under the LSST stack.

```json
{
  "schema_version": "0.2",
  "provenance": {"lsst_distrib": "w_2026_XX", "qgraph_uuid": "uuid",
                 "campaign": "name", "group_id": "uuid-in-campaign.json",
                 "rescue_of": "qgraph_uuid-or-null",
                 "pipeline_yaml": "drp_pipe/.../DRP.yaml#step1",
                 "input_collections": ["..."], "output_run": "u/...", "instrument": "LSSTCam"},
  "tasks": [{"label": "isr", "class": "lsst.ip.isr.IsrTask",
             "dimensions": ["visit","detector"], "resource_key": "isr:LSSTCam"}],
  "quanta": [{"qid": 1, "task": "isr", "data_id": {"visit": 12345, "detector": 42, "band": "i"},
              "inputs":  [{"dataset_type": "raw", "n": 1, "bytes_est": null}],
              "outputs": [{"dataset_type": "postISRCCD", "n": 1, "bytes_est": null}]}],
  "edges": [{"producer_qid": 1, "consumer_qid": 7, "dataset_type": "postISRCCD"}]
}
```

- `qid`: plain int, unique per file. `resource_key` lives on tasks (rule: `{task_label}:{instrument}`) and indexes §6.
- `bytes_est` nullable; per-type size distributions (§6) are the fallback. Edges carry `dataset_type` to bind transfer sizes.
- **Edges are consumed by the plugin, not CGSim core** (verified against core source 2026-07-15): core `getWorkload()` runs once pre-simulation over a flat priority queue and `Job` has no dependency fields. The extension point exists: jobs left `"pending"` by `assignJob()` are re-polled after every execution completion, so the plugin can gate release on parent completion there. One-shot `getWorkload()` also means rescue jobs must be pre-materialized in the initial queue and gated, or core needs a job-injection extension (open question 1).

## 5. Clustering overlay: `clustering.json`

Mirrors the BPS submit-YAML clustering section; applied in-simulator so clustering policy is a knob. **Load-bearing for §10**: PanDA records exist at post-clustering granularity, and requested memory set here drives queue routing (§9).

```json
{
  "schema_version": "0.2",
  "method": "single_quantum|user_labeled|dimension",
  "clusters": [{"name": "isr_calibrate_visit", "task_labels": ["isr","characterizeImage","calibrate"],
                "dimensions": ["visit","detector"], "equal_dimensions": [], "max_quanta": null,
                "request_memory_mb": 4096, "request_cpus": 1}],
  "overhead": {"pipetask_init_s": null, "final_job_s": null, "per_quantum_startup_s": null},
  "wms_retry": {"max_retries": 3, "memory_multiplier": null}
}
```

`request_*` mirror BPS `requestMemory/requestCpus` — *requests*, distinct from fitted *usage* (§6). `overhead` covers the BPS-generated init/final jobs. `wms_retry` is the pilot/WMS retry loop — deliberately separate from cm-service recovery actions (§8); conflating them double-counts retries.

## 6. Resource models: `resources.json`

Fitted from parsed `payload.stdout` (per-quantum `timeMethod` wall/CPU/MaxRSS) and butler size dumps; validated against OpenSearch job records. Never hand-authored; `fit_inputs` must list what the fit was made against.

```json
{
  "schema_version": "0.2",
  "provenance": {"fit_source": "gcs-stdout-parse", "campaign": "...", "n_samples": 0,
                 "lsst_distrib_versions": ["w_2026_XX"], "fit_inputs": ["qgraph_uuid"]},
  "models": {"isr:LSSTCam": {
      "cpu_s": {"dist": "lognorm", "params": [0,0,0]},
      "wall_s": {"dist": "lognorm", "params": [0,0,0]},
      "max_rss_mb": {"dist": "lognorm", "params": [0,0,0]},
      "covariates": {"n_inputs": "linear-scale-on-cpu_s"}}},
  "dataset_types": {"postISRCCD": {"bytes": {"dist": "lognorm", "params": [0,0,0]}}}
}
```

`dataset_types` feeds data-movement simulation (transfer time = size × link bandwidth, §9); fit from butler dumps and/or Rucio `transfer-done` payloads, which carry exact bytes.

## 7. Historical workload traces: `workload_trace.json`

One record per production WMS job from `panda_prod_test-YYYY-MM` (monthly, 2025-02→present, ~1–8M Rubin jobs/month). The raw layer §6 is fitted from and §10 is validated against — replay and generative sampling are one pipeline at two stages.

```json
{
  "schema_version": "0.2",
  "provenance": {"index": "panda_prod_test-2026-06", "extracted": "date", "query": "..."},
  "jobs": [{"pandaid": 0, "taskid": 0, "resource_key": "gbdesHealpix3AstrometricFit:LSSTCam",
            "queue": "CC-IN2P3_Rubin_8G", "site": "in2p3",
            "creationtime": "ts", "starttime": "ts", "endtime": "ts",
            "jobstatus": "finished|failed|closed|cancelled",
            "corecount": 0, "maxrss_kb": 0, "cpuconsumptiontime_s": 0,
            "piloterrorcode": 0, "transexitcode": "0", "attemptnr": 0}]
}
```

`resource_key` is recovered from the PanDA `jobname`, which embeds the BPS task/cluster label (`u_lsstgrid_{...}_{taskLabel}_{...}Z_{NN}_{clusterLabel}`). PanDA `jobstatus` stays verbatim; the §3↔WMS mapping already exists in cm-service.

## 8. Failure model: `failures.json`

Vocabulary lifted from cm-service enums so injected failures round-trip into the taxonomy operators and AskPanDA use — **Source**: `cmservice | local_script | htc_workflow | manifest` (+ `panda_pilot`); **Flavor**: `infrastructure | configuration | pipelines`; **Action**: `fail | requeue_and_pause | rescue | auto_retry | review | accept`.

Quantum outcomes: `processing | done | failed | failed_upstream | missing` plus `no_work_found` (a *successful* empty result). Only `p_fail` and `p_no_work_found` are parameterized — `failed_upstream` and `missing` are emergent from DAG propagation and must not be injected directly. Conflating any of these corrupts training labels.

```json
{
  "schema_version": "0.2",
  "provenance": {"rate_source": "opensearch-error-taxonomy", "window": "2026-01..2026-06"},
  "site_events": [{"site": "in2p3", "type": "outage|degraded|queue_block", "rate_per_day": 0.0,
                   "duration_dist": {"dist": "lognorm", "params": [0,0,0]}}],
  "quantum_failures": [{"resource_key": "assembleCoadd:LSSTCam", "flavor": "pipelines",
                        "p_fail": 0.0, "p_no_work_found": 0.0,
                        "action_policy": "auto_retry", "max_retries": 3}],
  "transfer_failures": [{"link": "SLAC_BUTLER_DISK->IN2P3_RAW_DISK", "p_fail": 0.0, "retry_backoff_s": 0}]
}
```

**Production grounding (2026-06, `opensearch_reference/README.md`):** ~12.7% of Rubin WMS jobs failed. `exeerrorcode` was 0 on every failure — the discriminators are `piloterrorcode` (1305 dominates), `transexitcode`, and free-text `piloterrordiag`; quantum-level failure detail exists only in payload stdout, so the §6 stdout-parsing path is unavoidable. Failures were ~97% concentrated at CC-IN2P3 that month — empirical support for `site_events` over uniform rates. Rucio failed-vs-done event counts give per-link `p_fail` (~10% aggregate).

## 9. Sites, queues & data movement

- Compute sites `usdf | lanc | ral | in2p3`; per-queue caps from CRIC (same ingestion path as CGSim's ATLAS calibration).
- **Queues are memory-tiered** (production: `{SLAC,LANCS,RAL,CC-IN2P3}_Rubin_{4G..32G,Extra_Himem}`); a job routes to the tier matching its `request_memory_mb` (§5). The site model is `(site, queue)` with per-queue caps — starvation/`blocked` dynamics follow from requests, not usage.
- Storage per RTN-101, confirmed against live Rucio events: `{SITE}_RAW_DISK` (immutable inputs), `{SITE}_BUTLER_DISK` (products), identity LFN→PFN. Rucio rules drive replication; FTS moves data; products consolidate to USDF. (`DESC_*`/`IDAC_*` distribution egress out of scope.)
- Network topology, fitted from Rucio `transfer-done` throughput:

```json
{"schema_version": "0.2",
 "links": [{"src": "SLAC_BUTLER_DISK", "dst": "IN2P3_RAW_DISK",
            "bandwidth_MBps": 0, "latency_s": 0, "max_concurrent_transfers": 0}]}
```

- Minimal model: input staging as a precondition on group start at a site; product consolidation as post-job USDF-bound transfers, rate-limited per link.

## 10. Output records (simulator → AskPanDA)

The output plugin emits one document per simulated WMS job conforming to the production mapping (`opensearch_reference/panda_prod_test_mapping.json`, 99 fields), so simulated and production records are interchangeable for training. Field classes:

| Class | Meaning | Examples |
|---|---|---|
| **simulated** | Produced by the simulation | `jobstatus`, `computingsite`, timestamps, `corecount`, `maxrss`, `cpuconsumptiontime`, `piloterrorcode/diag`, `transexitcode`, `attemptnr` |
| **synthesized** | Generated ids with production-faithful format | `pandaid`, `taskid`, `jeditaskid`, `jobname` (**must follow the `u_lsstgrid_..._{taskLabel}_..._{clusterLabel}` pattern** — it is the join key to §5) |
| **null** | Honestly absent | ATLAS-isms, unfilled fields |

**How AskPanDA consumes this** (verified 2026-07-15 against `flow-maestro/sft` + `panda_opensearch_MCP`): training is tool-use trajectory SFT/DPO. `metadata_search` returns full `_source` — whole records land in model context, so every non-null field must be plausible. Trajectories reason over a narrow set (ids, status, site, error code/diag, timestamps, cpu/memory, log URL), and **~half chain into `log_query` over pilot-log content**, including deliberate metadata-vs-log conflicts. Error injection must therefore emit a consistent triple per failure: (`piloterrorcode`, `piloterrordiag`, pilot-log tail). The trajectory generator inlines log content at training time (no storage backend needed); production `log_query` dereferences any URL/local path, so a served log store is only required if the live assistant should query simulated jobs.

Output streams: **(1)** PanDA job records — grounds `metadata_search`; **(2)** pilot-log text per failed (and sampled successful) job — grounds `log_query`; **(3)** §3 state-transition events — for campaign-level studies. Rucio-style transfer events are deferred: no DDM tool exists in the AskPanDA toolset.

## 11. Out of scope (v0.2)

Prompt processing / alert production; butler registry contention; human review latency at `breakpoint`/`reviewable` (exogenous parameter); distribution egress to `DESC_*`/`IDAC_*` RSEs.

## 12. Open questions

1. **(Paul/Raees)** CGSim core has no DAG support (verified). Decide: implement dependency-triggered release plugin-side via the pending-job mechanism, or extend core? Same decision covers rescue-job injection, since `getWorkload()` is one-shot.
2. **(Zhaoyu)** cm-service activity logs are not in `rubinobs-opensearch` (full inventory checked). Exported to any other store, or site-resident only?
3. **(Kenny)** Pin the rc2_subset/tutorial stack version for exporter development; confirm data-rights posture on sharing data IDs in DAG exports pre-DR.
4. **(Raees)** Serialization at scale: JSON-lines per quantum vs. single JSON, before the 10⁶-quantum stress test.
5. `breakpoint` nodes: zero-latency pass-through (default) or parameterized delay?
6. Pilot-log synthesis: who owns the per-error-code template library mapping injected failures to (`piloterrordiag`, log-tail) pairs? Source material = real diag strings in `panda_prod_test`; templates must stay consistent with §8's taxonomy.

**Resolved along the way** (details in `opensearch_reference/`): AskPanDA consumption model (tool trajectories; full `_source`; pilot logs required) · transfer events deferred (no DDM tool) · log storage (inlined at training time) · `qid` pinned int · campaign↔qgraph join keys · requests-vs-usage split · cm-service logs absent from `rubinobs-opensearch`.

---
*Sources: cm-service@67bb63a (`enums.py`, `machines/campaign.py`, `machines/nodes/*`, `models/lib/graph.py`); RTN-101 (2025-07-03); RTN-001 (rev 2024-02-07); RTN-043 is a stub — the code is the design document. Production grounding extracted 2026-07-15 from `rubinobs-opensearch` (see `opensearch_reference/`); CGSim core behavior verified against `include/job.h`, `include/DispatcherPlugin.h`, `util/job_executor.cpp`; AskPanDA consumption verified against `flow-maestro/sft` datasets and `panda_opensearch_MCP/mcp_server.py`.*
