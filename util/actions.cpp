#include "actions.h"

void Actions::release_ready_children(Job* j)
{
    bool dag_job_created = false;
    for (const auto& [child_job_id, rel_creation_time] : j->children)
    {
        auto* child_job = JOB_EXECUTOR::all_jobs[child_job_id];
        bool active = true;
        for (const auto& parent_job_id : child_job->parents)
        {
            auto* parent_job = JOB_EXECUTOR::all_jobs[parent_job_id];
            if (parent_job->metadata["outputs_complete"] != "true") active = false;
        }

        if (active)
        {
            Job* new_child_job = new Job(*child_job);
            new_child_job->creation_time = sg4::Engine::get_clock() + rel_creation_time;
            JOB_EXECUTOR::all_jobs[child_job_id] = new_child_job;
            JOB_EXECUTOR::jobs.push(new_child_job);
            dag_job_created = true;
        }
    }
    if (dag_job_created)
        JOB_EXECUTOR::pending_activities.push(
            sg4::MessageQueue::by_name("JOB-SERVER-MQ")->put_async(&dag_wakeup_msg));
}

sg4::ExecPtr Actions::exec_task_multi_thread_async(Job* j)
{
    auto host = sg4::Host::by_name(j->comp_host);
    sg4::ExecPtr exec_activity = sg4::Exec::init()
        ->set_flops_amount((1.0*j->flops)/(1.0*j->cores))
        ->set_host(host)
        ->set_name("Exec_Job_" + std::to_string(j->jobid) + "_on_" + host->get_name());

    exec_activity->on_this_start_cb([j](simgrid::s4u::Exec const& ex) {
        j->status = CGSim::STATUS::RUNNING;
        CGSim::get_site_manager()->get_site(j->comp_site)->assigned_jobs.erase(j->jobid);
        CGSim::get_site_manager()->get_site(j->comp_site)->running_jobs[j->jobid] = j;
        JOB_EXECUTOR::dispatcher->onJobExecutionStart(j,ex);
    });

    exec_activity->on_this_completion_cb([j, host](simgrid::s4u::Exec const& ex) {
        j->status = CGSim::STATUS::FINISHED;
        CGSim::get_site_manager()->get_site(j->comp_site)->running_jobs.erase(j->jobid);
        CGSim::get_site_manager()->get_site(j->comp_site)->finished_jobs[j->jobid] = j;
        host->extension<HostExtensions>()->onJobFinish(j);
        JOB_EXECUTOR::FINISHED_JOBS++;
        JOB_EXECUTOR::dispatcher->onJobExecutionEnd(j,ex);
        JOB_EXECUTOR::dispatch_site_pending_jobs(j->comp_site);

        if (j->output_files.empty()) {
            j->metadata["outputs_complete"] = "true";
            Actions::release_ready_children(j);
        }

        });

    return exec_activity;
}

sg4::IoPtr Actions::read_file_async(Job* j, const std::string& filename)
{

    auto read_activity = CGSim::get_file_manager()->read(filename, j->comp_site,j->comp_host,j->disk);
    read_activity->set_name("Read_File_"+ filename + "_for_Job_" + std::to_string(j->jobid) + "_on_" + j->comp_host);
    auto size = CGSim::get_file_manager()->request_file_size(filename);
    read_activity->on_this_start_cb([j,filename,size](simgrid::s4u::Io const& io) {
        JOB_EXECUTOR::dispatcher->onFileReadStart(j,filename,size,io);
        });

    read_activity->on_this_completion_cb([j,filename,size](simgrid::s4u::Io const& io) {
            j->total_io_read_time += (io.get_finish_time() - io.get_start_time());
            JOB_EXECUTOR::dispatcher->onFileReadEnd(j,filename,size,io);
            });

  return read_activity;
}

sg4::IoPtr Actions::write_file_async(Job* j, const std::string& filename, const unsigned long long& size)
{
    auto write_activity = CGSim::get_file_manager()->write(filename, size, j->comp_site,j->comp_host,j->disk);
    write_activity->set_name("Write_File_"+ filename + "_for_Job_" +std::to_string(j->jobid) + "_on_" + j->comp_host);

    write_activity->on_this_start_cb([j,filename,size](simgrid::s4u::Io const& io) {
        JOB_EXECUTOR::dispatcher->onFileWriteStart(j,filename,size,io);
        });

    write_activity->on_this_completion_cb([j,filename,size](simgrid::s4u::Io const& io) {
            j->total_io_write_time += (io.get_finish_time() - io.get_start_time());
            JOB_EXECUTOR::dispatcher->onFileWriteEnd(j,filename,size,io);
            auto remaining = std::stoull(j->metadata.at("pending_output_writes"));
            if (remaining == 1) {
                j->metadata["pending_output_writes"] = "0";
                j->metadata["outputs_complete"] = "true";
                Actions::release_ready_children(j);
            } else {
                j->metadata["pending_output_writes"] = std::to_string(remaining - 1);
            }
       });

    return write_activity;
}

sg4::CommPtr Actions::transfer_file_async(Job* j, const std::string& filename, const std::string& src_site, const std::string& dst_site, CGSim::FileTransferDecisionMode mode)
{
    auto transfer_activity = CGSim::get_file_manager()->transfer(filename,src_site,dst_site,mode);
    const auto size = static_cast<unsigned long long>(transfer_activity->get_remaining());

    transfer_activity->on_this_start_cb([j,filename,size,src_site,dst_site](simgrid::s4u::Comm const& co) {
        if (!started_transfers.insert(co.get_name()).second) return;
        JOB_EXECUTOR::dispatcher->onFileTransferStart(j,filename,size,co,src_site,dst_site);
        });

    transfer_activity->on_this_completion_cb([filename,size,src_site,dst_site,j](simgrid::s4u::Comm const& co) {
        started_transfers.erase(co.get_name());
        j->file_transfer_queue_time = std::max(j->file_transfer_queue_time , co.get_finish_time() - co.get_start_time());
        JOB_EXECUTOR::dispatcher->onFileTransferEnd(j,filename,size,co,src_site,dst_site);
        });

    return transfer_activity;
}
