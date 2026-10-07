#include "plugin.h"
#include "track4_dispatcher.h"
#include "track4_workload_manager.h"
#include "track4_output.h"

class Track4Plugin : public CGSim::Plugin {

public:
    Track4Plugin();
    virtual void setWorkload(CGSim::JobQueue& jobs) final override;
    virtual void assignJob(CGSim::Job* job) final override;

    virtual void onJobSubmission(CGSim::Job* job) final override;
    virtual void onJobAssignment(CGSim::Job* job) final override;
    virtual void onJobSitePending(CGSim::Job* job) final override;
    virtual void onJobFailure(CGSim::Job* job) final override;
    virtual void onJobExecutionStart(CGSim::Job* job) final override;
    virtual void onJobExecutionEnd(CGSim::Job* job) final override;
 

private:
    std::unique_ptr<TRACK4_DISPATCHER>        t4d = std::make_unique<TRACK4_DISPATCHER>();
    std::unique_ptr<TRACK4_WORKLOAD_MANAGER>  t4wm = std::make_unique<TRACK4_WORKLOAD_MANAGER>();
    std::unique_ptr<TRACK4_OUTPUT>            t4ou = std::make_unique<TRACK4_OUTPUT>();
    //std::unique_ptr<TRACK4_OUTPUT_CALIBRATION> t4ouc = std::make_unique<TRACK4_OUTPUT_CALIBRATION>();

};

Track4Plugin::Track4Plugin()
{
}

void Track4Plugin::setWorkload(CGSim::JobQueue& jobs)
{
   t4wm->setWorkload(jobs);
}

void Track4Plugin::assignJob(CGSim::Job* job)
{
   t4d->assignJob(job);
}

void Track4Plugin::onJobSubmission(CGSim::Job* job)
{
   t4ou->onJobStatusChange(job);
}

void Track4Plugin::onJobSitePending(CGSim::Job* job)
{
   t4ou->onJobStatusChange(job);
}

void Track4Plugin::onJobFailure(CGSim::Job* job)
{
   t4ou->onJobStatusChange(job);
}

void Track4Plugin::onJobAssignment(CGSim::Job* job)
{
   t4ou->onJobStatusChange(job);
}

void Track4Plugin::onJobExecutionStart(CGSim::Job* job)
{
   t4ou->onJobStatusChange(job);
}

void Track4Plugin::onJobExecutionEnd(CGSim::Job* job)
{
   t4ou->onJobStatusChange(job);
}

extern "C" Track4Plugin* createTrack4Plugin()
{
    return new Track4Plugin;
}
