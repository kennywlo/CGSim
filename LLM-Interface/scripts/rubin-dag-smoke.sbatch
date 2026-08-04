#!/bin/bash
#SBATCH --job-name=rubin-dag-smoke
#SBATCH --account=m2616
#SBATCH --qos=shared
#SBATCH --constraint=cpu
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem-per-cpu=1900
#SBATCH --time=00:15:00
#SBATCH --output=/pscratch/sd/k/kennylo/cgsim-rubin/logs/rubin-dag-smoke-%j.log
#SBATCH --error=/pscratch/sd/k/kennylo/cgsim-rubin/logs/rubin-dag-smoke-%j.log
#
# QGraph/DAG-gated Rubin plugin smoke test, submitted via Slurm rather than run
# on a login node. Builds a synthetic rubin_campaign_schema v0.2 campaign, runs
# it through cg-sim + libRubinDispatcherPlugin.so, and validates DAG-gated
# execution ordering (see scripts/smoke-rubin-dag-perlmutter.sh).
#
# Requires the build already done once (not part of this job):
#   source scripts/perlmutter-env.sh
#   scripts/build-cgsim-perlmutter.sh
#   scripts/build-rubin-plugin-perlmutter.sh
#
# Submit with `make rubin-dag-smoke-submit` or directly:
#   sbatch scripts/rubin-dag-smoke.sbatch

set -euo pipefail

echo "[$(date +%T)] node=$(hostname) job=${SLURM_JOB_ID:-none}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${script_dir}/smoke-rubin-dag-perlmutter.sh"

echo "[$(date +%T)] done"
