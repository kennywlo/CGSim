#!/usr/bin/env python3
"""
Compare quality metrics across two SFT datagen runs (e.g. V3 vs V4).

Usage:
  python compare_runs.py \
      --a sft_baseline_v3.jsonl sft_usdf_degraded_v3.jsonl ... \
      --b sft_baseline_v4.jsonl sft_usdf_degraded_v4.jsonl ... \
      --label-a "V3 (Haiku+Sonnet)" --label-b "V4 (gpt-oss:120b)"

  # Or compare the latest file per scenario across two output dirs:
  python compare_runs.py \
      --outputs-a /pscratch/.../cgsim-outputs-v3 \
      --outputs-b /pscratch/.../cgsim-outputs-v4
"""

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def extract_fields(example: dict) -> dict:
    """Pull question, sql, tool_result, answer out of an SFT example."""
    msgs = example.get("messages", [])
    out = {"question": "", "sql": "", "tool_result": "", "answer": ""}
    for m in msgs:
        role = m.get("role")
        if role == "user" and isinstance(m.get("content"), str):
            out["question"] = m["content"]
        elif role == "assistant":
            tcs = m.get("tool_calls") or []
            if tcs:
                fn = (tcs[0] or {}).get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                out["sql"] = args.get("sql", "")
            elif m.get("content"):
                out["answer"] = m["content"]
        elif role == "tool" and isinstance(m.get("content"), str):
            out["tool_result"] = m["content"]
    return out


# ---------------------------------------------------------------------------
# SQL complexity
# ---------------------------------------------------------------------------

_SQL_FEATURES = {
    "join":      re.compile(r"\bjoin\b", re.I),
    "group_by":  re.compile(r"\bgroup\s+by\b", re.I),
    "having":    re.compile(r"\bhaving\b", re.I),
    "subquery":  re.compile(r"\(\s*select\b", re.I),
    "where":     re.compile(r"\bwhere\b", re.I),
    "order_by":  re.compile(r"\border\s+by\b", re.I),
    "avg":       re.compile(r"\bavg\s*\(", re.I),
    "count":     re.compile(r"\bcount\s*\(", re.I),
    "max_min":   re.compile(r"\b(?:max|min)\s*\(", re.I),
    "json_extract": re.compile(r"\bjson_extract\b", re.I),
}

def sql_features(sql: str) -> dict:
    return {k: bool(p.search(sql)) for k, p in _SQL_FEATURES.items()}

def sql_complexity_score(sql: str) -> int:
    """Simple integer complexity score (higher = more complex)."""
    f = sql_features(sql)
    return (f["join"] * 2 + f["group_by"] * 2 + f["having"] * 3
            + f["subquery"] * 3 + f["order_by"] + f["avg"] + f["count"]
            + f["max_min"] + f["json_extract"])


# ---------------------------------------------------------------------------
# Answer grounding signals
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*(?:e[+-]?\d+)?\b")
_TABLE_RE  = re.compile(r"\|.*\|")
_HEADER_RE = re.compile(r"^#{1,3}\s", re.M)

def answer_signals(answer: str) -> dict:
    nums = _NUMBER_RE.findall(answer)
    return {
        "num_count":    len(nums),
        "has_table":    bool(_TABLE_RE.search(answer)),
        "has_headers":  bool(_HEADER_RE.search(answer)),
        "char_len":     len(answer),
        "word_count":   len(answer.split()),
    }


# ---------------------------------------------------------------------------
# Question diversity
# ---------------------------------------------------------------------------

def bigrams(text: str) -> set:
    words = re.findall(r"\w+", text.lower())
    return set(zip(words, words[1:]))

def diversity_score(questions: list) -> float:
    """Mean proportion of unique bigrams across all questions (0–1)."""
    if not questions:
        return 0.0
    all_bg = Counter()
    per_q = []
    for q in questions:
        bg = bigrams(q)
        per_q.append(bg)
        all_bg.update(bg)
    if not all_bg:
        return 0.0
    # proportion of bigrams that appear only once (unique)
    unique = sum(1 for v in all_bg.values() if v == 1)
    return unique / len(all_bg)


# ---------------------------------------------------------------------------
# Per-file metrics
# ---------------------------------------------------------------------------

def compute_metrics(examples: list) -> dict:
    if not examples:
        return {}

    fields = [extract_fields(e) for e in examples]
    questions  = [f["question"]    for f in fields]
    sqls       = [f["sql"]         for f in fields]
    answers    = [f["answer"]      for f in fields]

    sql_feat_list = [sql_features(s) for s in sqls]
    ans_sig_list  = [answer_signals(a) for a in answers]

    def pct(lst, key):
        return 100 * sum(d[key] for d in lst) / len(lst)

    def avg(lst, key):
        return sum(d[key] for d in lst) / len(lst)

    complexities = [sql_complexity_score(s) for s in sqls]

    return {
        "n":                  len(examples),
        # Questions
        "q_len_avg":          sum(len(q) for q in questions) / len(questions),
        "q_diversity":        diversity_score(questions),
        # SQL
        "sql_complexity_avg": sum(complexities) / len(complexities),
        "pct_join":           pct(sql_feat_list, "join"),
        "pct_group_by":       pct(sql_feat_list, "group_by"),
        "pct_having":         pct(sql_feat_list, "having"),
        "pct_subquery":       pct(sql_feat_list, "subquery"),
        "pct_multi_agg":      100 * sum(
            1 for f in sql_feat_list
            if sum([f["avg"], f["count"], f["max_min"]]) >= 2
        ) / len(sql_feat_list),
        # Answers
        "ans_len_avg":        avg(ans_sig_list, "char_len"),
        "ans_words_avg":      avg(ans_sig_list, "word_count"),
        "ans_nums_avg":       avg(ans_sig_list, "num_count"),
        "pct_has_table":      pct(ans_sig_list, "has_table"),
        "pct_has_headers":    pct(ans_sig_list, "has_headers"),
    }


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> list:
    examples = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def latest_per_scenario(outputs_dir: Path) -> dict:
    pattern = re.compile(r"^sft_(.+?)_\d{8}_\d{6}\.jsonl$")
    by_scenario: dict = defaultdict(list)
    for f in outputs_dir.glob("sft_*.jsonl"):
        if f.stat().st_size == 0:
            continue
        m = pattern.match(f.name)
        if m:
            by_scenario[m.group(1)].append(f)
    return {s: max(fs, key=lambda p: p.name) for s, fs in by_scenario.items()}


def load_dir(outputs_dir: Path) -> list:
    files = latest_per_scenario(outputs_dir)
    examples = []
    for path in sorted(files.values()):
        examples.extend(load_jsonl(path))
    return examples


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def fmt_row(label: str, a_val, b_val, fmt=".1f", higher_is_better=True) -> str:
    def f(v):
        if v is None:
            return "  n/a  "
        if isinstance(v, float):
            return f"{v:{fmt}}"
        return str(v)

    a_s, b_s = f(a_val), f(b_val)
    if isinstance(a_val, (int, float)) and isinstance(b_val, (int, float)):
        if a_val == b_val:
            arrow = "  ="
        elif (b_val > a_val) == higher_is_better:
            arrow = " ▲B"
        else:
            arrow = " ▲A"
    else:
        arrow = ""
    return f"  {label:<35} {a_s:>10}  {b_s:>10}  {arrow}"


def print_report(label_a: str, ma: dict, label_b: str, mb: dict) -> None:
    w = 62
    print("=" * w)
    print(f"  {'Metric':<35} {'A':>10}  {'B':>10}")
    print(f"  {'':35} {label_a[:10]:>10}  {label_b[:10]:>10}")
    print("=" * w)

    def row(label, key, fmt=".1f", hib=True):
        print(fmt_row(label, ma.get(key), mb.get(key), fmt=fmt, higher_is_better=hib))

    print("  --- Volume ---")
    row("Examples (n)",              "n",              fmt="d")
    print("  --- Questions ---")
    row("Avg question length (chars)","q_len_avg")
    row("Bigram diversity (0-1)",    "q_diversity",    fmt=".3f")
    print("  --- SQL Complexity ---")
    row("Avg complexity score",      "sql_complexity_avg")
    row("% with JOIN",               "pct_join")
    row("% with GROUP BY",           "pct_group_by")
    row("% with HAVING",             "pct_having")
    row("% with subquery",           "pct_subquery")
    row("% with 2+ aggregations",    "pct_multi_agg")
    print("  --- Answers ---")
    row("Avg answer length (chars)",  "ans_len_avg")
    row("Avg words per answer",       "ans_words_avg")
    row("Avg numbers cited",          "ans_nums_avg")
    row("% with markdown table",      "pct_has_table")
    row("% with headers",             "pct_has_headers")
    print("=" * w)
    print("  ▲A = A wins   ▲B = B wins   = = tied")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Compare two SFT datagen runs")
    grp_a = ap.add_mutually_exclusive_group(required=True)
    grp_a.add_argument("--a",          nargs="+", metavar="FILE", help="Run A JSONL files")
    grp_a.add_argument("--outputs-a",  metavar="DIR",  help="Run A outputs dir (picks latest per scenario)")
    grp_b = ap.add_mutually_exclusive_group(required=True)
    grp_b.add_argument("--b",          nargs="+", metavar="FILE", help="Run B JSONL files")
    grp_b.add_argument("--outputs-b",  metavar="DIR",  help="Run B outputs dir (picks latest per scenario)")
    ap.add_argument("--label-a", default="Run A")
    ap.add_argument("--label-b", default="Run B")
    ap.add_argument("--scenarios", nargs="+", help="Restrict to these scenarios")
    args = ap.parse_args()

    if args.a:
        examples_a = []
        for p in args.a:
            examples_a.extend(load_jsonl(Path(p)))
    else:
        examples_a = load_dir(Path(args.outputs_a))

    if args.b:
        examples_b = []
        for p in args.b:
            examples_b.extend(load_jsonl(Path(p)))
    else:
        examples_b = load_dir(Path(args.outputs_b))

    if not examples_a:
        sys.exit("Run A: no examples found")
    if not examples_b:
        sys.exit("Run B: no examples found")

    print(f"\nRun A [{args.label_a}]: {len(examples_a)} examples")
    print(f"Run B [{args.label_b}]: {len(examples_b)} examples\n")

    ma = compute_metrics(examples_a)
    mb = compute_metrics(examples_b)
    print_report(args.label_a, ma, args.label_b, mb)


if __name__ == "__main__":
    main()
