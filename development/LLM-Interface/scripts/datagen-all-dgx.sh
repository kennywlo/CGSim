#!/usr/bin/env bash
# Run a full datagen round on DGX Spark against the SLAC AI gateway, unattended.
#
# Opens a key-based SOCKS5 tunnel to SLAC (no MFA; same mechanism as datagen_run.sh),
# runs every scenario in parallel via datagen_local.py, then checks DAG order and
# merges with cleaning. The tunnel is closed on exit.
#
# Usage:
#   scripts/datagen-all-dgx.sh                 # fresh round, all scenarios
#   SCENARIOS="baseline high_load" N=50 scripts/datagen-all-dgx.sh
#   OUTPUTS_DIR=<existing round dir> scripts/datagen-all-dgx.sh   # resume
#   CHECK_ONLY=1 scripts/datagen-all-dgx.sh    # verify tunnel + gateway, then exit
#
# Env overrides: OUTPUTS_DIR, N, SCENARIOS, GENERATOR_MODEL, JUDGE_MODEL, PYTHON,
#                SLAC_HOST, SLAC_SSH_KEY, SLAC_PROXY_PORT
# SLAC_AI_KEY is taken from the environment, else from ~/.bash_aliases.
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/dgx-env.sh"
LLM_DIR="$(cd "${script_dir}/.." && pwd)"
RUBIN_DIR="${CGSIM_SOURCE_ROOT}/rubin-data"
MANIFEST="${RUBIN_DIR}/scenarios/manifest.json"

PYTHON="${PYTHON:-${HOME}/miniconda3/envs/cgsim-rubin/bin/python3}"
N="${N:-100}"
GENERATOR_MODEL="${GENERATOR_MODEL:-claude-sonnet-4-6}"
JUDGE_MODEL="${JUDGE_MODEL:-claude-sonnet-4-6}"
SLAC_HOST="${SLAC_HOST:-kennylo@s3dflogin.slac.stanford.edu}"
SLAC_SSH_KEY="${SLAC_SSH_KEY:-${HOME}/.ssh/id_slac}"
PROXY_PORT="${SLAC_PROXY_PORT:-1080}"
OUTPUTS_DIR="${OUTPUTS_DIR:-${HOME}/llm-apps/app/cgsim-outputs/round-$(date +%Y%m%d_%H%M%S)}"

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "[$(date +%T)] $*"; }

[[ -x "${PYTHON}" ]] || die "python not found: ${PYTHON}"
[[ -f "${SLAC_SSH_KEY}" ]] || die "SSH key not found: ${SLAC_SSH_KEY}"
[[ -f "${CGSIM_INSTALL_ROOT}/bin/cg-sim" ]] || die "cg-sim not installed: ${CGSIM_INSTALL_ROOT}/bin/cg-sim"

if [[ -z "${SLAC_AI_KEY:-}" && -f "${HOME}/.bash_aliases" ]]; then
    # shellcheck disable=SC1091
    source "${HOME}/.bash_aliases" >/dev/null 2>&1 || true
fi
[[ -n "${SLAC_AI_KEY:-}" ]] || die "SLAC_AI_KEY is not set (environment or ~/.bash_aliases)"
export SLAC_AI_KEY
# Either of these takes priority over the SLAC gateway in CGSimDataGenerator
unset OLLAMA_HOST ANTHROPIC_API_KEY

if [[ ! -f "${MANIFEST}" ]]; then
    log "no scenario manifest; generating scenario configs"
    "${PYTHON}" "${LLM_DIR}/clients/ScenarioConfigGenerator.py" --output-dir "${RUBIN_DIR}/scenarios" \
        || die "scenario config generation failed"
fi
if [[ -z "${SCENARIOS:-}" ]]; then
    SCENARIOS="$("${PYTHON}" -c "import json,sys; print(' '.join(e['name'] for e in json.load(open(sys.argv[1]))))" "${MANIFEST}")"
fi

# ---- SOCKS5 tunnel to SLAC (key-based, no MFA) ----------------------------
TUNNEL_PID=""
tunnel_cleanup() {
    [[ -n "${TUNNEL_PID}" ]] && kill "${TUNNEL_PID}" 2>/dev/null
    return 0
}
trap tunnel_cleanup EXIT

if ss -ltn | grep -q "127.0.0.1:${PROXY_PORT}\b"; then
    log "port ${PROXY_PORT} already listening; reusing that tunnel (will not close it)"
else
    log "opening SOCKS5 tunnel on 127.0.0.1:${PROXY_PORT} -> ${SLAC_HOST}"
    ssh -D "127.0.0.1:${PROXY_PORT}" -N -f \
        -i "${SLAC_SSH_KEY}" \
        -o IdentitiesOnly=yes \
        -o ControlMaster=no \
        -o ControlPath=none \
        -o LogLevel=ERROR \
        -o BatchMode=yes \
        -o ExitOnForwardFailure=yes \
        -o ServerAliveInterval=30 \
        -o ServerAliveCountMax=3 \
        -o StrictHostKeyChecking=accept-new \
        "${SLAC_HOST}" || die "could not open SSH tunnel (key not authorized, or host unreachable)"
    TUNNEL_PID="$(pgrep -n -f "ssh -D 127.0.0.1:${PROXY_PORT}.*${SLAC_HOST##*@}")"
    log "tunnel up (pid=${TUNNEL_PID})"
fi
export SLAC_PROXY_PORT="${PROXY_PORT}"

# Auth header via a process-substitution config so the key never appears in ps
gateway_status="$(curl -s -m 20 --socks5-hostname "127.0.0.1:${PROXY_PORT}" -o /dev/null \
    -w '%{http_code}' --config <(printf 'header = "Authorization: Bearer %s"\n' "${SLAC_AI_KEY}") \
    https://ai-api.slac.stanford.edu/v1/models)"
[[ "${gateway_status}" == "200" ]] || die "gateway check failed (http ${gateway_status}; expected 200)"
log "gateway reachable and key accepted (http 200)"

if [[ -n "${CHECK_ONLY:-}" ]]; then
    log "CHECK_ONLY set; tunnel and gateway OK, exiting"
    exit 0
fi

# ---- run all scenarios in parallel ---------------------------------------
mkdir -p "${OUTPUTS_DIR}/logs"
log "round dir: ${OUTPUTS_DIR}"
log "scenarios: ${SCENARIOS}"
log "n=${N}  generator=${GENERATOR_MODEL}  judge=${JUDGE_MODEL}"

declare -A pids
for s in ${SCENARIOS}; do
    "${PYTHON}" "${LLM_DIR}/datagen_local.py" \
        --manifest "${MANIFEST}" \
        --outputs-dir "${OUTPUTS_DIR}" \
        --python "${PYTHON}" \
        --clients-dir "${LLM_DIR}/clients" \
        --cgsim-bin "${CGSIM_INSTALL_ROOT}/bin/cg-sim" \
        --n "${N}" \
        --scenarios "${s}" \
        --generator-model "${GENERATOR_MODEL}" \
        --judge-model "${JUDGE_MODEL}" \
        > "${OUTPUTS_DIR}/logs/${s}.log" 2>&1 &
    pids[${s}]=$!
done
log "launched ${#pids[@]} scenarios; logs in ${OUTPUTS_DIR}/logs/"

failed=()
for s in "${!pids[@]}"; do
    if wait "${pids[${s}]}"; then
        log "done: ${s}"
    else
        log "FAILED: ${s} (see ${OUTPUTS_DIR}/logs/${s}.log)"
        failed+=("${s}")
    fi
done

# ---- verify DAG ordering, then merge with cleaning ------------------------
dag_bad=()
for s in ${SCENARIOS}; do
    [[ " ${failed[*]:-} " == *" ${s} "* ]] && continue
    d="${RUBIN_DIR}/scenarios/${s}"
    if "${PYTHON}" "${RUBIN_DIR}/verify_dag_order.py" "${OUTPUTS_DIR}/rubin_${s}.db" \
            --qgraph "${d}/qgraph_export.json" --clustering "${d}/clustering.json" > "${OUTPUTS_DIR}/logs/${s}.dag.txt" 2>&1; then
        log "dag ok: ${s}"
    else
        log "DAG VIOLATIONS: ${s} (see ${OUTPUTS_DIR}/logs/${s}.dag.txt)"
        dag_bad+=("${s}")
    fi
done

merged="${OUTPUTS_DIR}/merged_$(date +%Y%m%d).jsonl"
"${PYTHON}" "${LLM_DIR}/merge.py" --outputs-dir "${OUTPUTS_DIR}" --out "${merged}" \
    || log "merge failed"

echo
log "round finished: ${#failed[@]} scenario failures, ${#dag_bad[@]} DAG failures"
[[ ${#failed[@]} -gt 0 ]] && echo "  failed scenarios: ${failed[*]}  (rerun with OUTPUTS_DIR=${OUTPUTS_DIR} to resume)"
[[ ${#dag_bad[@]} -gt 0 ]] && echo "  DAG violations:   ${dag_bad[*]}"
echo "  merged output: ${merged}"
[[ ${#failed[@]} -eq 0 && ${#dag_bad[@]} -eq 0 ]]
