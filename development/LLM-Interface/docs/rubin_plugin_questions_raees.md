# Rubin PanDA plugin — confirmations for Raees (Wed 2026-08-05)

Context: Raees's repository at `/home/kennylo/llm-apps/app/Rubin-Plugin` was reviewed
and smoke-tested on DGX on 2026-08-03. It supplies a native-DAG prototype through
CGSim's `dag_dependencies` branch; see `raees_rubin_plugin_compatibility.md` for the
verified result and prioritized gaps. `dispatch_plugins/rubin-plugin/` remains a
working scaffold implementing the DAG scheme from `rubin_campaign_schema_v0.2.md`
(verified end-to-end 2026-08-03; see its README for design and known core
constraints).

This document separates settled implementation requirements from decisions that
actually need Raees's answer. If a proposed default below is acceptable, a simple
"accept" is enough; only exceptions need a new design discussion.

## Fixed scope and decisions

- WMS: PanDA only; no HTCondor path
- compute: all Rubin PanDA facilities — SLAC, CC-IN2P3, LANCS, and RAL
- data movement: Rucio/FTS links among the corresponding facility RSEs
- calibration: PanDA records and pilot logs fitted separately by site/queue; no cm-service
  activity-log dependency
- dependency release: plugin-side pending-job gating is the pinned v0.2 baseline;
  native core DAG is the candidate, pending rebase and output-barrier tests
- rescue: pre-materialized gated clusters for v0.2
- interchange: manifest + `quanta.jsonl` + `edges.jsonl`

## Settled implementation requirements

- **Queue routing:** map BPS `requestMemory` to the documented
  `<site>_Rubin_<size>G` tier using CRIC-derived caps for SLAC, CC-IN2P3, LANCS,
  and RAL. This is an acceptance requirement, not an open design question.
- **OOM retry:** model the PanDA/JEDI memory escalation separately from non-OOM
  retries. Keep the memory-tier ladder in versioned configuration rather than
  hard-coding it in C++.
- **Failure records:** emit explicit records for downstream work that cannot run;
  never leave children waiting forever or omit them silently.
- **Input contract:** consume `qgraph_manifest.json`, streaming `quanta.jsonl`,
  `edges.jsonl`, and `clustering.json` without retaining duplicate full-graph
  representations.
- **Outputs:** preserve the existing `EVENTS` stream and add PanDA-compatible job
  records, including synthesized `pandaid` and `jobname` join keys, plus pilot-log
  artifacts. Do not replace `EVENTS` in v1.
- **Pilot diagnostics:** Kenny supplies generic error-code messages and fitted Rubin
  diagnostic/log-tail templates; the plugin consumes them and emits a coherent
  `(piloterrorcode, piloterrordiag, log tail)` triple.
- **Data movement:** start with per-link Rucio/FTS-style staged transfers among the
  four facilities. Direct xrootd access, concurrency limits, and outage behavior are
  P1 unless Raees identifies a blocker.

## Confirmations needed from Raees

1. **Native DAG plan.** Proposed default: port `dag_dependencies` to current CGSim,
   include the tested parent-output-write barrier, and use native DAG release for v1
   only after both acceptance fixtures pass. Are you willing to own that port/PR?
2. **Special queues.** Which tasks or cluster shapes, if any, should route to
   `_Merge` or `_Multi` in v1? Proposed default: ordinary memory-tier routing unless
   an authoritative rule is available.
3. **Failure terminology.** Proposed default: store the simulator outcome as
   `failed_upstream`, with Rubin's `blocked` as an optional source-vocabulary field.
   Accept or request a different canonical representation?
4. **Recovery linkage.** Proposed minimum fields are `attempt`, `retry_of`,
   `rescue_of`, `qgraph_id`, and `cluster_id`. Are additional identifiers required
   by your implementation?
5. **Outages.** Proposed default: v1 uses site/queue/resource-key failure fits only;
   correlated site outage/degradation events move to P1. Accept?
6. **Delivery shape.** Proposed sequence: portability/build PR, current-CGSim DAG
   PR, then PanDA input/routing/output PRs. Does this split fit how you want to land
   the work, or is there a dependency that requires a different order?

---
Sources: [Rubin PanDA queues & memory mapping](https://panda.lsst.io/user/data_facilities_and_queues.html) ·
[PanDA brokerage (OOM ramCount ladder)](https://panda-wms.readthedocs.io/en/latest/advanced/brokerage.html) ·
[pilot errorcodes](https://panda-wms.readthedocs.io/en/latest/_modules/pilot/common/errorcodes.html) ·
[pipetask report / QuantumProvenanceGraph](https://pipelines.lsst.io/modules/lsst.ctrl.mpexec/pipetask.html) ·
[ctrl_bps quickstart (bps restart, rescue qgraphs)](https://pipelines.lsst.io/modules/lsst.ctrl.bps/quickstart.html) ·
[QuantumGraph save format](https://community.lsst.org/t/changes-to-saving-and-loading-quantumgraphs/4587)
