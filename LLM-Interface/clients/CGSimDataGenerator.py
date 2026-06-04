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
uses the OpenAI-compatible client (targeting SLAC AI gateway or direct Anthropic),
and grounds every answer in executed SQL.

Usage:
  python CGSimDataGenerator.py --db /tmp/rubin_output.db --n 50 \
      --out askpanda_sft_cgsim_$(date +%Y%m%d).jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import httpx
import openai
from pydantic import BaseModel

# ============================================================
# Models (override on the CLI / constructor to pin a version)
# ============================================================
# Pick a sensible default at import time: Ollama when OLLAMA_HOST is set,
# otherwise the Sonnet model name that _resolve_model() will prepend with
# the SLAC gateway prefix (us.anthropic.) before use.
def _default_model() -> str:
    return "gpt-oss:120b" if os.environ.get("OLLAMA_HOST") else "claude-sonnet-4-6"

GENERATOR_MODEL = _default_model()
JUDGE_MODEL     = _default_model()

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
- size, bandwidth, and disk_read/write_bw values are in bytes or bytes/s. Do NOT
  propose questions that ask for MiB, GiB, or MiB/s — ask for bytes or seconds
  instead, or compute the ratio directly in raw units. This avoids unit-conversion
  errors in the SQL (wrong divisor: 1024 vs 1048576).
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


def sanitize_question(q: str) -> str:
    """Strip emoji/numbering artifacts left by the proposer model."""
    # Keycap sequences: digit + optional variation selector + combining enclosing keycap
    q = re.sub(r"\d️?⃣\s*", "", q)
    # Remaining emoji (misc symbols, pictographs, transport, variation selectors, etc.)
    q = re.sub(
        r"[\U0001F300-\U0001F9FF☀-➿︀-️⃐-⃿]+",
        "",
        q,
        flags=re.UNICODE,
    )
    return " ".join(q.split())


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


class JudgeVerdict(BaseModel):
    keep: bool
    reason: str


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
# OpenAI-compatible client — SLAC AI gateway or direct Anthropic
# ============================================================
_SLAC_BASE_URL      = "https://ai-api.slac.stanford.edu/v1"
_SLAC_MODEL_PREFIX  = "us.anthropic."


def _slac_proxy() -> str:
    port = os.environ.get("SLAC_PROXY_PORT", "1080")
    return f"socks5h://localhost:{port}"


def _resolve_model(name: str) -> str:
    """Prepend SLAC model prefix when using SLAC AI gateway; skip for Ollama."""
    if os.environ.get("OLLAMA_HOST"):
        return name
    if os.environ.get("SLAC_AI_KEY"):
        return _SLAC_MODEL_PREFIX + name
    return name


def _make_client() -> openai.OpenAI:
    # Local Ollama server (highest priority — no gateway, no tunnel)
    ollama_host = os.environ.get("OLLAMA_HOST")
    if ollama_host:
        return openai.OpenAI(
            api_key="ollama",
            base_url=f"{ollama_host.rstrip('/')}/v1",
        )
    slac_key = os.environ.get("SLAC_AI_KEY")
    if slac_key:
        return openai.OpenAI(
            api_key=slac_key,
            base_url=_SLAC_BASE_URL,
            http_client=httpx.Client(proxy=_slac_proxy()),
        )
    # Direct Anthropic via openai-compatible shim
    return openai.OpenAI(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        base_url="https://api.anthropic.com/v1/",
        default_headers={"anthropic-version": "2023-06-01"},
    )


# ============================================================
# Generator
# ============================================================
class CGSimDataGenerator:
    def __init__(
        self,
        db_path: str,
        generator_model: str = GENERATOR_MODEL,
        judge_model: str = JUDGE_MODEL,
        use_judge: bool = True,
        client: openai.OpenAI | None = None,
    ):
        self.db_path = db_path
        self.generator_model = _resolve_model(generator_model)
        self.judge_model = _resolve_model(judge_model)
        self.use_judge = use_judge
        self.client = client or _make_client()
        print(f"  generator: {self.generator_model}  judge: {self.judge_model}")

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
    def _propose_batch(self, n: int, seen_questions: list[str] | None = None) -> list[QAPair]:
        """Request up to n pairs in a single API call."""
        exclusion = ""
        if seen_questions:
            # Cap exclusion list to last 30 to keep prompt size bounded
            listed = "\n".join(f"- {q}" for q in seen_questions[-30:])
            exclusion = (
                f"\n\nDo NOT propose any of these already-covered questions:\n{listed}\n"
                "Generate entirely new questions that explore different aspects of the data."
            )
        prompt = (
            f"Propose {n} DISTINCT analytical questions an operator might ask about "
            "this simulation, each paired with a single SQL SELECT against EVENTS that "
            "answers it. Cover a range: per-site performance, file transfer bottlenecks, "
            "disk I/O, job duration/retries, CPU/storage utilization, and cross-site "
            "comparisons. Vary aggregation (AVG, MAX, COUNT, GROUP BY). Every SQL must be "
            "valid SQLite using only the documented schema and json_extract for metadata."
            f"{exclusion}"
        )
        # 8000 cap: leaves ~6000 for Q+SQL output after ~2000 reasoning tokens,
        # enough for 10-15 pairs at ~400 tokens each.
        resp = self.client.beta.chat.completions.parse(
            model=self.generator_model,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": DOMAIN_PRIMER},
                {"role": "user",   "content": prompt},
            ],
            response_format=QABatch,
        )
        batch = resp.choices[0].message.parsed
        return batch.pairs if batch else []

    @staticmethod
    def _load_checkpoint(ckpt_path: str) -> list[QAPair]:
        pairs = []
        with open(ckpt_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    pairs.append(QAPair(question=d["question"], sql=d["sql"]))
        return pairs

    def propose_pairs(
        self,
        n: int,
        batch_size: int = 5,
        checkpoint_path: str | None = None,
        preloaded: list[QAPair] | None = None,
    ) -> list[QAPair]:
        """Propose n pairs total, resuming from preloaded if provided.

        Saves each batch to checkpoint_path so restarts can skip re-proposing.
        """
        pairs: list[QAPair] = list(preloaded or [])
        seen_questions: list[str] = [p.question for p in pairs]
        remaining = n - len(pairs)
        stall = 0  # consecutive batches that yielded no novel questions
        token_limit_hits = 0  # consecutive token-limit failures at minimum batch size
        current_batch = batch_size
        while remaining > 0:
            try:
                got = self._propose_batch(min(remaining, current_batch), seen_questions=seen_questions)
                current_batch = batch_size  # reset after success
                token_limit_hits = 0
            except Exception as e:
                if "length" in str(e).lower() or "LengthFinishReason" in type(e).__name__:
                    if current_batch <= 1:
                        token_limit_hits += 1
                        print(f"  [warn] batch_size=1 still hits limit ({token_limit_hits}/5) — skipping batch", flush=True)
                        if token_limit_hits >= 5:
                            print("  [warn] too many token-limit failures at batch_size=1 — stopping proposals early", flush=True)
                            break
                        current_batch = batch_size  # reset and try full size again next round
                        continue
                    current_batch = max(1, current_batch // 2)
                    print(f"  [warn] token limit hit, retrying with batch_size={current_batch}", flush=True)
                    continue
                if isinstance(e, TypeError) and "NoneType" in str(e):
                    # Gateway returned malformed response (choices=None) — transient outage, retry
                    print(f"  [warn] gateway returned null response, retrying in 15s...", flush=True)
                    import time; time.sleep(15)
                    continue
                raise
            novel = [p for p in got if p.question not in seen_questions]
            pairs.extend(novel)
            seen_questions.extend(p.question for p in novel)
            remaining -= len(novel)
            if checkpoint_path and novel:
                with open(checkpoint_path, "a") as f:
                    for p in novel:
                        f.write(json.dumps({"question": p.question, "sql": p.sql}) + "\n")
            if not got or not novel:
                stall += 1
                if stall >= 3:  # schema diversity exhausted — stop trying
                    break
            else:
                stall = 0
        return pairs

    # ---- Step 2: explain real results ----------------------------------
    def explain(self, question: str, sql: str, result_text: str) -> str:
        prompt = (
            f"Question:\n{question}\n\n"
            f"SQL executed:\n{sql}\n\n"
            f"Real query results (JSON):\n{result_text}\n\n"
            "Write a concise, operational answer grounded ONLY in these results. "
            "Rules:\n"
            "- Every number you state MUST come directly from the query results above. "
            "Do NOT compute aggregates in your head — if the SQL already computed a sum "
            "or average, read it from the results; do NOT re-sum rows yourself.\n"
            "- When counting rows or items, count them from the data, then state the count. "
            "Do not guess or estimate row counts.\n"
            "- Use consistent units throughout (pick one: MB or MiB, not both).\n"
            "- No SQL jargon, no speculation beyond the data."
        )
        resp = self.client.chat.completions.create(
            model=self.generator_model,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": DOMAIN_PRIMER},
                {"role": "user",   "content": prompt},
            ],
        )
        # LiteLLM-based gateways (e.g. SLAC) return errors as choices=None + resp.error
        # instead of raising an exception.
        if err := getattr(resp, "error", None):
            raise RuntimeError(f"API error: {err.get('message', err)}")
        if not resp.choices or resp.choices[0].message is None:
            return ""
        choice = resp.choices[0]
        content = choice.message.content
        if not content:
            reason = getattr(choice, "finish_reason", "unknown")
            print(f"  skip (explain): empty response (finish_reason={reason})", file=sys.stderr)
            return ""
        return content.strip()

    # ---- Step 3: judge quality ------------------------------------------
    def judge_example(self, question: str, sql: str, result_text: str, answer: str) -> JudgeVerdict:
        prompt = (
            "You are a quality-filter for an SFT dataset that teaches a model to answer "
            "ATLAS Grid computing questions by querying a simulation database.\n\n"
            "Evaluate the following example on ALL six criteria:\n\n"
            "1. QUESTION: Non-trivial operational question (not just a bare row count).\n\n"
            "2. SQL: Uses only documented EVENTS columns and json_extract keys; no hallucinated "
            "schema. The SQL must correctly answer the question AS LITERALLY STATED — do NOT "
            "reject because a more comprehensive query could exist. If the question asks about "
            "source sites only, a query that filters on source_site is correct even if it omits "
            "destination_site. Pass if the query is a valid, reasonable interpretation.\n\n"
            "3. GROUNDING: Every number in the answer must be derivable from the query results. "
            "Allow ≤5% relative error on derived figures (ratios, percentages, averages). "
            "Reject only when a figure is clearly wrong or unrelated to the actual results. "
            "NOTE: numeric values in the DB are raw simulation units (bytes, seconds, etc.) — "
            "do not penalise the answer for not labelling units if the question did not specify "
            "them, and do not reject unit-label choices (MB vs MiB, bps vs bytes/s) unless the "
            "numeric conversion itself is wrong by more than 5%.\n\n"
            "4. ANSWER QUALITY: Clear, concise, operationally useful; no SQL jargon. Minor "
            "self-corrections are fine as long as the final stated answer is correct.\n"
            "5. SELF-CONSISTENCY: If the query returned rows but the answer declares the "
            "results invalid, meaningless, or uninterpretable — reject. An answer that "
            "explains a null/empty result is fine; an answer that reports numbers while "
            "calling them wrong is not.\n\n"
            "6. INFORMATIVE RESULT: The query result must contain meaningful variation or "
            "non-trivial values. Reject if every numeric value in the result is identical "
            "(e.g. all 0.0, all the same constant) or if the answer's main finding is that "
            "all measured metrics are zero or uniform across all rows. A result showing all "
            "jobs with status 'finished' is acceptable; a result where every metric value is "
            "exactly 0.0 or identical across every row is not informative — reject it.\n\n"
            f"Question:\n{question}\n\n"
            f"SQL:\n{sql}\n\n"
            f"Query results (JSON):\n{result_text}\n\n"
            f"Answer:\n{answer}\n\n"
            "Set keep=true only if ALL six criteria pass. "
            "Set keep=false and state which criterion failed and why in ≤40 words."
        )
        resp = self.client.beta.chat.completions.parse(
            model=self.judge_model,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": DOMAIN_PRIMER},
                {"role": "user",   "content": prompt},
            ],
            response_format=JudgeVerdict,
        )
        return resp.choices[0].message.parsed or JudgeVerdict(keep=False, reason="no verdict returned")

    # ---- Build one SFT row ---------------------------------------------
    def generate_example(self, pair: QAPair) -> dict[str, Any] | None:
        question = sanitize_question(pair.question)
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
        try:
            answer = self.explain(question, sql, result_text)
        except Exception as e:
            print(f"  skip (explain error): {e}", file=sys.stderr)
            return None
        if not answer:
            print("  skip (explain): empty response", file=sys.stderr)
            return None

        if self.use_judge:
            verdict = self.judge_example(question, sql, result_text, answer)
            if not verdict.keep:
                print(f"  skip (judge): {verdict.reason}", file=sys.stderr)
                return None

        messages = [
            {"role": "system", "content": SFT_SYSTEM_PROMPT},
            {"role": "user", "content": question},
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
        ckpt_path = str(Path(self.db_path).parent / (Path(self.db_path).stem + ".ckpt.jsonl"))

        # Resume from checkpoint if one exists from a prior interrupted run.
        preloaded: list[QAPair] = []
        if Path(ckpt_path).exists():
            preloaded = self._load_checkpoint(ckpt_path)
            print(f"[checkpoint] loaded {len(preloaded)} pairs from {ckpt_path}", flush=True)

        if len(preloaded) >= n:
            pairs = preloaded[:n]
            print(f"[checkpoint] proposal complete ({len(pairs)} pairs) — skipping proposer", flush=True)
        else:
            need = n - len(preloaded)
            print(
                f"Proposing {need} more question/SQL pairs with {self.generator_model}"
                + (f" ({len(preloaded)} already checkpointed)" if preloaded else "") + "...",
                flush=True,
            )
            pairs = self.propose_pairs(n, checkpoint_path=ckpt_path, preloaded=preloaded)

        # Skip pairs already written in a previous (partial) run.
        out = Path(output_path)
        done_questions: set[str] = set()
        if out.exists() and out.stat().st_size > 0:
            for line in out.open():
                line = line.strip()
                if not line:
                    continue
                ex = json.loads(line)
                for m in ex.get("messages", []):
                    if m.get("role") == "user" and isinstance(m.get("content"), str):
                        done_questions.add(m["content"])
                        break
            if done_questions:
                print(f"[checkpoint] skipping {len(done_questions)} already-written pairs", flush=True)

        pending = [p for p in pairs if p.question not in done_questions]
        print(f"Got {len(pairs)} pairs total; {len(pending)} to process. Executing and explaining...", flush=True)

        written = 0
        with out.open("a") as f:
            for i, pair in enumerate(pending, 1):
                print(f"[{i}/{len(pending)}] {pair.question[:70]}")
                row = self.generate_example(pair)
                if row:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    written += 1

        # Clean up checkpoint only after a full successful run.
        if Path(ckpt_path).exists():
            Path(ckpt_path).unlink()
            print(f"[checkpoint] removed {ckpt_path}", flush=True)

        print(f"\nWrote {written} examples to {out}")
        return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate AskPanDA SFT data from a CGSim DB")
    ap.add_argument("--db", required=True, help="Path to CGSim SQLite output DB")
    ap.add_argument("--n", type=int, default=50, help="Number of examples to attempt")
    ap.add_argument("--out", required=True, help="Output JSONL path")
    ap.add_argument("--generator-model", default=GENERATOR_MODEL)
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    ap.add_argument("--no-judge", action="store_true", help="Disable judge quality filter")
    args = ap.parse_args()

    if not Path(args.db).exists():
        sys.exit(f"DB not found: {args.db}")

    gen = CGSimDataGenerator(
        db_path=args.db,
        generator_model=args.generator_model,
        judge_model=args.judge_model,
        use_judge=not args.no_judge,
    )
    gen.run(args.n, args.out)


if __name__ == "__main__":
    main()
