# AskPanDA SFT Dataset v4 — Datagen Run Summary

**Date:** June 3, 2026  
**Output:** `askpanda_sft_cgsim_v4_20260603.jsonl` — **1,154 examples**

---

## Research context

This dataset is part of the **AskPanDA Next-Phase Research** program
(*Simulation-Grounded Training for Scientific Workflow Failure Diagnosis*, SLAC/REDWOOD,
DOE ASCR), targeting SC27/PMBS as the follow-on to the SC26 paper (pap440).

**SC26 baseline (pap440):** A GPT-OSS-20B model fine-tuned on ~500 manually curated SFT
samples achieves 85% diagnostic accuracy on a 48-scenario benchmark, outperforming Claude
Sonnet 4 (71%) and the untuned base model (25%). That result demonstrates passive distillation
of operational reasoning is feasible — but it is limited by manual curation cost, a fixed
training distribution, and purely correlational (non-causal) reasoning.

**Next-phase architecture** addresses these limits in three stages:

| Stage | CGSim role | LLM activity |
|---|---|---|
| 1 — Schema audit | Output audited against OpenSearch PanDA schema; translation layer or fork built | — |
| 2 — FastMCP wrapping | Exposed as MCP server (`run_simulation`, `verify_diagnosis`, `generate_counterfactual`) | Interactive tool calls during training |
| 3 — SFT at scale *(this dataset)* | Generates synthetic job records across diverse failure scenarios | Learns failure pattern recognition at scale |
| 4 — GRPO training | Acts as ground-truth verifier for candidate diagnoses | Learns causal reasoning; rewarded for simulator-validated diagnoses |
| 5 — Benchmark expansion | Generates novel OOD scenarios, cascade failures, multi-hop causal chains | Evaluated on expanded benchmark |

**v4 is Stage 3 — a validation-scale run** (1,154 examples; target for full SFT is 5K–25K).
It establishes the datagen pipeline, confirms simulation fidelity for Rubin Operations, and
surfaces the schema and tooling gaps (see Future Directions) that Stage 1 must close before
scaling.

**Deployment-time independence:** CGSim is a *training-time dependency only*. The GRPO phase
(Stage 4) crystallizes simulator-derived causal reasoning into model weights. In production,
AskPanDA operates autonomously against real operational data (OpenSearch PanDA index) with no
CGSim dependency — the query tool at inference is the live operational DB, not the simulator.

---

## What it is

Supervised fine-tuning data for teaching a model to answer Rubin Operations operational
questions by querying a simulation database. Each example is a `(question, SQL, result, answer)`
tuple grounded in simulation EVENTS data produced by CGSim (a SimGrid-based Rubin Observatory
grid simulator).

**Why simulation instead of real PanDA data?** Real operational data from PanDA/Rucio is
difficult to use for SFT at scale: it requires access to live infrastructure, ground-truth
labels are expensive to produce, and rare failure modes are underrepresented in normal telemetry.
CGSim provides full control over scenario conditions (degraded sites, saturated links, burst
workloads), produces labeled EVENTS data deterministically, and can generate arbitrarily large
datasets without operational risk. The training bet is that reasoning patterns learned on
simulated grid behavior transfer to real operational queries when the tool backend is swapped.

**SimGrid** is an open-source discrete-event simulation framework for distributed systems.
CGSim uses it to model the Rubin Observatory grid topology (568 nodes across USDF, Base,
FrDF, UKDF, and Summit sites), emulating job scheduling, file transfers, and storage I/O as
discrete events. Each simulated event is written as a row in an append-only SQLite `EVENTS`
table — the substrate the datagen pipeline queries.

```
┌─────────────────────────────────────────────────────────────┐
│                        CGSim (SimGrid)                      │
│   9 scenarios × Rubin Observatory topology (568 nodes)      │
└──────────────────────┬──────────────────────────────────────┘
                       │ SQLite EVENTS DB (28–53K rows/scenario)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    CGSimDataGenerator                        │
│                                                             │
│  ┌─────────────┐    ┌──────────┐    ┌──────────┐           │
│  │  Proposer   │───▶│ Executor │───▶│ Explainer│           │
│  │ Sonnet 4.6  │    │   SQL    │    │Sonnet 4.6│           │
│  │ (question,  │    │ (runs on │    │(grounds  │           │
│  │    SQL)     │    │   DB)    │    │ answer)  │           │
│  └─────────────┘    └──────────┘    └────┬─────┘           │
│                                          │                  │
│                                     ┌────▼─────┐           │
│                                     │  Judge   │           │
│                                     │Sonnet 4.6│           │
│                                     │6 criteria│           │
│                                     └────┬─────┘           │
└──────────────────────────────────────────┼─────────────────┘
                                           │ keep / reject
                                           ▼
                              ┌────────────────────────┐
                              │   SFT Example JSONL    │
                              │  (question, SQL,       │
                              │   result, answer)      │
                              └────────────────────────┘
```

---

## Pipeline: proposer → executor → judge

All LLM calls (Proposer, Explainer, Judge) are made to **Claude Sonnet 4.6 via the SLAC AI
gateway**. Each scenario runs as an independent process with its own CGSim instance and
establishes its own connection to the SLAC AI API — the 9 jobs run fully in parallel with no
shared state between them.

**Proposer** — Claude Sonnet 4.6 via SLAC AI  
Generates diverse `(question, SQL)` pairs against the EVENTS schema. Given the schema and a list
of already-seen questions to avoid, it proposes batches covering per-site performance, file
transfer bottlenecks, disk I/O, job duration/retries, CPU/storage utilization, and cross-site
comparisons.

**Scenarios vs. question categories — these are orthogonal.** The 9 scenarios define the
*simulated world state* (which site is degraded, which link is congested, etc.) and each
produces its own SQLite DB. The 6 question categories define the *type of question* the Proposer
is asked to generate. The pipeline runs independently per scenario: for each of the 9 scenarios,
the Proposer generates questions spanning all 6 categories against that scenario's DB. The same
category (e.g. "file transfer bottlenecks") will yield structurally similar questions but
numerically different answers across scenarios, because the underlying simulation data differs.
Together they form a **9 × 6 matrix of 54 distinct analytical perspectives**, each contributing
~20–25 examples to reach the 150-per-scenario target.

The seen-questions list is built up incrementally at runtime — it starts empty on a fresh run
(non-empty only when resuming from a checkpoint). When empty, no exclusion block is added and
the Proposer relies entirely on the base prompt and the EVENTS schema to generate the first
batch. The schema context — injected via a system prompt (`DOMAIN_PRIMER`) — provides the full
table definition, authoritative `json_extract` key list per event type, and analysis rules (e.g.
use `STATE='Finished'` for performance metrics, never invent columns). This gives the model
enough structure to produce valid, diverse questions without any seed examples.

To keep prompt size bounded, only the **last 30** seen questions are included in the exclusion
block on subsequent batches.

**`EVENT_SCHEMA` — the authoritative key list** injected into `DOMAIN_PRIMER`:

| Event | State | Metadata keys |
|---|---|---|
| JobAllocation | Started | status, site, host |
| JobAllocation | Finished | status, site, host, site_storage_util, grid_storage_util, site_cpu_util, grid_cpu_util |
| JobExecution | Started | flops, cores, speed, site, host, start_time, site_cpu_util, grid_cpu_util |
| JobExecution | Finished | flops, cores, speed, cost, site, host, duration, retries, total_io_read_time, file_transfer_queue_time, resource_waiting_queue_time, total_queue_time, site_cpu_util, grid_cpu_util |
| FileTransfer | Started/Finished | file, size, source_site, destination_site, bandwidth, latency, link_load, site_storage_util, grid_storage_util (+ duration on Finished) |
| FileRead | Started/Finished | file, size, site, host, disk, disk_read_bw (+ duration on Finished) |
| FileWrite | Started/Finished | file, size, site, host, disk, disk_write_bw, site_storage_util, grid_storage_util (+ duration on Finished) |

The Judge validates that every `json_extract` key in proposed SQL appears in this schema — any
hallucinated key is an automatic reject.

**Batch size and retry behavior** — the Proposer requests pairs in batches of 5 by default.
On a token-limit error the batch size is halved (down to a minimum of 1) and retried; after 5
consecutive failures at batch size 1 the proposer stops early. On a gateway null response
(transient API outage) it waits 15 seconds and retries. If 3 consecutive batches produce no
novel questions the proposer concludes the schema diversity is exhausted and stops.

**Executor** — deterministic  
Runs each proposed SQL against the actual simulated SQLite DB. Filters empty results and
non-SELECT queries before proceeding.

**Explainer** — Claude Sonnet 4.6 via SLAC AI  
Given the question, SQL, and real query results, writes a concise operational answer grounded
strictly in the returned data. Instructed not to recompute aggregates or hallucinate numbers.

**Judge** — Claude Sonnet 4.6 via SLAC AI  
Filters each `(question, SQL, result, answer)` tuple on 6 criteria before it enters the dataset.
Scoring is **all-or-nothing**: `keep=true` only if every criterion passes; a single failure
rejects the example. The Judge returns a structured verdict with a ≤40-word reason when
rejecting, identifying which criterion failed.

1. **Question quality** — non-trivial operational question, not a bare row count
2. **SQL correctness** — uses only documented schema columns and `json_extract` keys
3. **Grounding** — every number in the answer derivable from query results (≤5% tolerance)
4. **Answer quality** — clear, concise, operationally useful; no SQL jargon
5. **Self-consistency** — answer doesn't contradict or invalidate its own results
6. **Informative result** *(new in v4)* — rejects examples where every metric value is identical
   or zero across all rows (flat/boring simulation artifacts)

---

## v4 vs v3

| | v3 | v4 |
|---|---|---|
| Examples | 831 | **1,154** (+39%) |
| Target per scenario | 100 | 150 |
| Judge criteria | 5 | **6** |
| Boring examples filtered | ~19% passed through | **Blocked at judge** |
| Gateway crash resilience | None | Auto-retry on malformed response |

---

## Dataset composition

### Scenarios (9)

Each scenario is an independent CGSim instance producing its own SQLite EVENTS DB and
connecting to the SLAC AI gateway separately. The 9 jobs run in parallel on Perlmutter with
no shared state. Together they cover the four failure-mode classes: normal operations,
single-site failures, network bottlenecks, and burst workloads. The simulation DBs collectively
contain **~277K raw events** (53K for `high_coadd_burst` + ~28K each for the remaining 8
scenarios), from which 1,154 training examples were distilled — roughly **1 example per 240
simulation events**.

| Scenario | Description | Examples |
|---|---|---|
| usdf_degraded | USDF disk I/O degraded — write bandwidth reduced, causing longer FileWrite durations and elevated storage queue times at the US facility. | 132 |
| base_degraded | Base facility (Chilean summit storage) experiencing storage degradation, reducing local read/write throughput and increasing I/O latency. | 131 |
| frdf_offline | French Data Facility taken offline, forcing all jobs and transfers that would have routed through FrDF to fall back to remaining sites. | 131 |
| high_coadd_burst | Sudden burst of coadd (image co-addition) processing jobs flooding grid compute resources, producing the largest EVENTS DB (53K rows) and the heaviest CPU contention. | 130 |
| usdf_storage_throttled | USDF storage bandwidth artificially throttled below normal capacity, degrading both read and write throughput without taking the site fully offline. | 129 |
| summit_link_bottleneck | The Summit-to-USDF uplink saturated, creating a transfer queue backlog for data leaving the Chilean summit site and inflating file_transfer_queue_time. | 128 |
| transatlantic_congested | Transatlantic network links congested, collapsing achieved throughput to a fraction of declared bandwidth for all US↔Europe transfers (see A.2). | 127 |
| baseline | Normal Rubin Observatory grid operations with no injected faults — the reference scenario against which degraded cases are compared. | 124 |
| high_load | Grid-wide high CPU and storage utilization with no single point of failure — a capacity stress test where every site is under pressure simultaneously. | 122 |

### Question categories (6)

The Proposer is instructed to distribute questions across six analytical categories. There are
no per-category quotas; the model decides the distribution within each batch. Across the full
dataset the 9 scenarios × 6 categories form a **54-cell matrix**, each cell contributing
~20–25 examples toward the 150-per-scenario target.

Per-cell counts are not labeled in the output (the Proposer distributes freely without tagging
categories). The matrix below shows approximate per-cell counts derived as scenario total ÷ 6.

```
                        │ Per-site │ File     │ Disk  │ Job dur/ │ CPU/stor │ Cross-  │ Total
  Scenario               │ perf     │ transfer │ I/O   │ retries  │ util     │ site    │
 ──────────────────────────────────────────────────────────────────────────────────────────────
  usdf_degraded          │  ~22     │  ~22     │  ~22  │   ~22    │  ~22     │  ~22    │  132
  base_degraded          │  ~22     │  ~22     │  ~22  │   ~22    │  ~22     │  ~21    │  131
  frdf_offline           │  ~22     │  ~22     │  ~22  │   ~22    │  ~22     │  ~21    │  131
  high_coadd_burst       │  ~22     │  ~22     │  ~22  │   ~21    │  ~22     │  ~21    │  130
  usdf_storage_throttled │  ~22     │  ~21     │  ~22  │   ~21    │  ~22     │  ~21    │  129
  summit_link_bottleneck │  ~21     │  ~21     │  ~21  │   ~21    │  ~22     │  ~22    │  128
  transatlantic_congested│  ~21     │  ~21     │  ~21  │   ~21    │  ~22     │  ~21    │  127
  baseline               │  ~21     │  ~21     │  ~21  │   ~21    │  ~20     │  ~20    │  124
  high_load              │  ~20     │  ~20     │  ~20  │   ~21    │  ~21     │  ~20    │  122
 ──────────────────────────────────────────────────────────────────────────────────────────────
  Category total         │ ~193     │ ~192     │ ~193  │  ~192    │ ~193     │ ~191    │ 1,154
```

| Category | What it covers |
|---|---|
| Per-site performance | Aggregate job and I/O metrics scoped to a single facility — throughput, queue times, CPU/storage utilization — useful for identifying which site is under stress. |
| File transfer bottlenecks | Network transfer performance between sites: achieved throughput vs. declared bandwidth, link load tiers, transfer durations. Targets congestion and saturation conditions. |
| Disk I/O | Local read/write operations at a site: disk bandwidth, file size distributions, duration breakdowns. Relevant for diagnosing storage hardware or configuration issues. |
| Job duration/retries | How long jobs take to execute and how often they fail and are retried, surfacing scheduler inefficiencies, resource contention, or site instability. |
| CPU/storage utilization | Site-wide and grid-wide resource utilization captured at job and file events, showing how loaded the grid is during key operations. |
| Cross-site comparisons | Metrics compared across two or more facilities simultaneously, enabling relative performance analysis and identification of outlier sites. |

---

## Future directions

### Critical gaps: simulation vs. Rubin production

**1. Query interface (blocking)**
The model is trained on SQLite SQL with `json_extract`. Production Rubin Operations uses
OpenSearch, which has a different query language and field access model. The learned SQL patterns
will not transfer without either a translation layer at inference time or a retraining run
against OpenSearch-native queries. This is the most blocking gap before production deployment.

**2. Schema and field names (blocking)**
The CGSim EVENTS schema is a simulation abstraction. Real Rubin/PanDA operational data in
OpenSearch will have different index structures, field names, and event taxonomy. A model trained
on CGSim field names (e.g. `json_extract(METADATA, '$.site')`) will confidently generate queries
using wrong field names against a real index. Closing this gap requires either schema remapping
in the system prompt or a new datagen run against an OpenSearch-compatible schema.

**3. DAG-aware workflow modeling (high priority)**
CGSim currently models jobs as independent units. Real Rubin workflows are DAGs: ISR →
characterizeImage → calibrate → makeWarp → assembleCoadd → detectMeasure, with each step
dependent on the completion of upstream tasks. This gap means the current dataset cannot train
the model to answer workflow-level operational questions such as:
- "Which pipeline step is the bottleneck in tonight's DRP run?"
- "How many workflows are blocked waiting on step X?"
- "How far did this workflow progress before failing?"

Closing this gap requires DAG-level events and metadata in the EVENTS schema (see Rubin plugin
section below — addressed by Raees's workload scheduling plugin, step 3).

**4. Workload realism (medium priority)**
CGSim uses synthetic job distributions. Real Rubin operations run structured workload cadences —
nightly prompt processing, Data Release Processing (DRP), and forced photometry — each with
distinct job profiles, I/O footprints, and scheduling patterns. Scenarios calibrated to these
cadences would produce more operationally representative training examples.

**5. Site topology calibration (medium priority)**
Simulated site parameters (bandwidth, CPU capacity, storage) use approximate values. Calibrating
these to real USDF, Base, FrDF, UKDF, and Summit specifications would ensure the model learns
metric ranges that match real operational observations.

**6. Scenario coverage (ongoing)**
The 9 current scenarios cover archetypal failure modes but were not derived from real Rubin
operational incidents. Future scenario sets should be informed by actual event history and
on-call runbooks to ensure the training distribution covers the failure modes operators
actually encounter.

---

### Rubin plugin for CGSim (collaboration with Raees)

A Rubin-specific CGSim plugin is under development by Raees to address gaps 3–5 above. The
plugin will extend CGSim with Rubin pipeline semantics and emit output conforming to the
OpenSearch PanDA schema, making the simulation directly compatible with both the AskPanDA
production inference stack and the datagen pipeline.

**Raees's development plan:**

1. **Form the site topology** — model the actual USDF, Base, FrDF, UKDF, and Summit site
   specifications (bandwidth, CPU, storage) in CGSim to replace the current approximate values.

2. **Get historical workload information** — source real Rubin job history to derive per-task
   profiles (flops, I/O footprint, duration distributions) and submission cadences for prompt,
   DRP, and forced photometry pipelines.

3. **Construct the workload scheduling plugin** — implement DAG-aware job scheduling in CGSim
   reflecting the Rubin pipeline task dependency graph (Butler pipeline connections), so
   downstream tasks wait on upstream completions and failures propagate correctly.

4. **Define data movement policies** — specify how and when files move between sites based on
   Rubin's actual data flow (summit → USDF ingestion, cross-site replication to FrDF/UKDF, etc.).

5. **Construct the output plugin** — emit simulation events in the same schema as the
   OpenSearch PanDA operational index, replacing the current SQLite EVENTS table with an
   output format compatible with both production inference and the datagen pipeline.

6. **Integrate into the AskPanDA training pipeline** — wire the plugin output into
   `CGSimDataGenerator` so the Proposer, Explainer, and Judge operate against
   OpenSearch-schema-compatible data, closing the query interface and schema gaps.

7. **Start scenario studies with error injections** — design and run a new set of scenarios
   informed by real Rubin operational incidents, with fault injection targeting DAG-level
   failures (mid-pipeline stalls, upstream task failures, site-level degradation during
   active workflows).

**What this doc provides as a plugin spec:**
The current EVENTS schema (see `EVENT_SCHEMA` table in the Pipeline section) defines the
existing contract the datagen pipeline consumes. The output plugin (step 5) must produce
events that satisfy this contract — or the datagen pipeline is updated in lockstep to consume
the new OpenSearch schema directly.

---

## Compute resources (Perlmutter, NERSC)

| | |
|---|---|
| System | Perlmutter CPU partition (`shared` QOS) |
| Allocation | m2616 |
| Per job | 4 CPUs, 7.4 GB RAM, 2h wall time |
| Parallelism | 9 jobs simultaneously (one per scenario) |
| Wall-clock span | ~12.5 hours (09:00 – 21:30 PDT) |
| Total CPU-hours | ~957 (across all waves including retries) |

The high CPU-hour count relative to wall-clock time reflects the checkpoint/resume strategy:
scenarios that hit the 2h wall time were resubmitted and continued from saved state across
multiple job waves. The `high_coadd_burst` scenario was the most expensive, requiring 3 job waves
due to an 87% larger event database (53K vs 28K rows) that extends both simulation runtime
(~40 min vs ~5 min) and LLM context pressure during generation.

**Root causes of the 12.5-hour wall-clock span:**

1. **`high_coadd_burst` DB size** — at 53K rows (87% larger than the ~28K-row average), this
   scenario's CGSim simulation alone takes ~40 min vs. ~5 min for others. The larger DB also
   increases Executor query time and LLM context pressure per Proposer batch. It required 3
   job waves to complete, each restarting CGSim from scratch before the checkpoint could resume
   generation.

2. **Perlmutter 2h wall limit forcing multi-wave reruns** — each resubmitted wave pays the
   full job startup and CGSim initialization overhead again. The checkpoint ensures no work is
   lost, but does not reduce total compute — it only spreads it across waves. Any scenario
   requiring more than ~90 min of generation time spills into a second wave.

3. **Serial LLM calls per example** — the Proposer, Explainer, and Judge are invoked
   sequentially for each example with no batching at the explain/judge stage. Each of the
   1,154 examples makes at least 3 serial SLAC AI API calls, and gateway null responses
   (transient outages) add 15-second retry sleeps that compound across the run.

**Checkpoint/resume mechanics** — the pipeline maintains two save points per scenario:

1. **Proposal checkpoint** (`.ckpt.jsonl` alongside the DB) — each accepted `(question, SQL)`
   pair is appended immediately after the Proposer returns it. On resume, these pairs are loaded
   and counted toward the target so the Proposer only generates the remaining delta.
2. **Output checkpoint** (the output `.jsonl` itself) — if the job is interrupted mid-explain/judge
   loop, already-written examples are detected by scanning completed user-turn questions on restart.
   Only pending pairs are re-processed; no example is generated twice.

The proposal checkpoint is deleted on successful completion of a full run.

---

## Appendix: Example records

Each record is a single-line JSON object with two fields:

- **`messages`** — the structured conversation as a list of role/content objects, suitable for
  chat-format training or inspection.
- **`text`** — a pre-rendered string for training frameworks that consume a flat token sequence.
  It uses the following role tokens:

  ```
  <|start|>{role}<|message|>{content}<|end|>
  ```

  Assistant turns that invoke a tool are tagged `<|channel|>final` before `<|message|>` to
  signal to the inference stack that this is a tool-dispatch turn, not a free-form response.
  This distinction matters at inference time: the model must learn to route through the tool
  before producing a final answer rather than answering directly from weights.

### A.1 — FileWrite distribution across sites (`base_degraded` scenario)

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are AskPanDA, an expert assistant for ATLAS Grid computing and PanDA workload management. For questions about simulated grid behavior, you query the CGSim simulation database (an append-only EVENTS table) using the query_simulation_db tool, then explain the results in clear operational terms."
    },
    {
      "role": "user",
      "content": "For completed FileWrite operations per site, how are written file sizes distributed across small (<1 MB), medium (1 MB–1 GB), and large (>1 GB) buckets, and what are the write count, average duration, and average disk write bandwidth per bucket per site?"
    },
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "type": "function",
        "function": {
          "name": "query_simulation_db",
          "arguments": {
            "sql": "SELECT json_extract(METADATA, '$.site') AS site, CASE WHEN CAST(json_extract(METADATA, '$.size') AS FLOAT) < 1000000 THEN 'small_lt_1MB' WHEN CAST(json_extract(METADATA, '$.size') AS FLOAT) < 1000000000 THEN 'medium_1MB_1GB' ELSE 'large_gt_1GB' END AS size_bucket, COUNT(*) AS write_count, AVG(CAST(json_extract(METADATA, '$.duration') AS FLOAT)) AS avg_duration, AVG(CAST(json_extract(METADATA, '$.disk_write_bw') AS FLOAT)) AS avg_disk_write_bw, SUM(CAST(json_extract(METADATA, '$.size') AS FLOAT)) AS total_bytes FROM EVENTS WHERE EVENT = 'FileWrite' AND STATE = 'Finished' GROUP BY site, size_bucket ORDER BY site, size_bucket LIMIT 200"
          }
        }
      }]
    },
    {
      "role": "tool",
      "content": "{\"columns\": [\"site\", \"size_bucket\", \"write_count\", \"avg_duration\", \"avg_disk_write_bw\", \"total_bytes\"], \"rows\": [[\"Base\", \"large_gt_1GB\", 3, 0.364, 5000000000.0, 3130836233.0], [\"Base\", \"medium_1MB_1GB\", 536, 0.114, 5000000000.0, 30587406578.0], [\"FrDF\", \"large_gt_1GB\", 14, 0.239, 10000000000.0, 20342645574.0], [\"FrDF\", \"medium_1MB_1GB\", 265, 0.072, 10000000000.0, 63143993362.0], [\"UKDF\", \"large_gt_1GB\", 6, 0.197, 10000000000.0, 9439083532.0], [\"UKDF\", \"medium_1MB_1GB\", 154, 0.044, 10000000000.0, 25547679271.0], [\"USDF\", \"large_gt_1GB\", 24, 0.311, 10000000000.0, 36961763789.0], [\"USDF\", \"medium_1MB_1GB\", 814, 0.073, 10000000000.0, 141089412513.0]], \"row_count\": 8}"
    },
    {
      "role": "assistant",
      "content": "## FileWrite Distribution by Site and Size Bucket\n\n**Key finding: No small (<1 MB) files were written at any site.** All activity falls into the medium (1 MB–1 GB) and large (>1 GB) buckets only.\n\n| Site | Bucket | Write Count | Avg Duration (s) | Avg Disk Write BW | Total Bytes Written |\n|------|--------|-------------|------------------|-------------------|---------------------|\n| Base | medium | 536 | 0.114 | 5 GB/s | 30.59 GB |\n| Base | large | 3 | 0.364 | 5 GB/s | 3.13 GB |\n| FrDF | medium | 265 | 0.072 | 10 GB/s | 63.14 GB |\n| FrDF | large | 14 | 0.239 | 10 GB/s | 20.34 GB |\n| UKDF | medium | 154 | 0.044 | 10 GB/s | 25.55 GB |\n| UKDF | large | 6 | 0.197 | 10 GB/s | 9.44 GB |\n| USDF | medium | 814 | 0.073 | 10 GB/s | 141.09 GB |\n| USDF | large | 24 | 0.311 | 10 GB/s | 36.96 GB |\n\n1. **USDF dominates write volume** — 814 medium and 24 large writes, 141.09 GB in the medium bucket alone.\n2. **Large files take 2–4× longer** than medium at every site, consistent with larger payloads at the same bandwidth.\n3. **Base has half the disk write bandwidth** (5 GB/s vs 10 GB/s at others), resulting in the longest average durations.\n4. **Large writes are rare** — fewer than 5% of operations at all sites."
    }
  ],
  "text": "<|start|>system<|message|>...<|end|>\n<|start|>user<|message|>...<|end|>\n<|start|>assistant<|channel|>final<|message|>{\"name\": \"query_simulation_db\", \"arguments\": {\"sql\": \"...\"}}<|end|>\n<|start|>tool<|message|>...<|end|>\n<|start|>assistant<|channel|>final<|message|>...<|end|>"
}
```

### A.2 — Link congestion throughput analysis (`transatlantic_congested` scenario)


```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are AskPanDA, an expert assistant for ATLAS Grid computing and PanDA workload management. For questions about simulated grid behavior, you query the CGSim simulation database (an append-only EVENTS table) using the query_simulation_db tool, then explain the results in clear operational terms."
    },
    {
      "role": "user",
      "content": "For completed file transfers grouped by link-load tier (idle <0.2, light 0.2–0.5, moderate 0.5–0.8, heavy ≥0.8), what are the transfer count, average achieved throughput (bytes ÷ duration), average declared bandwidth, bandwidth efficiency ratio (achieved ÷ declared), average file size, and average duration?"
    },
    {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "type": "function",
        "function": {
          "name": "query_simulation_db",
          "arguments": {
            "sql": "SELECT CASE WHEN CAST(json_extract(METADATA, '$.link_load') AS REAL) < 0.2 THEN '1_idle (<0.2)' WHEN CAST(json_extract(METADATA, '$.link_load') AS REAL) < 0.5 THEN '2_light (0.2-0.5)' WHEN CAST(json_extract(METADATA, '$.link_load') AS REAL) < 0.8 THEN '3_moderate (0.5-0.8)' ELSE '4_heavy (>=0.8)' END AS link_load_tier, COUNT(*) AS transfer_count, AVG(CAST(json_extract(METADATA, '$.size') AS REAL) / NULLIF(CAST(json_extract(METADATA, '$.duration') AS REAL), 0)) AS avg_achieved_throughput_bps, AVG(CAST(json_extract(METADATA, '$.bandwidth') AS REAL)) AS avg_declared_bandwidth, AVG(CAST(json_extract(METADATA, '$.size') AS REAL) / NULLIF(CAST(json_extract(METADATA, '$.duration') AS REAL), 0)) / NULLIF(AVG(CAST(json_extract(METADATA, '$.bandwidth') AS REAL)), 0) AS bandwidth_efficiency_ratio, AVG(CAST(json_extract(METADATA, '$.size') AS REAL)) AS avg_file_size_bytes, AVG(CAST(json_extract(METADATA, '$.duration') AS REAL)) AS avg_duration FROM EVENTS WHERE EVENT = 'FileTransfer' AND STATE = 'Finished' AND CAST(json_extract(METADATA, '$.duration') AS REAL) > 0 GROUP BY link_load_tier ORDER BY link_load_tier LIMIT 200"
          }
        }
      }]
    },
    {
      "role": "tool",
      "content": "{\"columns\": [\"link_load_tier\", \"transfer_count\", \"avg_achieved_throughput_bps\", \"avg_declared_bandwidth\", \"bandwidth_efficiency_ratio\", \"avg_file_size_bytes\", \"avg_duration\"], \"rows\": [[\"4_heavy (>=0.8)\", 5424, 7679912.9, 3734789823.0, 0.00206, 91664627.9, 98.69]], \"row_count\": 1}"
    },
    {
      "role": "assistant",
      "content": "## File Transfer Performance by Link-Load Tier\n\n**Key finding: All 5,424 transfers occur under heavy congestion (≥0.8 link load).** No idle, light, or moderate observations exist — the entire workload operates under saturated conditions.\n\n| Metric | Value |\n|---|---|\n| Transfer count | 5,424 |\n| Average file size | 91.66 MB |\n| Average duration | 98.69 s |\n| Average achieved throughput | 7.68 MB/s |\n| Average declared bandwidth | 3,734.79 MB/s |\n| **Bandwidth efficiency ratio** | **0.0021 (≈ 0.21%)** |\n\nThe efficiency ratio of 0.0021 is the most striking figure: actual throughput represents only **0.21% of declared capacity** — a ~486× degradation driven entirely by link saturation."
    }
  ],
  "text": "<|start|>system<|message|>...<|end|>\n<|start|>user<|message|>...<|end|>\n<|start|>assistant<|channel|>final<|message|>{\"name\": \"query_simulation_db\", \"arguments\": {\"sql\": \"...\"}}<|end|>\n<|start|>tool<|message|>...<|end|>\n<|start|>assistant<|channel|>final<|message|>...<|end|>"
}
```

---

## Glossary

**AskPanDA** — The name of the assistant being trained. It is dual-purpose, covering both ATLAS
Grid/PanDA workload management and Rubin Operations questions. This CGSim dataset targets the
Rubin Operations use case specifically.

**ATLAS Grid** — The distributed computing infrastructure used by the ATLAS experiment at CERN
to process particle physics data. Jobs run across dozens of sites worldwide coordinated by the
PanDA workload manager.

**Base** — The Rubin Observatory base facility in La Serena, Chile, co-located with summit
storage. One of the five simulated sites in CGSim.

**Batch size** — Number of `(question, SQL)` pairs the Proposer is asked to generate in a
single API call. Defaults to 5; halved automatically on token-limit errors.

**CGSim** — A discrete-event grid simulator for the Rubin Observatory built on SimGrid. Models
job scheduling, file transfers, and storage I/O across 568 nodes at five sites, writing each
event as a row in a SQLite EVENTS table.

**CGSimDataGenerator** — The Python class that orchestrates the Proposer → Executor →
Explainer → Judge pipeline against a CGSim EVENTS database to produce SFT examples.

**Checkpoint/resume** — A fault-tolerance mechanism that saves pipeline state to disk after
each batch, allowing interrupted Perlmutter jobs to restart and continue from where they stopped
without regenerating already-accepted examples.

**Claude Sonnet 4.6** — The Anthropic model used for the Proposer, Explainer, and Judge roles
in the datagen pipeline, accessed via the SLAC AI gateway.

**SLAC AI** — The AI API gateway operated by SLAC National Accelerator Laboratory, used here
to route all Claude Sonnet 4.6 calls during datagen. Each scenario's process holds its own
independent connection to this gateway.

**Coadd** — Co-addition: the process of combining multiple astronomical exposures into a single
deeper image. Coadd jobs are among the most compute-intensive in the Rubin processing pipeline.

**DOMAIN_PRIMER** — The system prompt injected into every Proposer, Explainer, and Judge API
call. Contains the EVENTS table schema, the authoritative `EVENT_SCHEMA` key list, and analysis
rules (e.g. use `STATE='Finished'` for performance metrics, never invent columns).

**Discrete-event simulation** — A modeling approach where system state changes only at specific
points in time (events), rather than continuously. SimGrid uses this to efficiently simulate
large distributed systems.

**EVENT_SCHEMA** — A Python dict defining the authoritative metadata keys available per event
type and state (e.g. `JobExecution/Finished` has `duration`, `retries`, `cost`, etc.). Injected
into `DOMAIN_PRIMER` and used by the Judge to reject SQL that references hallucinated keys.

**EVENTS** — The append-only SQLite table written by CGSim. Each row records one simulation
event with columns: `_ID`, `EVENT`, `STATE`, `STATUS`, `JOB_ID`, `TIME`, and `METADATA` (a JSON
object whose keys vary by event type).

**Executor** — The deterministic pipeline stage that runs each Proposer-generated SQL against
the scenario's SQLite DB and filters out empty results and non-SELECT queries.

**Explainer** — The Claude Sonnet 4.6 pipeline stage that writes a grounded operational answer
given the question, SQL, and actual query results. Instructed not to recompute aggregates or
hallucinate numbers.

**FrDF** — French Data Facility. One of the five simulated Rubin Observatory grid sites.

**GRPO (Group Relative Policy Optimization)** — A reinforcement learning training technique
used in Stage 4 of the AskPanDA next-phase architecture. The model proposes diagnoses and is
rewarded based on validation by CGSim as a ground-truth verifier, eliminating the need for
human annotation per training sample. GRPO is what crystallizes simulator-derived causal
reasoning into model weights, enabling deployment-time independence from CGSim.

**Grounding** — The requirement that every number in an answer is derivable from the actual
query results (within ≤5% relative tolerance). Ungrounded answers are rejected by the Judge.

**Hallucination** — A model generating facts not supported by its input — e.g. inventing SQL
column names not in the schema, or stating metric values not present in query results. The Judge
filters hallucinated SQL keys and ungrounded answer numbers.

**json_extract** — A SQLite function used to read values from the METADATA JSON column:
`json_extract(METADATA, '$.key')`. The Judge validates that every key referenced exists in
`EVENT_SCHEMA`.

**JSONL** — JSON Lines format: one JSON object per line. Used for both the checkpoint files and
the final SFT dataset output.

**Judge** — The Claude Sonnet 4.6 pipeline stage that applies 6 all-or-nothing quality criteria
to each `(question, SQL, result, answer)` tuple. Returns `keep=true` only if all criteria pass.

**LLM** — Large Language Model. The class of model being fine-tuned (AskPanDA) and also used
as the Proposer, Explainer, and Judge agents during data generation.

**PanDA** — Production and Distributed Analysis workload management system used by ATLAS and
other HEP experiments to schedule and track jobs across the grid.

**Perlmutter** — The CPU/GPU supercomputer at NERSC (National Energy Research Scientific
Computing Center) used to run the datagen jobs. The v4 dataset was generated on the CPU
`shared` partition under allocation m2616.

**Proposer** — The Claude Sonnet 4.6 pipeline stage that generates batches of `(question, SQL)`
pairs given the EVENTS schema and a deduplication list of already-seen questions.

**`query_simulation_db`** — The tool the trained AskPanDA model calls at inference time to
execute a SQL SELECT against the operational (or simulation) database. During training, the
Executor plays this role deterministically.

**Rucio** — The scientific data management system used by ATLAS and other experiments to
catalog and transfer files across the grid. The real-world counterpart to CGSim's FileTransfer
events.

**Rubin Observatory** — The Vera C. Rubin Observatory under construction in Chile, which will
run the Legacy Survey of Space and Time (LSST). Its grid topology (USDF, Base, FrDF, UKDF,
Summit) is what CGSim models.

**SFT (Supervised Fine-Tuning)** — A training technique where a pre-trained language model is
further trained on labeled `(input, output)` examples to teach it specific behaviors — in this
case, answering grid operations questions via tool-call-then-explain.

**SimGrid** — An open-source C++ framework for discrete-event simulation of distributed
systems. CGSim uses it to emulate the Rubin Observatory grid at the level of individual job
executions, file transfers, and storage I/O operations.

**Summit** — The Rubin Observatory summit facility on Cerro Pachón, Chile, where raw telescope
data is first captured before being transferred to USDF for processing.

**UKDF** — UK Data Facility. One of the five simulated Rubin Observatory grid sites.

**USDF** — US Data Facility, located at SLAC National Accelerator Laboratory. The primary
processing site in the Rubin Observatory grid and the highest-volume site in the CGSim
scenarios.

**`text` field** — The pre-rendered flat-token string in each SFT record, used directly by
training frameworks that consume a single token sequence rather than structured message objects.
Uses role tokens `<|start|>`, `<|message|>`, `<|end|>`, and the `<|channel|>final` tag on
assistant tool-dispatch turns.
