# CGSim → AskPanDA SFT Datagen Pipeline

Generates supervised fine-tuning (SFT) data for the AskPanDA assistant by running
CGSim (a SimGrid-based Rubin grid simulator), then using an LLM to produce
question/answer pairs grounded in the resulting EVENTS database.

---

## Next run checklist

The simulation parameters changed since v2 (2026-06-02). Scenario configs on disk
are stale — **regenerate them before submitting jobs.**

**What changed:**
- ISR input file size: 42 MB → 80 MB (raw CCD)
- CPU times: 3–6× longer across all job types (ISR 30s→90s, Coadd 600s→3600s, etc.)
- `num_jobs` default: 500 → 1000 per scenario
- New scenario: `high_load` (1500 jobs, 20% capacity) — produces non-zero retry rates

**Steps:**

```bash
# 0. Environment — must be set before submitting
export SLAC_AI_KEY="<your key from the SLAC AI gateway>"   # required for LLM API calls
# SSH key to S3DF must exist at ~/.ssh/id_slac (used for SOCKS5 tunnel)

# 1. Regenerate scenario configs (stale since parameter changes)
cd LLM-Interface
make scenarios

# 2. Submit all 9 scenarios — bump wall time for high_load's longer jobs
make datagen-submit \
    ACCOUNT=m2616 \
    OUTPUTS_DIR=$PSCRATCH/cgsim-outputs \
    SLURM_TIME=02:00:00

# 3. Wait for all jobs to complete, then merge
make merge OUTPUTS_DIR=$PSCRATCH/cgsim-outputs

# 4. Post-process: strip emoji from questions (see Post-processing section below)
```

**Timing note:** With 1000 jobs and CPU times 3–6× longer, each scenario takes
roughly 2–4× longer to simulate than before. The `high_load` scenario (1500 jobs,
oversubscribed grid) is the most expensive — allow at least 90 minutes. Set
`SLURM_TIME=02:00:00` to be safe.

**Current dataset:** `data/askpanda_sft_cgsim_v2_20260602.jsonl` — 1201 examples,
9 scenarios. The next run targets ~900 examples (9 scenarios × 100) which merges
with or replaces v2 depending on your dedup strategy.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| `cg-sim` binary | Build from repo root: `cmake -B build && cmake --build build` |
| Conda env | `~/.conda/envs/wf-seminar/bin/python3.10` (or override `PYTHON=`) |
| SLAC AI gateway key | Set `SLAC_AI_KEY` in environment; SOCKS5 tunnel is opened automatically |
| SSH key to S3DF | `~/.ssh/id_slac` (or override `SLAC_SSH_KEY=`) |

---

## Quick start

```bash
cd LLM-Interface

# 1. Generate scenario config files (site_info, jobs.csv, config.json per scenario)
make scenarios

# 2a. Submit all 9 scenarios as individual sbatch jobs
make datagen-submit ACCOUNT=m2616 OUTPUTS_DIR=$PSCRATCH/cgsim-outputs

# 2b. Or run a single scenario locally (login node, SLAC tunnel must be active)
make datagen-local SCENARIO=baseline OUTPUTS_DIR=$PSCRATCH/cgsim-outputs

# 3. Merge all per-scenario JSONL into one training file
make merge OUTPUTS_DIR=$PSCRATCH/cgsim-outputs
```

Output lands in `LLM-Interface/data/askpanda_sft_cgsim_v<YYYYMMDD>.jsonl`.

---

## Scenarios

| Scenario | Jobs | Description |
|---|---|---|
| `baseline` | 1000 | Nominal 5-site Rubin grid |
| `usdf_degraded` | 1000 | USDF compute halved (hardware failure / maintenance) |
| `base_degraded` | 1000 | Base compute halved (prompt processing bottleneck) |
| `frdf_offline` | 1000 | FrDF links throttled to 10 Mbps (network partition) |
| `summit_link_bottleneck` | 1000 | Summit uplinks throttled to 1 Gbps |
| `transatlantic_congested` | 1000 | All transatlantic links at 2 Gbps |
| `usdf_storage_throttled` | 1000 | USDF disk I/O throttled to 1 GBps |
| `high_coadd_burst` | 1000 | Heavy Coadd/ForcedPhotom burst (DRP reprocessing campaign) |
| `high_load` | 1500 | All sites at 20% capacity — resource contention and scheduling retries |

`high_load` is the only scenario designed to produce non-zero scheduling retry
counts. It runs 1500 jobs against a grid at 20% capacity (~1.2–2× oversubscribed
per site), which drives the `retries` field on `JobExecution / Finished` events.

To run a subset of scenarios:

```bash
make datagen-submit ACCOUNT=m2616 OUTPUTS_DIR=$PSCRATCH/cgsim-outputs \
    # edit datagen_submit.py --scenarios flag, or use datagen-local SCENARIO=<name>
```

---

## Simulation topology

Five-site Rubin network (Summit → Base → {USDF, FrDF, UKDF}):

| Site | Role | Nodes | Cores | Storage |
|---|---|---|---|---|
| Summit | Telescope buffer | 8 | 32 | 10 TB |
| Base | Prompt processing (La Serena) | 50 | 32 | 200 TB |
| USDF | Primary archive + DRP (SLAC) | 300 | 32 | 5 PB |
| FrDF | Backup + reprocessing (CC-IN2P3) | 150 | 32 | 2 PB |
| UKDF | Additional processing (RAL/IRIS) | 60 | 32 | 1 PB |

Key links: Summit↔Base 100 Gbps/1 ms · Base↔USDF 100 Gbps/95 ms ·
transatlantic links 10 Gbps · FrDF↔UKDF 1 Gbps.

---

## Job workload

| Job type | Site | Cores | CPU time (mean) | Input size (mean) |
|---|---|---|---|---|
| Prompt_ISR | Base (85%) | 1 | 90s | 80 MB (raw CCD) |
| SingleFrame_Cal | USDF (70%) | 4 | 420s | 100 MB |
| Coadd | USDF (55%) | 8 | 3600s | 100 MB × 10–50 files |
| DiffImaging | USDF (65%) | 4 | 600s | 100 MB × 2–4 files |
| ForcedPhotom | USDF (58%) | 8 | 900s | 50 MB × 5–20 files |

Job type mix: 40% ISR · 25% SingleFrame · 15% Coadd · 12% DiffImaging · 8% ForcedPhotom.

---

## Makefile variables

| Variable | Default | Notes |
|---|---|---|
| `ACCOUNT` | `m2616` | Slurm account |
| `OUTPUTS_DIR` | `$PSCRATCH/cgsim-outputs` | Where DBs and JSONL are written |
| `EXAMPLES_PER_SCENARIO` | `100` | Questions generated per scenario |
| `CGSIM_BIN` | `~/llm-apps/app/CGSim/build/cg-sim` | Path to simulator binary |
| `GENERATOR_MODEL` | _(default in CGSimDataGenerator)_ | Override LLM for question generation |
| `JUDGE_MODEL` | _(default in CGSimDataGenerator)_ | Override LLM for judging |
| `SLURM_TIME` | `01:00:00` | Wall time per job |
| `SLURM_QOS` | `shared` | Slurm QOS |

---

## Regenerating simulation configs

If you change job parameters (CPU times, file sizes, job counts) in
`clients/ScenarioConfigGenerator.py`, regenerate all scenario configs before the
next datagen run:

```bash
make scenarios
```

If you change `rubin-data/generate.py` (the standalone baseline config), regenerate
the files it writes:

```bash
python rubin-data/generate.py
```

This updates `rubin-data/site_info.json`, `rubin-data/site_conn_info.json`, and
`rubin-data/jobs.csv`. These are only used by `rubin_config.json` (direct cg-sim
invocation), not by the scenario pipeline.

---

## Post-processing the merged JSONL

After `make merge`, strip any emoji that slipped through the question proposer:

```python
import json, re

def sanitize_question(q):
    q = re.sub(r'\d️?⃣\s*', '', q)
    q = re.sub(r'[\U0001F300-\U0001F9FF☀-➿︀-️⃐-⃿]+', '', q, flags=re.UNICODE)
    return ' '.join(q.split())

path = 'data/askpanda_sft_cgsim_v<date>.jsonl'
with open(path) as f:
    data = [json.loads(l) for l in f]
for d in data:
    for m in d['messages']:
        if m['role'] == 'user':
            m['content'] = sanitize_question(m['content'])
with open(path, 'w') as f:
    for d in data:
        f.write(json.dumps(d) + '\n')
```
