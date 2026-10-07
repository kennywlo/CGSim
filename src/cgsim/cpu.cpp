#include "cpu.h"
#include "resource_manager.h"
#include "host_extensions.h"

namespace CGSim {

void CPU::add_assigned_job(Job* j){assigned_jobs[j->id]=j;}
void CPU::remove_assigned_job(Job* j){assigned_jobs.erase(j->id);}
void CPU::add_running_job(Job* j){running_jobs[j->id]=j;}
void CPU::remove_running_job(Job* j){running_jobs.erase(j->id);}
void CPU::add_finished_job(Job* j){finished_jobs[j->id]=j;}
void CPU::add_failed_job(Job* j){failed_jobs[j->id]=j;}
void CPU::add_disk(Disk* d){disks.push_back(d);}

const std::string& CPU::get_name() const noexcept{return name;}
const std::vector<Disk*>& CPU::get_disks() const noexcept{return disks;}

const std::unordered_map<std::string,Job*>& CPU::get_assigned_jobs() const noexcept{return assigned_jobs;}
const std::unordered_map<std::string,Job*>& CPU::get_running_jobs() const noexcept{return running_jobs;}
const std::unordered_map<std::string,Job*>& CPU::get_finished_jobs() const noexcept{return finished_jobs;}
const std::unordered_map<std::string,Job*>& CPU::get_failed_jobs() const noexcept{return failed_jobs;}

unsigned int CPU::get_cores_available() const
{
    return simgrid_host->extension<Core::HostExtensions>()->get_cores_available();
}

unsigned int CPU::get_cores_used() const
{
    return simgrid_host->extension<Core::HostExtensions>()->get_cores_used();
}

unsigned int CPU::get_total_cores() const
{
    return simgrid_host->get_core_count();
}

double CPU::get_cpu_utilization() const
{
    auto total=simgrid_host->get_core_count();
    return total?double(get_cores_used())/total:0.0;
}

double CPU::get_speed() const
{
    return simgrid_host->get_speed();
}

unsigned long long CPU::get_memory_available() const
{
    return simgrid_host->extension<Core::HostExtensions>()->get_memory_available();
}

unsigned long long CPU::get_memory_used() const
{
    return simgrid_host->extension<Core::HostExtensions>()->get_memory_used();
}

double CPU::get_memory_utilization() const
{
    auto total=Utilities::parse_units_size(simgrid_host->get_property("ram"));
    return total?double(get_memory_used())/total:0.0;
}

}