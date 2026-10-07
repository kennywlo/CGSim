#pragma once

namespace CGSim::GlobalManagers
{
  class FileManager;
}

namespace CGSim::Core
{
  class Actions;
  class JOB_EXECUTOR;
}


namespace CGSim {

class Site;
  
class File {
public:
  std::string get_name() {return name;}
  unsigned long	long get_size() {return size;}
  const std::unordered_set<std::string>& get_locations() const {return locations;}
  
private:
  std::string name{};
  unsigned long long size{};
  std::unordered_set<std::string> locations{};

  friend class ::CGSim::GlobalManagers::FileManager;
  friend class ::CGSim::Site;
  friend class ::CGSim::Core::Actions;
  friend class ::CGSim::Core::JOB_EXECUTOR;

};

}