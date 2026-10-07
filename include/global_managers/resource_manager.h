#pragma once
#include <string>
#include <unordered_map>
#include <stdexcept>
#include <unordered_set>
#include <vector>
#include <deque>
#include <simgrid/s4u.hpp>
#include "job.h"
#include "units_parser.h"
#include "site.h"
#include "cpu.h"

namespace sg4 = simgrid::s4u;
int main(int argc, char** argv);

namespace CGSim::Core
{
class Platform;
class JOB_EXECUTOR;
class HostExtensions;
}

namespace CGSim::GlobalManagers 
{
class FileManager;
}

namespace CGSim {

namespace GlobalManagers {

class ResourceManager {
public:
    ResourceManager(const ResourceManager&)=delete;
    ResourceManager& operator=(const ResourceManager&)=delete;
    static ResourceManager& instance();

    unsigned long get_total_grid_cores() const noexcept{return TOTAL_GRID_CORES;}
    unsigned long get_used_grid_cores() const noexcept{return USED_GRID_CORES;}
    unsigned long long get_total_grid_memory_capacity() const noexcept{return TOTAL_GRID_MEMORY;}
    unsigned long long get_used_grid_memory() const noexcept{return USED_GRID_MEMORY;}
    unsigned long long get_total_grid_storage_capacity() const noexcept{return TOTAL_GRID_STORAGE;}
    unsigned long long get_used_grid_storage() const noexcept{return USED_GRID_STORAGE;}

    double get_grid_cpu_utilization() const noexcept{return TOTAL_GRID_CORES?double(USED_GRID_CORES)/TOTAL_GRID_CORES:0.0;}
    double get_grid_memory_utilization() const noexcept{return TOTAL_GRID_MEMORY?double(USED_GRID_MEMORY)/TOTAL_GRID_MEMORY:0.0;}
    double get_grid_storage_utilization() const noexcept{return TOTAL_GRID_STORAGE?double(USED_GRID_STORAGE)/TOTAL_GRID_STORAGE:0.0;}


    const std::unordered_map<std::string,Job*>& get_global_pending_jobs() const noexcept{return global_pending_jobs;}
    const std::unordered_map<std::string,Job*>& get_global_failed_jobs() const noexcept{return global_failed_jobs;}

    void set_custom_parameter(const std::string& k,const std::string& v){Custom_Parameters[k]=v;}
    const std::string& get_custom_parameter(const std::string& k) const{return Custom_Parameters.at(k);}

    const std::unordered_set<std::string>& get_list_of_sites() const noexcept{return list_of_sites;}
    const std::unordered_map<std::string,Site*>& get_all_sites() const noexcept{return global_site_map;}
    const std::unordered_map<std::string,CPU*>& get_all_cpus() const noexcept{return global_cpu_map;}

    Site* get_site(const std::string& site_name);
    CPU* get_cpu(const std::string& n) const{return global_cpu_map.at(n);}

    bool site_exists(const std::string& n) const noexcept{return global_site_map.count(n);}
    bool cpu_exists(const std::string& n) const noexcept{return global_cpu_map.count(n);}

    double get_connection_bandwidth(const std::string& site1_name, const std::string& site2_name);
    double get_connection_latency(const std::string& site1_name, const std::string& site2_name);
    double get_connection_load(const std::string& site1_name, const std::string& site2_name);
  
private:
    ResourceManager()=default;

    Site* create_site(const std::string&,sg4::NetZone*);
    CPU* create_cpu(const std::string&,sg4::Host*);
    Disk* create_disk(const std::string&,sg4::Disk*);
    void print_site_info(const std::string&);

    std::unordered_set<std::string> list_of_sites{};
    std::unordered_map<std::string,Site*> global_site_map{};
    std::unordered_map<std::string,CPU*> global_cpu_map{};
    std::unordered_map<std::string,Job*> global_pending_jobs{},global_failed_jobs{};

    unsigned long TOTAL_GRID_CORES=0,USED_GRID_CORES=0;
    unsigned long long TOTAL_GRID_MEMORY=0,USED_GRID_MEMORY=0;
    unsigned long long TOTAL_GRID_STORAGE=0,USED_GRID_STORAGE=0;
    std::unordered_map<std::string,std::string> Custom_Parameters{};

    friend int ::main(int,char**);
    friend class ::CGSim::Core::Platform;
    friend class ::CGSim::Core::JOB_EXECUTOR;
    friend class ::CGSim::Core::HostExtensions;
    friend class ::CGSim::GlobalManagers::FileManager;
};

inline ResourceManager* get_resource_manager(){return &ResourceManager::instance();}

}

}
