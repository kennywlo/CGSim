#include "parser.h"
#include <fstream>
#include <list>
#include <random>
#include <iomanip>
#include <algorithm>
#include <nlohmann/json.hpp>
#include <iostream>
#include <utility>

namespace CGSim { 

namespace Core {

using json = nlohmann::json;

Parser::Parser(std::string _siteConnInfoFile,
               std::string _siteInfoFile,
               const std::set<std::string>& _filteredSiteList)
    : siteConnInfoFile(std::move(_siteConnInfoFile)),
      siteInfoFile(std::move(_siteInfoFile)),
      filteredSiteList(_filteredSiteList){}

std::vector<SiteInfo> Parser::getSiteInfo() {

    std::ifstream in(siteInfoFile);
    if (!in.is_open()) throw std::runtime_error("Could not open site info file");
    json j;
    try {j = json::parse(in);}
    catch (const json::parse_error& e) {throw std::runtime_error(e.what());}

    std::vector<SiteInfo> sites;

    for (auto& [site_name, site_json] : j.items()) {

        if (!filteredSiteList.empty() && filteredSiteList.count(site_name) == 0) continue;
        SiteInfo site;
        site.name = site_name;
        site.storage = site_json.value("storage", "");

        // --- PROPERTIES ---
        for (auto& [key, value] : site_json["SITE_PROPERTIES"].items()) {
            site.properties[key] = value.get<std::string>();
        }

        // --- CPU INFO ---
        for (auto& cpu_json : site_json["CPUInfo"]) {
            CPUInfo        cpu;
            cpu.name     = cpu_json.value("name", "");
            cpu.units    = cpu_json.value("units", 0);
            cpu.cores    = cpu_json.value("cores", 0);
            cpu.speed    = cpu_json.value("speed", 0.0);
            cpu.BW_CPU   = cpu_json.value("BW_CPU", "");
            cpu.LAT_CPU  = cpu_json.value("LAT_CPU", "");
            cpu.ram      = cpu_json.value("ram", "");

            //Properties
            for (auto& prop_obj : cpu_json["properties"]) {
                for (auto& [key, value] : prop_obj.items()) {
                    cpu.properties[key] = value.get<std::string>();
                }
            }


            // --- Disks ---
            for (auto& disk_json : cpu_json["disks"]) {
                DiskInfo disk;
                disk.name = disk_json.value("name", "");
                disk.read_bw = disk_json.value("read_bw", "");
                disk.write_bw = disk_json.value("write_bw", "");
                cpu.disk_info.push_back(disk);
            }

            if (cpu.units != 0) site.cpu_info.push_back(cpu);
        }

        // --- Files ---
        for (auto& file : site_json["files"]) 
        {
            std::string name = file[0].get<std::string>();
            unsigned long long size = file[1].is_string() ? CGSim::Utilities::parse_units_size(file[1].get<std::string>()) : file[1].get<unsigned long long>();
            site.files[name] = size;
        }

        sites.push_back(site);
    }

    return sites;
}


std::vector<SiteConnInfo> Parser::getSiteConnInfo()
{
    std::ifstream in(siteConnInfoFile);
    if (!in.is_open()) throw std::runtime_error("Could not open site connections file");
    json j;
    try {j = json::parse(in);}
    catch (const json::parse_error& e) {throw std::runtime_error(e.what());}

    std::vector<SiteConnInfo> connections;

    // Iterate over all connections
    for (auto& [key, val] : j.items()) {
        auto pos = key.find(':');
        if (pos == std::string::npos) continue;

        SiteConnInfo conn;
        conn.site_A = key.substr(0, pos);
        conn.site_B = key.substr(pos + 1);

        if (!filteredSiteList.empty() && filteredSiteList.count(conn.site_A) == 0) continue;
        if (!filteredSiteList.empty() && filteredSiteList.count(conn.site_B) == 0) continue;

        conn.bandwidth = val.value("bandwidth", "");
        conn.latency   = val.value("latency", "");

        connections.push_back(conn);
    }
 
    return connections;
}

}

}