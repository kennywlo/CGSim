# OpenSearch Reference Dump — rubinobs-opensearch (USDF)

## Current project scope

Use PanDA records whose `computingsite` matches `SLAC_Rubin_*`,
`CC-IN2P3_Rubin_*`, `LANCS_Rubin_*`, or `RAL_Rubin_*` for fitting and validation.
Fit each site/queue stratum separately. The HTCondor index is inventory evidence
but is excluded from the target population. Rucio calibration is per link among
the corresponding facility RSEs. Production cm-service activity data is not required.

Extracted 2026-07-15 from the `rubinobs-opensearch` cluster (`opensearch-system` namespace,
`usdf-opensearch.slac.stanford.edu`), via `kubectl port-forward svc/rubinobs-opensearch-coordinator 9200`.
Admin credentials in secret `usdf-opensearch-admin-pw-*`.

Purpose: source material for the simulated-event → PanDA-job-record field mapping
("Output records" section planned for rubin_campaign_schema v0.2).

## Files

| File | Source | Notes |
|---|---|---|
| `panda_prod_test_mapping.json` | `GET panda_prod_test-2026-06/_mapping` | 99 mapped fields (classic PanDA jobsarchived schema); live docs carry ~128 fields (dynamic extras) |
| `sample_job_finished.json` | 1 finished Rubin job | CC-IN2P3 target-site structural example; sanitized |
| `sample_jobs_failed.json` | 2 failed Rubin jobs (piloterrorcode 1305, transexitcode 139) | CC-IN2P3 target-site examples; do not generalize their rates to other sites |
| `sample_rucio_transfer_done.json` | 2 `transfer-done` events from `rucio-events-000006` | Target data-movement examples; payload carries src/dst RSE, bytes, timestamps |

## Index inventory (relevant to CGSim)

- `panda_prod_test-YYYY-MM` — completed/failed job records, monthly, ~1–8M docs/month, 2025-02 → present. **Primary target for the output plugin schema.**
- `panda_active_test-YYYY-MM` — job state-update stream (24 fields), ~10–37M docs/month
- `panda_harvester_test-YYYY-MM` — harvester worker records (32 fields)
- `panda_running_test-YYYY-MM` — snapshot of running jobs (small)
- `rucio-events-00000N` — full Rucio transfer lifecycle: preparing → submitted → queued → done / failed / submission_failed (~30M done vs ~3.3M failed+submission_failed in current rollover, ≈10% link-level failure signal). RSE vocabulary confirms RTN-101: `{SLAC,RAL,IN2P3,LANCS}_{RAW,BUTLER}_DISK` plus `DESC_*`, `IDAC_*`, `BASE_CALIB_DISK`.
- `htcondor-history-v1` — 759M docs of HTCondor job history (USDF local batch).
- **No cm-service activity-log indices exist** (checked full index list).

## Observations for the schema work (2026-06 index)

- All Rubin: `vo: wlcg`; sites `LANCS_Rubin_*`, `RAL_Rubin_*`, `CC-IN2P3_Rubin_*`, `SLAC_Rubin_*`.
- **Queue names encode requested memory** (`_4G/_8G/_12G/_20G/_28G/_32G/_Extra_Himem`) — the requests-vs-usage distinction is embodied in queue routing, so the clustering overlay needs a request-memory field to reproduce site/queue assignment.
- Status split: 1,002,162 finished / 145,432 failed (~12.7%).
- `exeerrorcode` was 0 on all failed jobs; the discriminating fields are `piloterrorcode`
  (1305 "failed to execute payload" dominates: 83,322) + `transexitcode` + `piloterrordiag` (free text).
  Payload-level (quantum) failure detail is NOT in these records — it lives in payload stdout/logs.
- Failure concentration is site-skewed: CC-IN2P3 queues account for ~97% of June failures
  (106k of 145k in `CC-IN2P3_Rubin_8G` alone). This demonstrates why aggregate
  rates are unsafe: fit CC-IN2P3 separately and do not generalize it to other sites.
- `jobname` pattern `u_lsstgrid_{...}_{taskLabel}_{...}Z_{NN}_{clusterLabel}` carries the BPS
  cluster/task label — usable as the join key from PanDA records back to the clustering overlay (§5).
