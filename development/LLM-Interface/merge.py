#!/usr/bin/env python3
"""Merge per-scenario JSONL files into a single SFT training file.

For each scenario, only the most recent sft_<scenario>_*.jsonl is used
(earlier files are superseded by reruns). Deduplication is on by default:
within a scenario, duplicate questions are removed keeping the first
occurrence; across scenarios, all questions are kept (they cover different
simulation topologies).

Usage:
  python merge.py --outputs-dir $PSCRATCH/cgsim-outputs --out merged.jsonl
  python merge.py --outputs-dir $PSCRATCH/cgsim-outputs --out merged.jsonl --no-dedup
  python merge.py --outputs-dir $PSCRATCH/cgsim-outputs --out merged.jsonl --scenarios baseline usdf_degraded
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def latest_file_per_scenario(outputs_dir: Path, scenarios: "list[str] | None") -> "dict[str, Path]":
    """Return {scenario: most-recent sft_<scenario>_*.jsonl} for non-empty files."""
    pattern = re.compile(r"^sft_(.+?)_\d{8}_\d{6}\.jsonl$")
    by_scenario: dict[str, list[Path]] = defaultdict(list)
    for f in outputs_dir.glob("sft_*.jsonl"):
        if f.stat().st_size == 0:
            continue
        m = pattern.match(f.name)
        if m:
            by_scenario[m.group(1)].append(f)
    result = {}
    for scenario, files in by_scenario.items():
        if scenarios and scenario not in scenarios:
            continue
        result[scenario] = max(files, key=lambda p: p.name)  # lexicographic = chronological
    return result


def load_jsonl(path: Path) -> list[dict]:
    examples = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def extract_question(example: dict) -> str | None:
    for m in example.get("messages", []):
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            return m["content"]
    return None


def dedup(examples: list[dict]) -> tuple[list[dict], int]:
    seen: set[str] = set()
    out = []
    for e in examples:
        q = extract_question(e)
        if q is None or q not in seen:
            out.append(e)
            if q:
                seen.add(q)
    return out, len(examples) - len(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge CGSim SFT JSONL files")
    ap.add_argument("--outputs-dir", required=True, help="Directory containing sft_*.jsonl files")
    ap.add_argument("--out",         required=True, help="Output merged JSONL path")
    ap.add_argument("--scenarios",   nargs="*",     help="Only include these scenarios (default: all)")
    ap.add_argument("--no-dedup",    action="store_true", help="Disable per-scenario deduplication")
    args = ap.parse_args()

    outputs_dir = Path(args.outputs_dir)
    out_path    = Path(args.out)
    dedup_on    = not args.no_dedup

    files = latest_file_per_scenario(outputs_dir, args.scenarios)
    if not files:
        print("No non-empty sft_*.jsonl files found.", file=sys.stderr)
        sys.exit(1)

    total_raw = total_kept = total_dropped = 0
    all_examples: list[dict] = []

    print(f"{'Scenario':<35} {'Raw':>6} {'Kept':>6} {'Dropped':>8}  File")
    print("-" * 90)
    for scenario in sorted(files):
        path = files[scenario]
        examples = load_jsonl(path)
        raw = len(examples)
        if dedup_on:
            examples, dropped = dedup(examples)
        else:
            dropped = 0
        kept = len(examples)
        total_raw += raw
        total_kept += kept
        total_dropped += dropped
        all_examples.extend(examples)
        print(f"  {scenario:<33} {raw:>6} {kept:>6} {dropped:>8}  {path.name}")

    print("-" * 90)
    print(f"  {'TOTAL':<33} {total_raw:>6} {total_kept:>6} {total_dropped:>8}")
    print()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for e in all_examples:
            f.write(json.dumps(e) + "\n")

    print(f"Wrote {total_kept} examples → {out_path}")
    if dedup_on and total_dropped:
        print(f"  ({total_dropped} duplicates removed within-scenario)")


if __name__ == "__main__":
    main()
