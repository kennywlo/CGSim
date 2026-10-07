#!/usr/bin/env bash
# Build and install the CGSim core on DGX Spark (current upstream CGSim::Plugin API).
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/dgx-env.sh"

core_build="${CGSIM_SOURCE_ROOT}/build"

cmake -S "${CGSIM_SOURCE_ROOT}" -B "${core_build}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="${CGSIM_INSTALL_ROOT}" \
  -DSimGrid_PATH="${SIMGRID_INSTALL_ROOT}" \
  -DCMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH}"

cmake --build "${core_build}" -j"$(nproc)"
cmake --install "${core_build}"

echo "Installed CGSim to ${CGSIM_INSTALL_ROOT}"
