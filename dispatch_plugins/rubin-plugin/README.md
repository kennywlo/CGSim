# rubin-plugin — CGSim dispatcher scaffold for Rubin DRP workloads

Scaffold implementing the DAG scheme from `LLM-Interface/rubin_campaign_schema_v0.2.md`
(sections 4–6). Forked from `simple-test-plugin`; intended as the starting point for the
actual Rubin plugin (Raees) — the `TODO(Raees)` markers and the list below say where the
real work goes.

## What it does (v0 scaffold)

- **`QGRAPH_WORKLOAD`** (`qgraph_workload.{h,cpp}`) — loads a v0.2 `qgraph_export.json`,
  applies the `clustering.json` overlay (one CGSim `Job` per cluster, schema §5), samples
  per-cluster CPU time from `resources.json` lognorm models (scipy `[shape, loc, scale]`
  convention), derives the **cluster-level DAG** from the quantum `edges`, and
  materializes cross-cluster and terminal datasets as producer-side output files
  (written and storage-accounted on completion). External inputs (`raw`) become input
  files, which triggers their staging transfer from the site where the generator
  pre-registered them (Base by default). Intra-cluster intermediates are node-local and
  not materialized; consumer-side reads of parent products are not modeled — see
  constraint 5 below.
- **`RUBIN_DISPATCHER`** (`rubin_dispatcher.{h,cpp}`) — SIMPLE_DISPATCHER's site/CPU
  selection plus the **DAG gate**: `assignJob()` returns `"pending"` until every parent
  cluster has finished. This uses the verified core mechanism (`util/job_executor.cpp`,
  `start_server`): jobs left pending are re-polled after **every** execution completion,
  so no core changes are needed for dependency-triggered release.
- **`RubinDispatcherPlugin.cpp`** — plugin wiring; `onJobExecutionEnd` calls
  `QGRAPH_WORKLOAD::markDone()` to release children, then logs via the unchanged
  `OUTPUT` EVENTS writer (copied from simple-test-plugin).

Site selection: the campaign group that owns the qgraph (`provenance.group_id` →
`campaign.json` group node `site`) decides `comp_site`; `default_site` custom parameter is
the fallback. Site names must match SimGrid netzone names from `site_info.json`
(Summit/Base/USDF/FrDF/UKDF) — the schema's `usdf|in2p3|lanc|ral` vocabulary needs a
mapping when real campaign files arrive.

## Build & run

```bash
cd dispatch_plugins/rubin-plugin
# needs SimGrid, Boost, CGSim, spdlog, SQLite3 discoverable, e.g. locally:
cmake -B build \
  -DSimGrid_PATH=$HOME/llm-apps/app/simgrid-install \
  -DCMAKE_PREFIX_PATH="$HOME/llm-apps/app/simgrid-install;$HOME/llm-apps/app/local"
cmake --build build
# generate demo inputs (synthetic v0.2 instances, 624 quanta -> 264 cluster jobs):
python3 ../../rubin-data/generate_campaign.py
# run:
LD_LIBRARY_PATH="$HOME/llm-apps/app/simgrid-install/lib:$HOME/llm-apps/app/CGSim-install/lib" \
  cg-sim -c ../../rubin-data/rubin_dag_config.json
```

Verified locally 2026-08-03: 264 jobs complete, and each `assembleCoadd` job starts at
exactly the finish time of the last `makeWarp` in its patch (checked in the EVENTS db) —
the DAG gate works through the unmodified core.

Custom parameters consumed (all via root-netzone properties, like the template's
`jobs_file`): `qgraph_file`, `clustering_file` (required); `campaign_file`,
`resources_file`, `default_site` (optional); `output_file` (required by OUTPUT).

## Known constraints inherited from core (verified 2026-08, `util/job_executor.cpp`)

1. **`getWorkload()` is one-shot** — no mid-run job injection. Rescue jobs (schema §4)
   must be pre-materialized in the initial queue and gated on "parent failed", or core
   needs a job-injection extension (schema open question 1).
2. **At least one root must be schedulable in the initial pass**, otherwise
   `start_server` blocks waiting for an Exec that never comes. Holds for any DAG with
   runnable roots; also holds for the template, but worth remembering when adding
   admission control.
3. **`Job::retries` is polluted by dependency waiting** — the pending-poll loop increments
   it on every re-poll, so it counts polls, not WMS attempts. Do **not** map it to
   `attemptnr` in the §10 output plugin; track real attempts separately.
4. **`JobQueue` is `std::priority_queue<Job*>`** — it orders by *pointer*, not
   `Job::operator<`, so `priority` (set here to topological depth) is currently cosmetic.
   Correctness doesn't depend on it (children gate on parents regardless of pop order).
5. **Input file locations are resolved once at t=0** — `start_server` calls
   `FileManager::request_file_location` on every job in the initial pass, before any
   parent has run, and FileManager throws on files that don't exist yet. So a child
   cannot list a parent's product among its `input_files`; this scaffold models
   cross-cluster datasets producer-side only (write I/O + storage), and pre-registers
   external inputs in `site_info.json` (the generator's `build_site_info`). Consumer-side
   staging of parent products needs core to re-resolve locations at release time —
   raise with Paul alongside open question 1 (job injection).

## TODO(Raees) — mapping to the roadmap / schema

- **Failure semantics (§8, roadmap step 7)**: `markDone()` currently releases children on
  *any* execution end, success or failure. Needs `failed`/`failed_upstream` propagation,
  `failures.json` injection (site events, per-resource_key `p_fail`), and the
  consistent (`piloterrorcode`, `piloterrordiag`, log-tail) triple per §10.
- **Queue routing (§9, roadmap step 3)**: replace first-fit CPU selection with
  memory-tiered `(site, queue)` routing driven by `request_memory_mb`, with per-queue
  caps — this is what makes `blocked`/starvation dynamics real.
- **Multi-qgraph campaigns (§2–3)**: this scaffold runs one qgraph (one group). Full
  campaigns need multiple qgraph files with inter-step gating from the campaign graph,
  plus §3 state-transition events per element.
- **Data movement policy (§9, roadmap step 4)**: input staging as a precondition on group
  start, product consolidation to USDF; currently files just live where jobs run.
- **§10 output plugin (roadmap step 5)**: replace/extend the EVENTS writer with the
  99-field PanDA record emitter (`LLM-Interface/opensearch_reference/`), including the
  `jobname` join-key pattern and pilot-log artifacts.
- **Serialization at scale (open question 4)**: single-JSON parse is fine at demo scale;
  revisit (JSON-lines streaming) before the 10^6-quantum stress test.
