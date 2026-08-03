# CGSim + LLM-Interface

SimGrid-based grid workload simulator (C++ core + dispatcher plugins) feeding the
AskPanDA LLM training pipeline (`LLM-Interface/`). Current focus: Rubin DRP
simulation per `LLM-Interface/rubin_campaign_schema_v0.2.md`.

## Environments

- **DGX Spark (local dev)**: repo at `~/llm-apps/app/CGSim`; CGSim installed at
  `~/llm-apps/app/CGSim-install` (bin/cg-sim), SimGrid at
  `~/llm-apps/app/simgrid-install`. Run with both `lib/` dirs on
  `LD_LIBRARY_PATH`. Local LLM datagen via Ollama (`OLLAMA_HOST=localhost:11434`,
  gpt-oss:120b) — no SLAC tunnel needed.
- **Perlmutter (production runs)**: repo at `/global/homes/k/kennylo/llm-apps/app/CGSim`.
  Runs go through `LLM-Interface/Makefile` sbatch targets (`datagen-submit`,
  `grpo-submit`) → `datagen_run.sh` (opens SOCKS5 tunnel to SLAC AI gateway;
  needs `SLAC_AI_KEY` and `~/.ssh/id_slac`). SQLite output files must live on
  `/tmp`, not Lustre (WAL limitation) — see `*_perlmutter.json` configs.
  Scratch/logs: `/pscratch/sd/k/kennylo/cgsim-outputs/`.

## Rubin plugin work (active)

- `dispatch_plugins/rubin-plugin/` — DAG-gated dispatcher scaffold. **Read its
  README first**: build recipe, verified core constraints (one-shot getWorkload,
  t=0 file resolution, retries pollution, pointer-ordered JobQueue), and
  TODO(Raees) markers. Raees owns the real plugin (queue routing, failure model,
  PanDA-schema output); the scaffold is the agreed starting point.
- `rubin-data/generate_campaign.py` — synthetic schema-v0.2 instance generator
  (`campaign-demo/`). `rubin-data/rubin_dag_config.json` runs it (absolute local
  paths — make a `_perlmutter` variant, don't edit in place).
- `rubin-data/verify_dag_order.py <events.db>` — proves DAG ordering held in a
  run's EVENTS db. Run it after any plugin or core change.
- Task list: **`LLM-Interface/TODO.md`** (top section = Perlmutter scaffold-level
  run checklist). Open design questions for Raees:
  `LLM-Interface/docs/rubin_plugin_questions_raees.md`.

## Data sources

- `rubinobs-opensearch` (USDF): kubectl context `usdf-opensearch`, then
  `kubectl port-forward svc/rubinobs-opensearch-coordinator 9200:9200 -n opensearch-system`;
  admin creds in secret `usdf-opensearch-admin-pw-*`. Key indices:
  `panda_prod_test-YYYY-MM` (output-schema target), `rucio-events-*`.
  Node cert expires 2027-01-22. Reference dump:
  `LLM-Interface/opensearch_reference/`.
- kubectl OIDC tokens expire and can't auto-refresh — if every context fails
  with "No valid id-token", ask Kenny to re-auth via the browser flow.

## Conventions

- Plugin code style follows `simple-test-plugin` (caps class names, minimal
  comments). `json/` is vendored nlohmann — include via
  `../../json/single_include`.
- EVENTS db schema (`EVENT/STATE/STATUS/JOB_ID/TIME/METADATA`) is consumed by
  `LLM-Interface/clients/CGSimDataGenerator.py` — don't change it without
  checking downstream.
