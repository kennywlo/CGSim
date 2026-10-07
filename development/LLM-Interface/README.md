# CGSim → AskPanDA PanDA/QG Datagen Pipeline

Generates supervised fine-tuning (SFT) data for the AskPanDA assistant by running
CGSim (a SimGrid-based Rubin grid simulator), then using an LLM to produce
question/answer pairs grounded in the resulting EVENTS database.

## Active scope

The current target is **PanDA workflow behavior only**, with Rubin
QuantumGraph processing across every Rubin Data Facility attached to PanDA:

- USDF: `SLAC_Rubin_*`
- FrDF: `CC-IN2P3_Rubin_*`
- UKDF: `LANCS_Rubin_*` and `RAL_Rubin_*`
- site-specific PanDA/BPS queue routing, retries, failures, job records, and
  pilot logs
- Rucio/FTS movement among the corresponding SLAC, IN2P3, LANCS, and RAL
  storage endpoints where required
- no HTCondor workflow/history modeling
- no dependency on production cm-service activity logs

The scenario generator now emits Rubin QGraph scenarios (see "Scenarios" below). The
existing SFT datasets were produced from the old five-site flat workload and are
retained as historical baselines. They do not define the target topology or
calibration population for the PanDA/QG run unless filtered to PanDA semantics
and the canonical site identities above. See
`rubin_campaign_schema_v0.2.md` for the active contract.

## Real QuantumGraph export (Perlmutter)

`rubin-data/qgraph_exporter.py` and `rubin-data/validate_bundle.py` implement the
schema-section-4 streaming bundle (`qgraph_manifest.json`, `quanta.jsonl`,
`edges.jsonl`) against a real LSST QuantumGraph, replacing the synthetic
`campaign-demo/qgraph_export.json` for production exports. See
`rubin_campaign_schema_v0.2.md` section 4 for the schema, and "Running a real
QuantumGraph bundle through the simulator" below for how
`dispatch_plugins/rubin-plugin` (this repo's plugin) consumes it directly.
`docs/raees_rubin_plugin_compatibility.md` covers a separate, unrelated
codebase -- Raees's `Rubin-Plugin` repo -- not this one.

**Pinned environment** (established 2026-08-03 on Perlmutter; see
`rubin-data/perlmutter_inspection/perlmutter-env.txt` and `lsst-products.txt`):

```bash
export LSST_RELEASE_DIR=/cvmfs/sw.lsst.eu/almalinux-x86_64/lsst_distrib/w_2026_31
source "$LSST_RELEASE_DIR/loadLSST.bash"
setup lsst_distrib
setup obs_subaru
```

No `v30*` stable release exists under `/cvmfs/sw.lsst.eu`; `w_2026_31` is the
newest weekly and is pinned as the exporter baseline. Product revisions
(recorded in every export's provenance):

| Product | Revision |
|---|---|
| `lsst_distrib` | `g00e868bf88+c1824e70d0` |
| `pipe_base` | `g954f02917a+aa127417cf` |
| `ctrl_bps` | `ge3e32f3943+dd41cd23f8` |
| `drp_pipe` | `gc6b104cb6d+dad5072d3c` |
| `obs_subaru` | `g4db92921ce+973196f922` |

Also under `rubin-data/perlmutter_inspection/`: `butler-collections.txt` and
`butler-dataset-types.txt` (real `butler query-collections`/`query-dataset-types`
output against `rc2_subset/SMALL_HSC`) and `qgraph-inspection-regenerated.txt`
(the working `QuantumGraph` API introspection this exporter's field choices are
based on -- node/edge counts, task labels, data IDs, input/output `DatasetRef`
structure).

**Fixture:** `rc2_subset` at commit `432ea10`, Butler repo
`$HOME/llm-apps/app/rc2_subset/SMALL_HSC` (`butler.yaml` + `gen3.sqlite3`,
already populated — no separate Butler repository needs to be downloaded).

**The committed `central_six_coadd_9813.qgraph` does not load under `w_2026_31`.**
It was pickled 2021-06-11 by an old `daf_butler`; the current stack removed the
`lsst.daf.butler.core` module layout it used *and* the `unpickleInstanceMethod`
reducer it depends on for bound methods — a genuine format break, not an API
version mismatch. A bounded module-alias shim got past three renamed
submodules before hitting the unrecoverable reducer; see
`rubin-data/perlmutter_inspection/qgraph-inspection.txt` for the traceback and
`qgraph_exporter.load_quantum_graph`'s docstring for the fallback chain that
*is* supported (format-version-1 graphs missing only an embedded
`DimensionUniverse`, which is the actual common case for graphs from
~2022 onward). Rebuild a real graph from the same Butler repo instead:

```bash
pipetask qgraph \
  -b "$RC2_REPO" \
  -i HSC/RC2_subset/defaults \
  -o "u/$USER/RC2_subset/qgraph_regen_step1" \
  -p "$DRP_PIPE_DIR/pipelines/HSC/DRP-RC2_subset.yaml#nightlyStep1" \
  -q "$PSCRATCH/cgsim-rubin/artifacts/central_six_step1_9813.qgraph"
```

(`nightlyStep3`, the coadd subset the original fixture's name implies, builds
an *empty* graph in a fresh repo — it needs warp/visit-summary products from
steps 1–2, which have never actually been run here. `nightlyStep1`
(`isr`, `calibrateImage`, `transformPreSourceTable`) runs directly off the
raw+calib data already in the repo: 720 real quanta over 240 detector-visits.)

**Run the exporter:**

```bash
cd rubin-data
python qgraph_exporter.py \
  --qgraph "$PSCRATCH/cgsim-rubin/artifacts/central_six_step1_9813.qgraph" \
  --repo "$HOME/llm-apps/app/rc2_subset/SMALL_HSC" \
  --rc2-commit 432ea10 \
  --out-dir "$PSCRATCH/cgsim-rubin/artifacts/rc2_subset_nightlyStep1_export/run1"
```

`--sanitize` hashes non-dimension `data_id` values with a salted SHA-256
(`instrument`/`band`/`physical_filter`/`skymap` stay legible); not needed for
`rc2_subset` since public HSC identifiers are not proprietary (RDO-013 v1.2.5
DPOL-520), only for unreleased commissioning/LSSTCam exports.

**Validate a bundle** (pure stdlib, no LSST environment required):

```bash
python validate_bundle.py "$PSCRATCH/cgsim-rubin/artifacts/rc2_subset_nightlyStep1_export/run1/qgraph_manifest.json"
```

**Tests:**

```bash
python -m pytest rubin-data/tests/test_validate_bundle.py -v      # pure stdlib, always runs
python -m pytest rubin-data/tests/test_qgraph_exporter.py -v      # requires the activated LSST env above
```

**Verified 2026-08-03** against the real `central_six_step1_9813.qgraph`
(720 quanta / 480 edges / 35 dataset types / 3 tasks, from the real
`rc2_subset` Butler repo, not synthetic data):

- 14/14 validator unit tests pass, 7/7 exporter integration tests pass
  (every node appears exactly once; every edge references existing qids and
  a real `QuantumGraph.graph` edge; every edge's `dataset_type` is grounded
  in a DatasetRef shared between the producer's outputs and the consumer's
  inputs; the validator passes on the real export; provenance carries all
  five pinned revisions plus the `rc2_subset` commit)
- Two independent exports of the same graph are byte-identical in
  `quanta.jsonl` and `edges.jsonl`, and identical in `qgraph_manifest.json`
  apart from the `exported_at` timestamp
- `validate_bundle.py` CLI: `OK: bundle is valid`

---

## Running a real QuantumGraph bundle through the simulator (Perlmutter)

`rubin-data/build_real_bundle_run_config.py` bridges a real `qgraph_exporter.py`
bundle into a runnable CGSim configuration, and `dispatch_plugins/rubin-plugin`'s
`qgraph_workload.cpp` reads that bundle format directly (`qgraph_manifest.json`
+ `quanta.jsonl` + `edges.jsonl`) alongside the existing monolithic
`qgraph_export.json` test-fixture format used by `generate_campaign.py` --
auto-detected by presence of `quanta_file`/`edges_file` vs inline
`quanta`/`edges`. Same for `verify_dag_order.py`.

```bash
source scripts/perlmutter-env.sh
scripts/build-cgsim-perlmutter.sh          # once
scripts/build-rubin-plugin-perlmutter.sh   # once

RUN_DIR="$PSCRATCH/cgsim-rubin/artifacts/rc2_subset_nightlyStep1_export/run1"
python3 ../rubin-data/build_real_bundle_run_config.py \
  --manifest "$RUN_DIR/qgraph_manifest.json" \
  --site-info ../rubin-data/site_info.json \
  --raw-site Base \
  --default-site USDF \
  --dispatcher-plugin ../dispatch_plugins/rubin-plugin/build/libRubinDispatcherPlugin.so \
  --sites-connection-info ../rubin-data/site_conn_info.json \
  --out-dir "$RUN_DIR/run_config"

cg-sim -c "$RUN_DIR/run_config/rubin_dag_config.json"
python3 ../rubin-data/verify_dag_order.py /tmp/rubin_real_bundle_output.db \
  --qgraph "$RUN_DIR/qgraph_manifest.json" \
  --clustering "$RUN_DIR/run_config/clustering.json"
```

This is a structural smoke-test harness, not a production run configuration:
it uses one cluster per (task label, full real dimensions) -- no clustering
policy reduction -- and no fitted `resources.json` (real per-site resource
fits are separate, unstarted work; see TODO.md's "production resource,
failure, and topology inputs").

**Verified 2026-08-03**, first real (not synthetic) QuantumGraph run end to
end: `rc2_subset` `nightlyStep1` export (720 quanta, 480 edges) ->
`QGRAPH_WORKLOAD: 720 quanta -> 720 cluster jobs (240 roots, max depth 2)` ->
`verify_dag_order.py`: `clusters: 720  dag edges: 480  executed: 720` /
`OK: every child started at/after its last parent's end`.

---

## DGX Spark development environment

DGX Spark is the development, fitting, datagen, and model-work environment. The
real LSST-stack QuantumGraph export remains a Perlmutter (or other supported Rubin
environment) step; a full LSST Stack is not required here.

Create the isolated Python environment once:

```bash
conda env create -f environment-dgx.yml
```

For each shell, activate Python and expose the current CGSim/SimGrid installs:

```bash
conda activate cgsim-rubin
source scripts/dgx-env.sh
```

Reconfigure/rebuild the Rubin plugin against those installs and run the synthetic
DAG validation with:

```bash
scripts/build-rubin-plugin-dgx.sh
scripts/smoke-rubin-dag-dgx.sh
```

---

## Legacy flat-workload rerun checklist

Historical: this checklist describes the removed flat-workload pipeline
(`simple-test-plugin` / `jobs.csv`) and no longer applies. It is not the active
PanDA/QG run. The simulation parameters changed since v2 (2026-06-02). Scenario configs on disk
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

`make scenarios` runs `clients/ScenarioConfigGenerator.py`, which builds each scenario
from a synthetic Rubin DRP campaign (`rubin-data/generate_campaign.py`) executed by
`dispatch_plugins/rubin-plugin` on the topology below, plus capacity / network / storage
overrides. Each scenario sets the site that runs the campaign and the site holding the raw
inputs, so the degraded resource is on the path the workload uses.

| Scenario | Cluster jobs | Runs at (raw at) | Description |
|---|---|---|---|
| `baseline` | 264 | USDF (Base) | Nominal 5-site Rubin grid |
| `usdf_degraded` | 264 | USDF (Base) | USDF compute halved |
| `base_degraded` | 264 | Base (Summit) | Base compute halved (prompt processing) |
| `frdf_offline` | 264 | FrDF (Base) | FrDF links throttled to 10 Mbps |
| `summit_link_bottleneck` | 264 | USDF (Summit) | Summit uplinks throttled to 1 Gbps |
| `transatlantic_congested` | 264 | FrDF (USDF) | Transatlantic links at 2 Gbps |
| `usdf_storage_throttled` | 264 | USDF (Base) | USDF disk I/O throttled to 1 GBps |
| `high_coadd_burst` | 432 | USDF (Base) | 12 patches per visit (coadd-heavy) |
| `high_load` | 394 | USDF (Base) | All compute sites at 20% capacity, 1.5x visits |

Known limitation: with the plugin's current `GFLOPS × cpu_s × cores` flops formula, jobs
run in ~1e-7 s of simulated time, so compute-capacity overrides (`usdf_degraded`,
`high_load`) do not change makespan; the network, storage and workload-size scenarios do.

## Legacy flat-workload topology

Five-site Rubin network (Summit → Base → {USDF, FrDF, UKDF}):

| Site | Role | Nodes | Cores | Storage |
|---|---|---|---|---|
| Summit | Telescope buffer | 8 | 32 | 10 TB |
| Base | Prompt processing (La Serena) | 50 | 32 | 200 TB |
| USDF | Primary archive + DRP (SLAC) | 300 | 32 | 5 PB |
| FrDF | Backup + reprocessing (CC-IN2P3) | 150 | 32 | 2 PB |
| UKDF | Additional processing (RAL/IRIS) | 60 | 32 | 1 PB |

Key links: Summit↔Base 100 Gbps/1 ms · Base↔USDF 100 Gbps/95 ms ·
transatlantic links 10 Gbps · FrDF↔UKDF 10 Gbps (WLCG Tier-1 standard via GÉANT).

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
