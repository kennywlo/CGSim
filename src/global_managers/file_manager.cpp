#include "file_manager.h"
#include "plugin.h"

namespace CGSim {

namespace GlobalManagers {

FileManager& FileManager::instance()
{
    static FileManager fm;
    return fm;
}

const bool FileManager::exists(const std::string& filename) const
{
    return global_file_map.count(filename) > 0;
}

const bool FileManager::exists(const std::string& filename, const std::string& sitename) const
{
    auto it = global_file_map.find(filename);
    if (it == global_file_map.end()) return false;
    return it->second->locations.count(sitename) > 0;
}

bool FileManager::remove(const std::string& filename, const std::string& sitename) 
{
    auto it=global_file_map.find(filename);
    if(it==global_file_map.end()) return false;
    auto* file=it->second;
    if(!file->locations.erase(sitename)) return false;
    rm->get_site(sitename)->remove_file(file);
    rm->USED_GRID_STORAGE-=file->size;
    if(file->locations.empty()) {delete file; global_file_map.erase(it);}
    return true;
}

const bool FileManager::is_in_flight(const std::string& filename, const std::string& src_site, const std::string& dst_site) const{
    return in_flight_transfers.find(generate_transfer_key(filename, src_site, dst_site)) != in_flight_transfers.end();
}

const std::string FileManager::generate_transfer_key(const std::string& filename, const std::string& src_site, const std::string& dst_site) const {
    return filename + "|" + src_site + "|" + dst_site;
}

void FileManager::register_site(sg4::NetZone* site, const std::unordered_map<std::string, unsigned long long>& files)
{

    const std::string& site_name = site->get_name();
    for (const auto& [file, size] : files) {create(file,size,site_name);}
}

File* FileManager::request_file(const std::string& filename)
{
    auto it = global_file_map.find(filename);
    if (it == global_file_map.end()) throw std::runtime_error("Requested File: " + filename +" does not exist");
    else return it->second;
}

void FileManager::create(const std::string& filename,const unsigned long long& size,const std::string& sitename)
{
    if(exists(filename,sitename)) return;
    auto* site=rm->get_site(sitename);
    if(site->get_available_storage()<size) throw std::runtime_error("Site: "+sitename+" is out of storage");
    auto it=global_file_map.find(filename);
    CGSim::File* file;

    if(it!=global_file_map.end())
    {
        file=it->second;
        if(file->size!=size) throw std::runtime_error("File: " + filename +" already exists with different size");
    }
    else
    {
        file=new CGSim::File();
        file->name=filename;
        file->size=size;
        global_file_map[filename]=file;
    }

    file->locations.insert(sitename);
    site->add_file(file);
    rm->USED_GRID_STORAGE+=size;
}

void FileManager::create(const std::string& filename,const std::string& size,const std::string& sitename){
    create(filename,CGSim::Utilities::parse_units_size(size),sitename);
}

void FileManager::create(const std::string& filename,const unsigned long long& size,const std::unordered_set<std::string>& locations){
    for(const auto& location:locations) create(filename,size,location);
}

void FileManager::create(const std::string& filename,const std::string& size,const std::unordered_set<std::string>& locations){
    create(filename,CGSim::Utilities::parse_units_size(size),locations);
}

sg4::IoPtr FileManager::internal_write(const std::string& filename, const unsigned long long& size, const std::string& comp_sitename, const std::string& comp_host, const std::string& comp_disk){

    if (!rm->site_exists(comp_sitename)) throw std::runtime_error("Site: "+comp_sitename+" does not exist");
    if (exists(filename)) throw std::runtime_error("File: "+filename+" already exists on the grid");
    auto disk = sg4::Host::by_name(comp_host)->get_disk_by_name(comp_disk);
    auto write_activity = sg4::Io::init()->set_disk(disk)->set_size(size)->set_op_type(sg4::Io::OpType::WRITE);
    write_activity->on_this_completion_cb([this,filename,size,comp_sitename](simgrid::s4u::Io const& io) 
    {create(filename,size,comp_sitename);});
    return write_activity;
}

void FileManager::write(const std::string& filename, const unsigned long long& size, const std::string& site, const std::string& cpu, const std::string& disk){

    auto write_activity = internal_write(filename, size, site, cpu, disk);

    write_activity->on_this_start_cb([this, filename, size, site, cpu, disk](simgrid::s4u::Io const& io) {
        plugin->onUserFileWriteStart(filename,size, site, cpu, disk);
    });

    write_activity->on_this_completion_cb([this, filename, size, site, cpu, disk](simgrid::s4u::Io const& io){
        plugin->onUserFileWriteEnd(filename,size, site, cpu, disk);
    });

    write_activity->start();
}

void FileManager::write(const std::string& filename, const std::string& size, const std::string& site, const std::string& cpu, const std::string& disk){

    write(filename,CGSim::Utilities::parse_units_size(size),site,cpu,disk);
}

sg4::IoPtr FileManager::internal_read(const std::string& filename, const std::string& comp_sitename, const std::string& comp_host, const std::string& comp_disk){

    if (!exists(filename)) throw std::runtime_error("File: " +filename+ " does not exist");
    auto disk = sg4::Host::by_name(comp_host)->get_disk_by_name(comp_disk);
    auto size_in_bytes = global_file_map.at(filename)->size;
    auto read_activity = sg4::Io::init()->set_disk(disk)->set_size(size_in_bytes)->set_op_type(sg4::Io::OpType::READ);

    read_activity->on_this_start_cb([this,filename,comp_sitename](simgrid::s4u::Io const& io) {
        if (!exists(filename,comp_sitename)) throw std::runtime_error("File: " +filename+
            " does not exist on Site: "+comp_sitename);});
    return read_activity;
}

void FileManager::read(const std::string& filename, const std::string& site, const std::string& cpu, const std::string& disk){

    auto read_activity = internal_read(filename, site , cpu, disk);
    auto size = global_file_map.at(filename)->size;

    read_activity->on_this_start_cb([this, filename, size, site, cpu, disk](simgrid::s4u::Io const& io) {
        plugin->onUserFileReadStart(filename,size, site, cpu, disk);
    });

    read_activity->on_this_completion_cb([this, filename, size, site, cpu, disk](simgrid::s4u::Io const& io){
        plugin->onUserFileReadEnd(filename,size, site, cpu, disk);
    });

    read_activity->start();
}

sg4::CommPtr FileManager::internal_transfer(const std::string& filename, const std::string& src_site, const std::string& dst_site, FileTransferDecisionMode mode){

    if(!exists(filename,src_site)) throw std::runtime_error("File: "+filename+" does not exist at Site: "+src_site+" so no transfer");
    if(exists(filename,dst_site))  throw std::runtime_error("File: "+filename+" already exists at Site: "+dst_site+" so no transfer");

    const std::string key = generate_transfer_key(filename, src_site, dst_site);
    if (!in_flight_transfers.insert(key).second) throw std::runtime_error("File transfer: " + key + " is already in progress");
    if(!(CGSim::GlobalManagers::get_resource_manager()->get_site(dst_site)->incoming_file_transfers.insert({filename,src_site}).second)) 
    throw std::runtime_error("File: " + filename + " already being transferred to site:  " + dst_site);

    auto src_host = sg4::Engine::get_instance()->host_by_name_or_null(src_site+"_communication_server");
    auto dst_host = sg4::Engine::get_instance()->host_by_name_or_null(dst_site+"_communication_server");
    auto size     = global_file_map.at(filename)->size;
    auto transfer_activity = sg4::Comm::sendto_init()->set_source(src_host)->set_destination(dst_host)->set_payload_size(size);
    transfer_activity->set_name("Transfer_File_" + filename + "_from_" + src_site + "_to_" + dst_site);
    ongoing_transfers[key] = transfer_activity;

    //@ToDo Remove Redundant block or maybe keep?
    transfer_activity->on_this_start_cb([this,key,mode,filename,size,src_site,dst_site]
        (simgrid::s4u::Comm const& co) 
        {
            if (!internal_transfers.insert(co.get_name()).second) return;
        });

    transfer_activity->on_this_completion_cb([this,transfer_activity,key,mode,filename,size,src_site,dst_site]
        (simgrid::s4u::Comm const& co) 
        {
            internal_transfers.erase(co.get_name());
            ongoing_transfers.erase(key);
            CGSim::GlobalManagers::get_resource_manager()->get_site(dst_site)->incoming_file_transfers.erase(filename);
            create(filename,size,dst_site);
            if(mode == CGSim::FileTransferDecisionMode::MOVE) remove(filename, src_site);
            in_flight_transfers.erase(key);
        });
    return transfer_activity;
  }

  void FileManager::transfer(const std::string& filename, const std::string& src_site, const std::string& dst_site, CGSim::FileTransferDecisionMode mode, const std::string& metadata){

    auto t = internal_transfer(filename, src_site, dst_site, mode);
    const auto size = global_file_map.at(filename)->size;

    t->on_this_start_cb([t, this, metadata, filename, size, src_site, dst_site](simgrid::s4u::Comm const& co) {
        if (!user_initiated_transfers.insert(co.get_name()).second) return;
        plugin->onUserFileTransferStart(filename,size,src_site,dst_site,metadata);
    });

    t->on_this_completion_cb([this, metadata, filename, size, src_site, dst_site](simgrid::s4u::Comm const& co){
        user_initiated_transfers.erase(co.get_name());
        plugin->onUserFileTransferEnd(filename,size,src_site,dst_site,metadata);
    });
    
    t->start();
}

} 

}
