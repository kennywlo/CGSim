#include "track4_workload_manager.h"


std::vector<std::string> TRACK4_WORKLOAD_MANAGER::parseCSVLine(const std::string& line) {
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
std::string TRACK4_WORKLOAD_MANAGER::getColumn(const std::vector<std::string>& row,
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

void TRACK4_WORKLOAD_MANAGER::setWorkload(CGSim::JobQueue& jobs) {

    auto platform = sg4::Engine::get_instance()->get_netzone_root();
    std::string jobFile = platform->get_property("jobs_file");
    long max_jobs = std::stol(platform->get_property("Num_of_Jobs"));
    std::ifstream file(jobFile);
    if (!file.is_open()) {
        throw std::runtime_error("Could not open file: " + jobFile);
    }

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
            CGSim::Job* job = new CGSim::Job();

            std::string pandaid = getColumn(row, column_map, "pandaid", "0");
            job->set_id(pandaid);
            job->set_creation_time(std::stod(getColumn(row,column_map,"creationtime","0")));
	    //job->set_creation_time(1 + rand() % 100);
	    job->set_property("cpu_consumption_time",getColumn(row,column_map,"cpuconsumptiontime","0"));
            job->set_site(getColumn(row,column_map,"computingsite",""));
            job->set_cores(std::stoi(getColumn(row,column_map,"corecount","0")));

            double out_bytes = std::stod(getColumn(row,column_map,"outputfilebytes","0"));
            std::string out = "user.output."+job->get_id()+".00001.root";
            job->add_output_file(out,std::to_string((unsigned long long)out_bytes/10000));

            double in_bytes = std::stod(getColumn(row,column_map,"inputfilebytes","0"));
            std::string in = "user.input."+job->get_id()+".00001.root";
            job->add_input_file(in);
            CGSim::GlobalManagers::get_file_manager()->create(in,(unsigned long long)in_bytes/10000,job->get_site());

            if(!job->get_site().empty()) jobs.push(job);
            else delete job;

        } catch (const std::exception& e) {
            std::cerr << "Skipping invalid row: " << line << "\n";
            std::cerr << "Reason: " << e.what() << "\n";
        }
    }
    file.close();
}
