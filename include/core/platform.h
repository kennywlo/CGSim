#ifndef PLATFORM_H
#define PLATFORM_H

#include <map>
#include <set>
#include <fstream>
#include <string>
#include <math.h>
#include <simgrid/s4u.hpp>
#include "parser.h"
#include <utility>
#include "host_extensions.h"
#include "file_manager.h"
#include "resource_manager.h"
#include "units_parser.h"
namespace sg4 = simgrid::s4u;

namespace CGSim { 

namespace Core {

class Platform
{
public:
    Platform(const std::string&  platform_name, std::vector<SiteInfo>& site_info,
        std::vector<SiteConnInfo>& site_conn_info);
    ~Platform()= default;


    void create_platform(const std::string& platform_name, const std::vector<SiteInfo>& all_site_info);
    void initialize_site_connections(std::vector<SiteConnInfo>& site_conn_info);
    static void initialize_simgrid_plugins();
    void initialize_job_server();
    void add_routes();
    sg4::NetZone* get_simgrid_platform(){return platform;}


private:
    sg4::NetZone* platform = nullptr;
    std::unordered_map<std::string, sg4::NetZone*> sites{};

};

}

}
#endif

