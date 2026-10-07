#include "job_executor.h"

namespace CGSim { 

namespace Core {

std::shared_ptr<CGSim::Plugin>         JOB_EXECUTOR::plugin;
sg4::ActivitySet                       JOB_EXECUTOR::pending_activities;
std::unordered_map<std::string, Job*>  JOB_EXECUTOR::all_jobs;
std::vector<Job*>                      JOB_EXECUTOR::pending_jobs;
JobQueue                               JOB_EXECUTOR::jobs;
unsigned long                          JOB_EXECUTOR::DISPATCHED_JOBS = 0;
unsigned long                          JOB_EXECUTOR::ACTIVATED_JOBS = 0;
unsigned long                          JOB_EXECUTOR::RUNNING_JOBS = 0;
unsigned long                          JOB_EXECUTOR::FINISHED_JOBS = 0;
unsigned long                          JOB_EXECUTOR::TOTAL_JOBS;
unsigned long                          JOB_EXECUTOR::JOBS_IN_SITE_PENDING = 0;


unsigned long JOB_EXECUTOR::totalJobs(JobQueue jobs)
{
  while (!jobs.empty()) 
  {
      auto* job = jobs.top();
      all_jobs[job->id] = job;
      jobs.pop();
  }
  return all_jobs.size();
}

void JOB_EXECUTOR::start_job_execution()
{
  start_receivers();
  attach_callbacks();
  sg4::Host* job_server = sg4::Host::by_name("JOB-SERVER_cpu-0");
  if (!job_server) throw std::runtime_error("JOB-SERVER not initialized properly");
  plugin->setWorkload(jobs);
  TOTAL_JOBS = totalJobs(jobs);
  sg4::Actor::create("JOB-EXECUTOR-actor",job_server,start_server);
  sg4::Engine::get_instance()->run();
}

void JOB_EXECUTOR::get_jobs()
{
  while(DISPATCHED_JOBS != TOTAL_JOBS  && !jobs.empty())
  {
    Job* job = jobs.top();
    if(job->creation_time == -1.0) break;
    if (sg4::Engine::get_clock() >= job->creation_time) 
    {
      pending_jobs.push_back(job);
      job->submission_time = sg4::Engine::get_clock();
      job->status = CGSim::STATUS::GLOBAL_PENDING;
      CGSim::GlobalManagers::get_resource_manager()->global_pending_jobs[job->id] = job;
      plugin->onJobSubmission(job);
      jobs.pop();
    }
    else break;
  }
}

void JOB_EXECUTOR::advance_to_time(double time)
{
  auto dag_job_check = sg4::MessageQueue::by_name("JOB-SERVER-MQ")->get_async();
  pending_activities.push(dag_job_check);
  auto finish_dag_check = [&]() {pending_activities.erase(dag_job_check); dag_job_check->cancel();};

  while(jobs.top()->creation_time == -1.0) 
  {
    if(pending_activities.size() == 1 && ACTIVATED_JOBS < DISPATCHED_JOBS){sg4::this_actor::yield(); continue;}
    else pending_activities.wait_any();
  }
  
  while (sg4::Engine::get_clock() < time) 
  {
    if (pending_activities.size() == 1) //Only DAG Checking Activity Present
    {
      if (ACTIVATED_JOBS < DISPATCHED_JOBS){sg4::this_actor::yield(); continue;}
      finish_dag_check();
      sg4::this_actor::sleep_until(time); 
      return;
    }

    try 
    { 
      auto act = pending_activities.wait_any_for(time - sg4::Engine::get_clock());
      bool dag_received = false;
      while (auto compl_act = pending_activities.test_any()){if(compl_act == dag_job_check) dag_received = true;}
      if(dag_received || act == dag_job_check) return;
    }

    catch (const simgrid::TimeoutException&) 
    {
      finish_dag_check();
      return;
    }
  }  
}


void JOB_EXECUTOR::dispatch_global_pending_jobs()
{
  auto grid_available_cores = CGSim::GlobalManagers::get_resource_manager()->TOTAL_GRID_CORES - CGSim::GlobalManagers::get_resource_manager()->USED_GRID_CORES;

  for(auto it = pending_jobs.begin(); it != pending_jobs.end();)
  {
  if(plugin->stopGlobalJobDispatching()) break;
  Job* job = *it;
  if(job->cores>grid_available_cores) break; //One big job can stall the simulation. In Reality this is unlikely.
  plugin->assignJob(job);

  if(!job->site.empty() && job->cpu.empty())
  {
    job->status = CGSim::STATUS::SITE_PENDING;
    JOBS_IN_SITE_PENDING++;
    CGSim::GlobalManagers::get_resource_manager()->global_pending_jobs.erase(job->id); 
    CGSim::GlobalManagers::get_resource_manager()->get_site(job->site)->pending_jobs.emplace_back(job);
    plugin->onJobSitePending(job);
    job->retries++;
    it = pending_jobs.erase(it);
  }

  else if(!job->site.empty() && !job->cpu.empty())
  {
    job->status = CGSim::STATUS::ASSIGNED;
    CGSim::GlobalManagers::get_resource_manager()->global_pending_jobs.erase(job->id); 
    CGSim::GlobalManagers::get_resource_manager()->get_site(job->site)->add_assigned_job(job);
    onJobAssignment(job); 
    it = pending_jobs.erase(it);
  }

  //@ToDo Need concrete plan to deal with job failures.
  else if(++job->retries > plugin->maxJobRetries())
  {
    //grid_available_cores-=job->cores; @ToDo This job never occupied any cores.
    job->status = CGSim::STATUS::FAILED; 
    CGSim::GlobalManagers::get_resource_manager()->global_pending_jobs.erase(job->id);
    CGSim::GlobalManagers::get_resource_manager()->global_failed_jobs[job->id] = job;
    plugin->onJobFailure(job); 
    it = pending_jobs.erase(it); 
    DISPATCHED_JOBS++; //Internal book keeping
    ACTIVATED_JOBS++;
  }

  else ++it;
  }
}

void JOB_EXECUTOR::dispatch_site_pending_jobs(std::string& site_name)
{
  auto* s=CGSim::GlobalManagers::get_resource_manager()->get_site(site_name);
  auto available_cores = s->total_cores - s->used_cores;

  if(!s->job_assignment_enabled) return;

  while(!s->pending_jobs.empty() && s->job_assignment_enabled)
  {
    auto j=s->pending_jobs.front();
    if(j->cores>available_cores) break;
    plugin->assignJob(j);

    if(!j->cpu.empty())
    {
      available_cores-=j->cores; 
      j->status=CGSim::STATUS::ASSIGNED; 
      s->add_assigned_job(j); 
      s->pending_jobs.pop_front(); 
      JOBS_IN_SITE_PENDING--;
      onJobAssignment(j);
    }

    else if(++j->retries>=s->MAX_RETRIES)
    {
      j->status=CGSim::STATUS::FAILED; 
      s->pending_jobs.pop_front();
      s->add_failed_job(j);  
      plugin->onJobFailure(j); 
      DISPATCHED_JOBS++; 
      ACTIVATED_JOBS++;
      JOBS_IN_SITE_PENDING--;
    }
  }
}

void JOB_EXECUTOR::start_server()
{
  //@ToDo Put this while in a function, so it can be called again when failed jobs are resubmitted
  while (DISPATCHED_JOBS != TOTAL_JOBS) //All jobs have to be dispatched
  {
    if(pending_jobs.size() + DISPATCHED_JOBS + JOBS_IN_SITE_PENDING != TOTAL_JOBS) //All jobs have to be created
    {
    if(sg4::Engine::get_clock() < jobs.top()->creation_time || jobs.top()->creation_time == -1.0) advance_to_time(jobs.top()->creation_time);
    get_jobs();
    }

    else
    {
      while(!pending_activities.empty())
      {
        auto act = pending_activities.wait_any();
        if(act->get_name().find("Exec") != std::string::npos) break;
      }
    }

    //@ToDo If job cores are bigger than what any local cpu can handle, it can indefinitely block dispatch_site_pending_jobs
    if(!pending_jobs.empty()) dispatch_global_pending_jobs();
    CGSim::Utilities::printSimulationDashBoard(DISPATCHED_JOBS, TOTAL_JOBS, RUNNING_JOBS, FINISHED_JOBS, pending_jobs.size(), JOBS_IN_SITE_PENDING, 
    pending_activities.size(), sg4::Engine::get_clock(), CGSim::GlobalManagers::get_resource_manager()->get_grid_cpu_utilization());
  }

  while (ACTIVATED_JOBS != TOTAL_JOBS || !pending_activities.empty())
  {
    if (!pending_activities.empty()) pending_activities.wait_any();
    else sg4::this_actor::yield();
  }

  CGSim::GlobalManagers::PolicyManager::RUNNING = false;
  CGSim::Utilities::printSimulationDashBoard(DISPATCHED_JOBS, TOTAL_JOBS, RUNNING_JOBS, FINISHED_JOBS, pending_jobs.size(), JOBS_IN_SITE_PENDING, 
    pending_activities.size(), sg4::Engine::get_clock(), CGSim::GlobalManagers::get_resource_manager()->get_grid_cpu_utilization());
}

void JOB_EXECUTOR::onJobAssignment(Job* job)
{
  DISPATCHED_JOBS++;
  auto* job_host = sg4::Host::by_name(job->cpu);
  job->cpu_speed = job_host->get_speed();
  if(!job->disk.empty()){auto* job_disk = job_host->get_disk_by_name(job->disk); job->disk_read_bw = job_disk->get_read_bandwidth(); job->disk_write_bw = job_disk->get_write_bandwidth();}
  sg4::Host::by_name(job->cpu)->extension<HostExtensions>()->registerJob(job);
  plugin->onJobAssignment(job);
  sg4::MessageQueue* mqueue = sg4::MessageQueue::by_name(job->cpu + "-MQ");
  sg4::MessPtr job_transfer = mqueue->put_async(job)->set_name("Transfer_Job_" + job->id + "_to_" + job->cpu+"_from_JOB-SERVER");
  job_transfer->on_this_start_cb([job](simgrid::s4u::Mess const& me) {plugin->onJobTransferStart(job);});
  job_transfer->on_this_completion_cb([job](simgrid::s4u::Mess const& me)
    {job->resource_waiting_queue_time = sg4::Engine::get_clock() - job->creation_time; plugin->onJobTransferEnd(job);});
  pending_activities.push(job_transfer);
}

void JOB_EXECUTOR::execute_job(Job* j)
{
  auto exec_activity = Actions::exec_task_multi_thread_async(j);
  std::vector<sg4::IoPtr>   read_activities;
  std::vector<sg4::CommPtr> comm_activities;
  std::vector<sg4::IoPtr>   write_activities;

  for (const auto& filename : j->input_files) 
  {
    auto* file = CGSim::GlobalManagers::get_file_manager()->request_file(filename);
    if(j->disk.empty()) throw std::runtime_error("Disk not selected for Job " + j->id);
    auto read_activity = Actions::read_file_async(j,filename);
    std::string filelocation = "";
    CGSim::FileTransferDecisionMode mode = CGSim::FileTransferDecisionMode::COPY;

    plugin->onFileRequest(j, filename, file->size, file->locations, filelocation, mode);
    if(filelocation.empty()) throw std::runtime_error("File location not specified for file: "+filename);

    if (filelocation != j->site) 
    { 
      sg4::CommPtr comm_activity;
      auto incoming_file_transfers = CGSim::GlobalManagers::get_resource_manager()->get_site(j->site)->incoming_file_transfers;
      if(incoming_file_transfers.find(filename) != incoming_file_transfers.end())
      {
        auto src_site = incoming_file_transfers.at(filename);
        auto transfer_key = CGSim::GlobalManagers::get_file_manager()->generate_transfer_key(filename,src_site,j->site);
        comm_activity = CGSim::GlobalManagers::get_file_manager()->ongoing_transfers.at(transfer_key);
      }

      else 
      {
        comm_activity = Actions::transfer_file_async(j,filename,filelocation,j->site,mode);
        comm_activities.push_back(comm_activity);
      }

      comm_activity->add_successor(read_activity);
    }
   
    read_activity->add_successor(exec_activity);
    read_activities.push_back(read_activity);
  }

  for (const auto& [filename,size] : j->output_files) {
    if(j->disk.empty()) throw std::runtime_error("Disk not selected for Job " + j->id);
    auto write_activity = Actions::write_file_async(j,filename,CGSim::Utilities::parse_units_size(size));
    exec_activity->add_successor(write_activity);
    write_activities.push_back(write_activity);
  }

  for (const auto& comm_activity : comm_activities) {pending_activities.push(comm_activity);}
  for (const auto& read_activity : read_activities) {pending_activities.push(read_activity);}
  pending_activities.push(exec_activity);
  for (const auto& write_activity : write_activities) {pending_activities.push(write_activity);}


  for (const auto& comm_activity : comm_activities) {comm_activity->start();}
  for (const auto& read_activity : read_activities) {read_activity->start();}
  exec_activity->start();
  for (const auto& write_activity : write_activities) {write_activity->start();}

  ACTIVATED_JOBS++;
  RUNNING_JOBS++;
}

[[noreturn]] void JOB_EXECUTOR::receiver(const std::string& MQ_name)
{
  sg4::Actor::self()->daemonize();
  sg4::MessageQueue* mqueue = sg4::MessageQueue::by_name(MQ_name);

  while (true)
    {
    sg4::MessPtr mess = mqueue->get_async();
    mess->wait();
    auto* job = static_cast<Job*>(mess->get_payload());
    execute_job(job);
    }
}

void JOB_EXECUTOR::start_receivers()
{
  for (const auto& host : sg4::Engine::get_instance()->get_all_hosts()) 
  {
    if (host->get_name().find("JOB-SERVER_cpu") != std::string::npos) continue;
    if (host->get_name().find("_communication_server") != std::string::npos) continue;
    sg4::Actor::create(host->get_name() + "-actor", host, receiver, host->get_name() + "-MQ");
  }
}

void JOB_EXECUTOR::attach_callbacks()
{
  sg4::Engine::on_simulation_start_cb([](){plugin->onSimulationStart();});
  sg4::Engine::on_simulation_end_cb([]() {plugin->onSimulationEnd();});
}

}

}
