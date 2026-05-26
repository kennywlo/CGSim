#include "file_manager.h"

namespace CGSim {

std::unordered_map<std::string,std::unordered_set<std::string>>  FileManager::SiteFiles;
std::unordered_map<std::string, std::unordered_set<std::string>> FileManager::FileSites;
std::unordered_map<std::string, unsigned long long>              FileManager::FileSizes;
std::unordered_map<std::string,  long long>              FileManager::SiteStorages;


FileManager* FileManager::instance() {
    static FileManager instance; 
    return &instance;
}

bool FileManager::exists(const std::string& filename)
{
return FileSizes.count(filename) > 0;
}

bool FileManager::exists(const std::string& filename, const std::string& sitename)
{
return SiteFiles.at(sitename).count(filename) > 0;
}

bool FileManager::remove(const std::string& filename, const std::string& sitename)
{
return (FileSizes.erase(filename) > 0 && SiteFiles.at(sitename).erase(filename) > 0 && FileSites.at(filename).erase(sitename) > 0);
}

void FileManager::register_site(sg4::NetZone* site, const std::unordered_map<std::string, long long>& files){

    const std::string& site_name = site->get_name();
    SiteStorages[site_name] = std::stoll(site->get_property("storage_capacity_bytes"));
    SiteFiles[site_name];   // ensure entry exists even when no files are pre-registered

    for (const auto& [file, size] : files) {
        SiteFiles[site_name].insert(file);
        FileSizes[file] = size;
        FileSites[file].insert(site_name);
        SiteStorages[site_name] -= size;
        if (SiteStorages[site_name] < 0) throw std::runtime_error("Site "+site_name+" is out of storage");
    }
}

Job* FileManager::request_file_location(Job* j){
    for(auto& [file,file_info]: j->input_files)
    {
        if (!exists(file)) throw std::runtime_error("File: " +file+ " does not exist");
        file_info.first  = FileSizes.at(file);
        file_info.second = FileSites.at(file);
    }
    return j;
}

unsigned long long FileManager::request_file_size(const std::string& filename)
{
    if (!exists(filename)) throw std::runtime_error("File: " +filename+ " does not exist");
    return FileSizes.at(filename);

}

unsigned long long FileManager::request_remaining_grid_storage() {
    long long total = 0;
    for (const auto& [key, value] : SiteStorages) {
        total += value;
    }
    return total;
}

unsigned long long FileManager::request_remaining_site_storage(const std::string& sitename) {
    if (SiteStorages.count(sitename) == 0) throw std::runtime_error("Site"+sitename+" does not exist");
    return SiteStorages.at(sitename);
}

void FileManager::create(const std::string& filename, const unsigned long long& size, const std::string& sitename){

    //Check if Site exists
    if (SiteFiles.count(sitename) == 0) throw std::runtime_error("Site"+sitename+" does not exist");

    SiteFiles[sitename].insert(filename);
    FileSites[filename].insert(sitename);
    FileSizes[filename] = size;
    SiteStorages[sitename] -= size;

    if (SiteStorages[sitename] < 0) throw std::runtime_error("Site "+sitename+" is out of storage");
}

sg4::IoPtr FileManager::write(const std::string& filename, const unsigned long long& size, const std::string& comp_sitename, const std::string& comp_host, const std::string& comp_disk){

    if (SiteFiles.count(comp_sitename) == 0) throw std::runtime_error("Site"+comp_sitename+" does not exist");
    auto disk = sg4::Host::by_name(comp_host)->get_disk_by_name(comp_disk);
    auto write_activity = sg4::Io::init()->set_disk(disk)->set_size(size)->set_op_type(sg4::Io::OpType::WRITE);
    write_activity->on_this_completion_cb([filename,size,comp_sitename](simgrid::s4u::Io const& io) {
        create(filename,size,comp_sitename);
      });
    return write_activity;
}

sg4::IoPtr FileManager::read(const std::string& filename, const std::string& comp_sitename, const std::string& comp_host, const std::string& comp_disk){

    if (!exists(filename)) throw std::runtime_error("File: " +filename+ " does not exist");
    auto disk = sg4::Host::by_name(comp_host)->get_disk_by_name(comp_disk);
    auto size_in_bytes = FileSizes.at(filename);
    auto read_activity = sg4::Io::init()->set_disk(disk)->set_size(size_in_bytes)->set_op_type(sg4::Io::OpType::READ);

    read_activity->on_this_start_cb([filename,comp_sitename](simgrid::s4u::Io const& io) {
        if (!exists(filename,comp_sitename)) throw std::runtime_error("File: " +filename+
            " does not exist on Site: "+comp_sitename+" does not exist");});
    return read_activity;
}

} 

