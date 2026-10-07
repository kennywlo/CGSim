#include "resource_manager.h"
#include "print.h"

namespace CGSim::GlobalManagers {

ResourceManager& ResourceManager::instance(){static ResourceManager rm; return rm;}

Site* ResourceManager::get_site(const std::string& n)
{
    auto it=global_site_map.find(n);
    if(it==global_site_map.end()) throw std::runtime_error("Site does not Exist");
    return it->second;
}

void ResourceManager::print_site_info(const std::string& n){CGSim::Utilities::print_site(n);}

Site* ResourceManager::create_site(const std::string& n,sg4::NetZone* z)
{
    auto* s=new Site;
    s->name=n; s->simgrid_site=z;
    list_of_sites.insert(n);
    global_site_map[n]=s;
    return s;
}

CPU* ResourceManager::create_cpu(const std::string& n,sg4::Host* h)
{
    auto* c=new CPU;
    c->name=n; c->simgrid_host=h;
    global_cpu_map[n]=c;
    return c;
}

Disk* ResourceManager::create_disk(const std::string& n,sg4::Disk* d)
{
    auto* x=new Disk;
    x->name=n; x->simgrid_disk=d;
    return x;
}

double ResourceManager::get_connection_bandwidth(const std::string& site1_name, const std::string& site2_name)
{
    sg4::Link* link = sg4::Link::by_name_or_null("link_" + site1_name + ":" + site2_name);
    if (!link) link = sg4::Link::by_name_or_null("link_" + site2_name + ":" + site1_name);
    if (!link) throw std::runtime_error("Link not found");
    return link->get_bandwidth(); 
}
  
double ResourceManager::get_connection_latency(const std::string& site1_name, const std::string& site2_name)
{
    sg4::Link* link = sg4::Link::by_name_or_null("link_" + site1_name + ":" + site2_name);
    if (!link) link = sg4::Link::by_name_or_null("link_" + site2_name + ":" + site1_name);
    if (!link) throw std::runtime_error("Link not found");
    return link->get_latency();
}
  
double ResourceManager::get_connection_load(const std::string& site1_name, const std::string& site2_name)
{
    sg4::Link* link = sg4::Link::by_name_or_null("link_" + site1_name + ":" + site2_name);
    if (!link) link = sg4::Link::by_name_or_null("link_" + site2_name + ":" + site1_name);
    if (!link) throw std::runtime_error("Link not found");
    return link->get_load();
}

}
