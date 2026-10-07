#pragma once
#include <simgrid/s4u.hpp>
#include "job.h"
#include "file.h"
namespace sg4 = simgrid::s4u;

namespace CGSim {

namespace Core
{
class Platform;
class Actions;
class HostExtensions; 
class JOB_EXECUTOR; 
}

namespace GlobalManagers
{
class ResourceManager;
class FileManager;
}

class CPU;

class Site {
public:
    Site()=default;
    Site(const Site&)=delete;
    Site& operator=(const Site&)=delete;

    bool cpu_exists_at_site(const std::string& cpu_name) const;

    const std::vector<CPU*>& get_cpus() const noexcept{return cpus;}
    const std::unordered_set<std::string>& get_used_cpus_list() const noexcept{return used_cpus_list;}
    const std::deque<Job*>& get_pending_jobs() const noexcept{return pending_jobs;}
    const std::unordered_map<std::string,Job*>& get_assigned_jobs() const noexcept{return assigned_jobs;}
    const std::unordered_map<std::string,Job*>& get_running_jobs() const noexcept{return running_jobs;}
    const std::unordered_map<std::string,Job*>& get_finished_jobs() const noexcept{return finished_jobs;}
    const std::unordered_map<std::string,Job*>& get_failed_jobs() const noexcept{return failed_jobs;}

    double get_cpu_utilization() const noexcept{return total_cores?double(used_cores)/total_cores:0;}
    double get_memory_utilization() const noexcept{return total_memory?double(used_memory)/total_memory:0;}
  
    unsigned long get_number_of_total_cores() const noexcept{return total_cores;}
    unsigned long get_number_of_used_cores() const noexcept{return used_cores;}
    unsigned long get_number_of_total_cpus() const noexcept{return total_cpus;}
    unsigned long get_number_of_used_cpus() const noexcept{return used_cpus_list.size();}
    unsigned long long get_memory_capacity() const noexcept{return total_memory;}
    unsigned long long get_used_memory() const noexcept{return used_memory;}

    unsigned long long get_site_storage_capacity() const noexcept{return total_storage;}
    unsigned long long get_available_storage() const noexcept{return total_storage - used_storage;}
    double             get_storage_utilization() const noexcept{return (1.0*used_storage)/(1.0*total_storage);}

    void enable_job_assignment() noexcept{job_assignment_enabled=true;}
    void disable_job_assignment() noexcept{job_assignment_enabled=false;}
    bool is_job_assignment_enabled() const noexcept{return job_assignment_enabled;}

    void set_property(const std::string& k,const std::string& v){properties[k]=v;}
    const std::string& get_property(const std::string& k) const{return properties.at(k);}

    void set_max_retries(unsigned long n) noexcept{MAX_RETRIES=n;}
    unsigned long get_max_retries() const noexcept{return MAX_RETRIES;}

    std::unordered_map<std::string,std::string>& get_incoming_file_transfers() noexcept{return incoming_file_transfers;}
    const std::unordered_map<std::string,std::string>& get_incoming_file_transfers() const noexcept{return incoming_file_transfers;}

    const std::unordered_map<std::string, File*>& get_files() const noexcept {return files;}

private:
    std::string name{};
    unsigned long total_cores=0,used_cores=0,total_cpus=0,MAX_RETRIES=100000;
    unsigned long long total_memory=0,used_memory=0,total_storage=0,used_storage=0;
    std::vector<CPU*> cpus{};
    std::unordered_map<std::string, File*> files;
    std::unordered_map<std::string,sg4::Host*> simgrid_hosts{};
    std::unordered_set<std::string> used_cpus_list{};
    std::deque<Job*> pending_jobs{};
    std::unordered_map<std::string,Job*> assigned_jobs{},running_jobs{},finished_jobs{},failed_jobs{};
    std::unordered_map<std::string,std::string> properties{},incoming_file_transfers{};
    bool job_assignment_enabled=true;
    sg4::NetZone* simgrid_site=nullptr;

    void add_assigned_job(Job*),remove_assigned_job(Job*);
    void add_running_job(Job*),remove_running_job(Job*);
    void add_finished_job(Job*),add_failed_job(Job*);
    void add_cpu(CPU*);
    void add_file(File* file){files[file->name] = file; used_storage += file->size;}
    void remove_file(File* file){used_storage -= file->size; files.erase(file->name);}

    friend class CPU;
    friend class ::CGSim::Core::Platform;
    friend class ::CGSim::Core::Actions;
    friend class ::CGSim::Core::HostExtensions;
    friend class ::CGSim::Core::JOB_EXECUTOR;
    friend class GlobalManagers::ResourceManager;
    friend class GlobalManagers::FileManager;
};
}
