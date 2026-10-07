#include "track4_dispatcher.h"
#include <random>

double TRACK4_DISPATCHER::storage_needed(const std::unordered_map<std::string, std::string>& files) 
{
    long long sum = 0;
    for (const auto& [name, size] : files)
        sum += CGSim::Utilities::parse_units_size(size);
    return sum;
}

void TRACK4_DISPATCHER::findAvailableCPU(CGSim::Job* j)
{
  if(j->get_site().empty()) return;
  auto* site = CGSim::GlobalManagers::get_resource_manager()->get_site(j->get_site());
  if(site->get_pending_jobs().size() > 0) return;
  auto cpus = site->get_cpus();

  
  for(const auto& cpu: cpus)
  {
    if(cpu->get_cores_available() < j->get_cores()) continue;
    if(site->get_available_storage() < storage_needed(j->get_output_files())) continue;

    auto d = cpu->get_disks()[0]; //Change later
    j->set_disk(d->get_name());
    j->set_cpu(cpu->get_name());
    return;
  }
}

void TRACK4_DISPATCHER::assignJob(CGSim::Job* j)
{
  auto* site = CGSim::GlobalManagers::get_resource_manager()->get_site(j->get_site());
  j->set_flops(std::stol(site->get_property("GFLOPS"))*std::stod(j->get_property("cpu_consumption_time"))*j->get_cores());
  findAvailableCPU(j);
}
