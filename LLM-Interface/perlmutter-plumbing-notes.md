# Perlmutter CGSim/SimGrid build: what was already tried and what changed

Three build logs already existed at `$HOME/llm-apps/app/` from 2026-06-02
(`build_simgrid_cgsim.log`, `build_cgsim.log`, `build_plugin_run.log`), predating
the `scripts/perlmutter-env.sh` / `build-cgsim-perlmutter.sh` /
`build-rubin-plugin-perlmutter.sh` scripts added here. This documents what those
logs showed, since the working configuration isn't obvious from the CMake
invocations alone.

## Boost: `/usr` does not work, the Cray `dyninst` package's bundled Boost does

The first attempt (`build_simgrid_cgsim.log`) passed `-DBOOST_ROOT=/usr` (system
Boost 1.66.0) and failed building CGSim itself:

```
util/parser.cpp:10:10: fatal error: boost/parameter/aux_/pack/item.hpp: No such file or directory
```

A later attempt (`build_cgsim.log`) instead picked up Boost 1.75.0 via
`/opt/cray/pe/dyninst/12.3.6/lib/cmake/Boost-1.75.0/BoostConfig.cmake` and built
cleanly -- CGSim, `libCGSim.so`, and `cg-sim` all built without error. This repo's
`perlmutter-env.sh` pins `CGSIM_BOOST_ROOT=/opt/cray/pe/dyninst/12.3.6`
accordingly; there is no NERSC Lmod module that exposes this path via an
environment variable, so it has to be passed explicitly as `-DBOOST_ROOT`.

SimGrid and spdlog/fmt built fine either way; only CGSim's own sources hit the
missing header, since SimGrid's installed headers reference
`boost/parameter/aux_/pack/item.hpp` from a newer Boost version than 1.66 ships.

## simple-test-plugin built and linked correctly

`build_plugin_run.log` shows `libSimpleDispatcherPlugin.so` building cleanly
against the same install prefix, confirming `find_package(CGSim)` and
`find_package(SimGrid)` both resolve correctly once the install prefix is on
`CMAKE_PREFIX_PATH`.

## Runtime failure: swallowed sqlite error message, not a `/tmp`/WAL issue

Running `cg-sim` against `toy_config_perlmutter.json` (`output_file` already
pointed at `/tmp`) aborted with:

```
Uncaught exception std::runtime_error: Database table creation failed
```

Confirmed separately that plain SQLite `PRAGMA journal_mode=WAL` + `CREATE TABLE`
at `/tmp` works fine on a Perlmutter login node with the system `libsqlite3`
(`cg-sim` links `/usr/lib64/libsqlite3.so.0`), so this isn't a structural
`/tmp`/WAL incompatibility. The actual cause is unknown because
`OUTPUT::createEventsTable()` (`dispatch_plugins/*/src/output.cpp`) discarded
`sqlite3_exec`'s `errmsg` via `sqlite3_free` without ever logging it -- fixed in
both plugins to include the real message and return code in the thrown
exception, so the *next* failure (if any) will be actionable instead of generic.
The June run was via `srun` on a compute node (`nid004077`), not the login node
tested above, so environment differences between the two are still possible;
re-run the smoke test and read the (now non-generic) error if it recurs.

## Install prefix: `$PSCRATCH`, not `$HOME`

The original June logs installed spdlog/fmt/SimGrid/CGSim into
`$HOME/llm-apps/app/local`. This repo's scripts install into
`$PSCRATCH/cgsim-rubin/install` instead -- `$HOME` on Perlmutter has a hard
40 GiB NERSC quota that this project has already exceeded once (see the
`rc2_subset` Butler repo's move to `$PSCRATCH`); build artifacts have no reason
to live on the quota-constrained filesystem.
