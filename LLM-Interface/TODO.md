# Datagen TODO

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
      `rubin_config_perlmutter.json`)
- [ ] One-off shakedown: `cg-sim -c rubin_dag_config_perlmutter.json` in an
      interactive/sbatch job; verify coadd-after-warp ordering in the EVENTS db
      (same check as the local 2026-08-03 validation)
- [ ] Wire into the datagen pipeline: `ScenarioConfigGenerator.py` needs a
      `--dispatch-plugin` pointing at the rubin plugin and a v0.2 parameter block
      (`qgraph_file`/`clustering_file`/`campaign_file`/`resources_file`/
      `default_site` replacing `jobs_file`/`Num_of_Jobs`) so `make datagen-submit`
      / `grpo-submit` can drive it; scenario knobs (degraded sites, link
      bottlenecks) apply unchanged since they modify topology, not workload
- [ ] Confirm `CGSimDataGenerator.py` output on a DAG-gated EVENTS db (schema is
      identical; job ids now 1000+ cluster jobs, timing has dependency structure)

Context: this is the "scaffold-level" of the two next runs. The true
Rubin-plugin-enabled run additionally waits on Raees's v1 (queue routing, failure
model — see `docs/rubin_plugin_questions_raees.md`), possibly Paul (core hooks,
depending on Wednesday's Q5/Q6 answers), and the real qgraph exporter +
`resources.json` fits (Kenny).

---

## Workflow DAG dependencies (~3–4 days)

> **Partially superseded (2026-08-03)** by the `rubin-plugin` scaffold, which
> achieves DAG-gated release plugin-side via the existing pending-job re-poll —
> no `waiting` state or core changes needed. Still relevant below: the
> `FileManager::on_file_created` hook idea, which is exactly what consumer-side
> staging of parent products needs (rubin-plugin README, constraint 5).

Currently all job input files are pre-staged in `site_info.json` before the
simulation starts. Jobs execute independently with no awareness of upstream
producers, so training data never captures realistic queue patterns like
SingleFrame jobs backing up while waiting on ISR.

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
