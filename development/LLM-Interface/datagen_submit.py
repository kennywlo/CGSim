#!/usr/bin/env python3
"""Submit one sbatch job per scenario listed in manifest.json."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest",    required=True)
    ap.add_argument("--outputs-dir", required=True)
    ap.add_argument("--cgsim-bin",   required=True)
    ap.add_argument("--python",      required=True)
    ap.add_argument("--clients-dir", required=True)
    ap.add_argument("--run-script",  required=True, help="Path to datagen_run.sh")
    ap.add_argument("--account",     default="ntrain3")
    ap.add_argument("--qos",         default="shared")
    ap.add_argument("--constraint",  default="cpu")
    ap.add_argument("--time",        default="00:45:00")
    ap.add_argument("--cpus",        default="4")
    ap.add_argument("--mem-per-cpu", default="1900")
    ap.add_argument("--n",               default="100", help="Examples per scenario")
    ap.add_argument("--generator-model", default="", help="Override generator model")
    ap.add_argument("--judge-model",     default="", help="Override judge model")
    ap.add_argument("--scenarios",       nargs="+", help="Subset of scenarios (default: all)")
    ap.add_argument("--propose-only",    action="store_true", help="Generate GRPO prompt dataset (propose-only mode)")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    if args.scenarios:
        manifest = [e for e in manifest if e["name"] in args.scenarios]
        if not manifest:
            sys.exit(f"No matching scenarios in manifest: {args.scenarios}")

    Path(args.outputs_dir).mkdir(parents=True, exist_ok=True)

    submitted = []
    for entry in manifest:
        name   = entry["name"]
        config = entry["config"]
        db     = entry["output_db"]
        propose_only_arg = "1" if args.propose_only else ""
        gm = getattr(args, 'generator_model', '')
        jm = getattr(args, 'judge_model', '')
        # Quote every positional arg so empty strings aren't collapsed by the shell,
        # which would shift subsequent args into the wrong positional slots.
        wrap = (
            f'bash {args.run_script} "{name}" "{config}" "{db}"'
            f' "{args.n}" "{args.outputs_dir}" "{args.cgsim_bin}"'
            f' "{args.python}" "{args.clients_dir}"'
            f' "{gm}" "{jm}" "{propose_only_arg}"'
        )
        job_prefix = "grpo-propose" if args.propose_only else "cgsim-datagen"
        cmd = [
            "sbatch",
            f"--job-name={job_prefix}-{name}",
            f"--account={args.account}",
            f"--qos={args.qos}",
            f"--constraint={args.constraint}",
            "--ntasks=1",
            f"--cpus-per-task={args.cpus}",
            f"--mem-per-cpu={getattr(args, 'mem_per_cpu')}",
            f"--time={args.time}",
            f"--output={args.outputs_dir}/slurm-datagen-{name}-%j.log",
            "--export=ALL",
            "--wrap", wrap,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        line = (r.stdout.strip() or r.stderr.strip())
        print(f"  {name}: {line}")
        submitted.append(name)

    print(f"\nSubmitted {len(submitted)} jobs: {submitted}")


if __name__ == "__main__":
    main()
