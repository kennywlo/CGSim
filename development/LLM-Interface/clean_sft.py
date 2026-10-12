#!/usr/bin/env python3
"""Post-filter CGSimDataGenerator SFT JSONL: strip boilerplate, round floats, drop trivial examples.

Writes cleaned copies to --out-dir; input files are not modified.

Usage: clean_sft.py --out-dir cleaned sft_a.jsonl sft_b.jsonl ...
"""

import argparse
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "clients"))
from CGSimDataGenerator import render_canonical  # noqa: E402

DIRECT = re.compile(r"\b(?:taken|derived|come|comes|pulled|computed)\s+directly\s+from\b", re.IGNORECASE)
TRAILING_CLAUSE = re.compile(r"\s*(?:\(|,|;|\band\b)[^,;.()\n]*" + DIRECT.pattern + r"[^.;\n)]*\)?", re.IGNORECASE)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
MARKS = "*_ \t"


def strip_direct_sentence(sentence: str) -> str:
    """Drop the 'taken directly from the query' claim from one sentence, keeping other content."""
    if not DIRECT.search(sentence):
        return sentence
    trimmed = TRAILING_CLAUSE.sub("", sentence)
    if not DIRECT.search(trimmed):
        return trimmed
    lead = trimmed[: len(trimmed) - len(trimmed.lstrip(MARKS))]
    tail = trimmed[len(trimmed.rstrip(MARKS)):]
    segments = [seg.strip(MARKS) for seg in trimmed.strip(MARKS).split(";")]
    kept = [seg for seg in segments if seg and not DIRECT.search(seg)]
    if not kept:
        return ""
    body = "; ".join(kept)
    body = body[0].upper() + body[1:]
    if not body.endswith((".", "!", "?")):
        body += "."
    return lead + body + tail


def strip_direct(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        sentences = [strip_direct_sentence(x) for x in SENTENCE_SPLIT.split(line)]
        lines.append(" ".join(x for x in sentences if x.strip(MARKS + "-")))
    return "\n".join(lines)


NO_CALC = re.compile(
    r"[^\n.]*\bno\s+(?:additional|further|other|extra)\s+(?:calculations?|computations?)\b[^\n.]*\.?[ \t]*",
    re.IGNORECASE,
)
LONG_FLOAT = re.compile(r"(?<![\w.])(-?\d+)\.(\d{6,})(?![\w.])")
MIN_ANSWER_CHARS = 120


def round_float(m: re.Match) -> str:
    v = float(m.group(0))
    if abs(v) >= 1:
        return f"{v:.2f}"
    return f"{v:.4g}"


def clean_answer(text: str) -> str:
    text = NO_CALC.sub("", text)
    text = strip_direct(text)
    text = re.sub(r"^[ \t]*[-*][ \t]*$", "", text, flags=re.MULTILINE)
    text = LONG_FLOAT.sub(round_float, text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def all_numeric_zero(tool_content: str) -> bool:
    rows = json.loads(tool_content).get("rows", [])
    nums = [c for r in rows for c in r if isinstance(c, (int, float)) and not isinstance(c, bool)]
    return bool(nums) and all(n == 0 for n in nums)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = collections.Counter()
    seen_questions = set()

    for f in args.files:
        kept = []
        stats = collections.Counter()
        for line in open(f):
            ex = json.loads(line)
            msgs = ex["messages"]
            tool = json.loads(msgs[3]["content"])
            stats["in"] += 1
            question = msgs[1]["content"].strip()
            if question in seen_questions:
                stats["drop_duplicate_question"] += 1
                continue
            seen_questions.add(question)
            if tool.get("row_count") == 1 and all_numeric_zero(msgs[3]["content"]):
                stats["drop_single_row_all_zero"] += 1
                continue
            answer = clean_answer(msgs[4]["content"])
            if len(answer) < MIN_ANSWER_CHARS:
                stats["drop_short_answer"] += 1
                continue
            if answer != msgs[4]["content"].strip():
                stats["answers_modified"] += 1
            msgs[4]["content"] = answer
            kept.append({"messages": msgs, "text": render_canonical(msgs)})
            stats["out"] += 1
        out = out_dir / Path(f).name
        out.write_text("".join(json.dumps(e) + "\n" for e in kept))
        print(f"{Path(f).name}: {dict(stats)}")
        total.update(stats)

    print(f"TOTAL: {dict(total)}")


if __name__ == "__main__":
    main()
