# AskPanDA SFT Dataset v4 — Datagen Run Summary

**Date:** June 3, 2026  
**Output:** `askpanda_sft_cgsim_v4_20260603.jsonl` — **1,154 examples**

---

## What it is

Supervised fine-tuning data for teaching a model to answer ATLAS Grid computing operational
questions by querying a simulation database. Each example is a `(question, SQL, result, answer)`
tuple grounded in simulation EVENTS data produced by CGSim (a SimGrid-based Rubin Observatory
grid simulator).

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

**Proposer** — Claude Sonnet 4.6  
Generates diverse `(question, SQL)` pairs against the EVENTS schema. Given the schema and a list
of already-seen questions to avoid, it proposes batches covering per-site performance, file
transfer bottlenecks, disk I/O, job duration/retries, and cross-site comparisons.

**Executor** — deterministic  
Runs each proposed SQL against the actual simulated SQLite DB. Filters empty results and
non-SELECT queries before proceeding.

**Explainer** — Claude Sonnet 4.6  
Given the question, SQL, and real query results, writes a concise operational answer grounded
strictly in the returned data. Instructed not to recompute aggregates or hallucinate numbers.

**Judge** — Claude Sonnet 4.6  
Filters each `(question, SQL, result, answer)` tuple on 6 criteria before it enters the dataset:

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

| Scenario | Description | Examples |
|---|---|---|
| usdf_degraded | US Data Facility degraded I/O | 132 |
| base_degraded | Baseline with storage degradation | 131 |
| frdf_offline | French regional facility offline | 131 |
| high_coadd_burst | Burst of coadd processing jobs | 130 |
| usdf_storage_throttled | USDF storage bandwidth throttled | 129 |
| summit_link_bottleneck | Summit→USDF link saturated | 128 |
| transatlantic_congested | Transatlantic link congestion | 127 |
| baseline | Normal operations | 124 |
| high_load | Grid-wide high load | 122 |

9 scenarios covering normal operations, single-site failures, network bottlenecks, and burst
workloads.

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

---

## Appendix: Example records

Each record is a single-line JSON object. The `messages` array contains the full conversation
turn sequence; the `text` field is the pre-rendered SFT string used directly during training,
with role tokens (`<|start|>`, `<|message|>`, `<|end|>`) and a `<|channel|>final` tag on
assistant turns to distinguish tool calls from final responses.

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
