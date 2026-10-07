# SiteManager

The `SiteManager` is CGSim's user-facing interface for inspecting the simulated computing grid, retrieving sites, observing CPU utilization, inspecting job queues and job state, accessing custom configuration parameters, and controlling selected site-level scheduling behavior.

## Overview

A CGSim simulation is made up of one or more computing **sites**.

Each site contains a collection of SimGrid compute hosts, and each compute host may contain multiple CPU cores and one or more disks. Jobs are assigned to these resources by the active CGSim plugin.

The `SiteManager` provides the high-level view of this infrastructure.

It can answer questions such as:

- What sites exist in the simulation?
- How many cores exist across the grid?
- How many cores are currently in use?
- What is the current CPU utilization of a site?
- Which compute hosts belong to a site?
- How many cores are available on a particular host?
- Which jobs are pending, assigned, running, finished, or failed at a site?
- Which jobs are still pending at the global grid level?
- Which global configuration parameters were supplied by the user?
- What site-specific properties were configured?
- Can site-level job assignment temporarily be disabled?

The `SiteManager` is especially useful inside:

- scheduling plugins;
- resource-selection logic;
- monitoring code;
- periodic policies;
- simulation callbacks;
- custom metrics collection.

---

## Accessing the SiteManager

CGSim uses one global `SiteManager` instance.

Access it with:

```cpp
auto* sm = CGSim::get_site_manager();
```

For example:

```cpp
#include <CGSim/CGSim.h>

void print_grid_utilization()
{
    auto* sm = CGSim::get_site_manager();

    std::cout
        << "Grid utilization: "
        << sm->get_grid_cpu_utilization()
        << '\n';
}
```

You may also include the SiteManager header directly:

```cpp
#include <CGSim/site_manager.h>
```

The class is implemented as a singleton and cannot be copied.

Users should normally obtain it through:

```cpp
CGSim::get_site_manager()
```

rather than trying to construct their own manager.

---

## Sites in CGSim

The main data structure exposed by the SiteManager is:

```cpp
CGSim::Site
```

A site represents the CGSim-level view of one simulated computing location.

The current structure is:

```cpp
struct Site
{
    std::string name;
    std::vector<sg4::Host*> cpus;
    long total_cores;
    long used_cores;
    long total_cpus;
    long used_cpus;
    std::deque<Job*> pending_jobs;
    std::unordered_map<long long, Job*> assigned_jobs;
    std::unordered_map<long long, Job*> running_jobs;
    std::unordered_map<long long, Job*> finished_jobs;
    std::unordered_map<long long, Job*> failed_jobs;
    std::unordered_map<std::string, std::string> custom_parameters;
    bool job_assignment_enabled;
    long MAX_RETRIES;
    std::unordered_map<std::string, std::string> incoming_file_transfers;
};
```

A `Site*` can be obtained with:

```cpp
auto* site = sm->get_site("SiteA");
```

---

## How sites are created

Sites are created from the site-information JSON configuration.

For each configured site, CGSim:

1. creates a SimGrid network zone;
2. creates the site's compute hosts;
3. sets the core count of each compute host;
4. creates configured disks;
5. creates an internal communication-server host;
6. calculates the site's total number of compute cores;
7. registers the compute hosts with the SiteManager;
8. registers the site's files with the FileManager.

Conceptually:

```text
Site configuration
      |
      v
SimGrid site / NetZone
      |
      +--> compute host 0
      |      +--> cores
      |      +--> disks
      |
      +--> compute host 1
      |      +--> cores
      |      +--> disks
      |
      +--> ...
      |
      +--> internal communication server
      |
      v
SiteManager Site
```

The SiteManager's `cpus` vector contains only the **compute hosts**.

It does not contain the site's internal communication-server host.

---

## Compute-host naming

CGSim generates compute-host names from the site name.

For example, a site named:

```text
SiteA
```

will have compute hosts named:

```text
SiteA_cpu-0
SiteA_cpu-1
SiteA_cpu-2
...
```

The numbering is generated while CGSim creates the site's CPU clusters.

This is useful when assigning jobs:

```cpp
job->comp_site = "SiteA";
job->comp_host = "SiteA_cpu-0";
```

However, scheduling code usually does not need to construct these names manually. It can iterate over:

```cpp
site->cpus
```

instead.

---

## Getting all sites

### `get_all_sites()`

```cpp
std::unordered_set<std::string>
get_all_sites();
```

Returns the names of all sites registered with the SiteManager.

Example:

```cpp
auto* sm = CGSim::get_site_manager();

auto sites = sm->get_all_sites();

for (const auto& site_name : sites) {
    std::cout << site_name << '\n';
}
```

The returned set is a copy.

Changing it does not modify the SiteManager.

!!! note
    `get_all_sites()` returns an `std::unordered_set`, so iteration order is not guaranteed.

If deterministic ordering matters:

```cpp
auto site_set = sm->get_all_sites();

std::vector<std::string> sites(
    site_set.begin(),
    site_set.end()
);

std::sort(sites.begin(), sites.end());
```

This is recommended for reproducible scheduling policies when site order affects the result.

---

## Checking whether a site exists

### `exists()`

```cpp
bool exists(const std::string& site_name);
```

Returns `true` if the requested site is registered.

Example:

```cpp
if (sm->exists("SiteA")) {
    std::cout << "SiteA exists\n";
}
```

This is useful before calling:

```cpp
get_site()
```

because `get_site()` throws if the site is unknown.

---

## Getting a Site object

### `get_site()`

```cpp
CGSim::Site*
get_site(const std::string& site_name);
```

Returns the live `Site` object for the named site.

Example:

```cpp
auto* site =
    CGSim::get_site_manager()->get_site("SiteA");

std::cout
    << site->name
    << " has "
    << site->total_cores
    << " cores\n";
```

If the site does not exist, `get_site()` throws:

```cpp
std::runtime_error
```

---

### `get_site()` returns live state

Unlike methods such as:

```cpp
get_all_sites()
get_global_pending_jobs()
```

which return copies of containers, `get_site()` returns a pointer to the actual SiteManager state.

For example:

```cpp
auto* site = sm->get_site("SiteA");

std::cout << site->used_cores;
```

reads the site's current live core-usage counter.

The returned Site contains public fields, so C++ also permits user code to modify them.

For normal plugin code, treat framework bookkeeping fields such as:

```text
total_cores
used_cores
total_cpus
used_cpus
pending_jobs
assigned_jobs
running_jobs
finished_jobs
failed_jobs
incoming_file_transfers
```

as **read-only observation state**.

CGSim updates these fields as jobs and transfers progress.

Manually changing them can make internal resource and job-state accounting inconsistent.

Fields such as:

```text
job_assignment_enabled
MAX_RETRIES
```

are intended to influence site-level dispatch behavior and are discussed later in this page.

---

## Site fields

### `name`

```cpp
std::string name;
```

The site's configured name.

Example:

```cpp
auto* site = sm->get_site("SiteA");

std::cout << site->name;
```

The value matches the site key from the site-information configuration.

---

### `cpus`

```cpp
std::vector<sg4::Host*> cpus;
```

Contains the site's SimGrid **compute hosts**.

Example:

```cpp
auto* site = sm->get_site("SiteA");

for (auto* cpu : site->cpus) {
    std::cout
        << cpu->get_name()
        << '\n';
}
```

This is one of the most useful Site fields for scheduling plugins.

A scheduler can inspect each CPU and query its available cores:

```cpp
for (auto* cpu : site->cpus) {

    auto available =
        sm->get_cores_available(cpu);

    if (available >= job->cores) {
        job->comp_host = cpu->get_name();
        break;
    }
}
```

The vector excludes:

- the site's internal communication server;
- the global `JOB-SERVER`.

It contains only compute hosts created from the site's configured `CPUInfo`.

---

### `total_cores`

```cpp
long total_cores;
```

The total number of compute cores at the site.

CGSim calculates it by summing the configured core count for every compute host.

For example:

```text
4 hosts × 16 cores = 64 total_cores
```

Example:

```cpp
auto* site = sm->get_site("SiteA");

std::cout
    << "Total cores: "
    << site->total_cores
    << '\n';
```

The site's internal communication-server core is **not** included.

---

### `used_cores`

```cpp
long used_cores;
```

The total number of site compute cores currently reserved by assigned/running jobs.

Example:

```cpp
long available =
    site->total_cores - site->used_cores;
```

CGSim increments this value when a job is registered on its selected compute host and decrements it when that job finishes.

For example:

```text
Site total_cores = 64

Job A uses 8
Job B uses 16

used_cores = 24
```

The SiteManager uses this value to calculate site utilization.

Do not manually update `used_cores`; it is maintained by CGSim's host-resource bookkeeping.

---

### `total_cpus`

```cpp
long total_cpus;
```

The number of compute hosts at the site.

This is equivalent to the size of:

```cpp
site->cpus
```

at registration time.

Example:

```cpp
std::cout
    << site->total_cpus
    << " compute hosts\n";
```

A CPU in this context is a SimGrid compute host, not an individual core.

---

### `used_cpus`

```cpp
long used_cpus;
```

The name of this field can be misleading.

In the current implementation, `used_cpus` is incremented only when a compute host reaches:

```text
0 available cores
```

and decremented when that host later has at least one core available again.

Therefore it currently represents:

> **the number of fully occupied compute hosts**

rather than:

> the number of compute hosts with at least one active job.

For example, suppose a 16-core host has one 4-core job:

```text
cores used      = 4
cores available = 12
```

That host does **not** increment `used_cpus`.

If another workload fills the remaining 12 cores:

```text
cores used      = 16
cores available = 0
```

then the site's:

```cpp
used_cpus
```

is incremented.

!!! important
    Do not interpret `used_cpus / total_cpus` as ordinary host utilization unless "used CPU" in your analysis specifically means "fully occupied compute host."

For actual CPU capacity utilization, prefer:

```cpp
get_site_cpu_utilization()
```

which uses core counts.

---

## Site CPU utilization

### `get_site_cpu_utilization()`

```cpp
double
get_site_cpu_utilization(
    const std::string& site_name
);
```

Returns:

```text
used site cores
---------------
total site cores
```

Example:

```cpp
double utilization =
    sm->get_site_cpu_utilization("SiteA");
```

If:

```text
total_cores = 64
used_cores  = 16
```

then:

```text
utilization = 0.25
```

Interpretation:

```text
0.0 -> no site cores are in use
0.5 -> half the site cores are in use
1.0 -> all site cores are in use
```

Example:

```cpp
if (sm->get_site_cpu_utilization("SiteA") < 0.50) {
    // SiteA is using less than half of its compute cores.
}
```

The method internally calls `get_site()`, so an unknown site name raises `std::runtime_error`.

A normally configured compute site should contain at least one core.

---

## Grid CPU utilization

### `get_grid_cpu_utilization()`

```cpp
double
get_grid_cpu_utilization();
```

Returns:

```text
used grid cores
---------------
total grid cores
```

Example:

```cpp
double utilization =
    sm->get_grid_cpu_utilization();
```

If the simulated grid contains:

```text
256 total compute cores
64 used compute cores
```

then:

```text
utilization = 0.25
```

The value is a fraction, not a percentage.

To print a percentage:

```cpp
std::cout
    << sm->get_grid_cpu_utilization() * 100.0
    << "%\n";
```

---

## Total grid cores

### `get_total_grid_cores()`

```cpp
long
get_total_grid_cores();
```

Returns the sum of `total_cores` for all registered compute sites.

Example:

```cpp
auto total =
    sm->get_total_grid_cores();
```

For:

```text
SiteA = 64 cores
SiteB = 128 cores
SiteC = 32 cores
```

the method returns:

```text
224
```

Internal communication-server and job-server cores are not part of this total.

---

## Used grid cores

### `get_used_grid_cores()`

```cpp
long
get_used_grid_cores();
```

Returns the total number of compute cores currently reserved by jobs across the grid.

Example:

```cpp
auto used =
    sm->get_used_grid_cores();

auto total =
    sm->get_total_grid_cores();

auto available =
    total - used;
```

CGSim updates this value when jobs are assigned to and released from compute hosts.

---

## Per-host core usage

The SiteManager can also expose the current core accounting of individual SimGrid compute hosts.

### `get_cores_available()`

```cpp
unsigned int
get_cores_available(sg4::Host* cpu);
```

Returns the number of currently available cores on the specified host.

Example:

```cpp
auto* site = sm->get_site("SiteA");

for (auto* cpu : site->cpus) {

    auto free =
        sm->get_cores_available(cpu);

    std::cout
        << cpu->get_name()
        << ": "
        << free
        << " free cores\n";
}
```

This value comes from CGSim's `HostExtensions` resource-accounting extension.

---

### `get_cores_used()`

```cpp
unsigned int
get_cores_used(sg4::Host* cpu);
```

Returns the number of cores currently reserved on the specified host.

Example:

```cpp
for (auto* cpu : site->cpus) {

    auto used =
        sm->get_cores_used(cpu);

    std::cout
        << cpu->get_name()
        << ": "
        << used
        << " used cores\n";
}
```

For a compute host:

```text
get_cores_used(cpu)
+
get_cores_available(cpu)
=
cpu->get_core_count()
```

assuming resource accounting remains internally consistent.

---

## Example: choose a host with enough cores

One common use of SiteManager is selecting a compute host inside `assignJob()`.

For example:

```cpp
Job* assignJob(Job* job) override
{
    auto* sm = CGSim::get_site_manager();

    auto* site =
        sm->get_site("SiteA");

    for (auto* cpu : site->cpus) {

        if (sm->get_cores_available(cpu)
            >= static_cast<unsigned int>(job->cores))
        {
            job->comp_site = site->name;
            job->comp_host = cpu->get_name();

            return job;
        }
    }

    return job;
}
```

This example only illustrates CPU selection.

A real scheduler may also consider:

- site utilization;
- host speed;
- disk availability;
- file locality;
- memory properties;
- queue length;
- custom site properties;
- current data transfers.

---

## Example: choose the least-utilized site

A simple site-selection policy could inspect all sites:

```cpp
std::string choose_least_utilized_site()
{
    auto* sm = CGSim::get_site_manager();

    auto site_names =
        sm->get_all_sites();

    std::string selected;
    double best = 2.0;

    for (const auto& name : site_names) {

        double utilization =
            sm->get_site_cpu_utilization(name);

        if (utilization < best) {
            best = utilization;
            selected = name;
        }
    }

    return selected;
}
```

If ties matter for reproducibility, sort the site names first because `get_all_sites()` returns an unordered set.

---

## Job state in the SiteManager

The SiteManager also provides a view of where jobs are in the CGSim scheduling lifecycle.

The main lifecycle is:

```text
Created / waiting for creation time
          |
          v
GLOBAL_PENDING
          |
          +----------------------------+
          |                            |
          v                            v
     SITE_PENDING                  ASSIGNED
          |                            |
          v                            |
      ASSIGNED <-----------------------+
          |
          v
       RUNNING
          |
          v
      FINISHED
```

A job can also enter:

```text
FAILED
```

during scheduling if it exceeds the configured retry limit.

The exact SiteManager collection used depends on where the failure occurs.

---

## Global pending jobs

### `get_global_pending_jobs()`

```cpp
std::unordered_map<long long, Job*>
get_global_pending_jobs();
```

Returns the current map of jobs that have entered the simulation but have not yet been assigned to a site queue or compute host.

The map is:

```text
job ID -> Job*
```

Example:

```cpp
auto pending =
    sm->get_global_pending_jobs();

for (const auto& [id, job] : pending) {
    std::cout
        << "Global pending job "
        << id
        << '\n';
}
```

The returned map is a copy.

Removing an entry from the returned map does not remove the job from CGSim.

---

### When a job enters global pending

When a job's creation time is reached, CGSim:

1. resolves its input-file metadata;
2. records its submission time;
3. sets:

```cpp
job->status =
    CGSim::STATUS::GlOBAL_PENDING;
```

4. adds it to the SiteManager's global pending map;
5. calls the plugin's:

```cpp
onJobSubmission(job)
```

callback.

!!! note
    The current enum member is spelled exactly:

```cpp
CGSim::STATUS::GlOBAL_PENDING
```

That unusual capitalization is part of the current public code.

---

## Moving from global pending to a site queue

A plugin can assign only a site:

```cpp
job->comp_site = "SiteA";
job->comp_host = "";
```

If the job has a site but no host after `assignJob()`, CGSim moves the job to that site's:

```cpp
pending_jobs
```

queue.

The job status becomes:

```cpp
CGSim::STATUS::SITE_PENDING
```

and CGSim invokes:

```cpp
onJobSitePending(job)
```

The job is removed from the global pending map at this point.

This allows a two-stage scheduling model:

```text
global scheduler
      |
      v
choose site
      |
      v
site pending queue
      |
      v
choose compute host
```

---

## Site pending jobs

### `Site::pending_jobs`

```cpp
std::deque<Job*> pending_jobs;
```

Contains jobs assigned to the site but not yet assigned to a compute host.

Example:

```cpp
auto* site =
    sm->get_site("SiteA");

std::cout
    << site->pending_jobs.size()
    << " jobs waiting at SiteA\n";
```

You can inspect the queue:

```cpp
for (auto* job : site->pending_jobs) {
    std::cout
        << "Job "
        << job->jobid
        << " needs "
        << job->cores
        << " cores\n";
}
```

Treat this deque as framework-managed state.

Do not manually push, pop, or reorder it unless you fully understand the job executor's bookkeeping.

---

## Assigned jobs

### `Site::assigned_jobs`

```cpp
std::unordered_map<long long, Job*>
assigned_jobs;
```

Contains jobs that have been assigned to a specific compute host but whose computation has not yet entered the running state.

CGSim inserts a job into this map after:

```cpp
job->comp_site
```

and:

```cpp
job->comp_host
```

have both been selected.

Example:

```cpp
auto* site =
    sm->get_site("SiteA");

for (const auto& [id, job] :
     site->assigned_jobs)
{
    std::cout
        << "Job "
        << id
        << " assigned to "
        << job->comp_host
        << '\n';
}
```

A job is removed from `assigned_jobs` when its computation activity begins.

---

## Running jobs

### `Site::running_jobs`

```cpp
std::unordered_map<long long, Job*>
running_jobs;
```

Contains jobs whose compute activity has started.

When execution begins, CGSim:

```text
removes job from assigned_jobs
adds job to running_jobs
sets status = RUNNING
```

Example:

```cpp
auto* site =
    sm->get_site("SiteA");

std::cout
    << site->running_jobs.size()
    << " running jobs\n";
```

A running job remains in this map while its computation executes.

If the job has output files, it remains logically active until its output-write completion path finishes the job.

---

## Finished jobs

### `Site::finished_jobs`

```cpp
std::unordered_map<long long, Job*>
finished_jobs;
```

Contains jobs that completed successfully at the site.

For jobs without output files, CGSim marks the job finished when computation completes.

For jobs with output files, the job is marked finished after the final output write completes.

At completion, CGSim:

```text
sets status = FINISHED
removes job from running_jobs
adds job to finished_jobs
releases reserved host/site/grid cores
calls onJobFinish(job)
```

Example:

```cpp
for (const auto& [id, job] :
     site->finished_jobs)
{
    std::cout
        << "Finished job "
        << id
        << '\n';
}
```

---

## Failed jobs at a site

### `Site::failed_jobs`

```cpp
std::unordered_map<long long, Job*>
failed_jobs;
```

Contains jobs that entered a site's pending queue but exceeded the site's retry limit before obtaining a compute-host assignment.

Example:

```cpp
auto* site =
    sm->get_site("SiteA");

for (const auto& [id, job] :
     site->failed_jobs)
{
    std::cout
        << "Site-level failed job "
        << id
        << '\n';
}
```

These failures are different from failures that occur while the job is still in the global pending stage.

---

## Global failed jobs

### `get_global_failed_jobs()`

```cpp
std::unordered_map<long long, Job*>
get_global_failed_jobs();
```

Returns jobs that failed during global dispatch before being placed into a site-local queue or assigned to a host.

Example:

```cpp
auto failed =
    sm->get_global_failed_jobs();

for (const auto& [id, job] : failed) {
    std::cout
        << "Global scheduling failure: "
        << id
        << '\n';
}
```

The returned map is a copy.

---

### Global versus site failures

CGSim currently keeps these failure collections separate:

```text
Global scheduling failure
    -> SiteManager::get_global_failed_jobs()

Site-pending scheduling failure
    -> Site::failed_jobs
```

Therefore, if you want to collect **all** scheduling failures, inspect both.

Example:

```cpp
auto global_failed =
    sm->get_global_failed_jobs();

std::size_t total_failed =
    global_failed.size();

for (const auto& site_name :
     sm->get_all_sites())
{
    total_failed +=
        sm->get_site(site_name)
          ->failed_jobs.size();
}
```

---

## Job status strings

### `get_status_string()`

```cpp
std::string
get_status_string(CGSim::STATUS status);
```

Converts a CGSim job-status enum to a lowercase string.

The current mappings are:

| Enum | String |
|---|---|
| `CGSim::STATUS::GlOBAL_PENDING` | `"global_pending"` |
| `CGSim::STATUS::SITE_PENDING` | `"site_pending"` |
| `CGSim::STATUS::ASSIGNED` | `"assigned"` |
| `CGSim::STATUS::RUNNING` | `"running"` |
| `CGSim::STATUS::FINISHED` | `"finished"` |
| `CGSim::STATUS::FAILED` | `"failed"` |
| `CGSim::STATUS::NONE` | `"none"` |

Example:

```cpp
std::cout
    << sm->get_status_string(job->status)
    << '\n';
```

This is useful for:

- logging;
- CSV output;
- metrics;
- human-readable reports.

---

## Resource accounting lifecycle

Core usage is updated through CGSim's `HostExtensions`.

When a job is assigned to a host, CGSim registers it on that host.

The accounting changes are:

```text
host cores_used      += job cores
host cores_available -= job cores

site used_cores      += job cores

grid used cores      += job cores
```

When the job finishes:

```text
host cores_used      -= job cores
host cores_available += job cores

site used_cores      -= job cores

grid used cores      -= job cores
```

This is why users should rely on:

```cpp
get_cores_available()
get_cores_used()
get_site_cpu_utilization()
get_grid_cpu_utilization()
```

instead of manually maintaining their own resource counters.

---

## When cores become reserved

A subtle but important point is that CGSim reserves job cores when the job receives its compute-host assignment.

That occurs before the job's compute activity actually begins.

Therefore:

```cpp
site->used_cores
```

and:

```cpp
get_used_grid_cores()
```

represent cores currently **reserved by assigned/running jobs**, not only cores whose compute execution is actively consuming simulated FLOPs at that exact moment.

This matters if you compare SiteManager utilization with lower-level SimGrid execution activity.

---

## Site assignment control

### `Site::job_assignment_enabled`

```cpp
bool job_assignment_enabled = true;
```

This flag controls whether CGSim dispatches jobs from the site's:

```cpp
pending_jobs
```

queue to compute hosts.

The default is:

```cpp
true
```

When set to:

```cpp
false
```

`dispatch_site_pending_jobs()` returns without assigning local pending jobs.

Example:

```cpp
auto* site =
    CGSim::get_site_manager()
        ->get_site("SiteA");

site->job_assignment_enabled = false;
```

This can be used to model situations such as:

- maintenance;
- temporary scheduling shutdown;
- simulated site policy changes;
- draining a local queue;
- experimental admission-control logic.

---

### What `job_assignment_enabled` does not do

The flag applies specifically to **site-pending dispatch**.

It does not automatically:

- stop jobs that are already running;
- cancel jobs that are already assigned;
- disable the SimGrid hosts;
- prevent the plugin's global `assignJob()` from assigning a job directly to both a site and host.

For example, a global scheduling decision that sets:

```cpp
job->comp_site = "SiteA";
job->comp_host = "SiteA_cpu-0";
```

does not pass through the site-pending dispatch check.

Therefore, if your model needs a completely unavailable site, your plugin should also avoid selecting that site or its hosts during global assignment.

---

### Re-enabling site assignment

You can restore local assignment with:

```cpp
site->job_assignment_enabled = true;
```

However, the current implementation only invokes site-pending redispatch at specific framework events, particularly when a job at the site finishes.

The source currently warns that disabling this flag can be risky: if jobs remain pending and there is no later site event that causes the queue to be reconsidered, simply turning the flag back on may not immediately trigger dispatch.

For temporary site outages, make sure your model has an event that causes pending jobs to be reconsidered after re-enabling assignment.

---

## Site retry limit

### `Site::MAX_RETRIES`

```cpp
long MAX_RETRIES = 100000;
```

Controls how many failed compute-host assignment attempts a job may make while it is in a site's pending queue.

The default is:

```text
100000
```

When a site-pending job repeatedly passes through `assignJob()` without receiving:

```cpp
job->comp_host
```

its retry count increases.

When:

```cpp
job->retries >= site->MAX_RETRIES
```

the job is moved to:

```cpp
site->failed_jobs
```

and its status becomes:

```cpp
CGSim::STATUS::FAILED
```

Example:

```cpp
auto* site =
    sm->get_site("SiteA");

site->MAX_RETRIES = 100;
```

---

### Site retries versus global retries

There are two different retry mechanisms.

### Global pending retry limit

While a job is still in the global queue, CGSim uses the plugin's:

```cpp
maxJobRetries()
```

behavior.

A job that exceeds the global retry limit is stored in:

```cpp
get_global_failed_jobs()
```

### Site-pending retry limit

After the job has entered a site queue, CGSim uses:

```cpp
site->MAX_RETRIES
```

A job that exceeds this limit is stored in:

```cpp
site->failed_jobs
```

These values are independent.

---

## Global custom parameters

### `get_custom_parameter()`

```cpp
std::string
get_custom_parameter(
    const std::string& param_name
);
```

Returns a value from the simulation's top-level:

```json
"Custom_Parameters"
```

configuration.

For example, the main CGSim configuration can contain:

```json
{
  "Grid_Name": "MyGrid",

  "Sites_Information": "sites.json",
  "Sites_Connection_Information": "connections.json",
  "Dispatcher_Plugin": "libMyPlugin.so",

  "Limited_Sites": [],

  "Custom_Parameters": {
    "experiment": "baseline",
    "scheduler_mode": "backfill",
    "dataset_version": "v3"
  }
}
```

Then plugin code can read:

```cpp
auto* sm = CGSim::get_site_manager();

auto experiment =
    sm->get_custom_parameter("experiment");
```

which returns:

```text
baseline
```

All values are stored as strings.

---

### Missing global custom parameter

The implementation uses:

```cpp
Custom_Parameters.at(param_name)
```

so requesting a key that does not exist throws:

```cpp
std::out_of_range
```

A plugin should only request keys it expects to exist, or catch the exception if the parameter is optional.

Example:

```cpp
try {
    auto value =
        sm->get_custom_parameter("optional_setting");
}
catch (const std::out_of_range&) {
    // Parameter was not configured.
}
```

---

## Site-specific custom parameters

Each `Site` also contains:

```cpp
std::unordered_map<std::string, std::string>
custom_parameters;
```

These values come from that site's:

```json
"SITE_PROPERTIES"
```

object.

For example:

```json
{
  "SiteA": {

    "SITE_PROPERTIES": {
      "storage_capacity_bytes": "2000000000000",
      "region": "us-east",
      "site_class": "large",
      "energy_profile": "renewable"
    },

    "CPUInfo": [
      {
        "units": 2,
        "cores": 16,
        "speed": 20000000.0,
        "BW_CPU": "100GBps",
        "LAT_CPU": "100ns",

        "properties": [],

        "disks": []
      }
    ],

    "files": []
  }
}
```

Then:

```cpp
auto* site =
    sm->get_site("SiteA");

auto region =
    site->custom_parameters.at("region");
```

returns:

```text
us-east
```

---

## Global parameters versus site properties

These two mechanisms are different.

### Global parameter

Configuration:

```json
"Custom_Parameters": {
  "scheduler_mode": "backfill"
}
```

Read with:

```cpp
sm->get_custom_parameter(
    "scheduler_mode"
);
```

---

### Site parameter

Configuration:

```json
"SiteA": {
  "SITE_PROPERTIES": {
    "region": "us-east"
  }
}
```

Read with:

```cpp
sm->get_site("SiteA")
  ->custom_parameters.at("region");
```

---

### Comparison

| Configuration location | Scope | Access |
|---|---|---|
| Top-level `Custom_Parameters` | Whole simulation | `SiteManager::get_custom_parameter()` |
| Site `SITE_PROPERTIES` | One site | `Site::custom_parameters` |

This distinction is useful when designing plugins.

Use global custom parameters for experiment-wide settings and site properties for site-specific metadata.

---

## Site properties are strings

The parser stores site properties as:

```cpp
std::unordered_map<std::string, std::string>
```

so values should be supplied as JSON strings.

For example:

```json
"SITE_PROPERTIES": {
  "priority": "10",
  "region": "eu-west"
}
```

If you need a numeric value:

```cpp
int priority =
    std::stoi(
        site->custom_parameters.at("priority")
    );
```

---

## CPU/host properties

SiteManager's:

```cpp
Site::custom_parameters
```

contains site-level `SITE_PROPERTIES`.

CPU-cluster properties are attached directly to the SimGrid host rather than copied into the Site object.

For example, a host property can be read through SimGrid:

```cpp
for (auto* cpu : site->cpus) {

    const char* ram =
        cpu->get_property("ram");

    if (ram) {
        std::cout
            << cpu->get_name()
            << " RAM: "
            << ram
            << '\n';
    }
}
```

This gives a scheduling plugin access to both:

```text
site-level metadata
+
host-level metadata
```

---

## Example: region-aware site selection

Suppose sites define:

```json
"SITE_PROPERTIES": {
  "region": "us-east"
}
```

A plugin can filter sites by region:

```cpp
std::vector<CGSim::Site*>
sites_in_region(
    const std::string& region
)
{
    auto* sm =
        CGSim::get_site_manager();

    std::vector<CGSim::Site*> result;

    for (const auto& name :
         sm->get_all_sites())
    {
        auto* site =
            sm->get_site(name);

        auto it =
            site->custom_parameters.find("region");

        if (it !=
            site->custom_parameters.end()
            &&
            it->second == region)
        {
            result.push_back(site);
        }
    }

    return result;
}
```

---

## Example: resource-aware scheduling

The SiteManager provides enough information to implement basic site and CPU selection.

For example:

```cpp
Job* assignJob(Job* job) override
{
    auto* sm =
        CGSim::get_site_manager();

    for (const auto& site_name :
         sm->get_all_sites())
    {
        auto* site =
            sm->get_site(site_name);

        if (!site->job_assignment_enabled) {
            continue;
        }

        if (site->total_cores - site->used_cores
            < job->cores)
        {
            continue;
        }

        for (auto* cpu : site->cpus) {

            if (sm->get_cores_available(cpu)
                >= static_cast<unsigned int>(
                    job->cores))
            {
                job->comp_site =
                    site->name;

                job->comp_host =
                    cpu->get_name();

                return job;
            }
        }
    }

    return job;
}
```

This is a simple example.

A real scheduling policy may combine SiteManager with:

```cpp
CGSim::get_file_manager()
```

to incorporate data locality and storage state.

---

## Example: file-aware scheduling

A scheduler can use SiteManager and FileManager together.

Conceptually:

```cpp
auto* sm =
    CGSim::get_site_manager();

auto* fm =
    CGSim::get_file_manager();
```

For each site:

```text
1. Is there enough CPU capacity?
2. Are the job's input files already present?
3. Is storage available?
4. Which host can accommodate the required cores?
```

Example locality count:

```cpp
std::size_t local_files = 0;

for (const auto& file :
     job->input_files)
{
    if (fm->exists(
            file,
            site->name))
    {
        local_files++;
    }
}
```

The SiteManager supplies compute state while the FileManager supplies data-placement state.

---

## Incoming file transfers

### `Site::incoming_file_transfers`

```cpp
std::unordered_map<std::string, std::string>
incoming_file_transfers;
```

Tracks files currently being transferred into the site.

The map represents:

```text
filename -> source site
```

For example:

```text
input.root -> SiteA
```

inside `SiteB` means a transfer of `input.root` from `SiteA` into `SiteB` is currently in progress.

CGSim uses this map when jobs request data so that another job can reuse an existing incoming transfer rather than starting a duplicate transfer.

---

### Treat incoming transfers as framework-managed

Although the field is publicly visible through `Site`, users should normally treat:

```cpp
incoming_file_transfers
```

as read-only state.

The FileManager updates it as transfers begin and finish.

Manually changing it can make the SiteManager and FileManager disagree about active transfers.

For user-defined transfer checks, prefer FileManager APIs such as:

```cpp
is_in_flight(...)
```

when appropriate.

---

## Example: inspect incoming data

```cpp
auto* site =
    sm->get_site("SiteB");

for (const auto& [filename, source] :
     site->incoming_file_transfers)
{
    std::cout
        << filename
        << " is arriving from "
        << source
        << '\n';
}
```

This can be useful for:

- monitoring;
- data-aware scheduling;
- avoiding redundant source choices;
- debugging transfer behavior.

---

## Site queue sizes

The Site struct makes it easy to inspect queue and state counts.

Example:

```cpp
auto* site =
    sm->get_site("SiteA");

std::cout
    << "pending: "
    << site->pending_jobs.size()
    << '\n'
    << "assigned: "
    << site->assigned_jobs.size()
    << '\n'
    << "running: "
    << site->running_jobs.size()
    << '\n'
    << "finished: "
    << site->finished_jobs.size()
    << '\n'
    << "failed: "
    << site->failed_jobs.size()
    << '\n';
```

These metrics are useful in plugin callbacks or periodic policies.

---

## Example: site snapshot function

A monitoring helper might look like:

```cpp
void print_site_snapshot(
    const std::string& name
)
{
    auto* sm =
        CGSim::get_site_manager();

    auto* site =
        sm->get_site(name);

    std::cout
        << "Site: "
        << site->name
        << '\n';

    std::cout
        << "CPU utilization: "
        << sm->get_site_cpu_utilization(name)
        << '\n';

    std::cout
        << "Used cores: "
        << site->used_cores
        << " / "
        << site->total_cores
        << '\n';

    std::cout
        << "Pending jobs: "
        << site->pending_jobs.size()
        << '\n';

    std::cout
        << "Assigned jobs: "
        << site->assigned_jobs.size()
        << '\n';

    std::cout
        << "Running jobs: "
        << site->running_jobs.size()
        << '\n';

    std::cout
        << "Finished jobs: "
        << site->finished_jobs.size()
        << '\n';

    std::cout
        << "Failed jobs: "
        << site->failed_jobs.size()
        << '\n';
}
```

---

## Using SiteManager from simulation callbacks

SiteManager state can be inspected from plugin lifecycle and job callbacks.

For example:

```cpp
void onSimulationStart() override
{
    auto* sm =
        CGSim::get_site_manager();

    std::cout
        << "Grid cores: "
        << sm->get_total_grid_cores()
        << '\n';
}
```

Or when a job begins execution:

```cpp
void onJobExecutionStart(
    Job* job,
    simgrid::s4u::Exec const& ex
) override
{
    auto* sm =
        CGSim::get_site_manager();

    auto utilization =
        sm->get_site_cpu_utilization(
            job->comp_site
        );

    std::cout
        << job->comp_site
        << " utilization: "
        << utilization
        << '\n';
}
```

Because the simulation is event-driven, these queries reflect the current SiteManager accounting at the time the callback runs.

---

## Using SiteManager from PolicyManager

SiteManager is also useful inside repeating policies.

For example, a policy could inspect site utilization every simulated interval:

```cpp
void inspect_grid()
{
    auto* sm =
        CGSim::get_site_manager();

    for (const auto& site_name :
         sm->get_all_sites())
    {
        std::cout
            << site_name
            << ": "
            << sm->get_site_cpu_utilization(
                   site_name)
            << '\n';
    }
}
```

This can support:

- adaptive scheduling;
- simulated maintenance;
- load balancing;
- data replication decisions;
- utilization logging.

---

## Example: temporarily disable a heavily loaded site

A policy could use a custom rule:

```cpp
void update_site_admission()
{
    auto* sm =
        CGSim::get_site_manager();

    for (const auto& name :
         sm->get_all_sites())
    {
        auto* site =
            sm->get_site(name);

        double utilization =
            sm->get_site_cpu_utilization(name);

        if (utilization > 0.95) {
            site->job_assignment_enabled = false;
        }
        else if (utilization < 0.70) {
            site->job_assignment_enabled = true;
        }
    }
}
```

Remember that `job_assignment_enabled` only controls dispatch from the site's pending queue. Your global `assignJob()` logic should also respect the same state if you want the site to be completely excluded from new assignments.

---

## Status lifecycle in detail

The SiteManager job collections can be understood as the following state machine.

### Global pending

```text
status:
    GlOBAL_PENDING

stored in:
    SiteManager global pending map
```

The job has entered the simulation but is not yet tied to a site queue or host.

---

### Site pending

```text
status:
    SITE_PENDING

stored in:
    Site::pending_jobs
```

The scheduler selected:

```cpp
job->comp_site
```

but did not select:

```cpp
job->comp_host
```

---

### Assigned

```text
status:
    ASSIGNED

stored in:
    Site::assigned_jobs
```

The site and compute host are selected.

CGSim also reserves the requested cores at this stage.

---

### Running

```text
status:
    RUNNING

stored in:
    Site::running_jobs
```

The SimGrid execution activity has started.

The job is removed from `assigned_jobs`.

---

### Finished

```text
status:
    FINISHED

stored in:
    Site::finished_jobs
```

The job's completion path has finished.

For jobs with outputs, this happens after all output writes finish.

Core reservations are released.

---

### Failed

A scheduling failure may appear in one of two places.

### Global failure

```text
SiteManager global failed map
```

### Site-pending failure

```text
Site::failed_jobs
```

---

## Important timing detail: assigned versus running

The distinction between:

```text
ASSIGNED
```

and:

```text
RUNNING
```

is important.

Once the job receives a compute host, CGSim:

- places it in `assigned_jobs`;
- reserves its requested cores;
- transfers the job message to the host.

Only when the execution activity actually starts does CGSim move it into:

```cpp
running_jobs
```

Therefore a job can consume SiteManager core capacity while still appearing in:

```cpp
assigned_jobs
```

rather than `running_jobs`.

This is expected behavior in the current model.

---

## Important timing detail: computation end versus job finish

A job with no output files is normally marked finished when its compute activity completes.

A job with output files remains unfinished until all output file writes complete.

Therefore:

```text
computation completed
```

does not always mean:

```text
job is already in Site::finished_jobs
```

This distinction matters for metrics involving:

- CPU completion;
- total job completion;
- output-I/O delay.

---

## Public API reference

### `CGSim::get_site_manager()`

```cpp
CGSim::SiteManager*
CGSim::get_site_manager();
```

Returns the global SiteManager instance.

Example:

```cpp
auto* sm =
    CGSim::get_site_manager();
```

---

### `exists(site_name)`

```cpp
bool exists(
    const std::string& site_name
);
```

Returns whether the site is registered.

---

### `get_all_sites()`

```cpp
std::unordered_set<std::string>
get_all_sites();
```

Returns a copy of all registered site names.

Order is not guaranteed.

---

### `get_site(site_name)`

```cpp
CGSim::Site*
get_site(
    const std::string& site_name
);
```

Returns the live Site object.

Throws `std::runtime_error` if the site does not exist.

---

### `get_site_cpu_utilization(site_name)`

```cpp
double
get_site_cpu_utilization(
    const std::string& site_name
);
```

Returns:

```text
site used cores / site total cores
```

---

### `get_grid_cpu_utilization()`

```cpp
double
get_grid_cpu_utilization();
```

Returns:

```text
grid used cores / grid total cores
```

---

### `get_total_grid_cores()`

```cpp
long
get_total_grid_cores();
```

Returns the total number of compute cores across registered sites.

---

### `get_used_grid_cores()`

```cpp
long
get_used_grid_cores();
```

Returns currently reserved compute cores across the grid.

---

### `get_cores_available(cpu)`

```cpp
unsigned int
get_cores_available(
    sg4::Host* cpu
);
```

Returns the host's available CGSim cores.

---

### `get_cores_used(cpu)`

```cpp
unsigned int
get_cores_used(
    sg4::Host* cpu
);
```

Returns the host's currently reserved CGSim cores.

---

### `get_global_pending_jobs()`

```cpp
std::unordered_map<long long, Job*>
get_global_pending_jobs();
```

Returns a copy of jobs currently in the grid-level pending state.

---

### `get_global_failed_jobs()`

```cpp
std::unordered_map<long long, Job*>
get_global_failed_jobs();
```

Returns a copy of jobs that failed during global dispatch.

It does not include jobs stored in individual:

```cpp
Site::failed_jobs
```

maps.

---

### `get_custom_parameter(param_name)`

```cpp
std::string
get_custom_parameter(
    const std::string& param_name
);
```

Returns a top-level value from the main configuration's:

```json
"Custom_Parameters"
```

object.

Throws `std::out_of_range` for an unknown key.

---

### `get_status_string(status)`

```cpp
std::string
get_status_string(
    CGSim::STATUS status
);
```

Returns the lowercase human-readable name of a job status.

---

## `Site` field reference

| Field | Meaning | Recommended user behavior |
|---|---|---|
| `name` | Site name | Read |
| `cpus` | Compute-host pointers | Read / iterate |
| `total_cores` | Total compute cores | Read |
| `used_cores` | Reserved site cores | Read |
| `total_cpus` | Number of compute hosts | Read |
| `used_cpus` | Number of fully occupied hosts | Read |
| `pending_jobs` | Site-pending queue | Read |
| `assigned_jobs` | Assigned jobs | Read |
| `running_jobs` | Running jobs | Read |
| `finished_jobs` | Completed jobs | Read |
| `failed_jobs` | Site-level failed jobs | Read |
| `custom_parameters` | Site `SITE_PROPERTIES` | Read; modify only intentionally |
| `job_assignment_enabled` | Gate site-pending dispatch | May be changed by policy |
| `MAX_RETRIES` | Site-pending retry limit | May be configured by policy |
| `incoming_file_transfers` | Incoming file → source site | Read; framework-managed |

---

## Framework-managed SiteManager state

The SiteManager also contains private state used by the framework:

```cpp
std::unordered_map<std::string, Site*> Sites;

std::unordered_set<std::string> list_of_sites;

std::unordered_map<long long, Job*>
    GlobalPendingJobs;

std::unordered_map<long long, Job*>
    GlobalFailedJobs;

long long TOTAL_GRID_CORES;

long long USED_GRID_CORES;

std::unordered_map<std::string, std::string>
    Custom_Parameters;
```

Users access this state through the public methods rather than modifying it directly.

CGSim's:

- `Platform`;
- `JOB_EXECUTOR`;
- `HostExtensions`;

are friends of SiteManager because they maintain this internal bookkeeping.

---

## Site registration is framework-managed

The internal:

```cpp
register_site(...)
```

method is private.

Users do not manually register sites through SiteManager.

Sites are registered automatically when the `Platform` is built from the configuration files.

At registration, SiteManager records:

```text
site name
compute-host vector
total core count
compute-host count
site properties
```

and increments the grid-wide total-core counter.

---

## Choosing SiteManager data for scheduling

A scheduler should generally use these values:

### Grid-level screening

```cpp
sm->get_used_grid_cores()
sm->get_total_grid_cores()
sm->get_grid_cpu_utilization()
```

---

### Site-level screening

```cpp
site->total_cores
site->used_cores
sm->get_site_cpu_utilization(site->name)
site->pending_jobs.size()
site->job_assignment_enabled
```

---

### Host-level screening

```cpp
site->cpus
sm->get_cores_available(cpu)
sm->get_cores_used(cpu)
cpu->get_speed()
cpu->get_core_count()
cpu->get_property(...)
```

---

### Data-aware screening

Use FileManager together with SiteManager:

```cpp
CGSim::get_file_manager()
```

---

## Example: select the site with the most free cores

```cpp
CGSim::Site*
select_site_with_most_free_cores()
{
    auto* sm =
        CGSim::get_site_manager();

    CGSim::Site* selected = nullptr;
    long most_free = -1;

    for (const auto& name :
         sm->get_all_sites())
    {
        auto* site =
            sm->get_site(name);

        if (!site->job_assignment_enabled) {
            continue;
        }

        long free_cores =
            site->total_cores
            - site->used_cores;

        if (free_cores > most_free) {
            most_free = free_cores;
            selected = site;
        }
    }

    return selected;
}
```

---

## Example: select the host with the most free cores

```cpp
sg4::Host*
select_host_with_most_free_cores(
    CGSim::Site* site
)
{
    auto* sm =
        CGSim::get_site_manager();

    sg4::Host* selected = nullptr;
    unsigned int most_free = 0;

    for (auto* cpu : site->cpus) {

        auto free =
            sm->get_cores_available(cpu);

        if (selected == nullptr ||
            free > most_free)
        {
            selected = cpu;
            most_free = free;
        }
    }

    return selected;
}
```

---

## Example: find a host for a specific job

```cpp
sg4::Host*
find_host_for_job(
    Job* job,
    CGSim::Site* site
)
{
    auto* sm =
        CGSim::get_site_manager();

    for (auto* cpu : site->cpus) {

        if (sm->get_cores_available(cpu)
            >= static_cast<unsigned int>(
                job->cores))
        {
            return cpu;
        }
    }

    return nullptr;
}
```

---

## Example: count all active jobs at a site

Depending on the definition of "active", a user may want to include both assigned and running jobs:

```cpp
std::size_t active_jobs(
    CGSim::Site* site
)
{
    return
        site->assigned_jobs.size()
        +
        site->running_jobs.size();
}
```

If site-pending jobs should also be included:

```cpp
std::size_t queued_or_active =
    site->pending_jobs.size()
    +
    site->assigned_jobs.size()
    +
    site->running_jobs.size();
```

Choose the definition that matches the metric you want to report.

---

## Example: count all failed jobs

```cpp
std::size_t count_all_failed_jobs()
{
    auto* sm =
        CGSim::get_site_manager();

    std::size_t count =
        sm->get_global_failed_jobs().size();

    for (const auto& name :
         sm->get_all_sites())
    {
        count +=
            sm->get_site(name)
              ->failed_jobs.size();
    }

    return count;
}
```

---

## Common mistakes

### Treating `used_cpus` as partially busy hosts

Do not assume:

```cpp
site->used_cpus
```

counts every host running a job.

It currently counts hosts with zero remaining cores.

Use core utilization for general load measurements.

---

### Assuming unordered site order is deterministic

This:

```cpp
auto site =
    *sm->get_all_sites().begin();
```

does not provide a stable scheduling policy.

Sort or explicitly rank sites when reproducibility matters.

---

### Modifying job maps manually

Avoid operations such as:

```cpp
site->running_jobs.erase(...);
site->finished_jobs[...]=...;
```

from plugin code.

These containers are part of CGSim's lifecycle bookkeeping.

Use them for inspection.

---

### Manually changing `used_cores`

Do not write:

```cpp
site->used_cores += job->cores;
```

CGSim already updates site and grid core accounting when jobs are registered and finished.

Manual changes will double-count resources.

---

### Confusing global and site retry limits

Remember:

```text
global queue
    -> plugin maxJobRetries()

site pending queue
    -> Site::MAX_RETRIES
```

---

### Confusing global and site custom parameters

Remember:

```text
top-level Custom_Parameters
    -> SiteManager::get_custom_parameter()

SITE_PROPERTIES
    -> Site::custom_parameters
```

---

### Assuming `job_assignment_enabled` disables the whole site

It only gates site-pending dispatch.

A global scheduler can still assign directly to a host unless your plugin checks the flag.

---

### Assuming assigned jobs are not using resources

Cores are reserved when the job is assigned to the compute host.

An `ASSIGNED` job may therefore already contribute to:

```cpp
site->used_cores
```

and:

```cpp
sm->get_used_grid_cores()
```

before the computation is in `RUNNING`.

---

## Recommended usage

For most scheduling plugins:

1. Get the SiteManager with:

```cpp
auto* sm = CGSim::get_site_manager();
```

2. Enumerate sites with:

```cpp
sm->get_all_sites();
```

3. Retrieve live site state with:

```cpp
sm->get_site(name);
```

4. Inspect site capacity with:

```cpp
site->total_cores
site->used_cores
sm->get_site_cpu_utilization(name)
```

5. Inspect compute hosts with:

```cpp
site->cpus
```

6. Inspect host capacity with:

```cpp
sm->get_cores_available(cpu);
```

7. Set:

```cpp
job->comp_site
job->comp_host
```

when a suitable resource is found.

8. Use FileManager when file locality matters.

9. Treat Site job maps and resource counters as read-only framework state.

10. Use `job_assignment_enabled` and `MAX_RETRIES` deliberately when implementing site-level admission or dispatch experiments.

---

## Quick reference

| Goal | API / field |
|---|---|
| Get SiteManager | `CGSim::get_site_manager()` |
| List sites | `get_all_sites()` |
| Check site existence | `exists()` |
| Get site | `get_site()` |
| Grid utilization | `get_grid_cpu_utilization()` |
| Site utilization | `get_site_cpu_utilization()` |
| Total grid cores | `get_total_grid_cores()` |
| Used grid cores | `get_used_grid_cores()` |
| Total site cores | `Site::total_cores` |
| Used site cores | `Site::used_cores` |
| Compute hosts | `Site::cpus` |
| Available host cores | `get_cores_available()` |
| Used host cores | `get_cores_used()` |
| Global pending jobs | `get_global_pending_jobs()` |
| Global failed jobs | `get_global_failed_jobs()` |
| Site pending jobs | `Site::pending_jobs` |
| Assigned jobs | `Site::assigned_jobs` |
| Running jobs | `Site::running_jobs` |
| Finished jobs | `Site::finished_jobs` |
| Site failures | `Site::failed_jobs` |
| Global custom setting | `get_custom_parameter()` |
| Site property | `Site::custom_parameters` |
| Status text | `get_status_string()` |
| Pause site-pending assignment | `Site::job_assignment_enabled` |
| Site-pending retry limit | `Site::MAX_RETRIES` |
| Inspect incoming transfers | `Site::incoming_file_transfers` |

---

## Key points

1. **SiteManager is CGSim's central compute-resource and site-state interface.**

2. **Use `CGSim::get_site_manager()` to access the singleton.**

3. **`get_all_sites()` returns site names in an unordered set.**  
   Sort them when deterministic order matters.

4. **`get_site()` returns a live mutable `Site*`.**  
   Treat framework bookkeeping fields as read-only unless a field is explicitly being used as a policy control.

5. **`Site::cpus` contains compute hosts only.**  
   It excludes communication-server and job-server hosts.

6. **`total_cores` and grid core totals count compute resources only.**

7. **`used_cores` counts cores reserved by assigned/running jobs.**

8. **`used_cpus` currently counts fully occupied hosts, not all partially busy hosts.**

9. **Use `get_site_cpu_utilization()` for normal site load measurements.**

10. **Use `get_cores_available()` when deciding whether a host can accept a job.**

11. **Global and site-pending job queues are separate.**

12. **Global failures and site-level failures are stored separately.**

13. **Cores are reserved when a compute host is assigned, before execution necessarily reaches `RUNNING`.**

14. **Jobs with output files are considered finished after their final output write completes.**

15. **Top-level `Custom_Parameters` are read through `get_custom_parameter()`.**

16. **Site `SITE_PROPERTIES` are exposed through `Site::custom_parameters`.**

17. **`job_assignment_enabled` only controls dispatch from the site's local pending queue.**

18. **`Site::MAX_RETRIES` applies to site-pending host assignment, not the global retry limit.**

19. **`incoming_file_transfers` is framework-managed state used to coordinate data staging.**

20. **SiteManager and FileManager are designed to be used together for resource- and data-aware scheduling.**

The SiteManager gives plugins and policies a high-level, continuously updated view of CGSim's compute infrastructure. Simple schedulers can use it to find free cores and assign jobs, while more advanced experiments can combine site utilization, queue state, host properties, custom metadata, job lifecycle information, and file placement to implement realistic distributed scheduling policies.