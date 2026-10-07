#ifndef PARSER_H
#define PARSER_H

#include <set>
#include <fstream>
#include "nlohmann/json.hpp"
#include <unordered_map>
#include <random>
#include <job.h>
#include <queue>
#include <list>
#include <sstream>
#include "units_parser.h"

namespace CGSim { 

namespace Core {

using namespace nlohmann;

//Information needed to a specify a Disk                                                      
struct DiskInfo {
  std::string   name{};
  std::string   read_bw{};
  std::string   write_bw{};
};

//Information needed to a specify a host (CPU)
struct CPUInfo {
  std::string                                              name{};
  int                                                      units{};
  int                                                      cores{};
  double                                                   speed{};
  std::string                                              BW_CPU{};
  std::string                                              LAT_CPU{};
  std::string                                              ram{};
  std::vector<DiskInfo>                                    disk_info{};
  std::unordered_map<std::string, std::string>             properties{};
};

struct SiteInfo {
  std::string                                              name{};
  std::vector<CPUInfo>                                     cpu_info{};
  std::unordered_map<std::string, std::string>             properties{};
  std::unordered_map<std::string, unsigned long long>      files{};
  std::string                                              storage{};
};

struct SiteConnInfo {
  std::string                 site_A{};
  std::string                 site_B{};
  std::string                 latency{};
  std::string                 bandwidth{};
};

class Parser
{
public:
  Parser(std::string  _siteConnInfoFile, std::string  _siteInfoFile, const std::set<std::string>& filteredSiteList);
 ~Parser()= default;
  std::vector<SiteInfo>                     getSiteInfo();
  std::vector<SiteConnInfo>                 getSiteConnInfo();

 
 
private:
  std::string                   siteConnInfoFile;
  std::string                   siteInfoFile;
  const std::set<std::string>   filteredSiteList;
};

}

}
#endif

