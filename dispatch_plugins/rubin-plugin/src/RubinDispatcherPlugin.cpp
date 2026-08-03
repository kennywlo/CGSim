#include "DispatcherPlugin.h"
#include "rubin_dispatcher.h"
#include "qgraph_workload.h"
#include "output.h"

class RubinDispatcherPlugin : public DispatcherPlugin {

public:
    RubinDispatcherPlugin();
    virtual JobQueue getWorkload() override;
    virtual Job* assignJob(Job* job) final override;

    virtual void onSimulationStart() final override;
    virtual void onSimulationEnd() final override;
    virtual void onJobExecutionStart(Job* job, simgrid::s4u::Exec const& ex) final override;
    virtual void onJobExecutionEnd(Job* job, simgrid::s4u::Exec const& ex) final override;
    virtual void onJobTransferStart(Job* job, simgrid::s4u::Mess const& me) final override;
    virtual void onJobTransferEnd(Job* job, simgrid::s4u::Mess const& me) final override;
    virtual void onFileTransferStart(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Comm const& co, const std::string& src_site, const std::string& dst_site) final override;
    virtual void onFileTransferEnd(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Comm const& co, const std::string& src_site, const std::string& dst_site) final override;
    virtual void onFileReadStart(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Io const& io) final override;
    virtual void onFileReadEnd(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Io const& io) final override;
    virtual void onFileWriteStart(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Io const& io) final override;
    virtual void onFileWriteEnd(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Io const& io) final override;

private:
    std::unique_ptr<QGRAPH_WORKLOAD>  qw = std::make_unique<QGRAPH_WORKLOAD>();
    std::unique_ptr<RUBIN_DISPATCHER> rd = std::make_unique<RUBIN_DISPATCHER>(qw.get());
    std::unique_ptr<OUTPUT>           ou = std::make_unique<OUTPUT>();

};

RubinDispatcherPlugin::RubinDispatcherPlugin()
{
}

JobQueue RubinDispatcherPlugin::getWorkload()
{
  return qw->getWorkload();
}

Job* RubinDispatcherPlugin::assignJob(Job* job)
{
  return rd->assignJob(job);
}

void RubinDispatcherPlugin::onSimulationStart()
{
  ou->onSimulationStart();
}

void RubinDispatcherPlugin::onSimulationEnd()
{
   ou->onSimulationEnd();
}

void RubinDispatcherPlugin::onJobExecutionStart(Job* job, simgrid::s4u::Exec const& ex)
{
   ou->onJobExecutionStart(job,ex);
}

void RubinDispatcherPlugin::onJobExecutionEnd(Job* job, simgrid::s4u::Exec const& ex)
{
   // Release children in the cluster DAG before logging, so the executor's
   // next pending-jobs poll already sees them as ready.
   // TODO(Raees): on failed executions this releases children as if the parent
   // succeeded — split into success/failure paths when the failure model
   // (failures.json, schema section 8) lands.
   qw->markDone(job);
   ou->onJobExecutionEnd(job,ex);
}

void RubinDispatcherPlugin::onJobTransferStart(Job* job, simgrid::s4u::Mess const& me)
{
   ou->onJobTransferStart(job,me);
}

void RubinDispatcherPlugin::onJobTransferEnd(Job* job, simgrid::s4u::Mess const& me)
{
   ou->onJobTransferEnd(job,me);
}

void RubinDispatcherPlugin::onFileTransferStart(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Comm const& co, const std::string& src_site, const std::string& dst_site)
{
   ou->onFileTransferStart(job,filename, filesize, co,src_site,dst_site);
}

void RubinDispatcherPlugin::onFileTransferEnd(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Comm const& co, const std::string& src_site, const std::string& dst_site)
{
   ou->onFileTransferEnd(job,filename, filesize, co,src_site,dst_site);
}

void RubinDispatcherPlugin::onFileReadStart(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Io const& io)
{
   ou->onFileReadStart(job,filename, filesize, io);
}

void RubinDispatcherPlugin::onFileReadEnd(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Io const& io)
{
   ou->onFileReadEnd(job,filename, filesize, io);
}

void RubinDispatcherPlugin::onFileWriteStart(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Io const& io)
{
   ou->onFileWriteStart(job,filename, filesize, io);
}

void RubinDispatcherPlugin::onFileWriteEnd(Job* job, const std::string& filename, const unsigned long long filesize, simgrid::s4u::Io const& io)
{
   ou->onFileWriteEnd(job,filename, filesize, io);
}

extern "C" RubinDispatcherPlugin* createRubinDispatcherPlugin()
{
    return new RubinDispatcherPlugin;
}
