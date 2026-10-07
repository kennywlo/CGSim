#pragma once
#include <simgrid/s4u.hpp>
#include "job.h"
namespace sg4 = simgrid::s4u;

namespace CGSim::GlobalManagers
{
class ResourceManager;
}

namespace CGSim {

class Disk
{
public:
    double get_read_bandwidth();
    double get_write_bandwidth();
    std::string get_name();

private:
    std::string name{};
    sg4::Disk* simgrid_disk = nullptr;

    friend class ::CGSim::GlobalManagers::ResourceManager;
};

}