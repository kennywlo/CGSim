#ifndef RUBIN_DISPATCHER_H
#define RUBIN_DISPATCHER_H

#include <map>
#include <iostream>
#include <string>
#include "CGSim.h"

// Site/CPU selection identical to SIMPLE_DISPATCHER. DAG gating is done by
// core: a job is only submitted once all parents declared via add_parent()
// have finished (src/core/actions.cpp).
class RUBIN_DISPATCHER
{

public:
  RUBIN_DISPATCHER(){};
 ~RUBIN_DISPATCHER(){};

  double      storage_needed(const std::unordered_map<std::string, std::string>& files);
  void        findAvailableCPU(CGSim::Job* j);
  void        assignJob(CGSim::Job* job);
};

#endif
