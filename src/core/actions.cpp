#include "actions.h"

namespace CGSim {

namespace Core {

void Actions::on_job_completion(Job* j)
{
     j->status = CGSim::STATUS::FINISHED;
            CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->remove_running_job(j);
            CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->add_finished_job(j);
            auto host = sg4::Host::by_name(j->cpu);
            host->extension<HostExtensions>()->onJobFinish(j);
            JOB_EXECUTOR::FINISHED_JOBS++;
            JOB_EXECUTOR::RUNNING_JOBS--;
            JOB_EXECUTOR::dispatch_site_pending_jobs(j->site);
            JOB_EXECUTOR::plugin->onJobFinish(j);

            //See if dependent jobs are ready to run
            bool dag_job_created = false;
            for(const auto& [child_job_id,rel_creation_time]: j->children)
            {
                auto* child_job = JOB_EXECUTOR::all_jobs[child_job_id];
                bool active = true;
                for(const auto& parent_job_id: child_job->parents)
                {
                    if(JOB_EXECUTOR::all_jobs[parent_job_id]->status != CGSim::STATUS::FINISHED) active = false;
                }

                if(active)
                {
                    Job* new_child_job = new Job(*child_job);
                    new_child_job->creation_time = sg4::Engine::get_clock() +  rel_creation_time;
                    JOB_EXECUTOR::all_jobs[child_job_id] = new_child_job;
                    JOB_EXECUTOR::jobs.dag_push(new_child_job);
                    dag_job_created = true;
                } 

            }
            if(dag_job_created) JOB_EXECUTOR::pending_activities.push(sg4::MessageQueue::by_name("JOB-SERVER-MQ")->put_async(&dag_wakeup_msg));

}

sg4::ExecPtr Actions::exec_task_multi_thread_async(Job* j)
{
    auto host = sg4::Host::by_name(j->cpu);
    sg4::ExecPtr exec_activity = sg4::Exec::init()
        ->set_flops_amount((1.0*j->flops)/(1.0*j->cores))
        ->set_host(host)
        ->set_name("Exec_Job_" + j->id + "_on_" + host->get_name());

    exec_activity->on_this_start_cb([j](simgrid::s4u::Exec const& ex) {
        j->status = CGSim::STATUS::RUNNING;
        CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->remove_assigned_job(j);
        CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->add_running_job(j);
        JOB_EXECUTOR::plugin->onJobExecutionStart(j);
    });

    exec_activity->on_this_completion_cb([j, host](simgrid::s4u::Exec const& ex) {

        j->cpu_consumption_time = ex.get_finish_time() - ex.get_start_time();
        
        if(j->output_files.size() == 0) on_job_completion(j);

        JOB_EXECUTOR::plugin->onJobExecutionEnd(j);
        CGSim::Utilities::printSimulationDashBoard(JOB_EXECUTOR::DISPATCHED_JOBS, JOB_EXECUTOR::TOTAL_JOBS, JOB_EXECUTOR::RUNNING_JOBS, 
                                                   JOB_EXECUTOR::FINISHED_JOBS, JOB_EXECUTOR::pending_jobs.size(), JOB_EXECUTOR::JOBS_IN_SITE_PENDING, 
                                                   JOB_EXECUTOR::pending_activities.size(), sg4::Engine::get_clock(), 
                                                   CGSim::GlobalManagers::get_resource_manager()->get_grid_cpu_utilization());

    });

    return exec_activity;
}

sg4::IoPtr Actions::read_file_async(Job* j, const std::string& filename)
{

    auto read_activity = CGSim::GlobalManagers::get_file_manager()->internal_read(filename, j->site,j->cpu,j->disk);
    read_activity->set_name("Read_File_"+ filename + "_for_Job_" + j->id + "_on_" + j->cpu);
    auto size = CGSim::GlobalManagers::get_file_manager()->request_file(filename)->size;
    read_activity->on_this_start_cb([j,filename,size](simgrid::s4u::Io const& io) {
        JOB_EXECUTOR::plugin->onFileReadStart(j,filename,size);
        });

    read_activity->on_this_completion_cb([j,filename,size](simgrid::s4u::Io const& io) {
            j->total_io_read_time += (io.get_finish_time() - io.get_start_time());
            JOB_EXECUTOR::plugin->onFileReadEnd(j,filename,size);
            });

  return read_activity;
}

sg4::IoPtr Actions::write_file_async(Job* j, const std::string& filename, const unsigned long long& size)
{
    auto write_activity = CGSim::GlobalManagers::get_file_manager()->internal_write(filename, size, j->site,j->cpu,j->disk);
    write_activity->set_name("Write_File_"+ filename + "_for_Job_" + j->id + "_on_" + j->cpu);

    write_activity->on_this_start_cb([j,filename,size](simgrid::s4u::Io const& io) {
        JOB_EXECUTOR::plugin->onFileWriteStart(j,filename,size);
        });

    write_activity->on_this_completion_cb([j,filename,size](simgrid::s4u::Io const& io) {
            j->total_io_write_time += (io.get_finish_time() - io.get_start_time());

            j->files_written++;

            if(j->files_written == j->output_files.size()) on_job_completion(j);
            JOB_EXECUTOR::plugin->onFileWriteEnd(j,filename,size);
            CGSim::Utilities::printSimulationDashBoard(JOB_EXECUTOR::DISPATCHED_JOBS, JOB_EXECUTOR::TOTAL_JOBS, JOB_EXECUTOR::RUNNING_JOBS, 
                                                   JOB_EXECUTOR::FINISHED_JOBS, JOB_EXECUTOR::pending_jobs.size(), JOB_EXECUTOR::JOBS_IN_SITE_PENDING, 
                                                   JOB_EXECUTOR::pending_activities.size(), sg4::Engine::get_clock(), 
                                                   CGSim::GlobalManagers::get_resource_manager()->get_grid_cpu_utilization());
        });

    return write_activity;
}

sg4::CommPtr Actions::transfer_file_async(Job* j, const std::string& filename, const std::string& src_site, const std::string& dst_site, CGSim::FileTransferDecisionMode mode)
{
    auto transfer_activity = CGSim::GlobalManagers::get_file_manager()->internal_transfer(filename,src_site,dst_site,mode);
    const auto size = static_cast<unsigned long long>(transfer_activity->get_remaining());

    transfer_activity->on_this_start_cb([j,filename,size,src_site,dst_site](simgrid::s4u::Comm const& co) {
        if (!started_transfers.insert(co.get_name()).second) return;
        JOB_EXECUTOR::plugin->onFileTransferStart(j,filename,size,src_site,dst_site);
        });

    transfer_activity->on_this_completion_cb([filename,size,src_site,dst_site,j](simgrid::s4u::Comm const& co) {
        started_transfers.erase(co.get_name());
        j->file_transfer_queue_time = std::max(j->file_transfer_queue_time , co.get_finish_time() - co.get_start_time());
        JOB_EXECUTOR::plugin->onFileTransferEnd(j,filename,size,src_site,dst_site);
        });

    return transfer_activity;
}

}

}
