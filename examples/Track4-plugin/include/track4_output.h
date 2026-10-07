#ifndef TRACK4_OUTPUT_H
#define TRACK4_OUTPUT_H

#include <iostream>
#include <string>
#include <stdexcept>
#include <sqlite3.h>
#include <vector>
#include <sstream>
#include "CGSim.h"
#include <nlohmann/json.hpp>
using json = nlohmann::json;

class TRACK4_OUTPUT {

public:
     TRACK4_OUTPUT(){initialize();};
    ~TRACK4_OUTPUT() {sqlite3_close_v2(db);}

    void initialize();
    void createEventsTable();
    void insert_event(
                    const std::string&  id,
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
                    long site_failed_jobs);

    long long input_files_bytes(CGSim::Job* job);
    long long output_files_bytes(CGSim::Job* job);
    void onJobStatusChange(CGSim::Job* job);


private:
    bool initialized = false;
    sqlite3 *db;
};

#endif
//TRACK4_OUTPUT_H