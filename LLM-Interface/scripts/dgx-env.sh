#!/usr/bin/env bash
# Source this file before building or running CGSim on DGX Spark:
#   source scripts/dgx-env.sh

_dgx_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CGSIM_SOURCE_ROOT="$(cd "${_dgx_script_dir}/../.." && pwd)"
export CGSIM_INSTALL_ROOT="/home/kennylo/llm-apps/app/CGSim-install"
export SIMGRID_INSTALL_ROOT="/home/kennylo/llm-apps/app/simgrid-install"

export PATH="${CGSIM_INSTALL_ROOT}/bin:${PATH}"
export LD_LIBRARY_PATH="${SIMGRID_INSTALL_ROOT}/lib:${CGSIM_INSTALL_ROOT}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export CMAKE_PREFIX_PATH="${CGSIM_INSTALL_ROOT}:${SIMGRID_INSTALL_ROOT}${CMAKE_PREFIX_PATH:+:${CMAKE_PREFIX_PATH}}"

unset _dgx_script_dir
