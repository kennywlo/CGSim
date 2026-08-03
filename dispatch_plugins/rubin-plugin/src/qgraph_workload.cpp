#include "qgraph_workload.h"
#include <map>
#include <set>
#include <cmath>

json QGRAPH_WORKLOAD::load_json(const std::string& path)
{
    std::ifstream f(path);
    if (!f.is_open()) {throw std::runtime_error("Could not open file: " + path);}
    return json::parse(f);
}

// scipy lognorm convention: params = [shape(sigma), loc, scale]
double QGRAPH_WORKLOAD::sample_lognorm(const json& dist_spec, double fallback)
{
    if (dist_spec.is_null() || !dist_spec.contains("params")) return fallback;
    auto p = dist_spec["params"];
    double sigma = p[0].get<double>();
    double loc   = p[1].get<double>();
    double scale = p[2].get<double>();
    std::normal_distribution<double> N(0.0, 1.0);
    return loc + scale * std::exp(sigma * N(rng));
}

long long QGRAPH_WORKLOAD::dataset_bytes(const std::string& dataset_type, const json& quantum_outputs)
{
    for (const auto& out : quantum_outputs)
        if (out["dataset_type"] == dataset_type && !out["bytes_est"].is_null())
            return out["bytes_est"].get<long long>();

    if (!resources.is_null() && resources.contains("dataset_types")
        && resources["dataset_types"].contains(dataset_type))
        return static_cast<long long>(
            sample_lognorm(resources["dataset_types"][dataset_type]["bytes"], 1e8));

    return 100000000LL;
}

std::string QGRAPH_WORKLOAD::cluster_key(const Quantum& q, const json& clustering)
{
    for (const auto& spec : clustering["clusters"])
    {
        for (const auto& label : spec["task_labels"])
        {
            if (label != q.task) continue;
            std::string key = spec["name"].get<std::string>();
            for (const auto& dim : spec["dimensions"])
                key += "_" + q.data_id[dim.get<std::string>()].dump();
            return key;
        }
    }
    // Task not covered by any cluster spec: fall back to single_quantum
    return "sq_" + q.task + "_" + std::to_string(q.qid);
}

JobQueue QGRAPH_WORKLOAD::getWorkload()
{
    json qgraph     = load_json(platform->get_property("qgraph_file"));
    json clustering = load_json(platform->get_property("clustering_file"));

    const char* res_path = platform->get_property("resources_file");
    if (res_path) resources = load_json(res_path);

    // Site comes from the campaign group that owns this qgraph (schema section 2:
    // "site per group is the multi-site knob"); fall back to default_site.
    std::string site = "USDF";
    const char* default_site = platform->get_property("default_site");
    if (default_site) site = default_site;
    const char* campaign_path = platform->get_property("campaign_file");
    if (campaign_path) {
        json campaign = load_json(campaign_path);
        std::string group_id = qgraph["provenance"]["group_id"].get<std::string>();
        for (const auto& node : campaign["campaign"]["nodes"])
            if (node["id"] == group_id && node["configuration"].contains("site"))
                site = node["configuration"]["site"].get<std::string>();
    }

    // ---- Parse quanta; map task label -> resource_key ----
    std::unordered_map<std::string, std::string> resource_key_of;
    for (const auto& t : qgraph["tasks"])
        resource_key_of[t["label"].get<std::string>()] = t["resource_key"].get<std::string>();

    std::unordered_map<long long, Quantum> quanta;
    for (const auto& q : qgraph["quanta"])
        quanta[q["qid"].get<long long>()] =
            Quantum{q["qid"].get<long long>(), q["task"].get<std::string>(),
                    q["data_id"], q["inputs"], q["outputs"]};

    // ---- Apply the clustering overlay: quantum -> cluster key ----
    // std::map keeps cluster iteration deterministic across runs.
    std::unordered_map<long long, std::string>       cluster_of;
    std::map<std::string, std::vector<long long>>    members;
    std::map<std::string, const json*>               spec_of;
    for (auto& [qid, q] : quanta)
    {
        std::string key = cluster_key(q, clustering);
        cluster_of[qid] = key;
        members[key].push_back(qid);
        if (spec_of.find(key) == spec_of.end()) {
            spec_of[key] = nullptr;
            for (const auto& spec : clustering["clusters"])
                for (const auto& label : spec["task_labels"])
                    if (label == q.task) spec_of[key] = &spec;
        }
    }

    // ---- One Job per cluster ----
    std::map<std::string, Job*> job_of;
    long long next_jobid = 1000;
    for (auto& [key, qids] : members)
    {
        Job* job = new Job();
        job->jobid     = next_jobid++;
        job->id        = key;
        job->status    = "created";
        job->retries   = 0;
        job->comp_site = site;
        job->priority  = 0;   // topo depth filled in below

        const json* spec = spec_of[key];
        job->cores        = spec ? (*spec)["request_cpus"].get<int>() : 1;
        job->memory_usage = spec ? (*spec)["request_memory_mb"].get<double>() : 2048.0;

        double cpu_s = 0.0;
        for (long long qid : qids) {
            const std::string& rkey = resource_key_of[quanta[qid].task];
            json model = (!resources.is_null() && resources.contains("models")
                          && resources["models"].contains(rkey))
                          ? resources["models"][rkey]["cpu_s"] : json();
            cpu_s += sample_lognorm(model, 60.0);
        }
        job->cpu_consumption_time = cpu_s;

        job_of[key] = job;
    }

    // ---- Cluster-level DAG + cross-cluster dataset files ----
    // (qid, dataset_type) pairs consumed by any edge, to find terminal outputs
    std::set<std::pair<long long, std::string>> consumed;
    std::set<std::pair<Job*, Job*>> dag_edges;
    for (const auto& e : qgraph["edges"])
    {
        long long   pq = e["producer_qid"].get<long long>();
        long long   cq = e["consumer_qid"].get<long long>();
        std::string dt = e["dataset_type"].get<std::string>();
        consumed.insert({pq, dt});

        Job* pjob = job_of[cluster_of[pq]];
        Job* cjob = job_of[cluster_of[cq]];
        if (pjob == cjob) continue;   // intra-cluster: node-local intermediate, no file

        // Producer side only: the product is written and storage-accounted on
        // completion. It is NOT added to the consumer's input_files, because
        // core resolves input locations once at t=0 (job_executor.cpp calls
        // FileManager::request_file_location before any parent has run) and
        // would throw on a file that doesn't exist yet. Consumer-side staging
        // of parent products needs core support — see README "Known constraints".
        std::string filename = dt + "_q" + std::to_string(pq);
        pjob->output_files[filename] = dataset_bytes(dt, quanta[pq].outputs);

        if (dag_edges.insert({pjob, cjob}).second) {
            children[pjob].push_back(cjob);
            parents_remaining[cjob]++;
        }
    }

    // ---- External inputs (no producer in this qgraph, e.g. raw) and terminal outputs ----
    std::set<std::string> produced_types;
    for (auto& [qid, q] : quanta)
        for (const auto& out : q.outputs)
            produced_types.insert(out["dataset_type"].get<std::string>());

    for (auto& [qid, q] : quanta)
    {
        Job* job = job_of[cluster_of[qid]];
        for (const auto& in : q.inputs) {
            std::string dt = in["dataset_type"].get<std::string>();
            if (produced_types.count(dt)) continue;
            std::string filename = dt + "_q" + std::to_string(qid);
            long long bytes = in["bytes_est"].is_null() ? dataset_bytes(dt, json::array())
                                                        : in["bytes_est"].get<long long>();
            job->input_files[filename] = {bytes, {}};
        }
        for (const auto& out : q.outputs) {
            std::string dt = out["dataset_type"].get<std::string>();
            if (consumed.count({qid, dt})) continue;
            job->output_files[dt + "_q" + std::to_string(qid)] = dataset_bytes(dt, q.outputs);
        }
    }

    // ---- Topological depth -> priority (roots highest). Note: core's JobQueue
    // is priority_queue<Job*>, which orders by pointer, not Job::operator< —
    // correctness does not depend on this, since all non-root jobs return
    // "pending" from assignJob() until their parents finish regardless of pop
    // order. The field is set for when core honors it. ----
    std::unordered_map<Job*, int> depth;
    std::vector<Job*> order;
    for (auto& [key, job] : job_of)
        if (parents_remaining.find(job) == parents_remaining.end()) {
            depth[job] = 0; order.push_back(job);
        }
    std::unordered_map<Job*, int> remaining = parents_remaining;
    for (size_t i = 0; i < order.size(); ++i)
        for (Job* child : children[order[i]])
            if (--remaining[child] == 0) {
                depth[child] = depth[order[i]] + 1; order.push_back(child);
            }
    if (order.size() != job_of.size())
        throw std::runtime_error("qgraph cluster DAG has a cycle");

    int max_depth = 0;
    for (auto& [job, d] : depth) max_depth = std::max(max_depth, d);

    JobQueue jobs;
    for (auto& [key, job] : job_of) {
        job->priority = max_depth - depth[job];
        jobs.push(job);
    }

    std::cout << "QGRAPH_WORKLOAD: " << quanta.size() << " quanta -> "
              << job_of.size() << " cluster jobs ("
              << order.size() - parents_remaining.size() << " roots, max depth "
              << max_depth << "), site " << site << std::endl;
    return jobs;
}

bool QGRAPH_WORKLOAD::ready(Job* job) const
{
    auto it = parents_remaining.find(job);
    return it == parents_remaining.end() || it->second == 0;
}

void QGRAPH_WORKLOAD::markDone(Job* job)
{
    auto it = children.find(job);
    if (it == children.end()) return;
    for (Job* child : it->second) parents_remaining[child]--;
    children.erase(it);   // idempotence: retried executions must not double-release
}
