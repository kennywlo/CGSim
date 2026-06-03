#!/bin/bash
#SBATCH --job-name=ollama-server
#SBATCH --account=m2616_g
#SBATCH --qos=regular
#SBATCH --constraint=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus=4
#SBATCH --cpus-per-task=64
#SBATCH --mem=240G
#SBATCH --time=04:00:00
#SBATCH --image=ollama/ollama:latest
#SBATCH --output=/pscratch/sd/k/kennylo/cgsim-outputs/logs/ollama-server-%j.log
#SBATCH --error=/pscratch/sd/k/kennylo/cgsim-outputs/logs/ollama-server-%j.log

set -euo pipefail

OLLAMA_MODELS_DIR="${OLLAMA_MODELS_DIR:-/pscratch/sd/k/kennylo/ollama/models}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gpt-oss:120b}"
SERVER_FILE="${SERVER_FILE:-/pscratch/sd/k/kennylo/cgsim-outputs/ollama_server.txt}"
PORT=11434

mkdir -p "$OLLAMA_MODELS_DIR" "$(dirname "$SERVER_FILE")" \
  /pscratch/sd/k/kennylo/cgsim-outputs/logs

echo "[$(date +%T)] node=$(hostname) job=$SLURM_JOB_ID"
echo "[$(date +%T)] model=$OLLAMA_MODEL  models_dir=$OLLAMA_MODELS_DIR"

cleanup() {
    echo "[$(date +%T)] shutting down — removing server file"
    rm -f "$SERVER_FILE"
}
trap cleanup EXIT

# Start Ollama server (we're inside the container via #SBATCH --image)
SHIFTER="shifter --image=ollama/ollama:latest"

OLLAMA_MODELS="$OLLAMA_MODELS_DIR" \
OLLAMA_HOST="0.0.0.0:${PORT}" \
OLLAMA_GPU_LAYERS=-1 \
OLLAMA_CONTEXT_LENGTH=65536 \
$SHIFTER ollama serve &
OLLAMA_PID=$!

# Wait up to 2 min for server to be ready
echo "[$(date +%T)] waiting for Ollama..."
for i in $(seq 1 60); do
    if curl -sf "http://localhost:${PORT}/api/tags" > /dev/null 2>&1; then
        echo "[$(date +%T)] Ollama ready (${i}s)"
        break
    fi
    sleep 2
    if [[ $i -eq 60 ]]; then
        echo "[$(date +%T)] ERROR: Ollama did not start in 120s" >&2
        exit 1
    fi
done

# Pull model if not already cached
if ! OLLAMA_MODELS="$OLLAMA_MODELS_DIR" $SHIFTER ollama list 2>/dev/null | grep -q "$(echo "$OLLAMA_MODEL" | cut -d: -f1)"; then
    echo "[$(date +%T)] pulling $OLLAMA_MODEL..."
    OLLAMA_MODELS="$OLLAMA_MODELS_DIR" OLLAMA_HOST="localhost:${PORT}" \
    $SHIFTER ollama pull "$OLLAMA_MODEL"
    echo "[$(date +%T)] pull complete"
else
    echo "[$(date +%T)] $OLLAMA_MODEL already cached"
fi

# Advertise address for datagen jobs
echo "http://$(hostname):${PORT}" > "$SERVER_FILE"
echo "[$(date +%T)] server ready at http://$(hostname):${PORT}"

wait $OLLAMA_PID
