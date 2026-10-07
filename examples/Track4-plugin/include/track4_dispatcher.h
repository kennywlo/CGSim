#ifndef TRACK4_DISPATCHER_H
#define TRACK4_DISPATCHER_H

#include <map>
#include <iostream>
#include <string>
#include "CGSim.h"

class TRACK4_DISPATCHER
{

public:
  TRACK4_DISPATCHER(){};
 ~TRACK4_DISPATCHER(){};

  double storage_needed(const std::unordered_map<std::string, std::string>& files);
  void   findAvailableCPU(CGSim::Job* j);
  void   assignJob(CGSim::Job* j);
};

#endif
