#ifndef QGRAPH_WORKLOAD_H
#define QGRAPH_WORKLOAD_H

#include <string>
#include <vector>
#include <unordered_map>
#include <random>
#include <iostream>
#include <fstream>
#include "CGSim.h"
#include <nlohmann/json.hpp>
using json = nlohmann::json;

// Builds the CGSim JobQueue from rubin_campaign_schema v0.2 files
// (qgraph_export.json + clustering.json, optionally resources.json /
// campaign.json) and owns the cluster-level DAG state used by
// RUBIN_DISPATCHER to gate job release on parent completion.
//
// One Job == one cluster of quanta (schema section 5): PanDA jobs exist at
// post-clustering granularity, so the DAG the dispatcher sees is the
// cluster DAG derived from the quantum edges.
class QGRAPH_WORKLOAD
{

public:
  QGRAPH_WORKLOAD(){};
 ~QGRAPH_WORKLOAD(){};

  JobQueue getWorkload();

  // DAG gate: true once every parent cluster has finished executing.
  bool ready(Job* job) const;

  // Called from onJobExecutionEnd to release children.
  void markDone(Job* job);

private:
  struct Quantum {
    long long   qid;
    std::string task;
    json        data_id;
    json        inputs;
    json        outputs;
  };

  json        load_json(const std::string& path);

  // Loads qgraph_file, which may be either the monolithic test-fixture
  // format (top-level "quanta"/"edges" arrays, as generate_campaign.py
  // produces) or a real v0.2 streaming bundle -- a qgraph_manifest.json
  // whose "quanta_file"/"edges_file" point at quanta.jsonl/edges.jsonl,
  // read line-by-line (see LLM-Interface/rubin_campaign_schema_v0.2.md
  // section 4 and rubin-data/qgraph_exporter.py). Both are normalized into
  // the same in-memory shape ("tasks"/"quanta"/"edges"/"provenance") so
  // every line below this call is unchanged either way.
  json        load_qgraph_bundle(const std::string& qgraph_file_path);

  std::string cluster_key(const Quantum& q, const json& clustering);
  double      sample_lognorm(const json& dist_spec, double fallback);
  long long   dataset_bytes(const std::string& dataset_type, const json& quantum_outputs);

  // parent-count / child-list bookkeeping, keyed by Job* (Job has no
  // dependency fields; the DAG lives entirely plugin-side)
  std::unordered_map<Job*, int>                parents_remaining;
  std::unordered_map<Job*, std::vector<Job*>>  children;

  json          resources;   // resources.json, may be empty
  std::mt19937  rng{42};

  sg4::NetZone* platform = sg4::Engine::get_instance()->get_netzone_root();
};

#endif
