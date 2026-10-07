#!/usr/bin/env python3
"""Derive per-task / per-queue resource profiles from an export_rubin_jobs.py snapshot.

Outputs (next to --out-prefix):
  <prefix>_profiles.json   per-task and per-queue summary stats and failure breakdown
  <prefix>_resources.json  resources.json-format lognorm fits (scipy [shape, loc, scale],
                           loc fixed at 0) for cpu_s, wall_s and max_rss_mb per "<task>:<instrument>"

Task label comes from the PanDA job name:
  <campaign>_<YYYYMMDDTHHMMSSZ>_<step>_<task label>_<NN>_<a>_<b>.<pandaid>
Distributions use finished jobs only; failure statistics use all rows.
"""
import argparse
import json
import re

import numpy as np
import pandas as pd

NAME_RE = re.compile(
    r"^(?P<campaign>.+?)_(?P<ts>\d{8}T\d{6}Z)_(?P<step>\d+)_(?P<label>.+)_\d+_\d+_\d+\.\d+$")
MIN_SAMPLES = 30
PCTS = [10, 50, 90]


def stats(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return None
    return {"n": int(len(x)), "mean": float(x.mean()),
            **{f"p{p}": float(np.percentile(x, p)) for p in PCTS}}


def lognorm_params(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x) & (x > 0)]
    if len(x) < MIN_SAMPLES:
        return None
    lx = np.log(x)
    return [round(float(lx.std()), 4), 0.0, round(float(np.exp(lx.mean())), 4)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--jobs", required=True, help="jobs .jsonl.gz from export_rubin_jobs.py")
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--instrument", default="HSC", help="suffix for resource_key (campaign instrument)")
    args = ap.parse_args()

    df = pd.read_json(args.jobs, lines=True, compression="gzip")
    parsed = df["jobname"].str.extract(NAME_RE)
    df = pd.concat([df, parsed], axis=1)
    unparsed = int(df["label"].isna().sum())
    df = df[df["label"].notna()].copy()
    df["queue"] = df["computingsite"]
    for c in ("starttime", "endtime"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["wall_s"] = (df["endtime"] - df["starttime"]).dt.total_seconds()
    cores = df["actualcorecount"].where(df["actualcorecount"] > 0, df["corecount"]).clip(lower=1)
    df["cpu_eff"] = df["cpuconsumptiontime"] / (df["wall_s"] * cores)
    df["max_rss_mb"] = df["maxrss"] / 1024.0   # PanDA maxrss is in KB

    ok = df[(df["jobstatus"] == "finished") & (df["cpuconsumptiontime"] > 0) & (df["wall_s"] > 0)]

    def group_summary(g_all, g_ok):
        out = {"n_jobs": int(len(g_all)),
               "n_failed": int((g_all["jobstatus"] == "failed").sum()),
               "fail_rate": round(float((g_all["jobstatus"] == "failed").mean()), 5),
               "cores": {str(k): int(v) for k, v in g_all["corecount"].value_counts().head(5).items()},
               "queues": {k: int(v) for k, v in g_all["queue"].value_counts().head(8).items()}}
        for name, col in (("cpu_s", "cpuconsumptiontime"), ("wall_s", "wall_s"),
                          ("cpu_eff", "cpu_eff"), ("max_rss_mb", "max_rss_mb"),
                          ("hs06", "hs06"), ("output_bytes", "outputfilebytes")):
            out[name] = stats(g_ok[col].dropna()) if col in g_ok else None
        return out

    labels = {}
    for lab, g in df.groupby("label"):
        labels[lab] = group_summary(g, ok[ok["label"] == lab])
        fails = g[g["jobstatus"] == "failed"]
        if len(fails):
            codes = (fails.assign(code=fails[["piloterrorcode", "exeerrorcode", "transexitcode"]]
                                  .fillna(0).astype(int).astype(str).agg("/".join, axis=1))
                     .groupby("code").agg(n=("code", "size"),
                                          diag=("piloterrordiag", lambda s: str(s.dropna().iloc[0])[:120] if s.notna().any() else "")))
            labels[lab]["top_failures"] = [
                {"pilot/exe/trans": k, "n": int(r.n), "diag": r.diag}
                for k, r in codes.sort_values("n", ascending=False).head(4).iterrows()]
    queues = {q: group_summary(g, ok[ok["queue"] == q]) for q, g in df.groupby("queue")}

    models = {}
    for lab, g in ok.groupby("label"):
        fits = {k: lognorm_params(g[col]) for k, col in
                (("cpu_s", "cpuconsumptiontime"), ("wall_s", "wall_s"), ("max_rss_mb", "max_rss_mb"))}
        if all(v is not None for v in fits.values()):
            models[f"{lab}:{args.instrument}"] = {k: {"dist": "lognorm", "params": v} for k, v in fits.items()}

    campaigns = sorted(df["campaign"].unique().tolist())
    meta = {"source": args.jobs.split("/")[-1], "rows_used": int(len(df)), "rows_unparsed_jobname": unparsed,
            "n_finished_used_for_fits": int(len(ok)), "campaigns": campaigns,
            "min_samples_per_fit": MIN_SAMPLES, "max_rss_unit": "MB (PanDA maxrss KB / 1024)"}
    with open(f"{args.out_prefix}_profiles.json", "w") as f:
        json.dump({"meta": meta, "labels": labels, "queues": queues}, f, indent=1)
    with open(f"{args.out_prefix}_resources.json", "w") as f:
        json.dump({"schema_version": "0.2",
                   "provenance": {"fit_source": "panda_prod_test (rubinobs-opensearch)", "n_samples": int(len(ok)),
                                  "campaigns": campaigns, "fit_inputs": [args.jobs.split("/")[-1]]},
                   "models": models}, f, indent=1)
    print(f"{len(df)} rows, {len(labels)} task labels, {len(models)} fitted models, "
          f"{len(queues)} queues, {unparsed} unparsed names")


if __name__ == "__main__":
    main()
