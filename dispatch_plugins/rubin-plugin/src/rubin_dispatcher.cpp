#include "rubin_dispatcher.h"

double RUBIN_DISPATCHER::storage_needed(const std::unordered_map<std::string, std::string>& files) {
    unsigned long long sum = 0;
    for (const auto& [_, size] : files)
        sum += CGSim::Utilities::parse_units_size(size);
    return sum;
  }

void RUBIN_DISPATCHER::findAvailableCPU(CGSim::Job* j)
{
    if (j->get_site().empty()) return;
    auto* site = CGSim::GlobalManagers::get_resource_manager()->get_site(j->get_site());

    for(const auto& cpu: site->get_cpus())
    {
        if(cpu->get_name().find("_communication") != std::string::npos) continue;
        if(cpu->get_name().find("JOB-SERVER") != std::string::npos) continue;
        if(cpu->get_cores_available() < j->get_cores()) continue;
        if(site->get_available_storage() < storage_needed(j->get_output_files())) continue;

        auto d = cpu->get_disks()[0];

        j->set_disk(d->get_name());
        j->set_cpu(cpu->get_name());
        // Job takes cpu_consumption_time seconds on the chosen CPU's cores.
        j->set_flops(cpu->get_speed()*std::stod(j->get_property("cpu_consumption_time"))*j->get_cores());
        return;
    }
}

void RUBIN_DISPATCHER::assignJob(CGSim::Job* job)
{
  // TODO(Raees): queue routing by request memory (schema section 9) — pick the
  // (site, queue) tier matching job->get_memory_usage() instead of first-fit CPU.
  findAvailableCPU(job);
}
