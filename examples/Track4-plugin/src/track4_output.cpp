#include "track4_output.h"

void TRACK4_OUTPUT::initialize()
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

void TRACK4_OUTPUT::createEventsTable()
{
    const char* create_stmt =
        "CREATE TABLE IF NOT EXISTS EVENTS ("
        "_ID INTEGER PRIMARY KEY AUTOINCREMENT, "
        "JOB_ID TEXT NOT NULL, "
        "CPU_NAME TEXT NOT NULL, "
        "STATE TEXT NOT NULL, "
        "TIMESTAMP REAL NOT NULL, "
        "SITE TEXT NOT NULL, "
        "AVAILABLE_SITE_CORES INTEGER NOT NULL, "
        "AVAILABLE_SITE_CPUS INTEGER NOT NULL, "
        "WORKLOAD TEXT NOT NULL, "
        "NINPUT_FILES INTEGER NOT NULL, "
        "NOUTPUT_FILES INTEGER NOT NULL, "
        "INPUT_FILE_BYTES INTEGER NOT NULL, "
        "OUTPUT_FILE_BYTES INTEGER NOT NULL, "
        "SYSTEM_PENDING_JOBS INTEGER NOT NULL, "
        "SITE_PENDING_JOBS INTEGER NOT NULL, "
        "SITE_RUNNING_JOBS INTEGER NOT NULL, "
        "SITE_FINISHED_JOBS INTEGER NOT NULL, "
        "SITE_FAILED_JOBS INTEGER NOT NULL"
        ");";

    char* errmsg = nullptr;
    int ret = sqlite3_exec(db, create_stmt, nullptr, nullptr, &errmsg);
    if (ret != SQLITE_OK) {
        std::string msg = errmsg ? errmsg : sqlite3_errmsg(db);
        sqlite3_free(errmsg);
        throw std::runtime_error("Database table creation failed: " + msg);
    }
}

void TRACK4_OUTPUT::insert_event(
    const std::string& id,
    const std::string& cpu_name,
    const std::string& state,
    double timestamp,
    const std::string& site,
    long available_site_cores,
    long available_site_cpus,
    long long workload,
    int ninput_files,
    int noutput_files,
    long long input_file_bytes,
    long long output_file_bytes,
    long long system_pending_jobs,
    long site_pending_jobs,
    long site_running_jobs,
    long site_finished_jobs,
    long site_failed_jobs)
{
    sqlite3_stmt* stmt = nullptr;

    const char* sql_insert =
        "INSERT INTO EVENTS ("
        "JOB_ID, CPU_NAME, STATE, TIMESTAMP, SITE, "
        "AVAILABLE_SITE_CORES, AVAILABLE_SITE_CPUS, WORKLOAD, "
        "NINPUT_FILES, NOUTPUT_FILES, INPUT_FILE_BYTES, OUTPUT_FILE_BYTES, "
        "SYSTEM_PENDING_JOBS, SITE_PENDING_JOBS, SITE_RUNNING_JOBS, SITE_FINISHED_JOBS, SITE_FAILED_JOBS"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);";

    int rc = sqlite3_prepare_v2(db, sql_insert, -1, &stmt, nullptr);
    if (rc != SQLITE_OK)
        throw std::runtime_error(std::string("SQLite prepare failed: ") + sqlite3_errmsg(db));

    sqlite3_bind_text(stmt, 1, id.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 2, cpu_name.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_text(stmt, 3, state.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_double(stmt, 4, timestamp);
    sqlite3_bind_text(stmt, 5, site.c_str(), -1, SQLITE_TRANSIENT);
    sqlite3_bind_int64(stmt, 6, available_site_cores);
    sqlite3_bind_int64(stmt, 7, available_site_cpus);
    sqlite3_bind_int64(stmt, 8, workload);
    sqlite3_bind_int(stmt, 9, ninput_files);
    sqlite3_bind_int(stmt, 10, noutput_files);
    sqlite3_bind_int64(stmt, 11, input_file_bytes);
    sqlite3_bind_int64(stmt, 12, output_file_bytes);
    sqlite3_bind_int64(stmt, 13, system_pending_jobs);
    sqlite3_bind_int64(stmt, 14, site_pending_jobs);
    sqlite3_bind_int64(stmt, 15, site_running_jobs);
    sqlite3_bind_int64(stmt, 16, site_finished_jobs);
    sqlite3_bind_int64(stmt, 17, site_failed_jobs);

    rc = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    if (rc != SQLITE_DONE)
        throw std::runtime_error(std::string("SQLite step failed: ") + sqlite3_errmsg(db));
}


void TRACK4_OUTPUT::onJobStatusChange(CGSim::Job* job)
{
  
  auto* site = CGSim::GlobalManagers::get_resource_manager()->get_site(job->get_site());

  insert_event
    (
     job->get_id(),
     job->get_cpu(),
     job->get_status(),
     sg4::Engine::get_clock(),
     job->get_site(),
     site->get_number_of_total_cores() - site->get_number_of_used_cores(),
     site->get_number_of_total_cpus() - site->get_number_of_used_cpus(),
     job->get_flops(),
     job->get_input_files().size(),
     job->get_output_files().size(),
     input_files_bytes(job),
     output_files_bytes(job),
     CGSim::GlobalManagers::get_resource_manager()->get_global_pending_jobs().size(),
     site->get_pending_jobs().size(),
     site->get_running_jobs().size(),
     site->get_finished_jobs().size(),
     site->get_failed_jobs().size()
     );
}

long long TRACK4_OUTPUT::input_files_bytes(CGSim::Job* job) 
{
  long long total_bytes = 0;
  auto* fm = CGSim::GlobalManagers::get_file_manager();
  for (const auto& filename: job->get_input_files()) {total_bytes += fm->request_file(filename)->get_size();}
  return total_bytes;
}

long long TRACK4_OUTPUT::output_files_bytes(CGSim::Job* job) 
{
  long long total_bytes = 0;
  for (const auto& [filename, filesize] : job->get_output_files()) {total_bytes += CGSim::Utilities::parse_units_size(filesize);}
  return total_bytes;
}
