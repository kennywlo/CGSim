import sqlite3
import argparse
import os
import re
import json
import google.generativeai as genai

# ============================================================
# Configuration
# ============================================================
DB_PATH = "/Users/raekhan/CGSim/toy_data/toy_job.db"
TABLE = "EVENTS"
MAX_ROWS = 10000

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY environment variable not set")

genai.configure(api_key=GEMINI_API_KEY)
llm = genai.GenerativeModel("models/gemma-3-27b-it")

# ============================================================
# Canonical schema
# ============================================================
COLUMNS = {"_ID", "EVENT", "STATE", "STATUS", "JOB_ID", "TIME", "METADATA"}

EVENT_SCHEMA = {
    "JobAllocation": {
        "AllocationStart": ["status", "site", "host"],
        "AllocationFinished": [
            "status", "site", "host",
            "site_storage_util", "grid_storage_util",
            "site_cpu_util", "grid_cpu_util"
        ]
    },
    "JobExecution": {
        "Start": [
            "flops", "cores", "speed", "site", "host", "start_time",
            "site_cpu_util", "grid_cpu_util"
        ],
        "Finished": [
            "flops", "cores", "speed", "cost", "site", "host",
            "duration", "retries", "queue_time",
            "site_cpu_util", "grid_cpu_util"
        ]
    },
    "FileTransfer": {
        "Start": [
            "file", "size", "source_site", "destination_site",
            "bandwidth", "latency", "link_load",
            "site_storage_util", "grid_storage_util"
        ],
        "Finished": [
            "file", "size", "source_site", "destination_site",
            "duration", "bandwidth", "latency",
            "link_load", "site_storage_util", "grid_storage_util"
        ]
    },
    "FileRead": {
        "Start": ["file", "size", "site", "host", "disk", "disk_read_bw"],
        "Finished": ["file", "size", "site", "host", "disk",
                     "duration", "disk_read_bw"]
    },
    "FileWrite": {
        "Start": ["file", "size", "site", "host", "disk", "disk_write_bw",
                  "site_storage_util", "grid_storage_util"],
        "Finished": ["file", "size", "site", "host", "disk", "duration",
                     "disk_write_bw", "site_storage_util", "grid_storage_util"]
    }
}

ALL_JSON_KEYS = {
    key
    for states in EVENT_SCHEMA.values()
    for keys in states.values()
    for key in keys
}

# ============================================================
# Domain primer (UNCHANGED)
# ============================================================
DOMAIN_PRIMER = f"""
You are an expert in analyzing discrete-event simulation outputs produced by a
SimGrid-based workload simulator.

DATABASE SEMANTICS
- The EVENTS table is append-only.
- Each row is a point-in-time event observation.
- Event lifecycles are reconstructed using (EVENT, STATE, JOB_ID).
- TIME is simulation clock time (float).

EVENTS TABLE SCHEMA
CREATE TABLE EVENTS (
    _ID INTEGER PRIMARY KEY AUTOINCREMENT,   -- Unique internal event ID
    EVENT TEXT NOT NULL,                     -- Event type (e.g., JobAllocation)
    STATE TEXT NOT NULL,                     -- Event state (Start or Finished)
    STATUS TEXT NOT NULL,                    -- Job status at the event (e.g., pending, running)
    JOB_ID TEXT NOT NULL,                    -- Unique identifier of the job
    TIME FLOAT NOT NULL,                     -- Simulation clock time when event started
    METADATA TEXT                            -- JSON object with event-specific keys
);


EVENT TYPES
- JobAllocation  : job allocation phase
- JobExecution   : CPU execution
- FileTransfer   : network transfers
- FileRead       : disk read I/O
- FileWrite      : disk write I/O

STATE SEMANTICS
- Start / Finished mark the beginning and end of an activity.
- AllocationStart / AllocationFinished are specific job transfer phases.
- Always use Finished events for performance metrics.

METADATA
- METADATA is JSON with event-specific keys.
- Keys only exist if explicitly produced by the simulator.
- NEVER assume missing keys exist.

SITE INVOLVEMENT RULES
- For JobExecution, FileRead, FileWrite: check METADATA.site
- For FileTransfer: a site may be involved as:
    * Outgoing transfer: METADATA.source_site = <site>
    * Incoming transfer: METADATA.destination_site = <site>
- Summaries should separate transfers by direction (incoming vs outgoing)

AUTHORITATIVE EVENT → STATE → METADATA KEYS
{json.dumps(EVENT_SCHEMA, indent=2)}

METADATA KEY DESCRIPTIONS

JobAllocation:
  AllocationStart:
    status          : string, current job status (e.g., "pending", "running")
    site            : string, site where the job is allocated
    host            : string, host executing or receiving the job
  AllocationFinished:
    status          : string, job status at allocation completion
    site            : string, site where the job was sent for execution
    host            : string, host executing or receiving the job
    site_storage_util: string [0-1], fraction of storage used at the site
    grid_storage_util: string [0-1], fraction of storage used across the grid
    site_cpu_util   : string [0-1], CPU utilization at the site
    grid_cpu_util   : string [0-1], CPU utilization across the grid

JobExecution:
  Start:
    flops           : string, total floating-point operations required by the job
    cores           : string, number of CPU cores allocated
    speed           : string, host CPU speed in FLOPS per second
    site            : string, site executing the job
    host            : string, host executing the job
    start_time      : string, simulation time when execution begins
    site_cpu_util   : string [0-1], CPU utilization at the site at start
    grid_cpu_util   : string [0-1], CPU utilization across the grid at start
  Finished:
    flops           : string, total floating-point operations performed
    cores           : string, number of cores used
    speed           : string, host CPU speed
    cost            : string, cost of executing the job
    site            : string, site executing the job
    host            : string, host executing the job
    duration        : string, time it took to complete the execution
    retries         : string, number of retries for this job
    queue_time      : string, time spent waiting before execution
    site_cpu_util   : string, CPU utilization at finish
    grid_cpu_util   : string,  CPU utilization across the grid at finish

FileTransfer:
  Start:
    file            : string, filename being transferred
    size            : string, file size in bytes
    source_site     : string, site sending the file
    destination_site: string, site receiving the file
    bandwidth       : string, link bandwidth in bytes/sec
    latency         : string, network latency in seconds
    link_load       : string [0-1], current load on the link
    site_storage_util: string [0-1], storage utilization at the job site
    grid_storage_util: string [0-1], storage utilization across the grid
    direction        : string, "outgoing" if site = source, "incoming" if site = destination (can be inferred in summaries)
  Finished:
    file            : string, filename transferred
    size            : string, file size in bytes
    source_site     : string, site sending the file
    destination_site: string, site receiving the file
    duration        : string, time it took to complete the transfer
    bandwidth       : string, link bandwidth
    latency         : string, network latency
    link_load       : string, link utilization at transfer end
    site_storage_util: string, storage utilization at the job site
    grid_storage_util: string, storage utilization across the grid
    direction        : string, "outgoing" if site = source, "incoming" if site = destination (can be inferred in summaries)

FileRead:
  Start:
    file            : string, filename being read
    size            : string, file size in bytes
    site            : string, site performing the read
    host            : string, host performing the read
    disk            : string, disk identifier
    disk_read_bw    : string, disk read bandwidth in bytes/sec
  Finished:
    file            : string, filename read
    size            : string, file size
    site            : string, site performing the read
    host            : string, host performing the read
    disk            : string, disk identifier
    duration        : string, time it took to complete the read
    disk_read_bw    : string, disk read bandwidth

FileWrite:
  Start:
    file            : string, filename being written
    size            : int, file size in bytes
    site            : string, site performing the write
    host            : string, host performing the write
    disk            : string, disk identifier
    disk_write_bw   : float, disk write bandwidth in bytes/sec
    site_storage_util: float [0-1], storage utilization at the job site
    grid_storage_util: float [0-1], storage utilization across the grid
  Finished:
    file            : string, filename written
    size            : string, file size
    site            : string, site performing the write
    host            : string, host performing the write
    disk            : string, disk identifier
    duration        : string, time it took to complete the write
    disk_write_bw   : string, disk write bandwidth
    site_storage_util: string, storage utilization at the job site
    grid_storage_util: string, storage utilization across the grid

ANALYSIS PRINCIPLES
- Use STATE='Finished' for performance metrics (durations, cost, throughput).
- Use STATE='Start' for load-at-start analysis (timestamps only).
- For site summaries:
    * Include all JobExecution, FileRead, FileWrite events where METADATA.site = <site>.
    * Include all FileTransfer events where METADATA.source_site = <site> OR METADATA.destination_site = <site>.
- Aggregate by JOB_ID for lifecycle analysis.
- Aggregate by site, disk, or link for infrastructure analysis.

ABSOLUTE RULES
- NEVER invent columns or JSON keys.
- NEVER modify the database.
- NEVER use multiple SQL statements.
- ALWAYS include FileTransfer source and destination sites when summarizing a site.

MOST CRITICAL RULE:
- NEVER take the time specified in the "TIME" column as duration, the duration is ALWAYS stores in the metadata in the field "duration".
"""


# ============================================================
# Few-shot examples (UNCHANGED)
# ============================================================
FEW_SHOT_EXAMPLES = """
EXAMPLE 1
Question: What is the average job execution duration?

SQL:
SELECT
  AVG(json_extract(METADATA, '$.duration')) AS avg_execution_duration
FROM EVENTS
WHERE EVENT = 'JobExecution'
  AND STATE = 'Finished'
LIMIT 1;

Explanation:
This computes the average execution duration using only completed job executions.

---

EXAMPLE 2
Question: Which jobs had the most retries?

SQL:
SELECT
  JOB_ID,
  MAX(json_extract(METADATA, '$.retries')) AS retries
FROM EVENTS
WHERE EVENT = 'JobExecution'
  AND STATE = 'Finished'
GROUP BY JOB_ID
ORDER BY retries DESC
LIMIT 10;

Explanation:
Retry counts are recorded at execution completion. Grouping by JOB_ID reveals jobs
with repeated failures.

---

EXAMPLE 3
Question: How does bandwidth affect file transfer duration?

SQL:
SELECT
  json_extract(METADATA, '$.bandwidth') AS bandwidth,
  AVG(json_extract(METADATA, '$.duration')) AS avg_duration
FROM EVENTS
WHERE EVENT = 'FileTransfer'
  AND STATE = 'Finished'
GROUP BY bandwidth
ORDER BY bandwidth
LIMIT 20;

Explanation:
This correlates network bandwidth with transfer duration for completed transfers.
"""

# ============================================================
# SQL helpers (FIXED)
# ============================================================
def sanitize_sql(sql: str) -> str:
    sql = re.sub(r"```sql|```", "", sql, flags=re.IGNORECASE).strip()
    sql = sql.replace('"', "'")
    sql = sql.rstrip(";")

    lower_sql = sql.lower()

    # Find WHERE, ORDER BY, LIMIT positions
    where_match = re.search(r"\bwhere\b", lower_sql)
    order_match = re.search(r"\border by\b", lower_sql)
    limit_match = re.search(r"\blimit\b", lower_sql)

    # Insert json_valid(METADATA) safely
    if "json_extract" in lower_sql and "json_valid" not in lower_sql:
        if where_match:
            # Insert json_valid inside existing WHERE, before ORDER BY or LIMIT
            insert_pos = order_match.start() if order_match else limit_match.start() if limit_match else len(sql)
            sql = sql[:insert_pos] + " AND json_valid(METADATA)" + sql[insert_pos:]
        else:
            # No WHERE → insert before ORDER BY or LIMIT
            insert_pos = order_match.start() if order_match else limit_match.start() if limit_match else len(sql)
            sql = sql[:insert_pos] + " WHERE json_valid(METADATA)" + sql[insert_pos:]

    # Ensure LIMIT at the very end
    if not limit_match:
        sql += f" LIMIT {MAX_ROWS}"

    return sql + ";"



# ============================================================
# SQL validator
# ============================================================
class SQLValidator:

    FORBIDDEN = re.compile(
        r"\b(insert|update|delete|drop|alter|create|pragma|attach|detach)\b",
        re.IGNORECASE
    )

    JSON_KEY_PATTERN = re.compile(
        r"json_extract\s*\(\s*METADATA\s*,\s*'\$\.(\w+)'\s*\)",
        re.IGNORECASE
    )

    @staticmethod
    def validate(sql: str):
        s = sql.lower()

        if not s.startswith("select"):
            raise ValueError("Only SELECT queries allowed")

        if s.count(";") > 1:
            raise ValueError("Multiple SQL statements detected")

        if SQLValidator.FORBIDDEN.search(s):
            raise ValueError("Forbidden SQL keyword used")

        for key in SQLValidator.JSON_KEY_PATTERN.findall(s):
            if key not in ALL_JSON_KEYS:
                raise ValueError(f"Unknown JSON key: {key}")

# ============================================================
# Analysis client
# ============================================================
class SimulationAnalysisClient:

    def generate_sql(self, question: str) -> str:
        prompt = f"""
{DOMAIN_PRIMER}

{FEW_SHOT_EXAMPLES}

Question:
\"\"\"{question}\"\"\"

Output ONLY raw SQL.
"""
        return llm.generate_content(prompt).text.strip()

    def execute(self, sql: str):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        conn.close()
        return cols, rows

    def explain(self, question, sql, cols, rows):
        # Flatten rows into readable table or list
        row_text = "\n".join([", ".join(str(v) for v in r) for r in rows[:MAX_ROWS]])
        
        prompt = f"""
            You are an expert in SimGrid simulation analysis.

            Question:
            {question}

            The database query has already been executed. Here are the results:

            Columns:
            {cols}

            Rows (first {min(len(rows), MAX_ROWS)}):
            {row_text}

            Provide a clear, concise answer to the question based on these results.
            Do NOT explain the SQL or database structure.
            Return the answer as a human-readable summary.
            """
        return llm.generate_content(prompt).text.strip()


# ============================================================
# Workflow
# ============================================================
def run(question: str):
    client = SimulationAnalysisClient()

    raw_sql = client.generate_sql(question)
    sql = sanitize_sql(raw_sql)
    SQLValidator.validate(sql)

    print("\n=== SQL ===")
    print(sql)

    cols, rows = client.execute(sql)
    explanation = client.explain(question, sql, cols, rows)

    print("\n=== Answer ===")
    print(explanation)

# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--question", required=True)
    args = parser.parse_args()
    run(args.question)
