# Raees Rubin Plugin: DGX compatibility and PanDA gap review

Reviewed and tested 2026-08-03 against Raees's repository at
`/home/kennylo/llm-apps/app/Rubin-Plugin` (upstream `main` commit `580db9a`).

## Result

The repository is a useful native-DAG prototype, but it is not yet the PanDA Rubin
plugin described by `rubin_campaign_schema_v0.2.md`.

An isolated DGX build and smoke test now works:

- Rubin Plugin local compatibility branch: `dgx-compat`
- CGSim source: isolated checkout from `dag_dependencies` commit `9efddea`, with
  the local correctness fix on branch `dgx-output-barrier`
- CGSim install prefix: `/home/kennylo/llm-apps/app/CGSim-dag-install`
- plugin build: `/home/kennylo/llm-apps/app/Rubin-Plugin/plugin/build-dgx-dag/libRubinPlugin.so`
- test input: the supplied 100-job synthetic workload
- result: 100/100 jobs started and completed; all 117 dependency edges were
  reciprocal and had zero parent-output-write/child-start ordering violations
- output: 838 SQLite `EVENTS` rows covering all 100 job IDs (274 reads, 64
  transfers, 200 writes, 100 allocations, and 200 execution transitions)

This did not alter the normal CGSim installation used by this repo.

## Compatibility changes made locally

Raees's `dgx-compat` branch has uncommitted changes that:

1. discover `nlohmann/json.hpp` explicitly in CMake;
2. replace removed `SiteManager::Custom_Parameters` access with SimGrid root-zone
   properties for `jobs_file` and `output_file`; and
3. add a portable Linux/DGX config, `config/rubin_config_dgx.json`, using `.so`
   rather than the original macOS `.dylib` and removing developer-specific paths.

The isolated CGSim `dag_dependencies` checkout also has an uncommitted correctness
fix. The original branch released children when parent compute ended, before the
parent's asynchronous output writes completed. That caused an immediate missing-file
crash. The local fix gates child release on completion of every parent's output
writes. It must be upstreamed or replaced by an equivalent tested barrier before the
native-DAG branch is adopted.

## What the prototype already provides

- native `parents` and `children` fields on CGSim jobs;
- delayed child creation after dependency satisfaction;
- single-parent chains and multi-parent fan-in;
- derived products that are written by parents and consumed by children;
- conventional CGSim allocation, execution, file-I/O, and transfer events.

This native mechanism is cleaner for generated-file availability than repeated
plugin-side polling. It is nevertheless based on an old branch, not current CGSim
`main`, and currently needs a core patch, so it is a candidate implementation—not
yet the repository's default architecture.

## Gaps to the PanDA-only Rubin target

### P0: reproducible and correct base

- Rebase or port `dag_dependencies` onto current CGSim and add automated DAG tests,
  including parent-output barriers, fan-in, zero-output jobs, and failed parents.
- Pin the compatible CGSim commit and make JSON/CMake dependencies portable.
- Decide with Raees/Paul whether native core DAG support replaces the v0.2
  plugin-side pending gate. Do not maintain both as production paths.
- Add a build/run recipe suitable for DGX and Perlmutter CI.

### P0: consume the agreed Rubin contract

- Read `qgraph_manifest.json`, streaming `quanta.jsonl`, `edges.jsonl`,
  `clustering.json`, campaign metadata, and fitted resources. The current plugin
  accepts a pre-clustered, in-memory `jobs` JSON file and therefore bypasses the
  v0.2 quantum/clustering separation.
- Preserve qgraph, quantum, cluster, task/resource, attempt, and rescue identifiers.
- Replace generic `Site0`–`Site4` with the four PanDA facility families:
  `SLAC_Rubin_*`, `CC-IN2P3_Rubin_*`, `LANCS_Rubin_*`, and `RAL_Rubin_*`.
- Route jobs by BPS memory/CPU requests to PanDA queues with CRIC-derived caps.

### P0: output needed by AskPanDA

- Keep `EVENTS` for existing tooling and additionally emit PanDA-compatible job
  records plus pilot-log artifacts; the prototype emits `EVENTS` only.
- Populate the identifiers, statuses, errors, timestamps, CPU/memory usage, site,
  queue, and log references used by `metadata_search` and `log_query`.
- Emit coherent `(piloterrorcode, piloterrordiag, log tail)` triples.

### P1: workflow behavior

- Model quantum/job failure, `failed_upstream` propagation, and children that never
  become runnable; the current core explicitly leaves failure handling as a TODO.
- Separate PanDA/JEDI retry attempts from BPS restart/rescue qgraphs and preserve
  their linkage.
- Fit resource use and failure behavior separately by site and queue.
- Model Rucio/FTS data movement between Rubin facilities rather than only generic
  links, and support multiple qgraphs/campaign groups.

### P2: later fidelity

- Direct xrootd access versus staged input, link concurrency, outages/degradation,
  dynamic rescue injection, and the long tail of the 99-field PanDA mapping.

HTCondor and cm-service integration are intentionally absent from this checklist.

## Recommended next integration step

Treat the native DAG prototype as the likely core mechanism, subject to a short
merge gate: port it to current CGSim, upstream the output-write barrier, and run both
the supplied 100-job graph and this repo's 624-quantum/264-cluster fixture. Only then
switch the v0.2 schema and Perlmutter plan from plugin-side gating to native DAG
release. In parallel, Raees can implement the P0 PanDA contract and output work
without waiting for Kenny's real qgraph/resource exports.
