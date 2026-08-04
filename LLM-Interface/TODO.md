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

## Raees: Rubin PanDA plugin v1

Repository: `/home/kennylo/llm-apps/app/Rubin-Plugin`. DGX compatibility work is on
local branch `dgx-compat`; the isolated CGSim correctness fix is on
`dgx-output-barrier`. See `docs/raees_rubin_plugin_compatibility.md` for the verified
build, smoke-test result, and detailed gap review.

Scope is PanDA/BPS only across SLAC, CC-IN2P3, LANCS, and RAL. Do not add HTCondor
or cm-service integration.

### Completed compatibility baseline

- [x] Build the plugin on DGX against the isolated `dag_dependencies` CGSim checkout
- [x] Complete the supplied 100-job graph and validate all 117 DAG edges
- [x] Fix child release so it waits for every parent's output writes, eliminating
      the missing-generated-input race
- [x] Add portable JSON discovery, current custom-parameter access, and a Linux/DGX
      `.so` configuration on the local compatibility branch

### P0 — required for Raees's v1

- [ ] Review and commit or rework the `dgx-compat` portability changes in the Rubin
      Plugin repository
- [ ] Port/rebase native DAG support onto current CGSim; upstream the output-write
      barrier with automated tests for chains, fan-in, zero-output jobs, and failed
      parents
- [ ] Replace the pre-clustered `jobs` JSON-only input with the v0.2 contract:
      `qgraph_manifest.json`, streaming `quanta.jsonl`, `edges.jsonl`,
      `clustering.json`, campaign metadata, and fitted resources
- [ ] Preserve qgraph, quantum, cluster, task/resource, PanDA attempt, and BPS rescue
      identifiers through scheduling and output
- [ ] Replace `Site0`–`Site4` with `SLAC_Rubin_*`, `CC-IN2P3_Rubin_*`,
      `LANCS_Rubin_*`, and `RAL_Rubin_*`; route by BPS memory/CPU requests using
      per-queue caps supplied from CRIC
- [ ] Keep the existing `EVENTS` stream and additionally emit PanDA-compatible job
      records plus pilot-log artifacts for AskPanDA `metadata_search` and `log_query`
- [ ] Implement job/quantum failure and downstream `failed_upstream` propagation;
      children of failed parents must terminate observably rather than wait forever
- [ ] Pass both acceptance fixtures: the supplied 100-job/117-edge graph and this
      repo's 624-quantum/264-cluster graph, with zero dependency-order violations

### P1 — after the v1 acceptance gate

- [ ] Separate PanDA/JEDI retry attempts from BPS restart/rescue qgraphs and retain
      explicit linkage among original jobs, attempts, and rescue jobs
- [ ] Model per-site Rucio/FTS transfers among the four Rubin facilities and support
      multiple qgraphs/campaign groups
- [ ] Consume site/queue-specific resource and failure fits; do not pool rates across
      facilities
- [ ] Add direct xrootd access, transfer concurrency, and site outage/degradation
      only after the staged-transfer model is validated

### Shared decisions before merging v1

- [ ] Raees + Kenny + Paul: choose native core DAG release or the pinned plugin-side
      pending gate after the current-CGSim port passes both acceptance fixtures; keep
      only one production path
- [ ] Raees + Kenny: confirm `_Merge`/`_Multi` queue rules, `failed_upstream` output
      terminology, attempt/rescue linkage fields, and whether site outages are v1 or
      deferred

### Inputs Kenny supplies to Raees

- [ ] Public HSC `rc2_subset` streaming QGraph fixture with pinned provenance
- [ ] `resources.json` and transfer/failure fits stratified by facility and queue
- [ ] Canonical PanDA Pilot error-code messages plus Rubin-specific diagnostic and
      log-tail templates
- [ ] Four-facility topology and canonical site/queue mapping

## Kenny: Perlmutter readiness and real QGraph export

The schema and synthetic fixtures are ready. The real QuantumGraph exporter and
bundle validator are now implemented and verified against a real `rc2_subset`
graph on Perlmutter (2026-08-03) -- see the "Real QuantumGraph export
(Perlmutter)" section of `README.md` for exact commands, pinned versions, and
results. This work is independent of Raees's v1 plugin.

### Available now

- [x] v0.2 manifest/JSONL contract and provenance requirements
- [x] Synthetic `campaign-demo/` fixture and `generate_campaign.py`
- [x] DAG ordering validator and DGX-verified Rubin scaffold plugin
- [x] Existing flat-workload Perlmutter config as a path and `/tmp` SQLite example
- [x] Perlmutter environment probe (`perlmutter-env.txt`) recording host
      architecture, loaded modules, Python version, and exact `lsst_distrib`,
      `pipe_base`, `ctrl_bps`, `drp_pipe`, `obs_subaru` revisions
      (`lsst-products.txt`); pinned to `w_2026_31` since no `v30*` stable
      release exists under `/cvmfs/sw.lsst.eu`
- [x] Real QuantumGraph exporter (`rubin-data/qgraph_exporter.py`) streaming
      `qgraph_manifest.json`, `quanta.jsonl`, `edges.jsonl`; monolithic
      `qgraph_export.json` remains synthetic-fixture-only
- [x] Standalone streaming bundle validator (`rubin-data/validate_bundle.py`,
      pure stdlib): schema version, unique integer `qid`, edge referential
      integrity, provenance completeness, line-by-line JSONL readability,
      referenced-file existence, edge/graph structural consistency
- [x] Tests against the real Butler repo (`rubin-data/tests/`): every node
      exactly once, edge topology agrees with `QuantumGraph.graph`, edge
      dataset types grounded in shared `DatasetRef`s, validator passes,
      repeated exports are structurally deterministic, provenance carries all
      pinned revisions

### Still open

- [ ] Add `rubin_dag_config_perlmutter.json` with configurable `/global/homes/...`
      paths and `output_file` under `/tmp`; do not reuse the existing flat-workload
      `rubin_config_perlmutter.json`
- [ ] Add a Perlmutter build helper for CGSim/SimGrid and
      `libRubinDispatcherPlugin.so`; remove DGX-specific install paths (explicitly
      out of scope for the exporter task -- do not build SimGrid on Perlmutter yet)
- [ ] Add a QGraph-specific Slurm wrapper and Make target. The current
      `datagen-submit`/`ScenarioConfigGenerator.py` path is legacy five-site only
- [ ] Add a QGraph manifest entry carrying the dispatch-plugin path and v0.2
      parameters instead of `jobs_file`/`Num_of_Jobs`
- [ ] Actually run `nightlyStep1`/`nightlyStep2*` via `pipetask run` (real
      compute, not just `pipetask qgraph`) against `rc2_subset` so a
      `nightlyStep3` (coadd) graph -- the originally-named fixture's actual
      stage -- has real upstream products to build against
- [ ] Build the Rubin scaffold plugin and run the synthetic campaign through Slurm
- [ ] Validate coadd-after-warp ordering and all cluster-DAG edges in the EVENTS DB
- [ ] Confirm `CGSimDataGenerator.py` accepts the DAG-gated EVENTS DB and rejects
      compute sites outside the four canonical PanDA prefixes

### Kenny: production resource, failure, and topology inputs

- [ ] Obtain enough PanDA/OpenSearch records for fitting; the committed mapping and
      sample documents are schema references, not a calibration population
- [ ] Parse `payload.stdout` timing/RSS records and Butler dataset sizes, then fit
      `resources.json` separately for SLAC, CC-IN2P3, LANCS, and RAL, recording all
      qgraph UUIDs and software versions in `fit_inputs`
- [ ] Seed generic failure messages from PanDA Pilot `ErrorCodes`; fit Rubin-specific
      `piloterrordiag` and log-tail templates as a separate data artifact
- [ ] Fit transfer and failure parameters per site, queue, and link; do not reuse
      aggregate cross-facility rates
- [ ] Replace the scaffold's collapsed `UKDF` zone with distinct LANCS and RAL zones
      and add canonical mapping: `SLAC→USDF`, `CC-IN2P3→FrDF`, `LANCS→LANCS`,
      `RAL→RAL`
- [ ] Apply identifier sanitization to unreleased commissioning/LSSTCam exports; do
      not emit real pre-release data IDs outside the rights environment without
      explicit Rubin Data Policy Committee approval

---

## Deferred core alternative: workflow DAG dependencies (~3–4 days)

> **Superseded for the pinned v0.2 baseline (2026-08-03)** by the `rubin-plugin` scaffold, which
> achieves DAG-gated release plugin-side via the existing pending-job re-poll —
> no `waiting` state, dynamic job injection, or core changes are needed. Do not
> implement the phases below directly. Raees's `dag_dependencies` branch is now the
> concrete native-core candidate; it supports produced-file inputs after the local
> output-write barrier fix. Evaluate that branch through the integration gate above
> instead of starting a second core design.

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
