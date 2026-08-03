# Rubin PanDA plugin — implementation questions for Raees (Wed 2026-08-05)

Context: `dispatch_plugins/rubin-plugin/` is a working scaffold implementing the DAG
scheme from `rubin_campaign_schema_v0.2.md` (verified end-to-end 2026-08-03; see its
README for design and known core constraints). These questions cover what remains for
the actual plugin. Several were simplified against public PanDA/Rubin docs — where the
production behavior is documented, the question is just "any objection to mirroring it?"
(sources at bottom).

## Fixed scope and decisions

- WMS: PanDA only; no HTCondor path
- compute: all Rubin PanDA facilities — SLAC, CC-IN2P3, LANCS, and RAL
- data movement: Rucio/FTS links among the corresponding facility RSEs
- calibration: PanDA records and pilot logs fitted separately by site/queue; no cm-service
  activity-log dependency
- dependency release: plugin-side pending-job gating
- rescue: pre-materialized gated clusters for v0.2
- interchange: manifest + `quanta.jsonl` + `edges.jsonl`

## Scheduling (queue routing)

1. Queue routing is documented (panda.lsst.io): BPS `requestMemory` maps to the
   `<site>_Rubin_<size>G` queue with minRSS < requestMemory <= maxRSS (e.g. 5000MB →
   `_8G`). Plan is to mirror exactly that rule, with per-queue caps from CRIC. Any
   objection? Apply to `SLAC_Rubin_*`, `CC-IN2P3_Rubin_*`, `LANCS_Rubin_*`, and
   `RAL_Rubin_*`. Open sub-question:
   which QG clusters require the special `_Merge` / `_Multi` queues in v1?
2. Memory-retry is also documented (PanDA brokerage): on an OOM failure, JEDI raises
   ramCount to the next rung of [1,2,3,4,6,8] GB above max(maxPSS, current), which
   re-routes the retry to a higher tier. OK to hard-code that ladder as the spill
   mechanism (non-OOM failures retry in the same tier)?

## Failure model

3. Status vocabulary decision: `pipetask report` (QuantumProvenanceGraph) calls
   downstream-of-failure quanta "blocked", while the schema calls their outcome
   `failed_upstream` (and reserves "wonky" cases for human review). Which
   vocabulary should the simulator emit, and do children of failed parents get explicit
   records or simply never release?
4. Start v1 with `resource_key` failure rates fitted separately for each site and
   queue. Should site-level outage/degraded events be included immediately, or wait
   until each site's sample supports stable rates?
5. Implement both PanDA/BPS recovery layers: same-submission `bps restart` and a
   pre-materialized subset-qgraph rescue gated on parent failure. Confirm the output
   linkage fields needed to distinguish retry attempts from rescue jobs.

## Data movement (Rucio + FTS + xrootd in production)

6. Core resolves input-file locations once at t=0, so children can't list parent
   products as inputs (scaffold README, constraint 5). Do you want to (a) ask Paul for
   re-resolution at release time, or (b) model Rucio-rule-driven transfers
   plugin-side? Which lands in v1?
7. Production moves data via Rucio rules + FTS, with jobs often reading via xrootd
   rather than staging to local disk. For the first studies, is a minimal per-link
   staging/consolidation model among SLAC, IN2P3, LANCS, and RAL enough, or
   do you need the direct-access (xrootd) vs. staged distinction and per-link
   concurrency limits from day one?

## Output plugin (PanDA schema, §10)

8. For the 99-field record emitter: which field classes are in your v1 — the
   "simulated" set only, or also the synthesized ids (`pandaid`, `jobname` with the
   `u_lsstgrid_..._{taskLabel}_..._{clusterLabel}` join-key pattern)?
9. Pilot-log templates: the pilot's `errorcodes.py` is public and carries the full
   code → message table (1305 = PAYLOADEXECUTIONFAILURE "Failed to execute payload"),
   so the template library can be seeded from it plus real `piloterrordiag` samples
   from `panda_prod_test`. Proposal: Kenny seeds the library on the datagen side;
   your emitter just writes (code, diag, log-tail) triples it's given. Agreed, or do
   you want the templates inside the plugin?
10. Do you emit PanDA records alongside the existing EVENTS table or replace it?
    (Downstream GRPO/SFT tooling currently reads EVENTS.)

## Scale & format

11. Implement the resolved bundle contract: `qgraph_manifest.json`,
    `quanta.jsonl`, and `edges.jsonl`. Can the parser consume records
    incrementally without retaining the full graph twice in memory?
12. Timeline: which of these do you want in your v1 vs. deferred, and does the
    scaffold's structure (QGRAPH_WORKLOAD / RUBIN_DISPATCHER / OUTPUT split) work for
    you as the base, or will you restructure?

---
Sources: [Rubin PanDA queues & memory mapping](https://panda.lsst.io/user/data_facilities_and_queues.html) ·
[PanDA brokerage (OOM ramCount ladder)](https://panda-wms.readthedocs.io/en/latest/advanced/brokerage.html) ·
[pilot errorcodes](https://panda-wms.readthedocs.io/en/latest/_modules/pilot/common/errorcodes.html) ·
[pipetask report / QuantumProvenanceGraph](https://pipelines.lsst.io/modules/lsst.ctrl.mpexec/pipetask.html) ·
[ctrl_bps quickstart (bps restart, rescue qgraphs)](https://pipelines.lsst.io/modules/lsst.ctrl.bps/quickstart.html) ·
[QuantumGraph save format](https://community.lsst.org/t/changes-to-saving-and-loading-quantumgraphs/4587)
