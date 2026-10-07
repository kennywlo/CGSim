#!/usr/bin/env python3
"""Export Rubin PanDA job records from rubinobs-opensearch to gzipped JSONL.

Read-only scroll over panda_prod_test-* (the OpenSearch cluster is reached via
`kubectl port-forward svc/rubinobs-opensearch-coordinator 19200:9200 -n opensearch-system`).
Credentials come from the environment, never the command line:
  OS_USER, OS_PASS   (optional OS_URL, default https://127.0.0.1:19200)

Default filter = "production" campaign jobs: Rubin queues (*_Rubin*, i.e. both <site>_Rubin and <site>_Rubin_<tier>), job names starting
HSC_runs_ (RC2 reprocessing campaigns; the u_<user>_test_* jobs are test runs), and a
terminal status (finished/failed).
"""
import argparse
import gzip
import json
import os
import sys
from datetime import datetime, timezone

import httpx

FIELDS = [
    "pandaid", "jobname", "computingsite", "jobstatus", "attemptnr", "maxattempt",
    "processingtype", "resource_type", "corecount", "actualcorecount",
    "cpuconsumptiontime", "cpuconsumptionunit", "cpuconversion", "hs06", "hs06sec",
    "maxrss", "avgrss", "maxvmem", "minramcount", "maxwalltime",
    "creationtime", "starttime", "endtime", "modificationtime",
    "nevents", "outputfilebytes", "totrbytes", "totwbytes", "diskio",
    "piloterrorcode", "piloterrordiag", "exeerrorcode", "exeerrordiag",
    "ddmerrorcode", "ddmerrordiag", "transexitcode", "superrorcode", "superrordiag",
    "taskbuffererrorcode", "jobdispatchererrorcode", "brokerageerrorcode",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--indices", default="panda_prod_test-2026-07,panda_prod_test-2026-08,"
                    "panda_prod_test-2026-09,panda_prod_test-2026-10")
    ap.add_argument("--jobname-prefix", default="HSC_runs_",
                    help="job-name prefix, or several separated by commas (any match); "
                         "empty string = include test/user jobs too")
    ap.add_argument("--statuses", default="finished,failed")
    ap.add_argument("--page", type=int, default=10000)
    ap.add_argument("--out", required=True, help="output .jsonl.gz")
    args = ap.parse_args()

    url = os.environ.get("OS_URL", "https://127.0.0.1:19200")
    auth = (os.environ["OS_USER"], os.environ["OS_PASS"])
    flt = [{"wildcard": {"computingsite.keyword": "*_Rubin*"}},
           {"terms": {"jobstatus.keyword": args.statuses.split(",")}}]
    if args.jobname_prefix:
        flt.append({"bool": {"minimum_should_match": 1, "should": [
            {"prefix": {"jobname.keyword": p}} for p in args.jobname_prefix.split(",")]}})
    body = {"size": args.page, "_source": FIELDS, "sort": ["_doc"], "query": {"bool": {"filter": flt}}}

    n = 0
    with httpx.Client(verify=False, auth=auth, timeout=300) as c, gzip.open(args.out, "wt") as out:
        r = c.post(f"{url}/{args.indices}/_search?scroll=5m&ignore_unavailable=true", json=body)
        r.raise_for_status()
        d = r.json()
        total = d["hits"]["total"]["value"]
        failed_shards = d["_shards"].get("failed", 0)
        print(f"total {total} docs; failed shards {failed_shards}", file=sys.stderr)
        while True:
            hits = d["hits"]["hits"]
            if not hits:
                break
            for h in hits:
                src = h["_source"]
                src["_index"] = h["_index"]
                out.write(json.dumps(src) + "\n")
            n += len(hits)
            print(f"\r{n}/{total}", end="", file=sys.stderr)
            r = c.post(f"{url}/_search/scroll", json={"scroll": "5m", "scroll_id": d["_scroll_id"]})
            r.raise_for_status()
            d = r.json()
        c.request("DELETE", f"{url}/_search/scroll", json={"scroll_id": d["_scroll_id"]})
    meta = {"exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": n,
            "expected_rows": total, "failed_shards": failed_shards, "indices": args.indices,
            "jobname_prefix": args.jobname_prefix, "statuses": args.statuses}
    with open(args.out.replace(".jsonl.gz", ".meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"\nwrote {n} rows to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
