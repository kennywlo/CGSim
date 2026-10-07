#ifndef TRACK4_WORKLOAD_MANAGER_H
#define TRACK4_WORKLOAD_MANAGER_H

#include "CGSim.h"
#include <fstream>
#include <sstream>

class TRACK4_WORKLOAD_MANAGER {

public:
    TRACK4_WORKLOAD_MANAGER(){};
   ~TRACK4_WORKLOAD_MANAGER(){};
    void setWorkload(CGSim::JobQueue& jobs);

private:

   std::vector<std::string> parseCSVLine(const std::string& line);
   std::string getColumn(const std::vector<std::string>& row,
                       const std::unordered_map<std::string,int>& column_map,
                       const std::string& key,
                       const std::string& default_val = "");
};


#endif //TRACK4_WORKLOAD_MANAGER_H
