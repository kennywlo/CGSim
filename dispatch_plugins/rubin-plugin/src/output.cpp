#include "output.h"
#include <filesystem>

void OUTPUT::initialize()
{
    if (initialized) return;
    std::string file_name = CGSim::GlobalManagers::get_resource_manager()->get_custom_parameter("output_file");
    if (std::filesystem::exists(file_name)) std::filesystem::remove(file_name);

    if (sqlite3_open(file_name.c_str(), &db) != SQLITE_OK) {
        throw std::invalid_argument("SQLite file " + file_name + " cannot be opened.");
    }

    if (SQLITE_OK != sqlite3_exec(db, "PRAGMA journal_mode=WAL;", nullptr, 0, nullptr)) {
        throw std::runtime_error("Failed to set database connection in WAL mode.");
    }
    initialized = true;
    createEventsTable();
}

void OUTPUT::createEventsTable()
{
    const char* create_stmt =
        "CREATE TABLE EVENTS ("
        "_ID INTEGER PRIMARY KEY AUTOINCREMENT, "
        "EVENT TEXT NOT NULL, "
        "STATE TEXT NOT NULL, "
        "STATUS TEXT NOT NULL, "
        "JOB_ID TEXT NOT NULL, "
        "TIME FLOAT NOT NULL, "
        "METADATA TEXT"
        ");";


    char* errmsg = nullptr;
    int ret = sqlite3_exec(db, create_stmt, nullptr, nullptr, &errmsg);
    if (ret != SQLITE_OK) {
        std::string message = "Database table creation failed: " +
            std::string(errmsg ? errmsg : "unknown sqlite3 error") +
            " (sqlite3 rc=" + std::to_string(ret) + ")";
        sqlite3_free(errmsg);
        throw std::runtime_error(message);
    }
}

void OUTPUT::insert_event(
                  const std::string& event,
                  const std::string& state,
                  const std::string& job_id,
                  const std::string& status,
                  double time,
                  const std::string& payload)
{
    sqlite3_stmt* stmt;
    std::string sql_insert =
        "INSERT INTO EVENTS (EVENT, STATE, JOB_ID, STATUS, TIME, METADATA) VALUES (?, ?, ?, ?, ?, ?)";

    int rc = sqlite3_prepare_v2(db, sql_insert.c_str(), -1, &stmt, nullptr);
    if (rc != SQLITE_OK)
        throw std::runtime_error(std::string("SQLite prepare failed: ") + sqlite3_errmsg(db));

    sqlite3_bind_text(stmt, 1, event.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, state.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, job_id.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 4, status.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_double(stmt, 5, time);
    sqlite3_bind_text(stmt, 6, payload.c_str(), -1, SQLITE_TRANSIENT);

    if (sqlite3_step(stmt) != SQLITE_DONE)
    {
        sqlite3_finalize(stmt);
        throw std::runtime_error(std::string("SQLite step failed: ") + sqlite3_errmsg(db));
    }

    sqlite3_finalize(stmt);
}


void OUTPUT::onSimulationStart()
{

}

void OUTPUT::onSimulationEnd()
{

}

void OUTPUT::onJobTransferStart(CGSim::Job* job)
{
    json payload = {
        {"site", job->get_site()},
        {"host", job->get_cpu()}
    };

    insert_event("JobAllocation", "Started",
                 job->get_id(),
                 job->get_status(),
                 sg4::Engine::get_clock(),
                 payload.dump());
}

void OUTPUT::onJobTransferEnd(CGSim::Job* job)
{
    json payload = {
        {"site", job->get_site()},
        {"host", job->get_cpu()},
        {"site_storage_util", calculate_site_storage_util(job->get_site())},
        {"grid_storage_util", calculate_grid_storage_util()},
        {"site_cpu_util", calculate_site_cpu_util(job->get_site())},
        {"grid_cpu_util", calculate_grid_cpu_util()}
    };

    insert_event("JobAllocation", "Finished",
                 job->get_id(),
                 job->get_status(),
                 sg4::Engine::get_clock(),
                 payload.dump());
}

void OUTPUT::onJobExecutionStart(CGSim::Job* job)
{
    const double now = sg4::Engine::get_clock();
    start_times[job->get_id()] = now;

    json payload = {
        {"flops", job->get_flops()},
        {"site", job->get_site()},
        {"host", job->get_cpu()},
        {"cores", job->get_cores()},
        {"speed", job->get_cpu_speed()},
        {"start_time", now},
        {"site_cpu_util", calculate_site_cpu_util(job->get_site())},
        {"grid_cpu_util", calculate_grid_cpu_util()}
    };

    insert_event("JobExecution", "Started",
                 job->get_id(),
                 job->get_status(),
                 now,
                 payload.dump());
}

void OUTPUT::onJobExecutionEnd(CGSim::Job* job)
{
    const double now = sg4::Engine::get_clock();

    json payload = {
        {"flops", job->get_flops()},
        {"cores", job->get_cores()},
        {"site", job->get_site()},
        {"host", job->get_cpu()},
        {"speed", job->get_cpu_speed()},
        {"cost", (1.0*job->get_flops())/(1.0*job->get_cores())},
        {"site_cpu_util", calculate_site_cpu_util(job->get_site())},
        {"grid_cpu_util", calculate_grid_cpu_util()},
        {"duration", now - start_times[job->get_id()]},
        {"retries", job->get_retries()},
        {"total_io_read_time", job->get_total_io_read_time()},
        {"file_transfer_queue_time", job->get_file_transfer_queue_time()},
        {"resource_waiting_queue_time", job->get_resource_waiting_queue_time()},
        {"total_queue_time", job->get_file_transfer_queue_time()+job->get_resource_waiting_queue_time()},
    };

    insert_event("JobExecution", "Finished",
                 job->get_id(),
                 job->get_status(),
                 now,
                 payload.dump());
}

void OUTPUT::onFileTransferStart(CGSim::Job* job,
                                 const std::string& filename,
                                 const unsigned long long filesize,
                                 const std::string& src_site,
                                 const std::string& dst_site)
{
    const double now = sg4::Engine::get_clock();
    start_times["transfer|" + job->get_id() + "|" + filename] = now;
    auto link = get_link(src_site, dst_site);

    json payload = {
        {"file", filename},
        {"size", filesize},
        {"source_site", src_site},
        {"destination_site", dst_site},
        {"bandwidth", link->get_bandwidth()},
        {"latency", link->get_latency()},
        {"link_load", link->get_load()},
        {"site_storage_util", calculate_site_storage_util(job->get_site())},
        {"grid_storage_util", calculate_grid_storage_util()}
    };

    insert_event("FileTransfer", "Started",
                 job->get_id(),
                 job->get_status(),
                 now,
                 payload.dump());
}

void OUTPUT::onFileTransferEnd(CGSim::Job* job,
                               const std::string& filename,
                               const unsigned long long filesize,
                               const std::string& src_site,
                               const std::string& dst_site)
{
    const double now = sg4::Engine::get_clock();
    auto link = get_link(src_site, dst_site);

    json payload = {
        {"file", filename},
        {"size", filesize},
        {"source_site", src_site},
        {"destination_site", dst_site},
        {"duration", now - start_times["transfer|" + job->get_id() + "|" + filename]},
        {"bandwidth", link->get_bandwidth()},
        {"latency", link->get_latency()},
        {"link_load", link->get_load()},
        {"site_storage_util", calculate_site_storage_util(job->get_site())},
        {"grid_storage_util", calculate_grid_storage_util()}
    };

    insert_event("FileTransfer", "Finished",
                 job->get_id(),
                 job->get_status(),
                 now,
                 payload.dump());
}

void OUTPUT::onFileReadStart(CGSim::Job* job,
                            const std::string& filename,
                            const unsigned long long filesize)
{
    const double now = sg4::Engine::get_clock();
    start_times["read|" + job->get_id() + "|" + filename] = now;

    json payload = {
        {"file", filename},
        {"size", filesize},
        {"site", job->get_site()},
        {"host", job->get_cpu()},
        {"disk", job->get_disk()},
        {"disk_read_bw", job->get_disk_read_bw()}
    };

    insert_event("FileRead", "Started",
                 job->get_id(),
                 job->get_status(),
                 now,
                 payload.dump());
}

void OUTPUT::onFileReadEnd(CGSim::Job* job,
                           const std::string& filename,
                           const unsigned long long filesize)
{
    const double now = sg4::Engine::get_clock();

    json payload = {
        {"file", filename},
        {"size", filesize},
        {"site", job->get_site()},
        {"host", job->get_cpu()},
        {"disk", job->get_disk()},
        {"disk_read_bw", job->get_disk_read_bw()},
        {"duration", now - start_times["read|" + job->get_id() + "|" + filename]}
    };

    insert_event("FileRead", "Finished",
                 job->get_id(),
                 job->get_status(),
                 now,
                 payload.dump());
}

void OUTPUT::onFileWriteStart(CGSim::Job* job,
                             const std::string& filename,
                             const unsigned long long filesize)
{
    const double now = sg4::Engine::get_clock();
    start_times["write|" + job->get_id() + "|" + filename] = now;

    json payload = {
        {"file", filename},
        {"size", filesize},
        {"site", job->get_site()},
        {"host", job->get_cpu()},
        {"disk", job->get_disk()},
        {"disk_write_bw", job->get_disk_write_bw()},
        {"site_storage_util", calculate_site_storage_util(job->get_site())},
        {"grid_storage_util", calculate_grid_storage_util()}
    };

    insert_event("FileWrite", "Started",
                 job->get_id(),
                 job->get_status(),
                 now,
                 payload.dump());
}

void OUTPUT::onFileWriteEnd(CGSim::Job* job,
                           const std::string& filename,
                           const unsigned long long filesize)
{
    const double now = sg4::Engine::get_clock();

    json payload = {
        {"file", filename},
        {"size", filesize},
        {"site", job->get_site()},
        {"host", job->get_cpu()},
        {"duration", now - start_times["write|" + job->get_id() + "|" + filename]},
        {"disk", job->get_disk()},
        {"disk_write_bw", job->get_disk_write_bw()},
        {"site_storage_util", calculate_site_storage_util(job->get_site())},
        {"grid_storage_util", calculate_grid_storage_util()}
    };

    insert_event("FileWrite", "Finished",
                 job->get_id(),
                 job->get_status(),
                 now,
                 payload.dump());
}


sg4::Link* OUTPUT::get_link(const std::string& src_site, const std::string& dst_site)
{

    sg4::Link* link = sg4::Link::by_name_or_null("link_" + src_site + ":" + dst_site);
    if (!link) link = sg4::Link::by_name_or_null("link_" + dst_site + ":" + src_site);
    if (!link) throw std::runtime_error("Link not found");
    return link;
}

double OUTPUT::calculate_grid_cpu_util()
{
    return CGSim::GlobalManagers::get_resource_manager()->get_grid_cpu_utilization();
}

double OUTPUT::calculate_site_cpu_util(const std::string& site_name)
{
    return CGSim::GlobalManagers::get_resource_manager()->get_site(site_name)->get_cpu_utilization();
}

double OUTPUT::calculate_grid_storage_util()
{
    return CGSim::GlobalManagers::get_resource_manager()->get_grid_storage_utilization();
}

double OUTPUT::calculate_site_storage_util(const std::string& site_name)
{
    return CGSim::GlobalManagers::get_resource_manager()->get_site(site_name)->get_storage_utilization();
}
