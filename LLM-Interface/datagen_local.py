#!/usr/bin/env python3
"""Run CGSimDataGenerator locally for one or all scenarios.

Skips CGSim if the persistent DB already exists in outputs_dir.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_cgsim(cgsim_bin: str, config: str, tmp_db: str, persistent_db: Path) -> bool:
    env = os.environ.copy()
    local_lib = str(Path.home() / "llm-apps/app/local/lib")
    env["LD_LIBRARY_PATH"] = local_lib + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    r = subprocess.run([cgsim_bin, "-c", config], env=env)
    if r.returncode != 0:
        return False
    shutil.copy(tmp_db, persistent_db)
    return True


def run_datagen(python: str, clients_dir: str, db: Path, n: str, out: Path) -> bool:
    r = subprocess.run([
        python,
        str(Path(clients_dir) / "CGSimDataGenerator.py"),
        "--db", str(db),
        "--n", n,
        "--out", str(out),
    ])
    return r.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Run datagen locally for CGSim scenarios")
    ap.add_argument("--manifest",    required=True)
    ap.add_argument("--outputs-dir", required=True)
    ap.add_argument("--python",      required=True)
    ap.add_argument("--clients-dir", required=True)
    ap.add_argument("--cgsim-bin",   required=True)
    ap.add_argument("--n",           default="100")
    ap.add_argument("--scenarios",   nargs="+", help="Subset of scenario names (default: all)")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    if args.scenarios:
        manifest = [e for e in manifest if e["name"] in args.scenarios]
        if not manifest:
            sys.exit(f"No matching scenarios: {args.scenarios}")

    outputs_dir = Path(args.outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    ok, failed = [], []
    for entry in manifest:
        name = entry["name"]
        persistent_db = outputs_dir / f"rubin_{name}.db"

        print(f"\n{'='*60}")
        print(f"Scenario: {name}")
        print(f"{'='*60}")

        if persistent_db.exists():
            print(f"  DB exists — skipping CGSim")
        else:
            print(f"  DB not found — running CGSim...")
            if not run_cgsim(args.cgsim_bin, entry["config"], entry["output_db"], persistent_db):
                print(f"  [FAIL] CGSim failed", file=sys.stderr)
                failed.append(name)
                continue
            print(f"  DB ready: {persistent_db}")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = outputs_dir / f"sft_{name}_{ts}.jsonl"
        if run_datagen(args.python, args.clients_dir, persistent_db, args.n, out):
            print(f"  -> {out}")
            ok.append(name)
        else:
            print(f"  [FAIL] datagen failed for {name}", file=sys.stderr)
            failed.append(name)

    print(f"\n{'='*60}")
    print(f"Done: {len(ok)} succeeded, {len(failed)} failed")
    if ok:
        print(f"  ok:     {ok}")
    if failed:
        print(f"  failed: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
