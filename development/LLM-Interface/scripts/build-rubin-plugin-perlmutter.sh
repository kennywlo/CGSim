#!/usr/bin/env bash
# Build the Rubin dispatcher plugin on Perlmutter, against the CGSim/SimGrid
# install produced by build-cgsim-perlmutter.sh.
#
#   source scripts/perlmutter-env.sh
#   scripts/build-cgsim-perlmutter.sh          # once, or after a CGSim source change
#   scripts/build-rubin-plugin-perlmutter.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/perlmutter-env.sh"

plugin_source="${CGSIM_SOURCE_ROOT}/dispatch_plugins/rubin-plugin"
plugin_build="${plugin_source}/build"

cmake -S "${plugin_source}" -B "${plugin_build}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DSimGrid_PATH="${SIMGRID_INSTALL_ROOT}" \
  -DBOOST_ROOT="${CGSIM_BOOST_ROOT}" \
  -DCGSim_DIR="${CGSIM_INSTALL_ROOT}/share/cmake/CGSim" \
  -DCMAKE_PREFIX_PATH="${CMAKE_PREFIX_PATH}"

cmake --build "${plugin_build}" -j"${SLURM_CPUS_PER_TASK:-8}"

echo "Built ${plugin_build}/libRubinDispatcherPlugin.so"
