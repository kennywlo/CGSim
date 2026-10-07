# Rubin job profiles from rubinobs-opensearch

Resource and failure profiles derived from real Rubin PanDA job records in
`panda_prod_test-*` (rubinobs-opensearch, USDF).

## Snapshot 2026-10-07

- Source: `panda_prod_test-2026-07` … `-2026-10`, queues `*_Rubin_*`, job names starting
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

## Reproduce

```bash
kubectl --context usdf-opensearch port-forward svc/rubinobs-opensearch-coordinator \
    19200:9200 -n opensearch-system
export OS_USER=… OS_PASS=…     # admin secret usdf-opensearch-admin-pw-* (never on the command line)
python export_rubin_jobs.py --out jobs_production.jsonl.gz
python derive_profiles.py --jobs jobs_production.jsonl.gz --out-prefix rubin_hsc_<date>
```

## Caveats

- These are RC2/HSC reprocessing jobs, not LSSTCam DRP1 (consistent with
  `real_quantum_graph.json` being an RC2-scale proxy).
- `hs06` is populated but its median is 1.0, so it is not a usable per-core benchmark;
  `cpuconsumptionunit` carries the worker-node CPU model string only.
- The task label is parsed from the job name
  (`<campaign>_<ts>_<step>_<label>_<NN>_<a>_<b>.<pandaid>`).
