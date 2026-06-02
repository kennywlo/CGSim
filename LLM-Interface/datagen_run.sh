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

LOCAL_LIB="${HOME}/llm-apps/app/local/lib"
export LD_LIBRARY_PATH="${LOCAL_LIB}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

PERSISTENT_DB="${OUTPUTS_DIR}/rubin_${SCENARIO}.db"
SFT_OUT="${OUTPUTS_DIR}/sft_${SCENARIO}_$(date +%Y%m%d_%H%M%S).jsonl"

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
    --out "${SFT_OUT}"

echo "[$(date +%T)] done → ${SFT_OUT}"
