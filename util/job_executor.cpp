#include "job_executor.h"

std::shared_ptr<DispatcherPlugin>    JOB_EXECUTOR::dispatcher;
sg4::ActivitySet                     JOB_EXECUTOR::pending_activities;
std::unordered_map<long long, Job*>  JOB_EXECUTOR::all_jobs;
std::vector<Job*>                    JOB_EXECUTOR::pending_jobs;
JobQueue                             JOB_EXECUTOR::jobs;
unsigned long                        JOB_EXECUTOR::DISPATCHED_JOBS = 0;
unsigned long                        JOB_EXECUTOR::ACTIVATED_JOBS = 0;
unsigned long                        JOB_EXECUTOR::FINISHED_JOBS = 0;
unsigned long                        JOB_EXECUTOR::TOTAL_JOBS;
unsigned long                        JOB_EXECUTOR::JOBS_IN_SITE_PENDING = 0;


unsigned long JOB_EXECUTOR::totalJobs(JobQueue jobs)
{
  while (!jobs.empty()) 
  {
      auto* job = jobs.top();
      all_jobs[job->jobid] = job;
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
  jobs = std::move(dispatcher->getWorkload());
  TOTAL_JOBS = totalJobs(jobs);
  std::cout << "TOTAL_JOBS: " << TOTAL_JOBS << std::endl;
  sg4::Actor::create("JOB-EXECUTOR-actor",job_server,start_server);
  sg4::Engine::get_instance()->run();
}

void JOB_EXECUTOR::get_jobs()
{
  while(DISPATCHED_JOBS != TOTAL_JOBS  && !jobs.empty())
  {
    Job* job = jobs.top();
    if(job->creation_time < 0) break;
    if (sg4::Engine::get_clock() >= job->creation_time) 
    {
      CGSim::get_file_manager()->request_file_location(job);
      pending_jobs.push_back(job);
      job->submission_time = sg4::Engine::get_clock();
      std::cout << job->jobid << ", submission time " << job->submission_time << ", creation time " << job->creation_time << std::endl;
      job->status = CGSim::STATUS::GlOBAL_PENDING;
      CGSim::get_site_manager()->GlobalPendingJobs[job->jobid] = job;
      dispatcher->onJobSubmission(job);
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
  while(jobs.top()->creation_time == -1) pending_activities.wait_any();
  
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
  auto grid_available_cores = CGSim::get_site_manager()->TOTAL_GRID_CORES - CGSim::get_site_manager()->USED_GRID_CORES;

  for(auto it = pending_jobs.begin(); it != pending_jobs.end();)
  {
  if(dispatcher->stopGlobalJobDispatching()) break;
  Job* job = *it;
  if(job->cores>grid_available_cores) break;
  dispatcher->assignJob(job);

  if(!job->comp_site.empty() && job->comp_host.empty())
  {
    job->status = CGSim::STATUS::SITE_PENDING;
    JOBS_IN_SITE_PENDING++;
    CGSim::get_site_manager()->GlobalPendingJobs.erase(job->jobid); 
    CGSim::get_site_manager()->get_site(job->comp_site)->pending_jobs.emplace_back(job);
    dispatcher->onJobSitePending(job);
    job->retries++;
    it = pending_jobs.erase(it);
  }

  else if(!job->comp_site.empty() && !job->comp_host.empty())
  {
    job->status = CGSim::STATUS::ASSIGNED;
    CGSim::get_site_manager()->GlobalPendingJobs.erase(job->jobid); 
    CGSim::get_site_manager()->get_site(job->comp_site)->assigned_jobs[job->jobid] = job;
    onJobAssignment(job); 
    it = pending_jobs.erase(it);
  }

  //@ToDo Need concrete plan to deal with job failures.
  else if(++job->retries > dispatcher->maxJobRetries())
  {
    grid_available_cores-=job->cores; 
    job->status = CGSim::STATUS::FAILED; 
    CGSim::get_site_manager()->GlobalPendingJobs.erase(job->jobid);
    CGSim::get_site_manager()->GlobalFailedJobs[job->jobid] = job;
    dispatcher->onJobFailure(job); 
    it = pending_jobs.erase(it); 
    DISPATCHED_JOBS++; //Internal book keeping
    ACTIVATED_JOBS++;
  }

  else ++it;
  }
}

void JOB_EXECUTOR::dispatch_site_pending_jobs(std::string& site_name)
{
  auto* s=CGSim::get_site_manager()->get_site(site_name);
  auto available_cores = s->total_cores - s->used_cores;

  if(!s->job_assignment_enabled) return;

  while(!s->pending_jobs.empty() && s->job_assignment_enabled)
  {
    auto j=s->pending_jobs.front();
    if(j->cores>available_cores) break;
    dispatcher->assignJob(j);

    if(!j->comp_host.empty())
    {
      available_cores-=j->cores; 
      j->status=CGSim::STATUS::ASSIGNED; 
      s->assigned_jobs[j->jobid]=j; 
      s->pending_jobs.pop_front(); 
      JOBS_IN_SITE_PENDING--;
      onJobAssignment(j);
    }

    else if(++j->retries>=s->MAX_RETRIES)
    {
      j->status=CGSim::STATUS::FAILED; 
      s->pending_jobs.pop_front();
      s->failed_jobs[j->jobid]=j;  
      dispatcher->onJobFailure(j); 
      DISPATCHED_JOBS++; 
      ACTIVATED_JOBS++;
    }
  }
}

void JOB_EXECUTOR::start_server()
{
  //@ToDo Put this while in a function, so it can be called again when failed jobs are resubmitted
  while (DISPATCHED_JOBS != TOTAL_JOBS) //All jobs have to be dispatched
  {
    std::cout << DISPATCHED_JOBS << " / " << TOTAL_JOBS << " jobs dispatched" << std::endl;
    std::cout << "Pending Jobs in Global Queue: " << pending_jobs.size() << std::endl;
    std::cout << "Pending Jobs in Site Queues: " << JOBS_IN_SITE_PENDING << std::endl;
    std::cout << "Pending Activities on Grid: " <<  pending_activities.size() << std::endl;
    std::cout << "Current Simulated Time: " << sg4::Engine::get_clock() << std::endl;
    std::cout << "Grid CPU Usage: " << CGSim::get_site_manager()->get_grid_cpu_utilization() << std::endl;

    if(pending_jobs.size() + DISPATCHED_JOBS + JOBS_IN_SITE_PENDING != TOTAL_JOBS) //All jobs have to be created
    {
    if(sg4::Engine::get_clock() < jobs.top()->creation_time || jobs.top()->creation_time == -1) advance_to_time(jobs.top()->creation_time);
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
  }

  while (ACTIVATED_JOBS != TOTAL_JOBS || !pending_activities.empty())
  {
    if (!pending_activities.empty()) pending_activities.wait_any();
    else sg4::this_actor::yield();
  }

  CGSim::PolicyManager::RUNNING = false;
}

void JOB_EXECUTOR::onJobAssignment(Job* job)
{
  DISPATCHED_JOBS++;
  std::cout << "Job: " << job->jobid << ", Cores: " << job->cores  << ", Status: " << CGSim::get_site_manager()->status_string.at(job->status) << " after " << job->retries << " tries" <<std::endl;
  sg4::Host::by_name(job->comp_host)->extension<HostExtensions>()->registerJob(job);
  dispatcher->onJobAssignment(job);
  sg4::MessageQueue* mqueue = sg4::MessageQueue::by_name(job->comp_host + "-MQ");
  sg4::MessPtr job_transfer = mqueue->put_async(job)->set_name("Transfer_Job_" + std::to_string(job->jobid) + "_to_" + job->comp_host+"_from_JOB-SERVER");
  job_transfer->on_this_start_cb([job](simgrid::s4u::Mess const& me) {dispatcher->onJobTransferStart(job, me);});
  job_transfer->on_this_completion_cb([job](simgrid::s4u::Mess const& me)
    {job->resource_waiting_queue_time = sg4::Engine::get_clock() - job->creation_time; dispatcher->onJobTransferEnd(job, me);});
  pending_activities.push(job_transfer);
}

void JOB_EXECUTOR::execute_job(Job* j)
{
  j->metadata["pending_output_writes"] = std::to_string(j->output_files.size());
  j->metadata["outputs_complete"] = "false";
  auto exec_activity = Actions::exec_task_multi_thread_async(j);
  std::vector<sg4::IoPtr>   read_activities;
  std::vector<sg4::CommPtr> comm_activities;
  std::vector<sg4::IoPtr>   write_activities;

  for (const auto& [filename,fileinfo] : j->input_files_sizes_locations) 
  {
    auto read_activity = Actions::read_file_async(j,filename);
    std::string filelocation = "";
    CGSim::FileTransferDecisionMode mode = CGSim::FileTransferDecisionMode::COPY;

    dispatcher->onFileRequest(j, filename, fileinfo.first, fileinfo.second, filelocation, mode);
    if(filelocation.empty()) throw std::runtime_error("File location not specified for file: "+filename);

    if (filelocation != j->comp_site) 
    { 
      sg4::CommPtr comm_activity;
      auto incoming_file_transfers = CGSim::get_site_manager()->get_site(j->comp_site)->incoming_file_transfers;
      if(incoming_file_transfers.find(filename) != incoming_file_transfers.end())
      {
        auto src_site = incoming_file_transfers.at(filename);
        auto transfer_key = CGSim::get_file_manager()->generate_transfer_key(filename,src_site,j->comp_site);
        comm_activity = CGSim::get_file_manager()->ongoing_transfers.at(transfer_key);
      }

      else 
      {
        comm_activity = Actions::transfer_file_async(j,filename,filelocation,j->comp_site,mode);
        comm_activities.push_back(comm_activity);
      }

      comm_activity->add_successor(read_activity);
    }
   
    read_activity->add_successor(exec_activity);
    read_activities.push_back(read_activity);
  }

  for (const auto& [filename,size] : j->output_files) {
    auto write_activity = Actions::write_file_async(j,filename,size);
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
  sg4::Engine::on_simulation_start_cb([](){dispatcher->onSimulationStart();});
  sg4::Engine::on_simulation_end_cb([]() {dispatcher->onSimulationEnd();});
}
