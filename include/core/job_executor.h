#ifndef JOB_EXECUTOR_H
#define JOB_EXECUTOR_H

#include "plugin.h"
#include "PluginLoader.h"
#include "actions.h"
#include "policy_manager.h"
#include "host_extensions.h"
#include <chrono>
#include <simgrid/kernel/Timer.hpp>
#include "units_parser.h"
#include "print.h"
#include "statistics.h"
#include "file.h"

namespace CGSim::Utilities
{
class Statistics;
}

namespace CGSim { 

namespace Core {

class Actions;

class JOB_EXECUTOR
{


public:
     JOB_EXECUTOR()= default;
    ~JOB_EXECUTOR()= default;
    friend class Actions;

    static void                set_plugin(std::shared_ptr<CGSim::Plugin>& p){plugin = p;}
    static void                start_job_execution();


private:
    static void                start_receivers();
    static void                start_server();
    static void                execute_job(Job* j);
    static void                onJobAssignment(Job* job);
    static void                get_jobs();
    static void                advance_to_time(double time);
    static void                dispatch_global_pending_jobs();
    static void                dispatch_site_pending_jobs(std::string& site_name);
    [[noreturn]] static void   receiver(const std::string& MQ_name);
    static void                attach_callbacks();
    static unsigned long       totalJobs(JobQueue jobs);


    static   sg4::ActivitySet                       pending_activities;
    static   unsigned long                          DISPATCHED_JOBS;
    static   unsigned long                          RUNNING_JOBS;
    static   unsigned long                          FINISHED_JOBS;
    static   unsigned long                          ACTIVATED_JOBS;
    static   unsigned long                          TOTAL_JOBS;
    static   unsigned long                          JOBS_IN_SITE_PENDING;
    static   JobQueue                               jobs;
    static   std::unordered_map<std::string, Job*>  all_jobs;
    static   std::vector<Job*>                      pending_jobs;
    static   std::shared_ptr<CGSim::Plugin>         plugin;

    friend class ::CGSim::Utilities::Statistics;

};

}

}
#endif //JOB_EXECUTOR_H
