#include <iostream>
#include <vector>
#include <map>
#include <set>
#include <fstream>
#include <string>
#include <memory>
#include <cmath>
#include <chrono>
#include <list>
#include <simgrid/s4u.hpp>
#include "parser.h"
#include "platform.h"
#include "version.h"
#include "logger.h"
#include "job_executor.h"
#include "file_manager.h"
#include "resource_manager.h"
#include "print.h"

int main(int argc, char** argv)
{
    //CGSim Logo
    CGSim::Utilities::Statistics::start();
    CGSim::Utilities::print_CGSim_Logo();
  
    //Initialize Logging
    CGSim::Utilities::logger::init();
    const std::string usage = std::string("usage: ") + argv[0] + " -c config.json";

    //Read in Configuration
    if (argc != 3 || std::string(argv[1]) != "-c") {throw std::runtime_error(usage);}
    const std::string configFile = argv[2];
    CG_SIM_LOG_INFO("Reading in configuration from: {}", configFile);

    std::ifstream in(configFile);
    if (!in.is_open()) { throw std::runtime_error("could not open configuration file");}
    auto j = nlohmann::json::parse(in);

    //Configuration Elements
    const std::string gridName                     = j["Grid_Name"];
    const std::string siteInfoFile                 = j["Sites_Information"];
    const std::string siteConnInfoFile             = j["Sites_Connection_Information"];
    const std::string pluginPath                   = j["Plugin"];
    const std::set<std::string> filteredSiteList   = j["Limited_Sites"].get<std::set<std::string>>();

    //Make Grid Name Accesible Globally
    CGSim::GlobalManagers::get_resource_manager()->set_custom_parameter("Grid Name", gridName);

    //Parse Input
    std::unique_ptr<CGSim::Core::Parser> parser = std::make_unique<CGSim::Core::Parser>(siteConnInfoFile, siteInfoFile, filteredSiteList);
    auto sitesInfo     = parser->getSiteInfo();
    auto siteConnInfo  = parser->getSiteConnInfo();

    // Initialize SimGrid
    sg4::Engine e(&argc, argv);
    //simgrid::s4u::Engine::set_config("precision/timing", 1e-3);

    // Create the platform
    std::unique_ptr<CGSim::Core::Platform> pf = std::make_unique<CGSim::Core::Platform>(gridName, sitesInfo, siteConnInfo);
    auto* platform = pf->get_simgrid_platform();
    for (auto& [key, value] : j["Custom_Parameters"].items()) 
    {
        platform->set_property(key,value.get<std::string>()); 
        CGSim::GlobalManagers::get_resource_manager()->set_custom_parameter(key,value);
    }

    CGSim::Utilities::PluginLoader<CGSim::Plugin> plugin_loader;
    auto unique_plugin = plugin_loader.load(pluginPath);
    std::shared_ptr<CGSim::Plugin> plugin = std::move(unique_plugin);

    // Create and set up executor
    CGSim::Core::JOB_EXECUTOR::set_plugin(plugin);
    CGSim::GlobalManagers::FileManager::set_plugin(plugin);
    plugin->beforeSimulationStart();
    CGSim::Core::JOB_EXECUTOR::start_job_execution();

    // Print version
    CG_SIM_LOG_INFO("CGSim version: {}.{}.{}", MAJOR_VERSION, MINOR_VERSION, BUILD_NUMBER);

    return 0;
}
