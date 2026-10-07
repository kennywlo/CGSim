#!/bin/bash
# Like datagen_run.sh but uses a shared Ollama server instead of SLAC AI gateway.
# The Ollama server job must be running first; it writes its address to SERVER_FILE.
#
# Usage (called by Makefile / sbatch):
#   datagen_run_ollama.sh <scenario_name> <config_json> <output_db> \
#                         <n_examples> <outputs_dir> <cgsim_bin> <python> <clients_dir>

set -euo pipefail

SCENARIO=$1
CONFIG=$2
OUTPUT_DB=$3
N=$4
OUTPUTS_DIR=$5
CGSIM_BIN=$6
PYTHON=$7
CLIENTS_DIR=$8

LOCAL_LIB="${HOME}/llm-apps/app/local/lib"
export LD_LIBRARY_PATH="${LOCAL_LIB}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

SERVER_FILE="${SERVER_FILE:-${OUTPUTS_DIR}/ollama_server.txt}"
PERSISTENT_DB="${OUTPUTS_DIR}/rubin_${SCENARIO}.db"
SFT_WORK="${OUTPUTS_DIR}/sft_${SCENARIO}.work.jsonl"
SFT_OUT="${OUTPUTS_DIR}/sft_${SCENARIO}_$(date +%Y%m%d_%H%M%S).jsonl"

# Wait for Ollama server to advertise itself (up to 60 min)
echo "[$(date +%T)] waiting for Ollama server at ${SERVER_FILE}..."
for i in $(seq 1 720); do
    if [[ -f "$SERVER_FILE" ]]; then
        OLLAMA_HOST=$(cat "$SERVER_FILE")
        echo "[$(date +%T)] found Ollama server: $OLLAMA_HOST"
        break
    fi
    sleep 5
done

if [[ -z "${OLLAMA_HOST:-}" ]]; then
    echo "[$(date +%T)] ERROR: Ollama server not ready after 60 min" >&2
    exit 1
fi

# Verify server is reachable
if ! curl -sf "${OLLAMA_HOST}/api/tags" > /dev/null 2>&1; then
    echo "[$(date +%T)] ERROR: Ollama server at $OLLAMA_HOST is not responding" >&2
    exit 1
fi

export OLLAMA_HOST

echo "[$(date +%T)] scenario=${SCENARIO}  config=${CONFIG}"
echo "[$(date +%T)] running cg-sim..."
"${CGSIM_BIN}" -c "${CONFIG}"

echo "[$(date +%T)] copying DB to ${PERSISTENT_DB}"
mkdir -p "${OUTPUTS_DIR}"
cp "${OUTPUT_DB}" "${PERSISTENT_DB}"

echo "[$(date +%T)] running CGSimDataGenerator (n=${N}, ollama=${OLLAMA_HOST})..."
"${PYTHON}" "${CLIENTS_DIR}/CGSimDataGenerator.py" \
    --db "${PERSISTENT_DB}" \
    --n "${N}" \
    --out "${SFT_WORK}"

mv "${SFT_WORK}" "${SFT_OUT}"
echo "[$(date +%T)] done → ${SFT_OUT}"
