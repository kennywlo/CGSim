# FileManager

The `FileManager` is CGSim's user-facing interface for working with files, file placement, site storage, file transfers, and standalone disk I/O during a simulation.

## Overview

The `FileManager` maintains CGSim's logical view of data across the simulated grid.

It tracks:

- which files exist;
- the size of each file;
- which sites contain each file;
- which files are stored at each site;
- the total and remaining logical storage at each site;
- file transfers currently in progress.

It also provides operations for:

- querying file and storage state;
- creating and removing files;
- simulating a site-to-site file transfer;
- simulating a standalone disk read;
- simulating a standalone disk write.

---

## Accessing the FileManager

CGSim uses one global `FileManager` instance.

Access it with:

```cpp
auto* fm = CGSim::get_file_manager();
```

For example:

```cpp
#include <CGSim/file_manager.h>

void inspect_file()
{
    auto* fm = CGSim::get_file_manager();

    if (fm->exists("input.root")) {
        auto size = fm->request_file_size("input.root");
        std::cout << "Size: " << size << " bytes\n";
    }
}
```

`FileManager` is implemented as a singleton and cannot be copied. Users should normally obtain it through `CGSim::get_file_manager()` rather than constructing their own instance.

---

## File model

### File names are global identities

CGSim identifies a file by its file-name string.

For example:

```text
dataset.root
```

If that name exists at several sites, the sites are treated as replicas of the same logical file:

```text
dataset.root
    ├── SiteA
    ├── SiteB
    └── SiteC
```

Internally, the `FileManager` maintains one size for the file and a set of locations.

This means that file names should be unique per logical file.

!!! warning
    If the same file name is used at several sites, all replicas should use the same size. The FileManager stores one global size value per file name.

---

### Placement is tracked at site level

The `FileManager` records whether a file exists at a **site**.

It does not expose logical placement as:

```text
file -> exact host disk
```

Instead:

```text
file -> one or more sites
```

For example:

```text
input.root
    ├── SiteA
    └── SiteC
```

Disk selection still matters for I/O. The `read()` and `write()` APIs require a site, CPU/host, and disk so SimGrid can model the local disk activity.

Conceptually:

```text
FileManager site storage
    -> logical capacity and replica placement

SimGrid host disk
    -> read/write performance and I/O contention
```

---

### Sizes are in bytes

File sizes are represented as integer byte counts.

For example:

```cpp
unsigned long long size = 1'000'000'000;
```

means one billion bytes.

Site logical storage is also configured in bytes through:

```text
storage_capacity_bytes
```

---

### Initial files and storage

Sites may begin a simulation with files already present.

During platform creation, CGSim registers each site's storage capacity and initial file set with the `FileManager`.

For every initial file:

```text
remaining site storage -= file size
```

For example, if a site has:

```text
Total storage:  2,000,000,000,000 bytes
input_A.root:       1,000,000,000 bytes
input_B.root:       2,500,000,000 bytes
```

the initial remaining storage becomes:

```text
1,996,500,000,000 bytes
```

If the configured initial files exceed a site's available logical capacity, CGSim throws an exception during site registration.

---

##API Documentation

## Querying files

### `exists(filename)`

```cpp
bool exists(const std::string& filename);
```

Returns `true` if at least one replica of the file exists anywhere in the FileManager.

Example:

```cpp
if (fm->exists("input.root")) {
    std::cout << "The file exists somewhere on the grid\n";
}
```

Use this when you only need to know whether the file exists globally.

To retrieve its current locations, use `request_file_sites()`.

---

### `exists(filename, sitename)`

```cpp
bool exists(
    const std::string& filename,
    const std::string& sitename
);
```

Returns `true` if the specified site currently contains the file.

Example:

```cpp
if (fm->exists("input.root", "SiteA")) {
    std::cout << "input.root is local to SiteA\n";
}
```

This is particularly useful for data-locality policies.

For example:

```cpp
if (fm->exists(filename, job->comp_site)) {
    // No site-to-site transfer is needed for this file.
}
```

If the site does not exist, the method throws `std::runtime_error`.

---

### `request_site_files(sitename)`

```cpp
std::unordered_set<std::string>
request_site_files(const std::string& sitename);
```

Returns the set of files currently registered at a site.

Example:

```cpp
auto files = fm->request_site_files("SiteA");

for (const auto& file : files) {
    std::cout << file << '\n';
}
```

The returned set is a copy. Changing it does not modify FileManager state.

If the site is unknown, the method throws `std::runtime_error`.

---

### `request_file_sites(filename)`

```cpp
std::unordered_set<std::string>
request_file_sites(const std::string& filename);
```

Returns every site currently containing the file.

Example:

```cpp
auto sites = fm->request_file_sites("input.root");

for (const auto& site : sites) {
    std::cout << site << '\n';
}
```

If the file does not exist, the method throws `std::runtime_error`.

!!! note
    The result is an `std::unordered_set`. Iteration order is not guaranteed. If reproducible source selection matters, do not rely on `*sites.begin()` as a deterministic policy.

A deterministic selection could sort the locations:

```cpp
auto locations = fm->request_file_sites(filename);

std::vector<std::string> candidates(
    locations.begin(),
    locations.end()
);

std::sort(candidates.begin(), candidates.end());

const auto& source = candidates.front();
```

---

### `request_file_size(filename)`

```cpp
unsigned long long
request_file_size(const std::string& filename);
```

Returns the registered file size in bytes.

Example:

```cpp
auto size = fm->request_file_size("input.root");
```

If the file does not exist, the method throws `std::runtime_error`.

---

## Querying storage

### `request_remaining_site_storage(sitename)`

```cpp
unsigned long long
request_remaining_site_storage(
    const std::string& sitename
);
```

Returns the site's currently available logical storage in bytes.

Example:

```cpp
auto remaining =
    fm->request_remaining_site_storage("SiteA");
```

This value decreases when files are registered at the site and increases when replicas are removed.

If the site does not exist, the method throws `std::runtime_error`.

---

### `request_remaining_grid_storage()`

```cpp
unsigned long long
request_remaining_grid_storage();
```

Returns the sum of remaining logical storage across all registered sites.

Example:

```cpp
auto grid_remaining =
    fm->request_remaining_grid_storage();
```

This can be useful for global storage-monitoring or data-placement policies.

---

### `request_site_storage_utilization(sitename)`

```cpp
double
request_site_storage_utilization(
    const std::string& sitename
);
```

Returns the storage utilization of the site:

```text
Used storage / total storage
```

For example:

```text
Total:      1000 GB
Used:       250 GB
```

returns:

```text
0.25
```

If your policy needs used capacity:

```cpp
double used_fraction =
    fm->request_site_storage_utilization("SiteA");
```

---

## File Creation and Deletion

### `create()`

```cpp
void create(
    const std::string& filename,
    const unsigned long long& size,
    const std::string& sitename
);
```

`create()` immediately registers a file or replica at a site.

Example:

```cpp
fm->create(
    "generated.root",
    500000000,
    "SiteA"
);
```

When successful, it:

1. adds the file to the site's file set;
2. adds the site to the file's location set;
3. records the file's size;
4. subtracts the file size from the site's remaining storage.

!!! warning
	There is **no simulated disk write** and **no network transfer**.

The state change is immediate.

---

### When to use `create()`

Use `create()` when your model intentionally needs an instantaneous logical file-placement change.

Examples include:

- injecting synthetic data into the simulation;
- initializing a custom policy's state;
- creating an abstract replica without modeling transfer or write time.

If physical cost matters:

```text
Need network movement -> transfer()
Need disk write time  -> write()
```

---

### Creating another replica

Suppose:

```text
input.root
    └── SiteA
```

You can add a logical replica with:

```cpp
auto size = fm->request_file_size("input.root");

fm->create(
    "input.root",
    size,
    "SiteB"
);
```

The result is:

```text
input.root
    ├── SiteA
    └── SiteB
```

!!! warning
    There is **no simulated disk write** and **no network transfer** in this creation.
	
Using `request_file_size()` for the new replica helps keep the file's size consistent.

---

### Creating a file already present at the site

If the file already exists at that site, `create()` simply returns.

It does not create a duplicate entry or deduct storage again.

---

### Capacity requirement

The destination must have enough remaining storage.

A typical check is:

```cpp
if (fm->request_remaining_site_storage(site) >= size) {
    fm->create(filename, size, site);
}
```

If there is insufficient storage, `create()` throws `std::runtime_error`.

---

### `remove()`

```cpp
bool remove(
    const std::string& filename,
    const std::string& sitename
);
```

Removes one replica from a site.

Example:

```cpp
bool removed =
    fm->remove("input.root", "SiteA");
```

If the replica exists, `remove()`:

1. removes the file from the site's file set;
2. removes the site from the file's location set;
3. restores the file size to the site's remaining storage;
4. returns `true`.

If the file is not present at that site, it returns `false`.

---

### Removing the final replica

Suppose:

```text
input.root
    ├── SiteA
    └── SiteB
```

After:

```cpp
fm->remove("input.root", "SiteA");
```

the file still exists globally:

```text
input.root
    └── SiteB
```

After removing the final replica:

```cpp
fm->remove("input.root", "SiteB");
```

the FileManager also removes the file's global size and location records.

At that point:

```cpp
fm->exists("input.root")
```

returns `false`.

---

### Removal is instantaneous

`remove()` changes FileManager metadata immediately.

It does not simulate a physical disk-delete activity.

---

## User-defined file transfers

### `transfer()`

```cpp
void transfer(
    const std::string& filename,
    const std::string& src_site,
    const std::string& dst_site,
    CGSim::FileTransferDecisionMode mode,
    const std::string& metadata = ""
);
```

Use `transfer()` to start a simulated network transfer between two sites.

Example:

```cpp
fm->transfer(
    "input.root",
    "SiteA",
    "SiteB",
    CGSim::FileTransferDecisionMode::COPY
);
```

The communication payload is the registered size of the file.

The transfer uses the communication-server hosts associated with the source and destination sites, so SimGrid models the transfer through the configured inter-site network.

---

### Transfer modes

CGSim defines:

```cpp
enum class FileTransferDecisionMode {
    COPY,
    MOVE
};
```

---

#### `COPY`

```cpp
CGSim::FileTransferDecisionMode::COPY
```

keeps the source replica and creates another replica at the destination.

Before:

```text
SiteA: input.root
SiteB:
```

After completion:

```text
SiteA: input.root
SiteB: input.root
```

Use `COPY` for:

- replication;
- pre-positioning;
- caching;
- making a job dataset available at another site.

Example:

```cpp
fm->transfer(
    "input.root",
    "SiteA",
    "SiteB",
    CGSim::FileTransferDecisionMode::COPY
);
```

---

#### `MOVE`

```cpp
CGSim::FileTransferDecisionMode::MOVE
```

creates the destination replica and removes the source replica after the transfer completes.

Before:

```text
SiteA: input.root
SiteB:
```

After completion:

```text
SiteA:
SiteB: input.root
```

Use `MOVE` for:

- migration;
- storage rebalancing;
- deliberate relocation of datasets.

Example:

```cpp
fm->transfer(
    "input.root",
    "SiteA",
    "SiteB",
    CGSim::FileTransferDecisionMode::MOVE
);
```

---

### Transfer metadata

The final `transfer()` argument is:

```cpp
const std::string& metadata = ""
```

It is optional.

This value is not interpreted by the FileManager. It is passed through to the user-transfer callbacks:

```cpp
onUserFileTransferStart(...)
onUserFileTransferEnd(...)
```

You can therefore use it to attach any useful label or context to the transfer.

For example:

```cpp
fm->transfer(
    "input.root",
    "SiteA",
    "SiteB",
    CGSim::FileTransferDecisionMode::COPY,
    "popular-file-replication"
);
```

or:

```cpp
fm->transfer(
    "input.root",
    "SiteA",
    "SiteB",
    CGSim::FileTransferDecisionMode::MOVE,
    "storage-rebalancing"
);
```

A plugin callback can inspect that string to distinguish different policy actions.

!!! note
    Earlier API versions called this parameter `policy_name`. The current API names it `metadata` because it is a general-purpose user string.

---

### Transfer execution semantics

The public `transfer()` method starts the communication automatically.

It returns:

```cpp
void
```

So user code should write:

```cpp
fm->transfer(
    filename,
    source,
    destination,
    CGSim::FileTransferDecisionMode::COPY
);
```

not:

```cpp
auto activity = fm->transfer(...); // invalid
activity->start();
```

Conceptually:

```text
transfer() called
      |
      v
validate transfer
      |
      v
create SimGrid communication
      |
      v
mark transfer in flight
      |
      v
start communication
      |
      v
onUserFileTransferStart(...)
      |
      v
simulated network activity
      |
      v
create destination replica
      |
      +---- COPY ---> keep source
      |
      +---- MOVE ---> remove source
      |
      v
clear in-flight state
      |
      v
onUserFileTransferEnd(...)
```

The transfer is asynchronous in simulated time. `transfer()` starts it but does not wait for completion.

---

### Transfer validation

A transfer is rejected if:

- the source site does not contain the file;
- the destination site already contains the file;
- the same `filename + source + destination` transfer is already in progress;
- the destination site is already receiving the same file.

These cases raise `std::runtime_error`.

---

### Destination storage and transfers

Destination capacity is not reserved when `transfer()` is called.

The destination replica is registered when the transfer completes. That registration eventually uses the same storage accounting as `create()`.

Therefore custom policies should check available capacity before starting a transfer:

```cpp
const auto size =
    fm->request_file_size(filename);

const auto free_space =
    fm->request_remaining_site_storage(destination);

if (free_space >= size) {
    fm->transfer(
        filename,
        source,
        destination,
        CGSim::FileTransferDecisionMode::COPY
    );
}
```

!!! caution
    A pre-check does not reserve the space. Other writes or transfers can still consume storage before this transfer completes.

This matters when several asynchronous operations target the same site at the same time.

---

### Tracking transfers in progress

#### `is_in_flight()`

```cpp
bool is_in_flight(
    const std::string& filename,
    const std::string& src_site,
    const std::string& dst_site
);
```

Returns whether that exact transfer is currently active.

Example:

```cpp
if (!fm->is_in_flight(
        "input.root",
        "SiteA",
        "SiteB"))
{
    fm->transfer(
        "input.root",
        "SiteA",
        "SiteB",
        CGSim::FileTransferDecisionMode::COPY
    );
}
```

This is useful in repeating policies.

---

### Exact-transfer versus destination-level checks

`is_in_flight()` checks:

```text
filename | source | destination
```

For example, if this transfer exists:

```text
input.root | SiteA | SiteC
```

then:

```cpp
fm->is_in_flight(
    "input.root",
    "SiteB",
    "SiteC"
);
```

can still return `false`, because it is a different source.

However, `transfer()` also prevents the same file from being transferred into the same destination from another source while an incoming copy is already active.

So a second transfer such as:

```text
input.root | SiteB | SiteC
```

will still be rejected while:

```text
input.root | SiteA | SiteC
```

is active. To check whether a file in incoming to a particular site, users can call

```cpp
CGSim::get_site_manager->get_site(site_name)->incoming_file_transfers.count(filename) > 0
```
which will return `true` if a file is incoming.
---

### `generate_transfer_key()`

```cpp
std::string generate_transfer_key(
    const std::string& filename,
    const std::string& src_site,
    const std::string& dst_site
);
```

Generates the key used for exact in-flight tracking.

For example:

```cpp
auto key =
    fm->generate_transfer_key(
        "input.root",
        "SiteA",
        "SiteB"
    );
```

produces:

```text
input.root|SiteA|SiteB
```

The FileManager also exposes:

```cpp
CGSim::FileManager::in_flight_transfers
```

as a public static set.

Most user code should prefer `is_in_flight()` unless direct access to the keys is specifically useful.

---

### User-defined transfer callbacks

Transfers started through public `FileManager::transfer()` invoke:

```cpp
virtual void onUserFileTransferStart(
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Comm const& co,
    const std::string& src_site,
    const std::string& dst_site,
    const std::string& metadata
) {}
```

and:

```cpp
virtual void onUserFileTransferEnd(
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Comm const& co,
    const std::string& src_site,
    const std::string& dst_site,
    const std::string& metadata
) {}
```

These callbacks provide:

| Argument | Meaning |
|---|---|
| `filename` | File being transferred |
| `filesize` | File size in bytes |
| `co` | SimGrid communication activity |
| `src_site` | Source site |
| `dst_site` | Destination site |
| `metadata` | User-provided string passed to `transfer()` |

Example:

```cpp
void onUserFileTransferEnd(
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Comm const& co,
    const std::string& src_site,
    const std::string& dst_site,
    const std::string& metadata
) override
{
    std::cout
        << metadata
        << ": transferred "
        << filesize
        << " bytes from "
        << src_site
        << " to "
        << dst_site
        << '\n';
}
```

---

## Standalone user reads

### `read()`

```cpp
void read(
    const std::string& filename,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk
);
```

Starts a simulated disk read for an existing file.

Example:

```cpp
fm->read(
    "input.root",
    "SiteA",
    "SiteA_cpu-0",
    "SITEA_DISK"
);
```

The FileManager automatically obtains the registered file size.

---

### What `read()` does

The current user-facing `read()` path:

1. verifies that the file exists globally;
2. finds the requested SimGrid host/CPU;
3. finds the named disk on that host;
4. creates a SimGrid read activity using the complete file size;
5. checks that the file exists at the specified site when the read starts;
6. attaches user-read callbacks;
7. starts the read;
8. returns `void`.

Conceptually:

```text
read(...)
   |
   v
create disk-read activity
   |
   v
onUserFileReadStart(...)
   |
   v
simulated disk read
   |
   v
onUserFileReadEnd(...)
```

The method starts the I/O immediately and does not wait for it to finish.

---

### The file must already be local

The file must exist at `site` when the read starts.

A safe pattern is:

```cpp
if (fm->exists(filename, site)) {
    fm->read(
        filename,
        site,
        cpu,
        disk
    );
}
```

If the file only exists at another site, it must be transferred first.

Because both `transfer()` and `read()` start asynchronously and return `void`, simply calling them one after the other does **not** create a transfer-before-read dependency:

```cpp
fm->transfer(...);
fm->read(...);   // does not wait for the transfer
```

If you need a standalone read to happen after a user-defined transfer, trigger the read after transfer completion, for example from `onUserFileTransferEnd()`.

---

### User-defined read callbacks

Public `FileManager::read()` calls invoke:

```cpp
virtual void onUserFileReadStart(
    const std::string& filename,
    const unsigned long long& filesize,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk,
    simgrid::s4u::Io const& io
) {}
```

and:

```cpp
virtual void onUserFileReadEnd(
    const std::string& filename,
    const unsigned long long& filesize,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk,
    simgrid::s4u::Io const& io
) {}
```

These hooks are specific to **user-initiated** reads.

They include the site, CPU/host, and disk passed to `FileManager::read()`.

Example:

```cpp
void onUserFileReadEnd(
    const std::string& filename,
    const unsigned long long& filesize,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk,
    simgrid::s4u::Io const& io
) override
{
    std::cout
        << "Finished reading "
        << filename
        << " from "
        << disk
        << " on "
        << cpu
        << '\n';
}
```

---

## Standalone user writes

### `write()`

```cpp
void write(
    const std::string& filename,
    const unsigned long long& size,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk
);
```

Starts a simulated disk write for a new file.

Example:

```cpp
fm->write(
    "generated.root",
    500000000,
    "SiteA",
    "SiteA_cpu-0",
    "SITEA_DISK"
);
```

---

### What `write()` does

The current public write path:

1. validates the site;
2. verifies that the filename does not already exist anywhere on the grid;
3. finds the requested host/CPU;
4. finds the requested disk;
5. creates a SimGrid write activity of the requested size;
6. attaches a completion handler that registers the file;
7. attaches user-write callbacks;
8. starts the I/O;
9. returns `void`.

Conceptually:

```text
write(...)
   |
   v
onUserFileWriteStart(...)
   |
   v
simulated disk write
   |
   v
register file at site
   |
   v
onUserFileWriteEnd(...)
```

The method starts the I/O immediately and does not wait for completion.

---

### The file is registered after the write completes

Calling:

```cpp
fm->write(...);
```

does not immediately make the file available in FileManager metadata.

The file is registered when the simulated write completes.

So immediately after starting a write:

```cpp
fm->write(
    "generated.root",
    size,
    site,
    cpu,
    disk
);

// generated.root may still be in progress here.
```

The file becomes part of FileManager state after I/O completion.

---

### Output name must be new

`write()` rejects a filename that already exists anywhere on the grid.

For example, if:

```text
result.root
```

already exists at `SiteB`, this will fail even if writing to `SiteA`:

```cpp
fm->write(
    "result.root",
    size,
    "SiteA",
    cpu,
    disk
);
```

Use a new file name when using `write()` to produce a new logical file.

---

### Check storage before starting a write

The new file is registered when the write completes, and storage is checked as part of registration.

A recommended pre-check is:

```cpp
if (fm->request_remaining_site_storage(site) >= size) {
    fm->write(
        filename,
        size,
        site,
        cpu,
        disk
    );
}
```

As with transfers, the pre-check does not reserve space. Other asynchronous activity can change the remaining capacity before the write completes.

---

### User-defined write callbacks

Public `FileManager::write()` calls invoke:

```cpp
virtual void onUserFileWriteStart(
    const std::string& filename,
    const unsigned long long& filesize,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk,
    simgrid::s4u::Io const& io
) {}
```

and:

```cpp
virtual void onUserFileWriteEnd(
    const std::string& filename,
    const unsigned long long& filesize,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk,
    simgrid::s4u::Io const& io
) {}
```

Example:

```cpp
void onUserFileWriteEnd(
    const std::string& filename,
    const unsigned long long& filesize,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk,
    simgrid::s4u::Io const& io
) override
{
    std::cout
        << "Finished writing "
        << filename
        << " at "
        << site
        << '\n';
}
```

---

### User-defined I/O callback summary

The current plugin API provides six callbacks for FileManager operations started explicitly by user code:

```cpp
onUserFileTransferStart(...)
onUserFileTransferEnd(...)

onUserFileReadStart(...)
onUserFileReadEnd(...)

onUserFileWriteStart(...)
onUserFileWriteEnd(...)
```

These are separate from CGSim's job-associated callbacks.

| User action | Start callback | End callback |
|---|---|---|
| `FileManager::transfer()` | `onUserFileTransferStart` | `onUserFileTransferEnd` |
| `FileManager::read()` | `onUserFileReadStart` | `onUserFileReadEnd` |
| `FileManager::write()` | `onUserFileWriteStart` | `onUserFileWriteEnd` |

This separation allows a plugin to distinguish normal workload activity from extra data-management activity introduced by a user-defined policy.

---

## Job-managed files

For ordinary jobs, users normally do **not** call `read()`, `write()`, or `transfer()` manually.

Jobs declare their input and output files.

Input files are stored in:

```cpp
job->input_files
```

Output files are stored in:

```cpp
job->output_files
```

For example:

```cpp
Job* job = new Job();

job->jobid = 42;

job->input_files = {
    "input_A.root",
    "input_B.root"
};

job->output_files = {
    {"result.root", 500000000}
};
```

CGSim uses private FileManager helpers to construct the required SimGrid activity graph for the job.

---

### Job input metadata

When a job is submitted, CGSim resolves each input filename to:

```text
file size
+
known site locations
```

and stores that information in:

```cpp
job->input_files_sizes_locations
```

Conceptually:

```text
input.root
    -> size: 1,000,000,000 bytes
    -> locations: {SiteA, SiteC}
```

If an input file does not exist anywhere when the job is submitted, CGSim throws an exception.

---

### Location data is captured for the job

The location information associated with the job is populated during job submission.

A later user-defined replication or migration may change the live FileManager state.

If a custom policy needs current locations, query:

```cpp
fm->request_file_sites(filename);
```

rather than assuming earlier job metadata is still current.

---

### Choosing a source for a job input

Before CGSim stages an input file, it invokes:

```cpp
virtual void onFileRequest(
    Job* job,
    std::string filename,
    long long filesize,
    std::unordered_set<std::string> file_locations,
    std::string& source_site,
    CGSim::FileTransferDecisionMode& mode
);
```

This callback lets the plugin choose the source site for job input data.

The arguments mean:

| Argument | Meaning |
|---|---|
| `job` | Job requesting the file |
| `filename` | Requested input |
| `filesize` | File size in bytes |
| `file_locations` | Known source locations associated with the job |
| `source_site` | Output parameter: selected source |
| `mode` | Output parameter: transfer mode if remote staging is required |

---

### Default behavior

The default plugin implementation prefers the compute site when it is already one of the known locations.

Otherwise it chooses the first element from the unordered location set.

Conceptually:

```cpp
if (file_locations.find(job->comp_site) != file_locations.end()) {
    source_site = job->comp_site;
}
else {
    source_site = *file_locations.begin();
}
```

Because `file_locations` is an `std::unordered_set`, the fallback choice among multiple remote replicas should not be treated as deterministic.

Override `onFileRequest()` when source selection matters to your experiment.

---

### Example custom source selection

```cpp
void onFileRequest(
    Job* job,
    std::string filename,
    long long filesize,
    std::unordered_set<std::string> file_locations,
    std::string& source_site,
    CGSim::FileTransferDecisionMode& mode
) override
{
    auto* fm = CGSim::get_file_manager();

    if (fm->exists(filename, job->comp_site)) {
        source_site = job->comp_site;
        return;
    }

    std::vector<std::string> candidates(
        file_locations.begin(),
        file_locations.end()
    );

    std::sort(
        candidates.begin(),
        candidates.end()
    );

    source_site = candidates.front();
    mode = CGSim::FileTransferDecisionMode::COPY;
}
```

More advanced policies could choose according to:

- network bandwidth;
- latency;
- site load;
- current transfers;
- replica count;
- storage availability;
- custom site metadata.

---

### Automatic job input pipeline

For a file already at the compute site:

```text
local disk read
      |
      v
computation
```

For a remote file:

```text
site-to-site transfer
      |
      v
local disk read
      |
      v
computation
```

With several inputs, CGSim builds the dependencies so the computation waits for all required reads.

For example:

```text
input A transfer -> input A read --\
                                    \
input B local read ------------------> computation
                                    /
input C transfer -> input C read --/
```

This is why normal jobs should use `Job::input_files` instead of manually invoking the public `read()` and `transfer()` methods.

---

### Job-managed callbacks

CGSim has separate callbacks for file activity associated with jobs.

### Job input transfers

```cpp
virtual void onFileTransferStart(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Comm const& co,
    const std::string& src_site,
    const std::string& dst_site
) {}
```

```cpp
virtual void onFileTransferEnd(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Comm const& co,
    const std::string& src_site,
    const std::string& dst_site
) {}
```

---

### Job input reads

```cpp
virtual void onFileReadStart(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Io const& io
) {}
```

```cpp
virtual void onFileReadEnd(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Io const& io
) {}
```

CGSim also accumulates job read time in:

```cpp
job->total_io_read_time
```

---

### Job output writes

```cpp
virtual void onFileWriteStart(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Io const& io
) {}
```

```cpp
virtual void onFileWriteEnd(
    Job* job,
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Io const& io
) {}
```

CGSim tracks completed output writes and accumulates write time for the job.

---

### Job callbacks versus user callbacks

The two families are intentionally separate.

| Activity | Job-managed callback | User-managed callback |
|---|---|---|
| Transfer | `onFileTransferStart/End` | `onUserFileTransferStart/End` |
| Read | `onFileReadStart/End` | `onUserFileReadStart/End` |
| Write | `onFileWriteStart/End` | `onUserFileWriteStart/End` |

Use the `onUser...` callbacks to observe operations your own policy starts through the public FileManager API.

Use the job callbacks to observe file activity created automatically as part of normal job execution.

---

##Examples

### Example: measuring workload traffic and policy traffic separately

```cpp
class MyPlugin : public CGSim::Plugin
{
public:
    unsigned long long job_transfer_bytes = 0;
    unsigned long long user_transfer_bytes = 0;

    void onFileTransferEnd(
        Job* job,
        const std::string& filename,
        const unsigned long long filesize,
        simgrid::s4u::Comm const& co,
        const std::string& src_site,
        const std::string& dst_site
    ) override
    {
        job_transfer_bytes += filesize;
    }

    void onUserFileTransferEnd(
        const std::string& filename,
        const unsigned long long filesize,
        simgrid::s4u::Comm const& co,
        const std::string& src_site,
        const std::string& dst_site,
        const std::string& metadata
    ) override
    {
        user_transfer_bytes += filesize;
    }

    // getWorkload() and assignJob() must also be implemented.
};
```

This can be useful when measuring whether proactive replication reduces network traffic generated directly by jobs.

---

### Example: replication helper

```cpp
void replicate_if_possible(
    const std::string& filename,
    const std::string& source,
    const std::string& destination
)
{
    auto* fm = CGSim::get_file_manager();

    if (!fm->exists(filename, source)) {
        return;
    }

    if (fm->exists(filename, destination)) {
        return;
    }

    if (fm->is_in_flight(
            filename,
            source,
            destination))
    {
        return;
    }

    const auto size =
        fm->request_file_size(filename);

    const auto remaining =
        fm->request_remaining_site_storage(destination);

    if (remaining < size) {
        return;
    }

    fm->transfer(
        filename,
        source,
        destination,
        CGSim::FileTransferDecisionMode::COPY,
        "replication"
    );
}
```

---

### Example: migration helper

```cpp
void migrate_if_possible(
    const std::string& filename,
    const std::string& source,
    const std::string& destination
)
{
    auto* fm = CGSim::get_file_manager();

    if (!fm->exists(filename, source)) {
        return;
    }

    if (fm->exists(filename, destination)) {
        return;
    }

    const auto size =
        fm->request_file_size(filename);

    if (fm->request_remaining_site_storage(destination) < size) {
        return;
    }

    fm->transfer(
        filename,
        source,
        destination,
        CGSim::FileTransferDecisionMode::MOVE,
        "migration"
    );
}
```

---

### Example: standalone read

```cpp
void start_read()
{
    auto* fm = CGSim::get_file_manager();

    const std::string filename = "input.root";
    const std::string site = "SiteA";
    const std::string cpu = "SiteA_cpu-0";
    const std::string disk = "SITEA_DISK";

    if (!fm->exists(filename, site)) {
        return;
    }

    fm->read(
        filename,
        site,
        cpu,
        disk
    );
}
```

The read begins immediately and completes asynchronously.

Its lifecycle can be observed through:

```cpp
onUserFileReadStart(...)
onUserFileReadEnd(...)
```

---

### Example: standalone write

```cpp
void start_write()
{
    auto* fm = CGSim::get_file_manager();

    const std::string filename = "generated.root";
    const unsigned long long size = 500000000;

    const std::string site = "SiteA";
    const std::string cpu = "SiteA_cpu-0";
    const std::string disk = "SITEA_DISK";

    if (fm->exists(filename)) {
        return;
    }

    if (fm->request_remaining_site_storage(site) < size) {
        return;
    }

    fm->write(
        filename,
        size,
        site,
        cpu,
        disk
    );
}
```

The file is registered when the simulated write completes.

Its lifecycle can be observed through:

```cpp
onUserFileWriteStart(...)
onUserFileWriteEnd(...)
```

---

### Example: read after a user transfer finishes

Because public transfer and read operations are asynchronous and return `void`, use the transfer-completion callback when one operation must wait for the other.

For example:

```cpp
void onUserFileTransferEnd(
    const std::string& filename,
    const unsigned long long filesize,
    simgrid::s4u::Comm const& co,
    const std::string& src_site,
    const std::string& dst_site,
    const std::string& metadata
) override
{
    if (metadata != "transfer-then-read") {
        return;
    }

    CGSim::get_file_manager()->read(
        filename,
        dst_site,
        "SiteB_cpu-0",
        "SITEB_DISK"
    );
}
```

The transfer can be started with:

```cpp
fm->transfer(
    "input.root",
    "SiteA",
    "SiteB",
    CGSim::FileTransferDecisionMode::COPY,
    "transfer-then-read"
);
```

This ensures the standalone read is not started until the user-defined transfer has completed.

---

## Storage accounting

FileManager storage accounting is site-level.

When a replica is created:

```text
remaining storage -= file size
```

When a replica is removed:

```text
remaining storage += file size
```

For `COPY`:

```text
source:
    storage unchanged

destination:
    consumes file size on completion
```

For `MOVE`:

```text
destination:
    consumes file size on completion

source:
    releases file size after source replica is removed
```

For `write()`:

```text
storage is consumed when the completed write is registered as a file
```

---

### Site storage versus disk performance

These are separate parts of CGSim.

```text
storage_capacity_bytes
    -> logical FileManager capacity

disk read bandwidth
    -> SimGrid read performance

disk write bandwidth
    -> SimGrid write performance
```

The FileManager does not currently expose a separate logical storage-capacity counter for each individual compute-host disk.

A site can therefore have one logical capacity while individual host disks provide the performance characteristics for simulated I/O.

---

### Common error conditions

Many invalid operations throw `std::runtime_error`.

| Operation | Common error |
|---|---|
| `exists(file, site)` | Site does not exist |
| `request_site_files(site)` | Site does not exist |
| `request_file_sites(file)` | File does not exist |
| `request_file_size(file)` | File does not exist |
| `request_remaining_site_storage(site)` | Site does not exist |
| `request_site_storage_utilization(site)` | Site does not exist |
| `create(...)` | Insufficient site storage |
| `read(...)` | File does not exist globally |
| `read(...)` | File is not present at requested site when read starts |
| `write(...)` | Site does not exist |
| `write(...)` | Filename already exists anywhere on grid |
| `transfer(...)` | Source does not contain file |
| `transfer(...)` | Destination already contains file |
| `transfer(...)` | Exact transfer is already in flight |
| `transfer(...)` | Destination is already receiving that file |
| Job submission | Requested input file does not exist |

For custom policy code, query state first rather than relying on exceptions for normal control flow.

---

### Recommended patterns

#### Query before modifying

Before creating, transferring, reading, or writing, check the relevant state.

For example:

```cpp
if (!fm->exists(filename)) {
    return;
}
```

or:

```cpp
if (fm->request_remaining_site_storage(site) < size) {
    return;
}
```

---

#### Use `transfer()` when network cost matters

Prefer:

```cpp
fm->transfer(...)
```

over:

```cpp
fm->create(...)
```

for replication or migration when the experiment is meant to include network cost and contention.

---

#### Use `write()` when disk cost matters

Prefer:

```cpp
fm->write(...)
```

over:

```cpp
fm->create(...)
```

when the simulation should include disk write time.

---

#### Use `create()` only for instantaneous logical placement

`create()` is appropriate when you deliberately want:

```text
no simulated disk write
no simulated network transfer
```

---

#### Use callbacks for asynchronous sequencing

Public:

```cpp
transfer()
read()
write()
```

all start their SimGrid activities and return `void`.

If one user-managed operation must happen after another one completes, use the corresponding `onUser...End()` callback to start the next operation.

---

#### Keep file sizes consistent

When adding a replica manually:

```cpp
auto size = fm->request_file_size(filename);
fm->create(filename, size, destination);
```

is safer than independently supplying another size.

---

#### Make source selection deterministic when needed

Do not rely on unordered-set iteration if the chosen replica affects results.

Use a deterministic rule or a policy based on network/storage state.

---

## API reference

### `CGSim::get_file_manager()`

```cpp
CGSim::FileManager* CGSim::get_file_manager();
```

Returns the global FileManager.

---

### `exists(filename)`

```cpp
bool exists(const std::string& filename);
```

Checks whether the file exists anywhere.

---

### `exists(filename, sitename)`

```cpp
bool exists(
    const std::string& filename,
    const std::string& sitename
);
```

Checks whether the file exists at one site.

---

### `request_site_files(sitename)`

```cpp
std::unordered_set<std::string>
request_site_files(const std::string& sitename);
```

Returns all files at the site.

---

### `request_file_sites(filename)`

```cpp
std::unordered_set<std::string>
request_file_sites(const std::string& filename);
```

Returns all current replicas/sites for the file.

---

### `request_file_size(filename)`

```cpp
unsigned long long
request_file_size(const std::string& filename);
```

Returns the file size in bytes.

---

### `request_remaining_site_storage(sitename)`

```cpp
unsigned long long
request_remaining_site_storage(
    const std::string& sitename
);
```

Returns remaining logical storage at the site.

---

### `request_remaining_grid_storage()`

```cpp
unsigned long long
request_remaining_grid_storage();
```

Returns remaining logical storage summed over all sites.

---

### `request_site_storage_utilization(sitename)`

```cpp
double
request_site_storage_utilization(
    const std::string& sitename
);
```

Returns used storage utilization ratio.

```text
used / total
```

---

### `create(filename, size, sitename)`

```cpp
void create(
    const std::string& filename,
    const unsigned long long& size,
    const std::string& sitename
);
```

Immediately creates a logical file/replica and consumes site storage.

---

### `remove(filename, sitename)`

```cpp
bool remove(
    const std::string& filename,
    const std::string& sitename
);
```

Immediately removes one replica and restores its storage.

---

### `transfer(filename, src, dst, mode, metadata)`

```cpp
void transfer(
    const std::string& filename,
    const std::string& src_site,
    const std::string& dst_site,
    CGSim::FileTransferDecisionMode mode,
    const std::string& metadata = ""
);
```

Creates and immediately starts a simulated site-to-site transfer.

The optional `metadata` string is forwarded to the user-transfer callbacks.

---

### `read(filename, site, cpu, disk)`

```cpp
void read(
    const std::string& filename,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk
);
```

Creates and immediately starts a simulated disk read.

Invokes:

```cpp
onUserFileReadStart(...)
onUserFileReadEnd(...)
```

---

### `write(filename, size, site, cpu, disk)`

```cpp
void write(
    const std::string& filename,
    const unsigned long long& size,
    const std::string& site,
    const std::string& cpu,
    const std::string& disk
);
```

Creates and immediately starts a simulated disk write.

The file is registered after the write completes.

Invokes:

```cpp
onUserFileWriteStart(...)
onUserFileWriteEnd(...)
```

---

### `is_in_flight(filename, src, dst)`

```cpp
bool is_in_flight(
    const std::string& filename,
    const std::string& src_site,
    const std::string& dst_site
);
```

Checks whether the exact transfer is currently active.

---

### `generate_transfer_key(filename, src, dst)`

```cpp
std::string generate_transfer_key(
    const std::string& filename,
    const std::string& src_site,
    const std::string& dst_site
);
```

Returns:

```text
filename|source|destination
```

---

## Framework-internal FileManager operations

The class also contains private helpers used by CGSim itself, including:

```cpp
register_site(...)
request_file_location(...)
internal_read(...)
internal_write(...)
internal_transfer(...)
```

These return or manipulate lower-level SimGrid activities so the framework can build job dependency graphs and attach job-specific callbacks.

They are not part of the normal user-facing API.

The public methods are intentionally simpler:

```text
public read()     -> start user read
public write()    -> start user write
public transfer() -> start user transfer
```

while CGSim uses the internal methods when it needs direct access to the activity object.

---

### Typical job-managed lifecycle

A normal job using input and output files follows this general path:

```text
Job submitted
     |
     v
Resolve input file sizes and locations
     |
     v
Assign compute site / CPU / disk
     |
     v
For each input:
     |
     +--> onFileRequest() chooses source
     |
     +--> local?
     |      |
     |      +--> yes: read
     |      |
     |      +--> no: transfer -> read
     |
     v
Run computation
     |
     v
Write output files
     |
     v
Register completed outputs
     |
     v
Job finishes
```

Users generally only need to:

- declare the files on the job;
- assign the job to valid compute resources;
- optionally override `onFileRequest()`.

---

### Typical user-policy lifecycle

A custom data-management policy usually follows:

```text
Policy executes
     |
     v
Query current FileManager state
     |
     v
Check location / storage / in-flight state
     |
     v
Choose an operation
     |
     +--> create()
     +--> remove()
     +--> transfer()
     +--> read()
     +--> write()
     |
     v
Observe onUser... callbacks as needed
```

---

### Key points

1. **File names are global identities.**  
   Multiple sites containing the same name represent replicas.

2. **File placement is site-level.**  
   The CPU/host disk is used to simulate local I/O performance.

3. **Sizes and storage capacities are bytes.**

4. **`create()` and `remove()` update FileManager metadata immediately.**

5. **`transfer()` starts a simulated network transfer and returns `void`.**

6. **`COPY` keeps the source replica; `MOVE` removes it after completion.**

7. **The optional transfer string is now called `metadata`.**  
   It is passed unchanged to user-transfer callbacks.

8. **`read()` and `write()` are public asynchronous user APIs.**  
   Both start their I/O activities immediately and return `void`.

9. **User reads now have `onUserFileReadStart/End` callbacks.**

10. **User writes now have `onUserFileWriteStart/End` callbacks.**

11. **User transfers use `onUserFileTransferStart/End`.**

12. **Job-managed file activity has a separate callback family.**

13. **A `write()` registers its file only when the simulated write completes.**

14. **A `read()` requires the file to be present at the requested site when the read starts.**

15. **Do not call `transfer()` and immediately call `read()` expecting automatic dependency ordering.**  
    Use a completion callback if a standalone read must wait for a standalone transfer.

16. **Destination storage is not reserved when an asynchronous transfer or write begins.**  
    Pre-check capacity, while remembering that concurrent activity can change it.

17. **`request_site_storage_utilization()` currently returns the remaining/free fraction.**

18. **Do not rely on `std::unordered_set` iteration order for deterministic file-source selection.**

The `FileManager` is CGSim's central data-management interface: normal jobs can rely on CGSim's automatic file lifecycle, while plugins and policies can use the public API to build custom replication, migration, storage-management, and standalone I/O behavior.