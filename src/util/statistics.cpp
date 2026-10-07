#include "statistics.h"
#include "job_executor.h"

namespace CGSim {

namespace Utilities {

unsigned long Statistics::get_pending_activities_size() {return CGSim::Core::JOB_EXECUTOR::pending_activities.size();}

double Statistics::get_system_clock() 
{
    double current_time = std::chrono::duration<double>(Clock::now() - start_).count();
    return current_time;
}



}

}
