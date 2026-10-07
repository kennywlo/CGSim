#!/usr/bin/env bash
# Source this file before building or running CGSim on Perlmutter:
#   source scripts/perlmutter-env.sh
#
# Run this in a clean GNU shell -- do NOT source an LSST/CVMFS loadLSST.bash
# in the same shell first. The LSST stack's conda env sets its own compiler
# and library search paths that can shadow the ones CGSim needs.
#
# Unlike DGX Spark, Perlmutter has no pre-existing SimGrid/spdlog/fmt
# install. build-cgsim-perlmutter.sh builds all three plus CGSim itself from
# source into $PSCRATCH -- never $HOME, whose 40 GiB NERSC quota has already
# been blown once in this project (see rc2_subset's move to $PSCRATCH).
#
# CGSim's find_package(Boost) needs Boost headers newer than the login
# node's system /usr Boost (1.66 -- missing
# boost/parameter/aux_/pack/item.hpp, which SimGrid's headers use). The Cray
# PrgEnv-gnu toolchain ships a newer bundled Boost (1.75) under the
# "dyninst" package that does work; -DBOOST_ROOT=/usr was tried first and
# failed (see LLM-Interface/perlmutter-plumbing-notes.md).

_pm_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CGSIM_SOURCE_ROOT="$(cd "${_pm_script_dir}/../../.." && pwd)"

: "${PSCRATCH:?PSCRATCH is not set -- are you on a NERSC login/compute node?}"

export CGSIM_PERLMUTTER_ROOT="${PSCRATCH}/cgsim-rubin"
export CGSIM_INSTALL_ROOT="${CGSIM_PERLMUTTER_ROOT}/install"
export SIMGRID_INSTALL_ROOT="${CGSIM_INSTALL_ROOT}"
export CGSIM_BUILD_ROOT="${CGSIM_PERLMUTTER_ROOT}/build"
export CGSIM_BOOST_ROOT="/opt/cray/pe/dyninst/12.3.6"

if [ ! -d "${CGSIM_BOOST_ROOT}" ]; then
    echo "WARNING: ${CGSIM_BOOST_ROOT} not found -- the Cray dyninst package" \
         "may have moved. Re-check 'find /opt/cray/pe/dyninst -iname BoostConfig.cmake'" \
         "and update CGSIM_BOOST_ROOT in this script." >&2
fi

export PATH="${CGSIM_INSTALL_ROOT}/bin:${PATH}"
export LD_LIBRARY_PATH="${CGSIM_INSTALL_ROOT}/lib64:${CGSIM_INSTALL_ROOT}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export CMAKE_PREFIX_PATH="${CGSIM_INSTALL_ROOT}${CMAKE_PREFIX_PATH:+:${CMAKE_PREFIX_PATH}}"

unset _pm_script_dir
