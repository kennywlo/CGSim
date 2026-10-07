#include "disk.h"
#include "resource_manager.h"

namespace CGSim {


double Disk::get_read_bandwidth()
{
    return simgrid_disk->get_read_bandwidth();
}

double Disk::get_write_bandwidth()
{
    return simgrid_disk->get_write_bandwidth();
}

std::string Disk::get_name()
{
    return name;
}

}