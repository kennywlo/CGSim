#include "platform.h"

namespace CGSim { 

namespace Core {

Platform::Platform(const std::string&  platform_name, std::vector<SiteInfo>& all_site_info,
    std::vector<SiteConnInfo>& site_conn_info)
{
    this->create_platform(platform_name,all_site_info);
    this->initialize_site_connections(site_conn_info);
    this->initialize_job_server();
}

void Platform::create_platform(const std::string& platform_name, const std::vector<SiteInfo>& all_site_info)
{
    platform = sg4::create_full_zone(platform_name);
    initialize_simgrid_plugins();
    unsigned long grid_cores = 0;
    unsigned long long grid_storage = 0;
    unsigned long long grid_memory = 0;
    for (auto& site_info : all_site_info){
        auto* site = sg4::create_star_zone(site_info.name);
        auto* cgsim_site = CGSim::GlobalManagers::get_resource_manager()->create_site(site_info.name, site);
        site->set_parent(platform);
        unsigned long site_cores = 0;
        unsigned long long site_memory = 0;
        unsigned long long site_storage = CGSim::Utilities::parse_units_size(site_info.storage);
        for (const auto& [key,value] : site_info.properties){cgsim_site->set_property(key,value); site->set_property(key,value);}
        for (const auto& cpu_cluster : site_info.cpu_info) 
        {
            for (int cpu = 0; cpu < cpu_cluster.units; ++cpu) 
            {
                std::string cpu_name = site_info.name + "_cpu_" + cpu_cluster.name + "-" + std::to_string(cpu);
                sg4::Host* host = site->create_host(cpu_name, cpu_cluster.speed);
                auto* cgsim_cpu = CGSim::GlobalManagers::get_resource_manager()->create_cpu(cpu_name, host);
                host->set_core_count(cpu_cluster.cores);
                site_cores += cpu_cluster.cores;
                host->set_property("ram",cpu_cluster.ram);
                site_memory += CGSim::Utilities::parse_units_size(cpu_cluster.ram);
                for (const auto& [key,value] : cpu_cluster.properties){cgsim_cpu->set_property(key,value); host->set_property(key,value);}
                const sg4::Link* link = site->create_split_duplex_link("link_" + cpu_name,
                    cpu_cluster.BW_CPU)->set_latency(cpu_cluster.LAT_CPU)->seal();
                site->add_route(host, nullptr, {{link, sg4::LinkInRoute::Direction::UP}}, true);
                for (const auto& d : cpu_cluster.disk_info) 
                {
                    auto* simgrid_disk = host->create_disk(d.name, d.read_bw, d.write_bw);
                    auto* cgsim_disk = CGSim::GlobalManagers::get_resource_manager()->create_disk(d.name,simgrid_disk);
                    cgsim_cpu->add_disk(cgsim_disk);
                }
                host->seal();
                cgsim_site->add_cpu(cgsim_cpu);
            }
        }

        //Adding a host on the site which will handle it's communication
        const double       comm_host_CPU_SPEED = 0.0;
        const std::string  comm_host_BW_CPU = "10000000GBps";
        const std::string  comm_host_LAT_CPU = "0ns";
        const int          comm_host_cores = 1;
        const std::string  comm_host_ram = "4GB";
        const sg4::Link*   link = site->create_split_duplex_link("link_" + site_info.name+"_communication_server",
            comm_host_BW_CPU)->set_latency(comm_host_LAT_CPU)->seal();

        sg4::Host* comm_host = site->create_host(site_info.name+"_communication_server",comm_host_CPU_SPEED);
        comm_host->set_core_count(comm_host_cores);
        comm_host->set_property("ram",comm_host_ram);
        site->add_route(comm_host, nullptr, {{link, sg4::LinkInRoute::Direction::UP}}, true);
        site->set_gateway(comm_host->get_netpoint());
        comm_host->seal();

        site->set_property("total_cores",std::to_string(site_cores));
        site->set_property("total_memory",std::to_string(site_memory));
        cgsim_site->total_storage = site_storage;
        cgsim_site->total_cores = site_cores;
        cgsim_site->total_memory = site_memory;
        cgsim_site->total_cpus = cgsim_site->cpus.size();
        sites[site_info.name] = site;

        grid_storage += site_storage;
        grid_cores   += site_cores;
        grid_memory  += site_memory;

        CGSim::GlobalManagers::get_resource_manager()->print_site_info(site_info.name);
        CGSim::GlobalManagers::get_file_manager()->register_site(site,site_info.files);
    }
    platform->set_property("grid_cores",  std::to_string(grid_cores));
    platform->set_property("grid_storage",std::to_string(grid_storage));

    CGSim::GlobalManagers::get_resource_manager()->TOTAL_GRID_CORES = grid_cores;
    CGSim::GlobalManagers::get_resource_manager()->TOTAL_GRID_MEMORY = grid_memory;
    CGSim::GlobalManagers::get_resource_manager()->TOTAL_GRID_STORAGE = grid_storage;
}

void Platform::initialize_site_connections(std::vector<SiteConnInfo>& site_conn_info)
{
    for (const auto& siteConn : site_conn_info) {
        const auto src_name = siteConn.site_A;
        const auto dst_name = siteConn.site_B;
        const auto linkname = "link_" + siteConn.site_A+":"+siteConn.site_B;

        const sg4::NetZone* src = sites.at(src_name);
        const sg4::NetZone* dst = sites.at(dst_name);

        const sg4::Link* interzonal_link = platform->create_link(linkname, siteConn.bandwidth)->set_latency(siteConn.latency)->seal();
        platform->add_route(src, dst, { sg4::LinkInRoute(interzonal_link) });
    }
}

void Platform::initialize_simgrid_plugins()
{
    host_extension_init();
}

void Platform::initialize_job_server()
{
    auto* JOB_SERVER_site = sg4::create_star_zone("JOB-SERVER");
    JOB_SERVER_site->set_parent(platform);

    const double       JOB_SERVER_CPU_SPEED = 0.0;
    const std::string  JOB_SERVER_BW_CPU = "10000000GBps";
    const std::string  JOB_SERVER_LAT_CPU = "0ns";
    const int          JOB_SERVER_cores = 1;
    const std::string  JOB_SERVER_ram = "4GB";
    const sg4::Link*   JOB_SERVER_link = JOB_SERVER_site->create_link(
        "link_JOB-SERVER_cpu-0", JOB_SERVER_BW_CPU)->set_latency(JOB_SERVER_LAT_CPU)->seal();

    sg4::Host* JOB_SERVER_host = JOB_SERVER_site->create_host("JOB-SERVER_cpu-0", JOB_SERVER_CPU_SPEED);
    JOB_SERVER_host->set_core_count(JOB_SERVER_cores);
    JOB_SERVER_host->set_property("ram",JOB_SERVER_ram);
    JOB_SERVER_site->add_route(JOB_SERVER_host, nullptr, { { JOB_SERVER_link, sg4::LinkInRoute::Direction::UP}}, true);
    JOB_SERVER_site->set_gateway(JOB_SERVER_host->get_netpoint());
    JOB_SERVER_host->seal();

    for (auto& [site_name, site] : sites) {
        const auto linkname = "link_JOB_SERVER:" + site_name;
        const std::string latency = "0ms";
        const double bandwidth = 1000 * 1.25e+7;
        const sg4::Link* server_site_link = platform->create_link(linkname, bandwidth)->set_latency(latency)->seal();
        platform->add_route(JOB_SERVER_site, site, {sg4::LinkInRoute(server_site_link)});
    }
}

}

}
