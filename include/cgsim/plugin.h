#ifndef PLUGIN_H
#define PLUGIN_H

#include "job.h"
#include "file_manager.h"

namespace CGSim
{
class Plugin {
public:
  // Constructor
  Plugin() = default;

  // Destructor
  virtual ~Plugin() = default;

  // Delete copy constructor and copy assignment operator
  Plugin(const Plugin&) = delete;
  Plugin& operator=(const Plugin&) = delete;
  
  // Delete move constructor and move assignment operator
  Plugin(Plugin&&) = delete;
  Plugin& operator=(Plugin&&) = delete;


  /*------Workload definition Module Interface------*/
  
  //Pure virtual function must be implemented by derived classes to get the Workload
  virtual void setWorkload(JobQueue& jobs) = 0;
  

  /*------Workload Dispatch Module Interface------*/

  // Pure virtual function must be implemented by derived classes to assign Jobs
  virtual void assignJob(Job* job) = 0;
  

  /*------Interaction Module Interface------*/

  // Virtual function can be implemented to execute code before simulation start
  virtual void beforeSimulationStart(){}

  // Virtual function can be implemented to execute code on simulation start
  virtual void onSimulationStart(){}

  // Virtual function can be implemented to execute code on simulation end
  virtual void onSimulationEnd(){}

  // Virtual function can be implemented on job submission to grid
  virtual void onJobSubmission(Job* job){}

    // Virtual function can be implemented on job entering site pending queue
  virtual void onJobSitePending(Job* job){}

  // Virtual function can be implemented on job assignment to site 
  virtual void onJobAssignment(Job* job){}

  // Virtual function can be implemented on job submission to grid
  virtual void onJobFailure(Job* job){}

  // Virtual function can be implemented when a job execution starts
  virtual void onJobExecutionStart(Job* job){}

  // Virtual function can be implemented when a job execution finishes
  virtual void onJobExecutionEnd(Job* job){}

  // Virtual function can be implemented when a job finishes
  virtual void onJobFinish(Job* job){}

  // Virtual function can be implemented when a job transfer starts
  virtual void onJobTransferStart(Job* job){}

  // Virtual function can be implemented when a job transfer ends
  virtual void onJobTransferEnd(Job* job){}

  // Virtual function can be implemented when a file transfer starts
  virtual void onFileTransferStart(Job* job, const std::string& file_name, 
    const unsigned long long filesize, const std::string& src_site, const std::string& dst_site){}

  // Virtual function can be implemented when a file transfer ends
  virtual void onFileTransferEnd(Job* job, const std::string& file_name, 
    const unsigned long long filesize, const std::string& src_site, const std::string& dst_site){}

  // Virtual function can be implemented when a user defined file transfer starts
  virtual void onUserFileTransferStart(const std::string& file_name, const unsigned long long filesize, 
    const std::string& src_site, const std::string& dst_site, const std::string& metadata){}

  // Virtual function can be implemented when a user defined file transfer ends
  virtual void onUserFileTransferEnd(const std::string& file_name, const unsigned long long filesize, 
    const std::string& src_site, const std::string& dst_site, const std::string& metadata){}

  // Virtual function can be implemented when a file read starts
  virtual void onFileReadStart(Job* job,const std::string& file_name, const unsigned long long filesize){}

  // Virtual function can be implemented when a file read ends
  virtual void onFileReadEnd(Job* job,const std::string& file_name, const unsigned long long filesize){}

   // Virtual function can be implemented when a user defined file read starts
  virtual void onUserFileReadStart(const std::string& file_name, const unsigned long long& filesize, 
    const std::string& site_name, const std::string& cpu_name, const std::string& disk_name){}

  // Virtual function can be implemented when a user defined file read ends
  virtual void onUserFileReadEnd(const std::string& file_name, const unsigned long long& filesize, 
    const std::string& site_name, const std::string& cpu_name, const std::string& disk_name){}

  // Virtual function can be implemented when a file write starts
  virtual void onFileWriteStart(Job* job,const std::string& file_name, const unsigned long long filesize){}

  // Virtual function can be implemented when a file write ends
  virtual void onFileWriteEnd(Job* job, const std::string& file_name, const unsigned long long filesize){}

   // Virtual function can be implemented when a user defined file write starts
  virtual void onUserFileWriteStart(const std::string& file_name, const unsigned long long& filesize, 
    const std::string& site_name, const std::string& cpu_name, const std::string& disk_name){}

  // Virtual function can be implemented when a user defined file write ends
  virtual void onUserFileWriteEnd(const std::string& file_name, const unsigned long long& filesize, 
    const std::string& site_name, const std::string& cpu_name, const std::string& disk_name){}


  /*------Policy Module Interface------*/

    // Virtual function can be implemented to define how to handle job file requests
  virtual void onFileRequest(Job* j, const std::string& file_name, const long long& filesize, 
    const std::unordered_set<std::string>& file_locations, std::string& source_site, 
    CGSim::FileTransferDecisionMode& mode)
  {
  //Current default behavior, choose file at the comp site or pick the first one in the location list
  if(file_locations.find(j->get_site()) != file_locations.end()) source_site = j->get_site();
  else source_site = *(file_locations.begin());
  }

  // Virtual function can be implemented to stop global job dispatching.
  virtual bool stopGlobalJobDispatching(){return false;}

  // Virtual function can be implemented to set number of retries a job has before being marked as failed.
  virtual int maxJobRetries(){return 100000;}
};

}
#endif //PLUGIN_H
