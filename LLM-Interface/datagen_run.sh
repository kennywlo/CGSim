#!/bin/bash
# Run one CGSim scenario end-to-end: cg-sim → copy DB → CGSimDataGenerator.
#
# Usage (called by Makefile / sbatch — not normally invoked directly):
#   datagen_run.sh <scenario_name> <config_json> <output_db> \
#                  <n_examples> <outputs_dir> <cgsim_bin> <python> <clients_dir>

set -euo pipefail

SCENARIO=$1
CONFIG=$2
OUTPUT_DB=$3        # /tmp/rubin_<scenario>.db  (written by cg-sim)
N=$4
OUTPUTS_DIR=$5
CGSIM_BIN=$6
PYTHON=$7
CLIENTS_DIR=$8
GENERATOR_MODEL=${9:-}   # optional; uses CGSimDataGenerator default if empty
JUDGE_MODEL=${10:-}      # optional; uses CGSimDataGenerator default if empty

LOCAL_LIB="${HOME}/llm-apps/app/local/lib"
export LD_LIBRARY_PATH="${LOCAL_LIB}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

SLAC_HOST="${SLAC_HOST:-kennylo@s3dflogin.slac.stanford.edu}"
SLAC_SSH_KEY="${SLAC_SSH_KEY:-${HOME}/.ssh/id_slac}"
# Use job-ID-derived port so co-scheduled jobs on the same node don't collide.
PROXY_PORT="${SLAC_PROXY_PORT:-$((20000 + (${SLURM_JOB_ID:-$$} % 30000)))}"

PERSISTENT_DB="${OUTPUTS_DIR}/rubin_${SCENARIO}.db"
# Stable per-scenario path so restarts can resume appending; renamed to timestamped
# name on completion so merge.py's "most recent" logic still works.
SFT_WORK="${OUTPUTS_DIR}/sft_${SCENARIO}.work.jsonl"
SFT_OUT="${OUTPUTS_DIR}/sft_${SCENARIO}_$(date +%Y%m%d_%H%M%S).jsonl"

# ---- open SOCKS5 tunnel to SLAC AI gateway --------------------------------
tunnel_cleanup() {
    [[ -n "${TUNNEL_PID:-}" ]] && kill "${TUNNEL_PID}" 2>/dev/null || true
}
trap tunnel_cleanup EXIT

echo "[$(date +%T)] opening SOCKS5 tunnel → ${SLAC_HOST}:${PROXY_PORT}"
ssh -D "${PROXY_PORT}" -N -f \
    -i "${SLAC_SSH_KEY}" \
    -o BatchMode=yes \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o StrictHostKeyChecking=accept-new \
    "${SLAC_HOST}"
TUNNEL_PID=$(pgrep -n -f "ssh -D ${PROXY_PORT}.*${SLAC_HOST##*@}")
echo "[$(date +%T)] tunnel up (pid=${TUNNEL_PID})"

export SLAC_AI_KEY="${SLAC_AI_KEY}"       # pass through from sbatch --export=ALL
export SLAC_PROXY_PORT="${PROXY_PORT}"    # let CGSimDataGenerator use same port

echo "[$(date +%T)] scenario=${SCENARIO}  config=${CONFIG}"
echo "[$(date +%T)] running cg-sim..."
"${CGSIM_BIN}" -c "${CONFIG}"

echo "[$(date +%T)] copying DB to ${PERSISTENT_DB}"
mkdir -p "${OUTPUTS_DIR}"
cp "${OUTPUT_DB}" "${PERSISTENT_DB}"

echo "[$(date +%T)] running CGSimDataGenerator (n=${N})..."
"${PYTHON}" "${CLIENTS_DIR}/CGSimDataGenerator.py" \
    --db "${PERSISTENT_DB}" \
    --n "${N}" \
    --out "${SFT_WORK}" \
    ${GENERATOR_MODEL:+--generator-model "$GENERATOR_MODEL"} \
    ${JUDGE_MODEL:+--judge-model "$JUDGE_MODEL"}

# Rename to timestamped final name so merge.py's "latest file" logic works correctly.
mv "${SFT_WORK}" "${SFT_OUT}"
echo "[$(date +%T)] done → ${SFT_OUT}"
# tunnel killed by trap on EXIT
