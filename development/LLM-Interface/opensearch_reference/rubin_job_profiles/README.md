# Rubin job profiles from rubinobs-opensearch

Resource and failure profiles derived from real Rubin PanDA job records in
`panda_prod_test-*` (rubinobs-opensearch, USDF).

## Snapshot 2026-10-07

- Source: `panda_prod_test-2026-07` … `-2026-10`, queues `*_Rubin*`, job names starting
  `HSC_runs_` (RC2 reprocessing campaigns; `u_<user>_test_*` jobs are test runs and excluded),
  terminal status `finished`/`failed`. 722,265 jobs, 3 campaigns
  (`HSC_runs_RC2_w_2026_28`, `_37`, `_40`). Cluster health was red (41 unassigned shards) at
  export time; the selected indices returned 0 failed shards.
- `rubin_hsc_2026-10-07_profiles.json`: per task label and per queue — job counts, failure
  rate and top error codes, cores, and p10/p50/p90 of CPU seconds, wall seconds, CPU
  efficiency (`cpu / (wall x cores)`), max RSS (MB) and output bytes (finished jobs only).
- `rubin_hsc_2026-10-07_resources.json`: `resources.json`-format lognormal fits
  (`[shape, loc=0, scale]`) for `cpu_s`, `wall_s`, `max_rss_mb` per `<task label>:HSC`
  (labels with at least 30 finished jobs).
- `jobs_production.meta.json`: export parameters. The raw rows (40 MB, not committed) are at
  `~/llm-apps/app/rubin-job-snapshots/2026-10-07/jobs_production.jsonl.gz`.

## Snapshot 2026-10-07: LSSTCam DRP campaigns

- Source: all indices (`panda_prod_test-*`), two LSSTCam DRP campaigns —
  `LSSTCam_runs_DRP_20250527-20250921_w_2025_41_DM-53071` and
  `LSSTCam_runs_DRP_w_2026_17_DM-54760` — `finished`/`failed` jobs only: 2,047,815 jobs, 104
  task labels. All of these jobs ran on `CC-IN2P3_Rubin_*` queues. OpenSearch holds about
  20.1 M `LSSTCam_runs_DRP_*` jobs in total (April 2025 to July 2026; SLAC 9.7 M, CC-IN2P3 9.0 M, LANCS 1.2 M, RAL 0.25 M); none is named DRP1, so
  which campaigns count as DRP1 is an open question.
- `rubin_lsstcam_drp_2026-10-07_profiles.json` / `_resources.json`: same layout as the HSC
  files (resource keys are `<task label>:LSSTCam`, 78 fitted models).
- `jobs_lsstcam_drp.meta.json`: export parameters. Raw rows (not committed) are at
  `~/llm-apps/app/rubin-job-snapshots/2026-10-07/jobs_lsstcam_drp.jsonl.gz`.
- The same task label has very different profiles in the two datasets (e.g. `coadd` median CPU
  337 s on LSSTCam vs 904 s on HSC RC2; `diffim` 589 s vs 76 s), so the HSC fits should not be
  used for LSSTCam work.
- Failure summaries keep error codes and counts only; the free-text diagnostics are not kept
  (they can contain paths and account names).

Note: earlier counts in this project used a `*_Rubin_*` queue filter, which missed the queues named
exactly `<site>_Rubin` (about 9 M jobs, mostly 2025). The two exported snapshots above were checked and
lost no jobs; the exporter now uses `*_Rubin*`.

## Reproduce

```bash
kubectl --context usdf-opensearch port-forward svc/rubinobs-opensearch-coordinator \
    19200:9200 -n opensearch-system
export OS_USER=… OS_PASS=…     # admin secret usdf-opensearch-admin-pw-* (never on the command line)
python export_rubin_jobs.py --out jobs_production.jsonl.gz
# several campaigns: --indices "panda_prod_test-*" --jobname-prefix "<prefix1>,<prefix2>"
python derive_profiles.py --jobs jobs_production.jsonl.gz --out-prefix rubin_hsc_<date>
```

## Caveats

- The HSC snapshot is RC2 reprocessing, not LSSTCam (consistent with `real_quantum_graph.json`
  being an RC2-scale proxy); see the LSSTCam snapshot above.
- `hs06` is populated but its median is 1.0, so it is not a usable per-core benchmark;
  `cpuconsumptionunit` carries the worker-node CPU model string only.
- The task label is parsed from the job name
  (`<campaign>_<ts>_<step>_<label>_<NN>_<a>_<b>.<pandaid>`).
