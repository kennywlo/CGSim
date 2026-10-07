#include "qgraph_workload.h"
#include <filesystem>
#include <map>
#include <set>
#include <cmath>

json QGRAPH_WORKLOAD::load_json(const std::string& path)
{
    std::ifstream f(path);
    if (!f.is_open()) {throw std::runtime_error("Could not open file: " + path);}
    return json::parse(f);
}

json QGRAPH_WORKLOAD::load_qgraph_bundle(const std::string& qgraph_file_path)
{
    json top = load_json(qgraph_file_path);

    // Monolithic test-fixture format: quanta/edges already inline.
    if (top.contains("quanta") && top.contains("edges")) return top;

    // v0.2 streaming bundle: top is qgraph_manifest.json. quanta_file/
    // edges_file are relative to the manifest's own directory, not cwd.
    if (!top.contains("quanta_file") || !top.contains("edges_file"))
        throw std::runtime_error(
            "qgraph_file " + qgraph_file_path +
            " has neither inline quanta/edges nor quanta_file/edges_file "
            "-- not a recognized qgraph bundle format");

    std::filesystem::path bundle_dir =
        std::filesystem::path(qgraph_file_path).parent_path();
    std::filesystem::path quanta_path = bundle_dir / top["quanta_file"].get<std::string>();
    std::filesystem::path edges_path  = bundle_dir / top["edges_file"].get<std::string>();

    json quanta = json::array();
    std::ifstream qf(quanta_path);
    if (!qf.is_open()) {throw std::runtime_error("Could not open file: " + quanta_path.string());}
    for (std::string line; std::getline(qf, line);) {
        if (line.empty()) continue;
        quanta.push_back(json::parse(line));
    }

    json edges = json::array();
    std::ifstream ef(edges_path);
    if (!ef.is_open()) {throw std::runtime_error("Could not open file: " + edges_path.string());}
    for (std::string line; std::getline(ef, line);) {
        if (line.empty()) continue;
        edges.push_back(json::parse(line));
    }

    top["quanta"] = std::move(quanta);
    top["edges"]  = std::move(edges);
    return top;
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

// Value of a dimension for a quantum's data ID. equal_dimensions pairs [a, b] say that dimension a of
// one task is the same value as dimension b of another (BPS equalDimensions, e.g. visit == exposure,
// so isr quanta, which carry exposure, cluster with calibrateImage quanta, which carry visit).
static std::string dim_value(const json& data_id, const std::string& dim, const json& spec)
{
    if (data_id.contains(dim)) return data_id[dim].dump();
    if (spec.contains("equal_dimensions"))
        for (const auto& pair : spec["equal_dimensions"])
        {
            const std::string a = pair[0].get<std::string>(), b = pair[1].get<std::string>();
            if (dim == a && data_id.contains(b)) return data_id[b].dump();
            if (dim == b && data_id.contains(a)) return data_id[a].dump();
        }
    return "null";
}

// Spec value that may be absent or null (e.g. request_memory_mb when no resources file was used).
static bool spec_has(const json& spec, const char* key)
{
    return spec.contains(key) && !spec[key].is_null();
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
                key += "_" + dim_value(q.data_id, dim.get<std::string>(), spec);
            // partition dimensions split a cluster into separate jobs (BPS partitionDimensions;
            // partition_max_clusters is recorded in the file but not enforced here)
            if (spec.contains("partition_dimensions"))
                for (const auto& dim : spec["partition_dimensions"])
                    key += "_" + dim_value(q.data_id, dim.get<std::string>(), spec);
            return key;
        }
    }
    // Task not covered by any cluster spec: fall back to single_quantum
    return "sq_" + q.task + "_" + std::to_string(q.qid);
}

void QGRAPH_WORKLOAD::setWorkload(CGSim::JobQueue& jobs)
{
    json qgraph     = load_qgraph_bundle(platform->get_property("qgraph_file"));
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
    // Ids stay numeric (1000+, sorted-key order) so EVENTS JOB_IDs match
    // rubin-data/verify_dag_order.py; the cluster key is kept as a property.
    std::map<std::string, CGSim::Job*> job_of;
    std::unordered_map<std::string, std::string> job_by_id;
    long long next_jobid = 1000;
    for (auto& [key, qids] : members)
    {
        CGSim::Job* job = new CGSim::Job();
        std::string id = std::to_string(next_jobid++);
        job->set_id(id);
        job->set_property("cluster_key", key);
        job->set_site(site);

        const json* spec = spec_of[key];
        job->set_cores(spec && spec_has(*spec, "request_cpus") ? (*spec)["request_cpus"].get<int>() : 1);
        job->set_memory_usage(std::to_string(spec && spec_has(*spec, "request_memory_mb") ? (*spec)["request_memory_mb"].get<double>() : 2048.0) + "MB");

        double cpu_s = 0.0;
        for (long long qid : qids) {
            const std::string& rkey = resource_key_of[quanta[qid].task];
            json model = (!resources.is_null() && resources.contains("models")
                          && resources["models"].contains(rkey))
                          ? resources["models"][rkey]["cpu_s"] : json();
            cpu_s += sample_lognorm(model, 60.0);
        }
        job->set_property("cpu_consumption_time", std::to_string(cpu_s));

        job_of[key] = job;
        job_by_id[id] = key;
    }

    // ---- Cluster-level DAG + cross-cluster dataset files ----
    // (qid, dataset_type) pairs consumed by any edge, to find terminal outputs
    std::set<std::pair<long long, std::string>> consumed;
    std::set<std::pair<CGSim::Job*, CGSim::Job*>> dag_edges;
    for (const auto& e : qgraph["edges"])
    {
        long long   pq = e["producer_qid"].get<long long>();
        long long   cq = e["consumer_qid"].get<long long>();
        std::string dt = e["dataset_type"].get<std::string>();
        consumed.insert({pq, dt});

        CGSim::Job* pjob = job_of[cluster_of[pq]];
        CGSim::Job* cjob = job_of[cluster_of[cq]];
        if (pjob == cjob) continue;   // intra-cluster: node-local intermediate, no file

        // Producer side only: the product is written and storage-accounted on
        // completion. It is not added to the consumer's input_files. Core now
        // resolves input locations at execution time, so consumer-side staging
        // is possible; this scaffold does not model it yet.
        std::string filename = dt + "_q" + std::to_string(pq);
        pjob->add_output_file(filename, std::to_string(dataset_bytes(dt, quanta[pq].outputs)) + "B");

        if (dag_edges.insert({pjob, cjob}).second) {
            std::string pid = pjob->get_id(), cid = cjob->get_id();
            pjob->add_child(cid, 0.0);
            cjob->add_parent(pid);
        }
    }

    // ---- External inputs (no producer in this qgraph, e.g. raw) and terminal outputs ----
    std::set<std::string> produced_types;
    for (auto& [qid, q] : quanta)
        for (const auto& out : q.outputs)
            produced_types.insert(out["dataset_type"].get<std::string>());

    for (auto& [qid, q] : quanta)
    {
        CGSim::Job* job = job_of[cluster_of[qid]];
        for (const auto& in : q.inputs) {
            std::string dt = in["dataset_type"].get<std::string>();
            if (produced_types.count(dt)) continue;
            std::string filename = dt + "_q" + std::to_string(qid);
            job->add_input_file(filename);
        }
        for (const auto& out : q.outputs) {
            std::string dt = out["dataset_type"].get<std::string>();
            if (consumed.count({qid, dt})) continue;
            job->add_output_file(dt + "_q" + std::to_string(qid), std::to_string(dataset_bytes(dt, q.outputs)) + "B");
        }
    }

    // ---- Roots are created at t=0; core sets child creation_time on release
    // (-1 = waiting on parents). A cycle would stall the simulation, so check. ----
    std::unordered_map<CGSim::Job*, int> remaining;
    std::vector<CGSim::Job*> order;
    for (auto& [key, job] : job_of) {
        remaining[job] = job->get_parents().size();
        if (remaining[job] == 0) {job->set_creation_time(0.0); order.push_back(job);}
        else job->set_creation_time(-1.0);
    }
    const size_t n_roots = order.size();
    for (size_t i = 0; i < order.size(); ++i)
        for (const auto& [cid, delay] : order[i]->get_children()) {
            CGSim::Job* child = job_of[job_by_id.at(cid)];
            if (--remaining[child] == 0) order.push_back(child);
        }
    if (order.size() != job_of.size())
        throw std::runtime_error("qgraph cluster DAG has a cycle");

    for (auto& [key, job] : job_of) jobs.push(job);

    std::cout << "QGRAPH_WORKLOAD: " << quanta.size() << " quanta -> "
              << job_of.size() << " cluster jobs ("
              << n_roots << " roots), site " << site << std::endl;
}
