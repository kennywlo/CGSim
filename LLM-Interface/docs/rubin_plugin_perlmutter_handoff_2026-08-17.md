# Rubin Plugin → Perlmutter handoff (2026-08-17)

Written by the DGX Spark session for whichever Claude Code session picks this up on
Perlmutter next. Memory does not carry over automatically — the two environments use
different absolute repo paths (`~/llm-apps/app/...` here vs.
`/global/homes/k/kennylo/llm-apps/app/...` there), so this file is the transfer
mechanism. Supersedes the DGX-only state in `docs/raees_rubin_plugin_compatibility.md`
(2026-08-03) with what changed since.

## What's new since the 2026-08-03 compatibility review

1. **`Rubin-Plugin` `dgx-compat` merged with Raees's `main` and pushed.** Merge commit
   `3491c87` is on `kenny/dgx-compat` (`git@github.com:kennywlo/Rubin-Plugin.git`).
   It brings in Raees's real workload (`workload/real_quantum_graph.json`, 3512 jobs)
   and a "new API" commit (`RubinPlugin.cpp` now targets `CGSim::Plugin`/`plugin.h`
   instead of `DispatcherPlugin`). The merge conflict in `workload_manager.cpp` was
   resolved in favor of the DGX-portable `platform->get_property("jobs_file")` form
   (kept from the `8c2c19b` fix), not Raees's `Custom_Parameters` form.

2. **New CGSim dependency: `origin/api_cleanup`.** The `CGSim::Plugin` API Raees's
   plugin now needs does not exist on `dag_dependencies` (what `CGSim-dag-install`
   was built from) or on `kennywlo/CGSim` `main`/`dgx-output-barrier`. It only exists
   on `REDWOOD24/CGSim` branch `api_cleanup`, which sits directly on top of
   `dag_dependencies` tip (`9b7cff2`) and *removes* `DispatcherPlugin.h` entirely —
   this is a real CGSim core API migration, not a cosmetic rename.

   On DGX: cloned `api_cleanup` fresh into `~/llm-apps/app/CGSim-api-cleanup`,
   built + installed to `~/llm-apps/app/CGSim-api-install`
   (`cmake -DCMAKE_INSTALL_PREFIX=.../CGSim-api-install -DCMAKE_PREFIX_PATH=.../simgrid-install`),
   then built the plugin against it:
   `cmake -S plugin -B plugin/build-api-cleanup -DCMAKE_PREFIX_PATH="<CGSim-api-install>;<simgrid-install>" -DNLOHMANN_JSON_INCLUDE_DIR=<CGSim-api-cleanup>/json/include`.
   Built clean, `libRubinPlugin.so` produced. **None of this transfers to Perlmutter
   as binaries** — DGX Spark is aarch64, Perlmutter is x86_64. Both CGSim
   (`api_cleanup`) and the plugin need a from-source rebuild there. The
   `dag_dependencies`-vs-`api_cleanup` output-write-barrier fix
   (`dgx-output-barrier`, see the 2026-08-03 doc) has **not** been ported onto
   `api_cleanup` yet — check whether the same missing-generated-input race exists
   there before trusting a run.

3. **Site topology is still a single placeholder site**, confirmed to represent
   USDF specifically. `config/site_topology.json` `Site0`'s core count (30,000)
   is a close match to real S3DF (~31,000 AMD Milan/Rome cores) and its storage
   figure (20 PB) is close to S3DF's current ~24 PB disk+NVMe total — but
   `config/site_connections.json` is empty (`{}}`), so there is zero inter-site
   network topology. TODO.md's target site set is `SLAC_Rubin_*` (USDF),
   `CC-IN2P3_Rubin_*` (FrDF), `LANCS_Rubin_*`/`RAL_Rubin_*` (UKDF) — i.e. 4 site
   families across 3 facilities, not 1. Raees's framing ("we just need a realistic
   description of the computing site") suggests this is the joint next step, not
   something to solve unilaterally — check whether Kenny/Raees met before assuming
   this is still open.

4. **`workload/real_quantum_graph.json` is confirmed RC2-derived, not LSSTCam
   DRP1-derived.** Cross-checked its 41 task-type labels against the real
   `pipeline_drp_pipe_LSSTCam_DRP.yaml` (in `~/llm-apps/app/rubin_drp_pipeline/`,
   the actual LSST Science Pipelines DRP.yaml) — only 18/40 match. The mismatches
   are systematic (`deblend`/`mergeDetections`/`measure`/`assembleCoadd` vs. the
   real pipeline's `deblendCoaddFootprints`/`mergeObjectDetection`/
   `measureObjectUnforced`/`assembleDeepCoadd`), consistent with CGSim commit
   `15ad224` ("Run a real rc2_subset QuantumGraph export"). Per-task costs are real
   measurements, just from HSC RC2, not an actual DRP1 campaign. Treat simulation
   results against this workload as RC2-scale proxy results, not DRP1-fidelity
   numbers, until it's regenerated from the real LSSTCam pipeline.

## Not yet done — still applies from the 2026-08-03 P0 list

Everything in `docs/raees_rubin_plugin_compatibility.md`'s "Gaps to the PanDA-only
Rubin target" section is still open: the v0.2 `qgraph_manifest.json`/streaming
contract, real 4-site PanDA facility names, PanDA-compatible output + pilot-log
artifacts, failure modeling, and the CGSim `dag_dependencies`/`api_cleanup`
core-DAG merge gate. None of today's session addressed those.

## Concretely missing before a Perlmutter run

- No `_perlmutter` config variant: `config/rubin_config.json` currently points at
  `libRubinPlugin.dylib` (macOS) and a relative `../output/events.db` — per this
  repo's convention, Perlmutter SQLite output must live on `/tmp`, not Lustre (WAL
  limitation).
- No Slurm/sbatch script for this specific build (`api_cleanup` CGSim +
  `dgx-compat` plugin + `real_quantum_graph.json`). The existing scripts in
  `Rubin-Plugin/scripts/` target the older nightly-resume/topology workflow.
- CGSim `api_cleanup` has not been built on Perlmutter at all yet — start from
  `origin/api_cleanup` at `REDWOOD24/CGSim`, same build recipe as above but with
  Perlmutter's module-loaded compiler/Boost/SimGrid instead of the DGX paths.
