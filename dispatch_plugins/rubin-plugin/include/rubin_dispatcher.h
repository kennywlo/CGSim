#ifndef RUBIN_DISPATCHER_H
#define RUBIN_DISPATCHER_H

#include <map>
#include <iostream>
#include <string>
#include "CGSim.h"
#include "qgraph_workload.h"

// Site/CPU selection identical to SIMPLE_DISPATCHER, plus the DAG gate:
// a job whose parent clusters have not all finished is left "pending",
// which core's job_executor re-polls after every execution completion
// (util/job_executor.cpp start_server loop).
class RUBIN_DISPATCHER
{

public:
  RUBIN_DISPATCHER(QGRAPH_WORKLOAD* workload) : workload(workload) {};
 ~RUBIN_DISPATCHER(){};

  double      storage_needed(std::unordered_map<std::string, long long>& files);
  sg4::Host*  findAvailableCPU(const std::vector<sg4::Host*>& cpus, Job* j);
  Job*        assignJob(Job* job);

private:
  QGRAPH_WORKLOAD* workload;
  sg4::NetZone* platform = sg4::Engine::get_instance()->get_netzone_root();
};

#endif
