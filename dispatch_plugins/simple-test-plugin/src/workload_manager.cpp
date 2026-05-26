#include "workload_manager.h"


std::vector<std::string> WORKLOAD_MANAGER::parseCSVLine(const std::string& line) {
    std::vector<std::string> row;
    std::string cell;
    bool in_quotes = false;

    for (char c : line) {
        if (c == '"') {
            in_quotes = !in_quotes;
        } else if (c == ',' && !in_quotes) {
            row.push_back(cell);
            cell.clear();
        } else {
            cell += c;
        }
    }
    row.push_back(cell);

    for (auto& field : row) {
        // Remove surrounding quotes
        if (!field.empty() && field.front() == '"' && field.back() == '"') {
            field = field.substr(1, field.size() - 2);
        }
        // Remove non-printable characters
        field.erase(std::remove_if(field.begin(), field.end(),
                    [](unsigned char c) { return !std::isprint(c); }),
                    field.end());
    }
    return row;
}

// Helper function to safely get a column value
std::string WORKLOAD_MANAGER::getColumn(const std::vector<std::string>& row,
                      const std::unordered_map<std::string,int>& column_map,
                      const std::string& key,
                      const std::string& default_val)
{
    auto it = column_map.find(key);
    if (it == column_map.end() || it->second >= static_cast<int>(row.size()) || row[it->second].empty()) {
        return default_val;
    }
    return row[it->second];
}

JobQueue WORKLOAD_MANAGER::getWorkload() {

    auto platform = sg4::Engine::get_instance()->get_netzone_root();
    std::string jobFile = platform->get_property("jobs_file");
    long max_jobs = std::stol(platform->get_property("Num_of_Jobs"));
    std::ifstream file(jobFile);
    if (!file.is_open()) {
        throw std::runtime_error("Could not open file: " + jobFile);
    }

    JobQueue jobs;
    std::string line;
    std::unordered_map<std::string, int> column_map;
    bool header_parsed = false;

    while (std::getline(file, line)) {
        auto row = parseCSVLine(line);

        if (!header_parsed) {
            header_parsed = true;
            for (int i = 0; i < static_cast<int>(row.size()); ++i) {
                std::string col = row[i];
                // lowercase header names
                std::transform(col.begin(), col.end(), col.begin(), ::tolower);
                column_map[col] = i;
            }
            continue;
        }

        if (max_jobs != -1 && static_cast<long>(jobs.size()) >= max_jobs) {
            break;
        }

        try {
            Job* job = new Job();

            // Safely get each column, providing defaults if missing
            job->jobid                 = std::stoll(getColumn(row, column_map, "pandaid", "0"));
            //job->creation_time         = getColumn(row, column_map, "creationtime", "");
            //job->job_status            = getColumn(row, column_map, "jobstatus", "");
            //job->job_name              = getColumn(row, column_map, "jobname", "");
            job->cpu_consumption_time  = std::stod(getColumn(row, column_map, "cpuconsumptiontime", "0"));
            job->comp_site             = getColumn(row, column_map, "computingsite", "");
            //job->destination_dataset_name = getColumn(row, column_map, "destinationdblock", "");
            //job->destination_SE        = getColumn(row, column_map, "destinationse", "");
            //job->source_site           = getColumn(row, column_map, "sourcesite", "");
            //job->transfer_type         = getColumn(row, column_map, "transfertype", "");
            //job->core_count            = getColumn(row, column_map, "corecount", "0").empty() ? 0 : std::stoi(getColumn(row, column_map, "corecount", "0"));
            job->cores                 = getColumn(row, column_map, "corecount", "0").empty() ? 0 : std::stoi(getColumn(row, column_map, "corecount", "0"));
            //job->no_of_inp_files       = std::stoi(getColumn(row, column_map, "ninputdatafiles", "0"));
            //job->inp_file_bytes        = std::stod(getColumn(row, column_map, "inputfilebytes", "0"));
            //job->no_of_out_files       = std::stoi(getColumn(row, column_map, "noutputdatafiles", "0"));
            //job->out_file_bytes        = std::stod(getColumn(row, column_map, "outputfilebytes", "0"));
            //job->pilot_error_code      = getColumn(row, column_map, "piloterrorcode", "");
            //job->exe_error_code        = getColumn(row, column_map, "exeerrorcode", "");
            //job->ddm_error_code        = getColumn(row, column_map, "ddmerrorcode", "");
            //job->dispatcher_error_code = getColumn(row, column_map, "jobdispatchererrorcode", "");
            //job->taskbuffer_error_code = getColumn(row, column_map, "taskbuffererrorcode", "");
            job->status                = "created";
            job->retries                = 0;

            // ---- Parse input files JSON ----
            std::string json_str = getColumn(row, column_map, "files_info", "");
            if (!json_str.empty() && json_str.front() == '"' && json_str.back() == '"') {
                json_str = json_str.substr(1, json_str.size()-2);
            }
            json_str.erase(std::remove(json_str.begin(), json_str.end(), '{'), json_str.end());
            json_str.erase(std::remove(json_str.begin(), json_str.end(), '}'), json_str.end());

            std::stringstream ss(json_str);
            std::string token;
            while (std::getline(ss, token, ',')) {
                auto colon_pos = token.find(':');
                if (colon_pos != std::string::npos) {
                    std::string key = token.substr(0, colon_pos);
                    key.erase(std::remove_if(key.begin(), key.end(), ::isspace), key.end());
                    key.erase(std::remove(key.begin(), key.end(), '"'), key.end());
                    job->input_files[key] = {0LL, {}};
                }
            }

            double no_of_out_files       = std::stoi(getColumn(row, column_map, "noutputdatafiles", "0"));
            double out_file_bytes        = std::stod(getColumn(row, column_map, "outputfilebytes", "0"));

            // ---- Generate output files ----
            long long size_per_out_file = no_of_out_files > 0 ? out_file_bytes / no_of_out_files : 0;
            for (int f = 1; f <= no_of_out_files; ++f) {
                std::string filename = "user.output." + std::to_string(job->jobid) + ".0000" + std::to_string(f) + ".root";
                job->output_files[filename] = size_per_out_file;
            }

            jobs.push(job);
        } catch (const std::exception& e) {
            std::cerr << "Skipping invalid row: " << line << "\n";
            std::cerr << "Reason: " << e.what() << "\n";
        }
    }
    file.close();
    return jobs;
}
