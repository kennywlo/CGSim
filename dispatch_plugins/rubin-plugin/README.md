# rubin-plugin — CGSim dispatcher scaffold for Rubin DRP workloads

Scaffold implementing the DAG scheme from `development/LLM-Interface/rubin_campaign_schema_v0.2.md`
(sections 4–6). Forked from `simple-test-plugin`; intended as the starting point for the
actual Rubin plugin (Raees) — the `TODO(Raees)` markers and the list below say where the
real work goes.

## What it does (v0 scaffold)

- **`QGRAPH_WORKLOAD`** (`qgraph_workload.{h,cpp}`) — `setWorkload()` loads a v0.2
  `qgraph_export.json`, applies the `clustering.json` overlay (one CGSim `Job` per cluster,
  schema §5), samples per-cluster CPU time from `resources.json` lognorm models (scipy
  `[shape, loc, scale]` convention), derives the **cluster-level DAG** from the quantum
  `edges`, and declares it on the Jobs with `add_parent()`/`add_child()`. Roots get
  `creation_time` 0; dependents get -1 and core sets their creation time when the last
  parent finishes. Job ids are numeric strings from 1000 (sorted cluster-key order, the
  cluster key is kept as the `cluster_key` property) so EVENTS `JOB_ID`s match
  `rubin-data/verify_dag_order.py`. Cross-cluster and terminal datasets become
  producer-side output files (written and storage-accounted on completion). External inputs
  (`raw`) become input files, which triggers their staging transfer from the site where the
  generator pre-registered them (Base by default). Intra-cluster intermediates are
  node-local and not materialized; consumer-side reads of parent products are not modeled
  yet — see constraint 5 below.
- **`RUBIN_DISPATCHER`** (`rubin_dispatcher.{h,cpp}`) — first-fit site/CPU selection as in
  `simple-test-plugin`. There is no DAG gate in the plugin: core only submits a child job
  after every parent has reached `FINISHED` (`src/core/actions.cpp`).
- **`RubinDispatcherPlugin.cpp`** — `CGSim::Plugin` wiring; the `on*` hooks feed the
  `OUTPUT` EVENTS writer (derived from `simple-test-plugin`). Core hooks no longer pass
  SimGrid activities, so `OUTPUT` keeps its own start times to compute `duration`.

Site selection: the campaign group that owns the qgraph (`provenance.group_id` →
`campaign.json` group node `site`) decides `comp_site`; `default_site` custom parameter is
the fallback. Site names must match SimGrid netzone names from `site_info.json`
(Summit/Base/USDF/FrDF/UKDF) — the schema's `usdf|in2p3|lanc|ral` vocabulary needs a
mapping when real campaign files arrive.

## Build & run

```bash
cd dispatch_plugins/rubin-plugin
# needs SimGrid, Boost, CGSim (installed from this tree), spdlog, SQLite3 discoverable, e.g. locally:
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

Verified locally 2026-10-06 against the merged upstream core (`CGSim::Plugin` /
`setWorkload` API): 264 jobs complete and every child starts at/after its last parent's
end (`rubin-data/verify_dag_order.py`). Config notes for the current core: the plugin key
is `"Plugin"` (was `"Dispatcher_Plugin"`), and `site_info.json` needs a per-site `storage`
(e.g. `"5000000000000000B"`) and a per-CPU-cluster `ram` (e.g. `"256GB"`) — the old
`SITE_PROPERTIES.storage_capacity_bytes` / `properties: [{"ram": ...}]` layout no longer
parses (`Invalid Size Units`).

Custom parameters consumed (all via root-netzone properties, like the template's
`jobs_file`): `qgraph_file`, `clustering_file` (required); `campaign_file`,
`resources_file`, `default_site` (optional); `output_file` (required by OUTPUT).

## Core behavior this plugin relies on (re-verified 2026-10, `src/core/`)

1. **`setWorkload()` is one-shot** — no mid-run job injection. Rescue jobs (schema §4)
   must be pre-materialized in the initial queue and gated on "parent failed", or core
   needs a job-injection extension (schema open question 1).
2. **Dependents are released only when every parent is `FINISHED`.** A failed parent
   leaves its subtree blocked rather than failing it — no `failed_upstream` propagation
   yet (see TODO below).
3. **`Job::retries`** is incremented on site-pending retries (and on global-dispatch
   failures), not on DAG waiting, so the old polling pollution is gone. It still counts
   dispatch attempts, not WMS attempts — track real attempts separately for the §10 output.
4. **`JobQueue` orders by `creation_time`** (negative = waiting-on-parents, lowest
   priority). The topological-depth `priority` field no longer exists.
5. **Input file locations are resolved at execution time** (`execute_job` →
   `FileManager::request_file`), so a child could list a parent's product in
   `input_files`, provided the file exists once the parent has written it. This scaffold
   still models cross-cluster datasets producer-side only; consumer-side staging is the
   natural next step but is not implemented or tested here.

## TODO(Raees) — mapping to the roadmap / schema

- **Failure semantics (§8, roadmap step 7)**: core releases children only on parent
  `FINISHED`; a failed parent just blocks its subtree. Needs `failed`/`failed_upstream` propagation,
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
  99-field PanDA record emitter (`development/LLM-Interface/opensearch_reference/`), including the
  `jobname` join-key pattern and pilot-log artifacts.
- **Serialization at scale (open question 4)**: single-JSON parse is fine at demo scale;
  revisit (JSON-lines streaming) before the 10^6-quantum stress test.
