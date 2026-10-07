#pragma once
#include <simgrid/s4u.hpp>
#include "disk.h"
#include "job.h"
namespace sg4 = simgrid::s4u;

namespace CGSim::Core 
{
    class Platform;
}

namespace CGSim {

class Site;

class CPU {
public:
    const std::string& get_name() const noexcept;
    unsigned int get_cores_available() const;
    unsigned int get_cores_used() const;
    unsigned int get_total_cores() const;

    double get_cpu_utilization() const;
    double get_speed() const;

    unsigned long long get_memory_available() const;
    unsigned long long get_memory_used() const;
    double get_memory_utilization() const;

    const std::unordered_map<std::string,Job*>& get_assigned_jobs() const noexcept;
    const std::unordered_map<std::string,Job*>& get_running_jobs() const noexcept;
    const std::unordered_map<std::string,Job*>& get_finished_jobs() const noexcept;
    const std::unordered_map<std::string,Job*>& get_failed_jobs() const noexcept;

    void set_property(const std::string& k,const std::string& v){properties[k]=v;}
    const std::string& get_property(const std::string& k) const{return properties.at(k);}

    const std::vector<Disk*>& get_disks() const noexcept;

private:
    std::string name{};
    sg4::Host* simgrid_host=nullptr;
    std::unordered_map<std::string,Job*> assigned_jobs{},running_jobs{},finished_jobs{},failed_jobs{};
    std::unordered_map<std::string,std::string> properties{};
    std::vector<Disk*> disks{};

    void add_assigned_job(Job*),remove_assigned_job(Job*);
    void add_running_job(Job*),remove_running_job(Job*);
    void add_finished_job(Job*),add_failed_job(Job*);
    void add_disk(Disk*);

    friend class ::CGSim::Core::Platform;
    friend class ::CGSim::GlobalManagers::ResourceManager;
    friend class Site;
};

}