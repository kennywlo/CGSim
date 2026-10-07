#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/dgx-env.sh"

plugin_source="${CGSIM_SOURCE_ROOT}/dispatch_plugins/rubin-plugin"
plugin_build="${plugin_source}/build"

cmake -S "${plugin_source}" -B "${plugin_build}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DSimGrid_PATH="${SIMGRID_INSTALL_ROOT}" \
  -DCGSim_DIR="${CGSIM_INSTALL_ROOT}/share/cmake/CGSim" \
  -DCMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH}"

cmake --build "${plugin_build}"

echo "Built ${plugin_build}/libRubinDispatcherPlugin.so"
