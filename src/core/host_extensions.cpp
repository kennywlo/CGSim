#include "host_extensions.h"
#include <iostream>

namespace CGSim { 

namespace Core {

simgrid::xbt::Extension<simgrid::s4u::Host, HostExtensions> HostExtensions::EXTENSION_ID;

void HostExtensions::registerJob(Job* j) {
    simgrid::kernel::actor::simcall_answered([this, j] {

        if(host->get_name().find("JOB-SERVER_cpu") != std::string::npos) throw std::runtime_error("Can't register job on main server");
        if(host->get_name().find("_communication_server") != std::string::npos) throw std::runtime_error("Can't register job on communication server: " + host->get_name());
        if(cores_available < j->cores) throw std::runtime_error("Job: " + j->id + " requires " + std::to_string(j->cores) + 
            " cores but was assigned to cpu " + host->get_name() + " which only has " + std::to_string(cores_available) + " cores available.");

        auto job_memory = CGSim::Utilities::parse_units_size(j->memory);
        if(memory_available < job_memory) throw std::runtime_error("Job: " + j->id + " requires " + std::to_string(job_memory) + 
            " bytes of memory but was assigned to cpu " + host->get_name() + " which only has " + std::to_string(memory_available) + " bytes of memory available.");


        job_ids.insert(j->id);
        cores_used       += j->cores;
        cores_available  -= j->cores;
        memory_used      += job_memory;
        memory_available -= job_memory;
        CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->used_cores += j->cores;
        CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->used_memory += job_memory;
        CGSim::GlobalManagers::get_resource_manager()->USED_GRID_CORES += j->cores; 
        CGSim::GlobalManagers::get_resource_manager()->USED_GRID_MEMORY += job_memory; 
        CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->used_cpus_list.insert(host->get_name());
        if(cores_available == 0 && available == true) {available = false;}
    });
}

void HostExtensions::onJobFinish(Job* j) {
    simgrid::kernel::actor::simcall_answered([this, j] {
        job_ids.erase(j->id);
        cores_used      -= j->cores;
        cores_available += j->cores;
        auto job_memory = CGSim::Utilities::parse_units_size(j->memory);
        memory_used      -= job_memory;
        memory_available += job_memory;
        CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->used_cores -= j->cores;
        CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->used_memory -= job_memory;
        CGSim::GlobalManagers::get_resource_manager()->USED_GRID_CORES -= j->cores;
        CGSim::GlobalManagers::get_resource_manager()->USED_GRID_MEMORY -= job_memory;   
        if(job_ids.size() == 0) CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->used_cpus_list.erase(host->get_name());
        if(cores_available > 0 && available == false) {available = true;}
    });
}

unsigned int HostExtensions::get_cores_used() const { return cores_used; }
unsigned int HostExtensions::get_cores_available() const { return cores_available; }

unsigned long long HostExtensions::get_memory_used() const { return memory_used; }
unsigned long long HostExtensions::get_memory_available() const { return memory_available; }

static void on_host_creation(simgrid::s4u::Host& h) {
    h.extension_set<HostExtensions>(new HostExtensions(&h));
}

void host_extension_init() {
    if (not HostExtensions::EXTENSION_ID.valid()) {
        HostExtensions::EXTENSION_ID = simgrid::s4u::Host::extension_create<HostExtensions>();
        simgrid::s4u::Host::on_creation_cb(&on_host_creation);
    }
}

}

}