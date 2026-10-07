#!/usr/bin/env bash
# Build spdlog, fmt, SimGrid, and CGSim from source on Perlmutter.
#
#   source scripts/perlmutter-env.sh
#   scripts/build-cgsim-perlmutter.sh
#
# See perlmutter-plumbing-notes.md for why -DBOOST_ROOT points at the Cray
# dyninst package's bundled Boost rather than the system /usr Boost.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${script_dir}/perlmutter-env.sh"

JOBS="${SLURM_CPUS_PER_TASK:-8}"
SRC="${CGSIM_BUILD_ROOT}"
PREFIX="${CGSIM_INSTALL_ROOT}"
mkdir -p "${SRC}" "${PREFIX}"

echo "=== source checkouts: ${SRC} ==="
echo "=== install prefix:   ${PREFIX} ==="
echo "=== jobs:              ${JOBS} ==="

# ── spdlog (brings its own bundled fmt config, but CGSim also finds fmt directly) ──
echo ""
echo "=== [1/4] Building spdlog ==="
cd "${SRC}"
if [ ! -d spdlog-src ]; then
    git clone --depth=1 --branch v1.13.0 https://github.com/gabime/spdlog.git spdlog-src
fi
mkdir -p spdlog-src/build && cd spdlog-src/build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DSPDLOG_BUILD_TESTS=OFF \
    -DSPDLOG_BUILD_EXAMPLE=OFF \
    -DCMAKE_BUILD_TYPE=Release
make -j"${JOBS}"
make install
echo "spdlog done."

# ── fmt ──────────────────────────────────────────────────────────────────────
echo ""
echo "=== [2/4] Building fmt ==="
cd "${SRC}"
if [ ! -d fmt-src ]; then
    git clone --depth=1 --branch 10.2.1 https://github.com/fmtlib/fmt.git fmt-src
fi
mkdir -p fmt-src/build && cd fmt-src/build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DFMT_TEST=OFF \
    -DFMT_DOC=OFF \
    -DCMAKE_BUILD_TYPE=Release
make -j"${JOBS}"
make install
echo "fmt done."

# ── SimGrid v3.36 ──────────────────────────────────────────────────────────────
echo ""
echo "=== [3/4] Building SimGrid v3.36 ==="
cd "${SRC}"
if [ ! -d simgrid-src ]; then
    git clone --depth=1 --branch v3.36 https://github.com/simgrid/simgrid.git simgrid-src
fi
mkdir -p simgrid-src/build && cd simgrid-src/build
cmake .. \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -Denable_documentation=OFF \
    -Denable_python=OFF \
    -Denable_smpi=OFF \
    -DBOOST_ROOT="${CGSIM_BOOST_ROOT}" \
    -DCMAKE_BUILD_TYPE=Release
make -j"${JOBS}"
make install
echo "SimGrid done."

# ── CGSim ──────────────────────────────────────────────────────────────────────
# Always start from a clean build/ dir: a stale build/ configured against a
# different install prefix (e.g. an old $HOME/llm-apps/app/local from before
# this project moved build output to $PSCRATCH) leaves libCGSim.so linked
# against the wrong SimGrid and its exported CMake target metadata pointing
# at the old prefix, which then corrupts anything built against it (seen as
# a CMake "cycle in the constraint graph" RPATH warning when building the
# Rubin plugin against a mismatched install).
echo ""
echo "=== [4/4] Building CGSim ==="
cd "${CGSIM_SOURCE_ROOT}"
rm -rf build
mkdir -p build && cd build
cmake .. \
    -DSimGrid_PATH="${PREFIX}" \
    -DBOOST_ROOT="${CGSIM_BOOST_ROOT}" \
    -DCMAKE_PREFIX_PATH="${PREFIX}" \
    -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
    -DCMAKE_BUILD_TYPE=Release
make -j"${JOBS}"
make install
echo "CGSim done."

echo ""
echo "=== Build complete ==="
echo "Binary:  ${PREFIX}/bin/cg-sim"
echo "Libs:    ${PREFIX}/lib64/ and ${PREFIX}/lib/"
echo "CMake config: ${PREFIX}/share/cmake/CGSim/"
