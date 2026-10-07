#ifndef JOB_H
#define JOB_H

#include <queue>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
#include <stdexcept>

namespace CGSim::Core
{
class Actions;
class JOB_EXECUTOR;
class HostExtensions;
}

namespace CGSim::GlobalManagers
{
class FileManager;
}


namespace CGSim {
    
class Site;
class CPU;
class Disk;

enum struct STATUS {
    GLOBAL_PENDING,
    SITE_PENDING,
    ASSIGNED,
    RUNNING,
    FINISHED,
    FAILED,
    NONE
};


class Job {
public:
    void set_id(std::string& v) { id = v; }
    void set_creation_time(double v) { creation_time = v; }
    void set_flops(long long v) { flops = v; }
    void set_cores(int v) { cores = v; }
    void set_disk(const std::string& v) { disk = v; }
    void set_memory_usage(const std::string& v) { memory = v; }
    void set_site(const std::string& v) { site = v; }
    void set_cpu(const std::string& v) { cpu = v; }
    void set_input_files(const std::unordered_set<std::string>& v) {input_files = v;}
    void set_output_files(const std::unordered_map<std::string, std::string>& v) {output_files = v;}
    void add_input_file(const std::string& v) { input_files.insert(v); }
    void add_output_file(const std::string& f, const std::string& s) { output_files[f] = s; }
    void add_parent(std::string& parent) {parents.insert(parent);}
    void add_child(std::string& child, double time) {children[child] = time;}
    void set_property(const std::string& key, const std::string& value) {metadata[key] = value;}

    std::string get_id() const {return id;}
    double get_creation_time() const { return creation_time; }
    double get_submission_time() const { return submission_time; }
    std::string get_status() const { return status_string.at(status); }

    long long get_flops() const { return flops; }
    int get_cores() const { return cores; }
    int get_retries() const { return retries; }

    const std::string& get_disk() const { return disk; }
    const std::string& get_memory_usage() const { return memory; }
    const std::string& get_site() const { return site; }
    const std::string& get_cpu() const { return cpu; }

    double get_disk_read_bw() const { return disk_read_bw; }
    double get_disk_write_bw() const { return disk_write_bw; }
    double get_cpu_speed() const { return cpu_speed; }
    double get_cpu_consumption_time() const { return cpu_consumption_time; }
    double get_total_io_read_time() const { return total_io_read_time; }
    double get_total_io_write_time() const { return total_io_write_time; }
    double get_file_transfer_queue_time() const { return file_transfer_queue_time; }
    double get_resource_waiting_queue_time() const { return resource_waiting_queue_time; }

    const std::unordered_set<std::string>& get_input_files() const {return input_files;}
    const std::unordered_map<std::string, std::string>& get_output_files() const {return output_files;}
    long get_number_of_files_written() const {return files_written;}
    const std::unordered_set<std::string>& get_parents() const {return parents;}
    const std::unordered_map<std::string, double>& get_children() const {return children;}
    std::string get_property(const std::string& key) const {return metadata.at(key);}

    bool operator<(const Job& other) const {return creation_time > other.creation_time;}

private:
    // Basic job info
    std::string id{};
    double creation_time{-1.0};
    double submission_time{};
    CGSim::STATUS status{CGSim::STATUS::NONE};

    // Resources
    long long flops{};
    int cores{};
    int retries{};
    std::string disk{};
    std::string memory{"0B"};
    std::string site{};
    std::string cpu{};

    // Performance
    double disk_read_bw{};
    double disk_write_bw{};
    double cpu_speed{};
    double cpu_consumption_time{};
    double total_io_read_time{};
    double total_io_write_time{};
    double file_transfer_queue_time{};
    double resource_waiting_queue_time{};

    // Files
    std::unordered_set<std::string> input_files{};
    std::unordered_map<std::string, std::string> output_files{};
    long files_written{};

    // Metadata / dependencies
    std::unordered_map<std::string, std::string> metadata{};
    std::unordered_set<std::string> parents{};
    std::unordered_map<std::string, double> children{};

    std::unordered_map<STATUS,std::string> status_string = {
    {CGSim::STATUS::GLOBAL_PENDING,"global_pending"},
    {CGSim::STATUS::SITE_PENDING,"site_pending"},
    {CGSim::STATUS::ASSIGNED,"assigned"},
    {CGSim::STATUS::RUNNING,"running"},
    {CGSim::STATUS::FINISHED,"finished"},
    {CGSim::STATUS::FAILED,"failed"},
    {CGSim::STATUS::NONE,"none"}};

    friend class ::CGSim::Core::Actions;
    friend class ::CGSim::Core::JOB_EXECUTOR;
    friend class ::CGSim::Core::HostExtensions;
    friend class ::CGSim::GlobalManagers::FileManager;
    friend class Site;
    friend class CPU;
    friend class Disk;

};

struct JobPtrCompare {
    bool operator()(const Job* a, const Job* b) const {
        const bool a_negative = a->get_creation_time() < 0;
        const bool b_negative = b->get_creation_time() < 0;
        if (a_negative != b_negative) return a_negative;
        return a->get_creation_time() > b->get_creation_time();
    }
};

class JobQueue {
public:
    void push(Job* job) {if(!((ids.insert(job->get_id())).second)) throw std::runtime_error("Job IDs must be unique"); queue.push(job);} 
    void pop() {if (queue.empty())return; ids.erase(queue.top()->get_id()); queue.pop();}
    Job* top() { return queue.empty() ? nullptr : queue.top();}
    bool empty() const { return queue.empty();}
    std::size_t size() const { return queue.size();}
    bool contains(std::string id) const {return ids.find(id) != ids.end();}

private:
    void dag_push(Job* job) {queue.push(job);}
    std::priority_queue<Job*, std::vector<Job*>, JobPtrCompare> queue;
    std::unordered_set<std::string> ids;

    friend class ::CGSim::Core::Actions;
    friend class ::CGSim::Core::JOB_EXECUTOR;
};

}

#endif
