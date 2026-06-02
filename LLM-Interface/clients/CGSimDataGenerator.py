"""
CGSimDataGenerator — turn CGSim simulation output (SQLite EVENTS table) into
SFT training examples for AskPanDA, using Claude as the teacher model.

Pipeline (per example):
  1. Claude proposes a diverse {question, sql} pair against the EVENTS schema.
  2. The SQL is validated (read-only) and executed against the REAL DB, so the
     tool result is ground truth, not a hallucination.
  3. Claude writes the analytical answer from the real results.
  4. The turn is emitted in the canonical {messages, text} SFT shape, matching
     flow-maestro/sft training data (OpenAI-style tool_calls + harmony `text`).

Successor to SimulationAnalysis.py (which used Gemini for live Q&A). This module
uses the Anthropic SDK, prompt caching on the schema prefix, and grounds every
answer in executed SQL.

Usage:
  python CGSimDataGenerator.py --db /tmp/rubin_output.db --n 50 \
      --out askpanda_sft_cgsim_$(date +%Y%m%d).jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import anthropic
from pydantic import BaseModel

# ============================================================
# Models (override on the CLI / constructor to pin a version)
# ============================================================
GENERATOR_MODEL = "claude-opus-4-8"   # teacher: question + SQL + answer
JUDGE_MODEL = "claude-sonnet-4-6"     # optional quality filter

MAX_ROWS = 200          # cap rows fed back as the tool result
MAX_RESULT_CHARS = 6000  # cap tool-result payload size in the SFT example

# ============================================================
# EVENTS schema — single source mirrored from
# LLM-Interface/schema/simulation_database_schema.txt
# ============================================================
EVENT_SCHEMA = {
    "JobAllocation": {
        "Started": ["status", "site", "host"],
        "Finished": [
            "status", "site", "host",
            "site_storage_util", "grid_storage_util",
            "site_cpu_util", "grid_cpu_util",
        ],
    },
    "JobExecution": {
        "Started": [
            "flops", "cores", "speed", "site", "host", "start_time",
            "site_cpu_util", "grid_cpu_util",
        ],
        "Finished": [
            "flops", "cores", "speed", "cost", "site", "host",
            "duration", "retries",
            "total_io_read_time", "file_transfer_queue_time",
            "resource_waiting_queue_time", "total_queue_time",
            "site_cpu_util", "grid_cpu_util",
        ],
    },
    "FileTransfer": {
        "Started": [
            "file", "size", "source_site", "destination_site",
            "bandwidth", "latency", "link_load",
            "site_storage_util", "grid_storage_util",
        ],
        "Finished": [
            "file", "size", "source_site", "destination_site",
            "duration", "bandwidth", "latency", "link_load",
            "site_storage_util", "grid_storage_util",
        ],
    },
    "FileRead": {
        "Started": ["file", "size", "site", "host", "disk", "disk_read_bw"],
        "Finished": ["file", "size", "site", "host", "disk",
                     "duration", "disk_read_bw"],
    },
    "FileWrite": {
        "Started": ["file", "size", "site", "host", "disk", "disk_write_bw",
                    "site_storage_util", "grid_storage_util"],
        "Finished": ["file", "size", "site", "host", "disk", "duration",
                     "disk_write_bw", "site_storage_util", "grid_storage_util"],
    },
}

ALL_JSON_KEYS = {
    key
    for states in EVENT_SCHEMA.values()
    for keys in states.values()
    for key in keys
}

# ============================================================
# Domain primer — stable, cached prefix
# ============================================================
DOMAIN_PRIMER = f"""\
You are an expert analyst of ATLAS Grid computing simulations produced by CGSim,
a discrete-event simulator built on SimGrid. The simulation writes an append-only
SQLite table named EVENTS.

EVENTS TABLE SCHEMA
CREATE TABLE EVENTS (
    _ID INTEGER PRIMARY KEY AUTOINCREMENT,  -- internal event id
    EVENT TEXT NOT NULL,                    -- JobAllocation | JobExecution | FileTransfer | FileRead | FileWrite
    STATE TEXT NOT NULL,                    -- Started | Finished
    STATUS TEXT NOT NULL,                   -- job status at the event
    JOB_ID TEXT NOT NULL,                   -- job identifier
    TIME FLOAT NOT NULL,                    -- simulation clock time of the event
    METADATA TEXT                           -- JSON object with event-specific keys
);

EVENT -> STATE -> METADATA keys (authoritative; never invent keys):
{json.dumps(EVENT_SCHEMA, indent=2)}

ANALYSIS RULES
- Use STATE='Finished' for performance metrics (duration, cost, throughput, retries).
- Use STATE='Started' for load-at-start / timestamp analysis.
- Durations live in METADATA.duration, never in the TIME column.
- For per-site summaries: include JobExecution/FileRead/FileWrite where
  METADATA.site = <site>, and FileTransfer where METADATA.source_site = <site>
  OR METADATA.destination_site = <site>.
- Extract metadata with json_extract(METADATA, '$.<key>').
- Never invent columns or JSON keys; never modify the database; one statement only.
"""

# ============================================================
# SFT target shaping
# ============================================================
SFT_SYSTEM_PROMPT = (
    "You are AskPanDA, an expert assistant for ATLAS Grid computing and PanDA "
    "workload management. For questions about simulated grid behavior, you query "
    "the CGSim simulation database (an append-only EVENTS table) using the "
    "query_simulation_db tool, then explain the results in clear operational terms."
)

# developer-turn tool spec rendered into the `text` field (harmony format)
TOOLS_SPEC = """# Tools

## query_simulation_db
// Run a single read-only SQL SELECT against the CGSim EVENTS table and return rows.
// Use json_extract(METADATA, '$.<key>') to read event-specific metadata.
// Use STATE='Finished' for performance metrics; durations are in METADATA.duration.
type query_simulation_db = (_: {
  // A single SQL SELECT statement against the EVENTS table.
  sql: string,
}) => any;""".strip()


# ============================================================
# Read-only SQL guard (ported from SimulationAnalysis.py)
# ============================================================
class SQLValidator:
    FORBIDDEN = re.compile(
        r"\b(insert|update|delete|drop|alter|create|pragma|attach|detach|replace)\b",
        re.IGNORECASE,
    )
    JSON_KEY_PATTERN = re.compile(
        r"json_extract\s*\(\s*METADATA\s*,\s*'\$\.(\w+)'\s*\)", re.IGNORECASE
    )

    @staticmethod
    def validate(sql: str) -> None:
        s = sql.strip().lower()
        if not s.startswith("select"):
            raise ValueError("Only SELECT queries allowed")
        if s.count(";") > 1:
            raise ValueError("Multiple SQL statements detected")
        if SQLValidator.FORBIDDEN.search(s):
            raise ValueError("Forbidden SQL keyword used")
        for key in SQLValidator.JSON_KEY_PATTERN.findall(s):
            if key not in ALL_JSON_KEYS:
                raise ValueError(f"Unknown JSON key: {key}")


def sanitize_sql(sql: str) -> str:
    sql = re.sub(r"```sql|```", "", sql, flags=re.IGNORECASE).strip()
    sql = sql.rstrip(";")
    if not re.search(r"\blimit\b", sql, re.IGNORECASE):
        sql += f" LIMIT {MAX_ROWS}"
    return sql


# ============================================================
# Structured output schema for the question+SQL batch
# ============================================================
class QAPair(BaseModel):
    question: str
    sql: str


class QABatch(BaseModel):
    pairs: list[QAPair]


# ============================================================
# Canonical SFT rendering (mirrors build_canonical_json_sft_dataset.render_canonical)
# ============================================================
def render_canonical(messages: list[dict[str, Any]]) -> str:
    rendered = [
        f"<|start|>system<|message|>{SFT_SYSTEM_PROMPT}<|end|>",
        f"<|start|>developer<|message|>{TOOLS_SPEC}<|end|>",
    ]
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            continue
        if role == "user":
            rendered.append(f'<|start|>user<|message|>{msg.get("content", "")}<|end|>')
        elif role == "assistant":
            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                fn = (tool_calls[0] or {}).get("function", {}) or {}
                call_obj = {
                    "name": str(fn.get("name", "")).strip(),
                    "arguments": fn.get("arguments", {}) or {},
                }
                rendered.append(
                    "<|start|>assistant<|channel|>final<|message|>"
                    f"{json.dumps(call_obj, sort_keys=True, ensure_ascii=False)}<|end|>"
                )
            else:
                rendered.append(
                    f'<|start|>assistant<|channel|>final<|message|>{msg.get("content", "")}<|end|>'
                )
        elif role == "tool":
            rendered.append(f'<|start|>tool<|message|>{msg.get("content", "")}<|end|>')
    return "\n".join(rendered)


# ============================================================
# Generator
# ============================================================
class CGSimDataGenerator:
    def __init__(
        self,
        db_path: str,
        generator_model: str = GENERATOR_MODEL,
        judge_model: str = JUDGE_MODEL,
        client: anthropic.Anthropic | None = None,
    ):
        self.db_path = db_path
        self.generator_model = generator_model
        self.judge_model = judge_model
        self.client = client or anthropic.Anthropic()
        # Cached system prefix: domain primer + schema (stable across all calls)
        self._system = [
            {
                "type": "text",
                "text": DOMAIN_PRIMER,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    # ---- DB execution (ground truth) -----------------------------------
    def _execute_sql(self, sql: str) -> tuple[list[str], list[tuple]]:
        SQLValidator.validate(sql)
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            cur = conn.cursor()
            cur.execute(sql)
            rows = cur.fetchmany(MAX_ROWS)
            cols = [d[0] for d in cur.description] if cur.description else []
            return cols, rows
        finally:
            conn.close()

    @staticmethod
    def _format_result(cols: list[str], rows: list[tuple]) -> str:
        payload = {"columns": cols, "rows": [list(r) for r in rows], "row_count": len(rows)}
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) > MAX_RESULT_CHARS:
            payload["rows"] = payload["rows"][:25]
            payload["truncated"] = True
            text = json.dumps(payload, ensure_ascii=False, default=str)
        return text

    # ---- Step 1: propose diverse {question, sql} pairs -----------------
    def propose_pairs(self, n: int) -> list[QAPair]:
        prompt = (
            f"Propose {n} DISTINCT analytical questions an operator might ask about "
            "this simulation, each paired with a single SQL SELECT against EVENTS that "
            "answers it. Cover a range: per-site performance, file transfer bottlenecks, "
            "disk I/O, job duration/retries, CPU/storage utilization, and cross-site "
            "comparisons. Vary aggregation (AVG, MAX, COUNT, GROUP BY). Every SQL must be "
            "valid SQLite using only the documented schema and json_extract for metadata."
        )
        # effort defaults to "high"; .parse() owns output_config.format, so don't
        # pass a separate output_config here (it would collide with the schema).
        resp = self.client.messages.parse(
            model=self.generator_model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=self._system,
            messages=[{"role": "user", "content": prompt}],
            output_format=QABatch,
        )
        batch = resp.parsed_output
        return batch.pairs if batch else []

    # ---- Step 2: explain real results ----------------------------------
    def explain(self, question: str, sql: str, result_text: str) -> str:
        prompt = (
            f"Question:\n{question}\n\n"
            f"SQL executed:\n{sql}\n\n"
            f"Real query results (JSON):\n{result_text}\n\n"
            "Write a concise, operational answer grounded ONLY in these results. "
            "Cite concrete numbers. Do not speculate beyond the data. No SQL talk."
        )
        resp = self.client.messages.create(
            model=self.generator_model,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=self._system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    # ---- Build one SFT row ---------------------------------------------
    def generate_example(self, pair: QAPair) -> dict[str, Any] | None:
        sql = sanitize_sql(pair.sql)
        try:
            cols, rows = self._execute_sql(sql)
        except (ValueError, sqlite3.Error) as e:
            print(f"  skip (SQL error): {e}", file=sys.stderr)
            return None
        if not rows:
            print("  skip (no rows)", file=sys.stderr)
            return None

        result_text = self._format_result(cols, rows)
        answer = self.explain(pair.question, sql, result_text)
        if not answer:
            return None

        messages = [
            {"role": "system", "content": SFT_SYSTEM_PROMPT},
            {"role": "user", "content": pair.question},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "query_simulation_db",
                            "arguments": {"sql": sql},
                        },
                    }
                ],
            },
            {"role": "tool", "content": result_text},
            {"role": "assistant", "content": answer},
        ]
        return {"messages": messages, "text": render_canonical(messages)}

    # ---- Run ------------------------------------------------------------
    def run(self, n: int, output_path: str) -> int:
        print(f"Proposing {n} question/SQL pairs with {self.generator_model}...")
        pairs = self.propose_pairs(n)
        print(f"Got {len(pairs)} pairs. Executing against {self.db_path} and explaining...")

        written = 0
        out = Path(output_path)
        with out.open("w") as f:
            for i, pair in enumerate(pairs, 1):
                print(f"[{i}/{len(pairs)}] {pair.question[:70]}")
                row = self.generate_example(pair)
                if row:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    written += 1
        print(f"\nWrote {written} examples to {out}")
        return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate AskPanDA SFT data from a CGSim DB")
    ap.add_argument("--db", required=True, help="Path to CGSim SQLite output DB")
    ap.add_argument("--n", type=int, default=50, help="Number of examples to attempt")
    ap.add_argument("--out", required=True, help="Output JSONL path")
    ap.add_argument("--generator-model", default=GENERATOR_MODEL)
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    args = ap.parse_args()

    if not Path(args.db).exists():
        sys.exit(f"DB not found: {args.db}")

    gen = CGSimDataGenerator(
        db_path=args.db,
        generator_model=args.generator_model,
        judge_model=args.judge_model,
    )
    gen.run(args.n, args.out)


if __name__ == "__main__":
    main()
