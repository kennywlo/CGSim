# Datagen TODO

## Active scope

Target PanDA/BPS workflows only, across all Rubin PanDA sites:
`SLAC_Rubin_*` (USDF), `CC-IN2P3_Rubin_*` (FrDF), and
`LANCS_Rubin_*`/`RAL_Rubin_*` (UKDF). Fit site and queue behavior separately;
do not pool facility rates. HTCondor history and cm-service activity logs are not
required inputs. The legacy five-site generator remains available for reproducing
older datasets.

## DGX Spark preparation — completed 2026-08-03

- [x] Verify GB10 CUDA execution (`nvidia-smi` plus a PyTorch CUDA tensor test)
- [x] Create and validate the `cgsim-rubin` Conda environment from
      `environment-dgx.yml`
- [x] Add reusable CGSim/SimGrid environment and build helpers under `scripts/`
- [x] Reconfigure and rebuild `rubin-plugin` against the current
      `CGSim-install` rather than `CGSim.old`
- [x] Run the isolated 624-quantum/264-job smoke test; all 260 cluster-DAG edges
      passed ordering validation
- [x] Keep the LSST Stack off DGX for now; perform the real qgraph export on
      Perlmutter or another supported Rubin environment

## Perlmutter scaffold-level run (rubin-plugin) — ~1 day

Goal: shakedown of the DAG-gated `rubin-plugin` (commit 5df1afb) through the full
Perlmutter sbatch pipeline, producing DAG-realistic EVENTS traces the existing
GRPO/SFT tooling can consume. Independent of Raees's v1 plugin work — this runs
the scaffold as-is on a synthetic v0.2 campaign.

- [ ] Build `libRubinDispatcherPlugin.so` on Perlmutter (same recipe as the
      2026-06-02 build fixes, commit 172523a: CGSim install + SimGrid module;
      plugin cmake needs `-DSimGrid_PATH` and CGSim discoverable)
- [ ] Run `rubin-data/generate_campaign.py` on Perlmutter (or regenerate — the
      committed `campaign-demo/` files are fine, but configs carry absolute paths)
- [ ] Add `rubin_dag_config_perlmutter.json`: `/global/homes/...` paths,
      `output_file` on `/tmp` (Lustre SQLite WAL workaround, as in
      `rubin_config_perlmutter.json`); require an explicit site on production
      groups and use `default_site=USDF` only for the synthetic demo
- [ ] One-off shakedown: `cg-sim -c rubin_dag_config_perlmutter.json` in an
      interactive/sbatch job; verify coadd-after-warp ordering in the EVENTS db
      (same check as the local 2026-08-03 validation)
- [ ] Wire into the datagen pipeline: `ScenarioConfigGenerator.py` needs a
      `--dispatch-plugin` pointing at the rubin plugin and a v0.2 parameter block
      (`qgraph_file`/`clustering_file`/`campaign_file`/`resources_file`/
      `default_site` replacing `jobs_file`/`Num_of_Jobs`) so `make datagen-submit`
      / `grpo-submit` can drive it; cover SLAC, CC-IN2P3, LANCS, and RAL
      compute queues and their Rucio/FTS data links
- [ ] Confirm `CGSimDataGenerator.py` output on a DAG-gated EVENTS db (schema is
      identical; job ids now 1000+ cluster jobs, timing has dependency structure);
      reject emitted compute sites outside the four canonical PanDA prefixes

Context: this is the "scaffold-level" of the two next runs. The true
Rubin-plugin-enabled run additionally waits on Raees's v1 (queue routing, failure
model — see `docs/rubin_plugin_questions_raees.md`), and the real qgraph exporter
plus `resources.json` fits (Kenny). The v0.2 architecture no longer waits on Paul for
core DAG or dynamic-injection hooks: release is plugin-side and rescue jobs are
pre-materialized. A core file-creation hook is only needed later if consumer-side
staging of parent products cannot be represented by the plugin.

## Kenny: real qgraph exporter and resource fits

- [ ] Pin exporter development to `lsst_distrib v30_0_4` plus exact
      `rc2_subset`, `pipe_base`, `ctrl_bps`, and `drp_pipe` commits in provenance
- [ ] Export the public HSC `rc2_subset` fixture as the v0.2 streaming bundle:
      `qgraph_manifest.json`, `quanta.jsonl`, and `edges.jsonl`
- [ ] Keep monolithic `qgraph_export.json` support only for small fixtures such as
      `campaign-demo/`; update the production reader to stream JSONL
- [ ] Add identifier sanitization for unreleased commissioning/LSSTCam exports;
      do not emit real pre-release data IDs outside the rights environment without
      explicit Rubin Data Policy Committee approval
- [ ] Parse `payload.stdout` timing/RSS records and Butler dataset sizes, then fit
      `resources.json` from PanDA records, stratified by SLAC, CC-IN2P3, LANCS,
      and RAL, with all qgraph UUIDs and software versions in `fit_inputs`
- [ ] Seed generic failure messages from PanDA Pilot `ErrorCodes`; fit Rubin-specific
      `piloterrordiag` and log-tail templates from production samples as a separate
      failure-model data artifact
- [ ] Fit transfer and failure parameters per site/link; do not reuse aggregate
      cross-facility rates
- [ ] Replace the scaffold's collapsed `UKDF` SimGrid zone with distinct LANCS
      and RAL zones, and add canonical mapping:
      `SLAC→USDF`, `CC-IN2P3→FrDF`, `LANCS→LANCS`, `RAL→RAL`

---

## Deferred core alternative: workflow DAG dependencies (~3–4 days)

> **Superseded for v0.2 DAG release (2026-08-03)** by the `rubin-plugin` scaffold, which
> achieves DAG-gated release plugin-side via the existing pending-job re-poll —
> no `waiting` state, dynamic job injection, or core changes are needed. Do not
> implement the phases below for v0.2. Still potentially relevant later: the
> `FileManager::on_file_created` hook idea, which is exactly what consumer-side
> staging of parent products needs (rubin-plugin README, constraint 5).

In the legacy flat-workload path, all job input files are pre-staged in
`site_info.json` before the simulation starts. Those jobs execute independently
with no awareness of upstream producers. The v0.2 Rubin plugin supplies DAG
gating without the core changes below.

### What to implement

**Phase 1 — ISR → SingleFrame (single predecessor)**

Python (`ScenarioConfigGenerator.py`, `rubin-data/generate.py`):
- Generate jobs in topological order; wire ISR output filenames to SingleFrame
  input filenames instead of pre-staging them
- Stop registering derived files in `site_info.json`; only source files
  (raw CCDs at Summit) are pre-staged

C++ (`job_executor.cpp`, `file_manager.cpp`):
- Add a `waiting` job state (inputs not yet produced) alongside `assigned`/`pending`
- Add `FileManager::on_file_created` static callback hook; fire it inside the
  existing `create()` call in `FileManager::write()`'s completion callback
  (`file_manager.cpp:94`)
- In `start_server`, park jobs with missing inputs in a `waiting_jobs` vector;
  on each `on_file_created` trigger, re-attempt dispatch for unblocked waiters

**Phase 2 — SingleFrame → Coadd (N-to-1 fan-in)**

- Track predecessor count per job; promote to dispatchable only when all N
  upstream outputs exist
- Adds ~1 day on top of Phase 1

### Estimated effort
| Phase | Effort |
|---|---|
| ISR → SingleFrame | ~3 days |
| + Coadd fan-in | +1 day |

### Notes
- SimGrid event loop is single-threaded so callback-based state transitions are
  safe without locks
- The natural hook point (`FileManager::write` completion → `create()`) is already
  in place; extending it is low-risk
- Job priority variation (all jobs currently have `priority=0`) is a related
  improvement worth pairing with this work — see below

---

## Job priority variation (~1 day)

`priority` is hardcoded to 0 in `workload_manager.cpp:106`. Adding per-job-type
priority (e.g. Prompt_ISR highest, ForcedPhotom lowest) would enable a new class
of training questions about PanDA priority scheduling.

Changes needed:
- Add `priority` column to jobs CSV in `generate.py` / `ScenarioConfigGenerator.py`
- Read it in `workload_manager.cpp`
- Log it in `output.cpp`'s `JobExecution` metadata

---

## Execution failure injection (~1 day, C++ only)

All jobs currently succeed. Adding a configurable per-job-type failure probability
would produce `JobExecution / Failed` events and realistic retry chains.

- Add `failure_rate` parameter to scenario configs
- In `actions.cpp` exec completion callback, draw against failure rate and set
  `j->status = "failed"`
- Add a mutex-protected failure queue; `start_server` drains it between
  `wait_any()` calls and requeues failed jobs up to `MAX_RETRIES`
- Log `JobExecution / Failed` in `output.cpp`

Note: the `high_load` scenario already produces non-zero *scheduling* retries
(resource contention). This work adds *execution* failure retries on top.
