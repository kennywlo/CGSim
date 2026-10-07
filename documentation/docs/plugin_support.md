# Plugin Support

CGSim plugins are user defined shared libraries that allow the user to provide custom  workloads, job-placement logic, optional file-source decisions, and lifecycle callbacks used during a simulation.

CGSim's philosophy behind this plugin mechanism is to provide users with a modular design to test custom policies without needing to modify the core code.

## Configuration

The plugin path in the CGSim configuration is set via:

```json
{
  "Plugin": "/path/to/libMyPlugin.so"
}
```


## Writing a Plugin

A plugin can follow this structure:

```text
plugin/
├── CMakeModules/
│   └── FindSimGrid.cmake
├── include/
│   ├── dispatcher.h
│   ├── output.h
│   └── workload_manager.h
├── src/
│   ├── MyPlugin.cpp
│   ├── dispatcher.cpp
│   ├── output.cpp
│   └── workload_manager.cpp
└── CMakeLists.txt
```

The plugin entrypoint stays in `src/MyPlugin.cpp`, while workload generation, scheduling, and callback/output logic can be split into separate helper classes.

## CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.12)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

project("MyPlugin")

add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")

set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/CMakeModules/")

include_directories(include/)

file(GLOB SOURCES src/*.cpp)

add_library(MyPlugin SHARED ${SOURCES})

find_package(SimGrid REQUIRED)
find_package(Boost REQUIRED)
find_package(CGSim REQUIRED)

target_link_libraries(
    MyPlugin
    PUBLIC
    ${SimGrid_LIBRARY}
    ${Boost_LIBRARIES}
    CGSim::CGSim
)

target_include_directories(
    MyPlugin
    PUBLIC
    ${SimGrid_INCLUDE_DIR}
    ${CGSim_INCLUDE_DIR}
    ${Boost_INCLUDE_DIR}
)
```

Place `FindSimGrid.cmake` in:

```text
plugin/CMakeModules/FindSimGrid.cmake
```

It can be found here [CMakeModules](https://github.com/REDWOOD24/CGSim/tree/main/cmake/CMakeModules). The following line makes that module available to `find_package(SimGrid REQUIRED)`:

```cmake
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/CMakeModules/")
```


## Build

From the `plugin/` directory:

```bash
mkdir build
cd build
cmake ..
make -j
```

A typical Linux build produces:

```text
build/libMyPlugin.so
```

A typical macOS build produces:

```text
build/libMyPlugin.dylib
```


## Workload Manager

### `include/workload_manager.h`

```cpp
#ifndef WORKLOAD_MANAGER_H
#define WORKLOAD_MANAGER_H

#include "CGSim.h"

class WorkloadManager
{
public:
    WorkloadManager() = default;
    ~WorkloadManager() = default;

    JobQueue getWorkload();
};

#endif
```

### `src/workload_manager.cpp`

```cpp
#include "workload_manager.h"

JobQueue WorkloadManager::getWorkload()
{
    JobQueue workload;

    auto* job = new Job();

    job->jobid = 1;
    job->creation_time = 0.0;
    job->flops = 1000000000;
    job->cores = 1;

    workload.push(job);

    return workload;
}
```

`getWorkload()` returns the `JobQueue` used by CGSim.

A job can also define input files, output files, metadata:

```cpp
auto* job = new Job();

job->jobid = 2;
job->creation_time = 10.0;
job->flops = 5000000000;
job->cores = 4;

job->input_files.insert("input.dat");

job->output_files["result.dat"] = 400000000; //bytes

job->metadata["type"] = "analysis";

workload.push(job);
```

Jobs can be linked with parent/child dependencies by using `add_parent()` and `add_child()`.

A dependent job starts with a default `creation_time` of -1.0 so that CGSim does not submit it until its parent dependencies are satisfied.

```cpp
JobQueue WorkloadManager::getWorkload()
{
    JobQueue workload;

    auto* parent = new Job();

    parent->jobid = 1;
    parent->creation_time = 0.0;
    parent->flops = 1000000000;
    parent->cores = 1;

    auto* child = new Job();

    child->jobid = 2;
    child->creation_time = -1.0; //Don't have to set this, CGSim sets it by default
    child->flops = 2000000000;
    child->cores = 1;

    // The child depends on the parent.
    child->add_parent(parent->jobid);

    // Activate the child 10 simulated seconds after the parent finishes.
    parent->add_child(child->jobid, 10.0);

    workload.push(parent);
    workload.push(child);

    return workload;
}
```

In this example:

- job `1` is submitted at simulation time `0.0`;
- job `2` remains dependency-driven because its initial `creation_time` is negative;
- job `2` becomes eligible only after job `1` finishes;
- the `10.0` value passed to `add_child()` adds a 10-second simulated delay before the child is submitted.

For a child with multiple parents, register every parent on the child and register the child on each parent:

```cpp
child->add_parent(parent_a->jobid);
child->add_parent(parent_b->jobid);

parent_a->add_child(child->jobid, 0.0);
parent_b->add_child(child->jobid, 0.0);
```

CGSim waits until all parents have completed before activating the child.

## Dispatcher

### `include/dispatcher.h`

```cpp
#ifndef DISPATCHER_H
#define DISPATCHER_H

#include "CGSim.h"

class Dispatcher
{
public:
    Dispatcher() = default;
    ~Dispatcher() = default;

    Job* assignJob(Job* job);
};

#endif
```

### `src/dispatcher.cpp`

```cpp
#include "dispatcher.h"

Job* Dispatcher::assignJob(Job* job)
{
    auto* sm = CGSim::get_site_manager();

    for (const auto& site_name : sm->get_all_sites())
    {
        auto* site = sm->get_site(site_name);

        for (auto* cpu : site->cpus)
        {
            if (sm->get_cores_available(cpu) <
                static_cast<unsigned int>(job->cores))
            {
                continue;
            }

            job->comp_site = site_name;
            job->comp_host = cpu->get_name();

            if (!cpu->get_disks().empty())
            {
                job->disk =
                    cpu->get_disks().front()->get_name();
            }

            return job;
        }
    }

    job->comp_site.clear();
    job->comp_host.clear();

    return job;
}
```

`assignJob()` should modify and return the supplied `Job*`.

For direct host assignment, set:

```cpp
job->comp_site;
job->comp_host;
```

For jobs using disk I/O, also set:

```cpp
job->disk;
```

To place a job into a site's pending queue, set the site and leave the host empty:

```cpp
job->comp_site = "SiteA";
job->comp_host.clear();
```

To leave the job globally pending:

```cpp
job->comp_site.clear();
job->comp_host.clear();
```

## Output and Callbacks

### `include/output.h`

```cpp
#ifndef OUTPUT_H
#define OUTPUT_H

#include "CGSim.h"

class Output
{
public:
    Output() = default;
    ~Output() = default;

    void onSimulationStart();
    void onSimulationEnd();
    void onJobFinish(Job* job);
};

#endif
```

### `src/output.cpp`

```cpp
#include "output.h"

void Output::onSimulationStart()
{
    CG_SIM_LOG_INFO("Simulation started");
}

void Output::onSimulationEnd()
{
    CG_SIM_LOG_INFO("Simulation finished");
}

void Output::onJobFinish(Job* job)
{
    CG_SIM_LOG_INFO(
        "Job {} finished at simulation time {}",
        job->jobid,
        simgrid::s4u::Engine::get_clock()
    );
}
```

## Plugin

### `src/MyPlugin.cpp`

```cpp
#include "CGSim.h"

#include "dispatcher.h"
#include "output.h"
#include "workload_manager.h"

#include <memory>

class MyPlugin : public CGSim::Plugin
{
public:
    MyPlugin() = default;

    JobQueue getWorkload() final override
    {
        return workload_manager->getWorkload();
    }

    Job* assignJob(Job* job) final override
    {
        return dispatcher->assignJob(job);
    }

    void onSimulationStart() final override
    {
        output->onSimulationStart();
    }

    void onSimulationEnd() final override
    {
        output->onSimulationEnd();
    }

    void onJobFinish(Job* job) final override
    {
        output->onJobFinish(job);
    }

private:
    std::unique_ptr<Dispatcher> dispatcher =
        std::make_unique<Dispatcher>();

    std::unique_ptr<WorkloadManager> workload_manager =
        std::make_unique<WorkloadManager>();

    std::unique_ptr<Output> output =
        std::make_unique<Output>();
};

extern "C" CGSim::Plugin* createMyPlugin()
{
    return new MyPlugin();
}
```

The plugin class must implement:

```cpp
virtual JobQueue getWorkload() = 0;
virtual Job* assignJob(Job* job) = 0;
```

All other callbacks are optional.

## Factory Naming

The exported factory name is derived from the shared-library filename.

For:

```text
libMyPlugin.so
```

export:

```cpp
extern "C" CGSim::Plugin* createMyPlugin()
{
    return new MyPlugin();
}
```

For:

```text
libDataAwarePlugin.so
```

export:

```cpp
extern "C" CGSim::Plugin* createDataAwarePlugin()
{
    return new DataAwarePlugin();
}
```


## Optional Plugin Callbacks

### Simulation

```cpp
void beforeSimulationStart() override;
void onSimulationStart() override;
void onSimulationEnd() override;
```

### Job Lifecycle

```cpp
void onJobSubmission(Job* job) override;
void onJobSitePending(Job* job) override;
void onJobAssignment(Job* job) override;
void onJobFailure(Job* job) override;

void onJobExecutionStart(
    Job* job,
    simgrid::s4u::Exec const& exec
) override;

void onJobExecutionEnd(
    Job* job,
    simgrid::s4u::Exec const& exec
) override;

void onJobFinish(Job* job) override;

void onJobTransferStart(
    Job* job,
    simgrid::s4u::Mess const& message
) override;

void onJobTransferEnd(
    Job* job,
    simgrid::s4u::Mess const& message
) override;
```

### Job File Transfers

```cpp
void onFileTransferStart(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Comm const& comm,
    const std::string& src_site,
    const std::string& dst_site
) override;

void onFileTransferEnd(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Comm const& comm,
    const std::string& src_site,
    const std::string& dst_site
) override;
```

### Job File Reads

```cpp
void onFileReadStart(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Io const& io
) override;

void onFileReadEnd(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Io const& io
) override;
```

### Job File Writes

```cpp
void onFileWriteStart(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Io const& io
) override;

void onFileWriteEnd(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Io const& io
) override;
```

### User File Transfers

```cpp
void onUserFileTransferStart(
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Comm const& comm,
    const std::string& src_site,
    const std::string& dst_site,
    const std::string& metadata
) override;

void onUserFileTransferEnd(
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Comm const& comm,
    const std::string& src_site,
    const std::string& dst_site,
    const std::string& metadata
) override;
```

### User File Reads

```cpp
void onUserFileReadStart(
    const std::string& filename,
    const unsigned long long& filesize,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk,
    simgrid::s4u::Io const& io
) override;

void onUserFileReadEnd(
    const std::string& filename,
    const unsigned long long& filesize,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk,
    simgrid::s4u::Io const& io
) override;
```

### User File Writes

```cpp
void onUserFileWriteStart(
    const std::string& filename,
    const unsigned long long& filesize,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk,
    simgrid::s4u::Io const& io
) override;

void onUserFileWriteEnd(
    const std::string& filename,
    const unsigned long long& filesize,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk,
    simgrid::s4u::Io const& io
) override;
```

## Input File Source Selection

A plugin can control which replica is used for an input file by overriding:

```cpp
void onFileRequest(
    Job* job,
    std::string filename,
    long long filesize,
    std::unordered_set<std::string> file_locations,
    std::string& source_site,
    CGSim::FileTransferDecisionMode& mode
) override;
```

Example:

```cpp
void MyPlugin::onFileRequest(
    Job* job,
    std::string filename,
    long long filesize,
    std::unordered_set<std::string> file_locations,
    std::string& source_site,
    CGSim::FileTransferDecisionMode& mode)
{
    if (file_locations.count(job->comp_site))
    {
        source_site = job->comp_site;
        mode = CGSim::FileTransferDecisionMode::COPY;
        return;
    }

    source_site = *file_locations.begin();
    mode = CGSim::FileTransferDecisionMode::COPY;
}
```

## Dispatch Controls

A plugin can stop the current global dispatch pass with:

```cpp
bool stopGlobalJobDispatching() override;
```

Example:

```cpp
bool MyPlugin::stopGlobalJobDispatching()
{
    return CGSim::get_site_manager()
               ->get_grid_cpu_utilization() >= 0.90;
}
```

A plugin can configure the maximum number of global assignment retries with:

```cpp
int maxJobRetries() override;
```

Example:

```cpp
int MyPlugin::maxJobRetries()
{
    return 100;
}
```
