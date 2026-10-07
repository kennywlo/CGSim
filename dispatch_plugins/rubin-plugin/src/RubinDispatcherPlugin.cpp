#include "plugin.h"
#include "rubin_dispatcher.h"
#include "qgraph_workload.h"
#include "output.h"

class RubinDispatcherPlugin : public CGSim::Plugin {

public:
    RubinDispatcherPlugin();
    virtual void setWorkload(CGSim::JobQueue& jobs) final override;
    virtual void assignJob(CGSim::Job* job) final override;

    virtual void onSimulationStart() final override;
    virtual void onSimulationEnd() final override;
    virtual void onJobExecutionStart(CGSim::Job* job) final override;
    virtual void onJobExecutionEnd(CGSim::Job* job) final override;
    virtual void onJobTransferStart(CGSim::Job* job) final override;
    virtual void onJobTransferEnd(CGSim::Job* job) final override;
    virtual void onFileTransferStart(CGSim::Job* job, const std::string& filename, const unsigned long long filesize, const std::string& src_site, const std::string& dst_site) final override;
    virtual void onFileTransferEnd(CGSim::Job* job, const std::string& filename, const unsigned long long filesize, const std::string& src_site, const std::string& dst_site) final override;
    virtual void onFileReadStart(CGSim::Job* job, const std::string& filename, const unsigned long long filesize) final override;
    virtual void onFileReadEnd(CGSim::Job* job, const std::string& filename, const unsigned long long filesize) final override;
    virtual void onFileWriteStart(CGSim::Job* job, const std::string& filename, const unsigned long long filesize) final override;
    virtual void onFileWriteEnd(CGSim::Job* job, const std::string& filename, const unsigned long long filesize) final override;

private:
    std::unique_ptr<QGRAPH_WORKLOAD>  qw = std::make_unique<QGRAPH_WORKLOAD>();
    std::unique_ptr<RUBIN_DISPATCHER> rd = std::make_unique<RUBIN_DISPATCHER>();
    std::unique_ptr<OUTPUT>           ou = std::make_unique<OUTPUT>();

};

RubinDispatcherPlugin::RubinDispatcherPlugin()
{
}

void RubinDispatcherPlugin::setWorkload(CGSim::JobQueue& jobs)
{
  qw->setWorkload(jobs);
}

void RubinDispatcherPlugin::assignJob(CGSim::Job* job)
{
  rd->assignJob(job);
}

void RubinDispatcherPlugin::onSimulationStart()
{
  ou->onSimulationStart();
}

void RubinDispatcherPlugin::onSimulationEnd()
{
   ou->onSimulationEnd();
}

void RubinDispatcherPlugin::onJobExecutionStart(CGSim::Job* job)
{
   ou->onJobExecutionStart(job);
}

void RubinDispatcherPlugin::onJobExecutionEnd(CGSim::Job* job)
{
   // TODO(Raees): core releases children only when a parent reaches FINISHED;
   // failed parents leave their subtree blocked. Add failed_upstream propagation
   // when the failure model (failures.json, schema section 8) lands.
   ou->onJobExecutionEnd(job);
}

void RubinDispatcherPlugin::onJobTransferStart(CGSim::Job* job)
{
   ou->onJobTransferStart(job);
}

void RubinDispatcherPlugin::onJobTransferEnd(CGSim::Job* job)
{
   ou->onJobTransferEnd(job);
}

void RubinDispatcherPlugin::onFileTransferStart(CGSim::Job* job, const std::string& filename, const unsigned long long filesize, const std::string& src_site, const std::string& dst_site)
{
   ou->onFileTransferStart(job,filename, filesize, src_site,dst_site);
}

void RubinDispatcherPlugin::onFileTransferEnd(CGSim::Job* job, const std::string& filename, const unsigned long long filesize, const std::string& src_site, const std::string& dst_site)
{
   ou->onFileTransferEnd(job,filename, filesize, src_site,dst_site);
}

void RubinDispatcherPlugin::onFileReadStart(CGSim::Job* job, const std::string& filename, const unsigned long long filesize)
{
   ou->onFileReadStart(job,filename, filesize);
}

void RubinDispatcherPlugin::onFileReadEnd(CGSim::Job* job, const std::string& filename, const unsigned long long filesize)
{
   ou->onFileReadEnd(job,filename, filesize);
}

void RubinDispatcherPlugin::onFileWriteStart(CGSim::Job* job, const std::string& filename, const unsigned long long filesize)
{
   ou->onFileWriteStart(job,filename, filesize);
}

void RubinDispatcherPlugin::onFileWriteEnd(CGSim::Job* job, const std::string& filename, const unsigned long long filesize)
{
   ou->onFileWriteEnd(job,filename, filesize);
}

extern "C" RubinDispatcherPlugin* createRubinDispatcherPlugin()
{
    return new RubinDispatcherPlugin;
}
