# PolicyManager

The `PolicyManager` is CGSim's interface for scheduling user-defined policies at specific points in simulated time.

A policy is a named callback with timing information. It can execute once or repeat at a configured interval, and it can optionally be limited to a finite time window.

Policies are useful for behavior such as:

- periodic resource monitoring;
- file replication and migration;
- storage-management decisions;
- site admission control;
- maintenance events;
- periodic metrics collection;
- scheduled experiment changes;
- time-driven updates to plugin state.

## Recommended policy pattern

The examples in this page use a policy factory pattern.

Each policy function:

1. allocates a `CGSim::Policy`;
2. configures it;
3. assigns its callback;
4. returns a `CGSim::Policy*`.

The registration function passes the returned pointer directly to:

```cpp
CGSim::get_policy_manager()->addPolicy(...);
```

For example:

```cpp
void POLICY::addPolicies()
{
    CGSim::get_policy_manager()->addPolicy(
        storage_rebalance_policy()
    );

    CGSim::get_policy_manager()->addPolicy(
        network_aware_rebalance_policy()
    );

    CGSim::get_policy_manager()->addPolicy(
        hotset_replication_policy()
    );
}
```

A policy factory follows this form:

```cpp
CGSim::Policy* POLICY::storage_rebalance_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Storage Rebalance Policy";

    p->start_time =
        0.0;

    p->end_time =
        0.0;

    p->repeat_interval =
        1000.0;

    const std::string policy_name =
        p->name;

    p->callback =
        [this]()
        {
            run_storage_rebalance();
        };

    return p;
}
```

This pattern keeps policy construction separate from policy registration and makes it easy to keep each policy's configuration in its own function.

## Example policy class

A policy helper class can declare one factory function per policy:

```cpp
#pragma once

#include <CGSim/CGSim.h>

class POLICY
{
public:
    void addPolicies();

private:
    CGSim::Policy*
    storage_rebalance_policy();

    CGSim::Policy*
    network_aware_rebalance_policy();

    CGSim::Policy*
    hotset_replication_policy();

    void run_storage_rebalance();
    void run_network_aware_rebalance();
    void run_hotset_replication();
};
```

The implementation can then contain:

```cpp
#include "policy.h"

void POLICY::addPolicies()
{
    CGSim::get_policy_manager()->addPolicy(
        storage_rebalance_policy()
    );

    CGSim::get_policy_manager()->addPolicy(
        network_aware_rebalance_policy()
    );

    CGSim::get_policy_manager()->addPolicy(
        hotset_replication_policy()
    );
}
```

Each factory returns its own configured `CGSim::Policy*`.

## Accessing PolicyManager

Use:

```cpp
auto* pm =
    CGSim::get_policy_manager();
```

For example:

```cpp
auto* pm =
    CGSim::get_policy_manager();

if (pm->exists(
        "Storage Rebalance Policy"))
{
    auto* p =
        pm->get_policy(
            "Storage Rebalance Policy"
        );

    std::cout
        << p->name
        << '\n';
}
```

The direct form is also convenient for registration:

```cpp
CGSim::get_policy_manager()->addPolicy(
    storage_rebalance_policy()
);
```

## Public API

After obtaining the manager:

```cpp
auto* pm =
    CGSim::get_policy_manager();
```

the following operations are available:

```cpp
pm->addPolicy(policy);

pm->deactivate_policy(
    policy_name
);

pm->reactivate_policy(
    policy_name
);

pm->get_policy(
    policy_name
);

pm->exists(
    policy_name
);

pm->get_policy_list();

pm->get_active_policy_list();

pm->get_deactivated_policy_list();
```

## The `Policy` class

A policy contains:

```cpp
class Policy
{
public:
    std::string name;
    double start_time = 0.0;
    double end_time = 0.0;
    double repeat_interval = 0.0;
    std::function<void()> callback;
    bool is_active() const;

private:
    std::size_t generation_number = 0;
    bool active = true;
};
```

Users configure:

- `name`;
- `start_time`;
- `end_time`;
- `repeat_interval`;
- `callback`.

PolicyManager maintains:

- the active state;
- the generation number.

### `Policy::name`

```cpp
std::string name;
```

The unique name used to register and identify the policy.

A factory normally assigns it immediately:

```cpp
CGSim::Policy* POLICY::monitor_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Grid Monitor";

    p->start_time =
        0.0;

    p->repeat_interval =
        60.0;

    p->callback = []()
    {
        // Monitoring logic.
    };

    return p;
}
```

Policy names must be unique.

Examples of useful names include:

```text
Storage Rebalance Policy
Network Aware Rebalance Policy
Hotset Replication Policy
Grid Monitor
Site Maintenance
```

Keep the registered name unchanged.

### `Policy::start_time`

```cpp
double start_time = 0.0;
```

The absolute simulated timestamp of the policy's first execution for an activation.

For example:

```cpp
CGSim::Policy* POLICY::delayed_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Delayed Policy";

    p->start_time =
        500.0;

    p->callback = []()
    {
        // Runs at simulated time 500.
    };

    return p;
}
```

A value of:

```cpp
p->start_time = 500.0;
```

means:

```text
execute at simulated time 500
```

not:

```text
execute 500 time units after registration
```

At registration or reactivation, the start time may equal the current simulated time.

A start time that has already passed is rejected.

### `Policy::end_time`

```cpp
double end_time = 0.0;
```

An optional upper execution boundary.

The default:

```cpp
0.0
```

means:

```text
no explicit policy end-time boundary
```

For a finite policy:

```cpp
p->start_time =
    100.0;

p->end_time =
    500.0;
```

the required relationship is:

```text
end_time > start_time
```

when `end_time` is greater than zero.

### End-time behavior

A repeating policy may execute exactly at its configured `end_time`.

For example:

```cpp
CGSim::Policy* POLICY::finite_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Finite Policy";

    p->start_time =
        100.0;

    p->end_time =
        500.0;

    p->repeat_interval =
        100.0;

    p->callback = []()
    {
        // Policy work.
    };

    return p;
}
```

This policy can execute at:

```text
100
200
300
400
500
```

The next candidate time would be beyond the configured end time, so the policy is deactivated.

### `Policy::repeat_interval`

```cpp
double repeat_interval = 0.0;
```

The simulated-time interval between repeated executions.

A value of:

```cpp
0.0
```

creates a one-shot policy.

A positive value creates a repeating policy.

For example:

```cpp
CGSim::Policy* POLICY::periodic_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Periodic Policy";

    p->start_time =
        100.0;

    p->repeat_interval =
        50.0;

    p->callback = []()
    {
        // Repeating work.
    };

    return p;
}
```

This policy can execute at:

```text
100
150
200
250
...
```

Negative repeat intervals are rejected.

### `Policy::callback`

```cpp
std::function<void()> callback;
```

The callback contains the work performed by the policy.

A factory can capture both the policy helper object and the policy name:

```cpp
CGSim::Policy* POLICY::storage_rebalance_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Storage Rebalance Policy";

    p->start_time =
        0.0;

    p->repeat_interval =
        1000.0;

    const std::string policy_name =
        p->name;

    p->callback =
        [this]()
        {
            run_storage_rebalance();
        };

    return p;
}
```

When a callback captures:

```cpp
[this]
```

the `POLICY` object must remain alive whenever that callback may execute.

### `Policy::is_active()`

```cpp
bool is_active() const;
```

Returns the active state maintained by PolicyManager.

Example:

```cpp
auto* pm =
    CGSim::get_policy_manager();

auto* p =
    pm->get_policy(
        "Storage Rebalance Policy"
    );

if (p->is_active()) {
    std::cout
        << "Policy is active\n";
}
```

Use the manager's lifecycle methods to deactivate or reactivate a policy.

## Policy pointer lifetime

`addPolicy()` stores the supplied `CGSim::Policy*`.

The object is not copied.

A factory such as:

```cpp
CGSim::Policy* POLICY::storage_rebalance_policy()
{
    auto* p =
        new CGSim::Policy();

    // Configuration...

    return p;
}
```

creates the policy on the heap, so returning from the factory does not destroy the policy object.

That makes the returned pointer suitable for registration:

```cpp
CGSim::get_policy_manager()->addPolicy(
    storage_rebalance_policy()
);
```

### Keep registered policies alive

A registered policy must remain valid for as long as PolicyManager may reference it.

The factory pattern satisfies this by allocating each policy with:

```cpp
new CGSim::Policy();
```

Do not delete a registered policy while it remains in the manager's registry.

### Callback owner lifetime

The heap allocation keeps the `CGSim::Policy` alive, but it does not keep objects captured by the callback alive.

For example:

```cpp
p->callback =
    [this]()
    {
        run_storage_rebalance();
    };
```

requires the object represented by `this` to remain valid whenever the callback can run.

### Deactivated policies remain registered

A deactivated policy remains available through:

```cpp
pm->get_policy(...)
```

and can later be reactivated.

Its `CGSim::Policy*` must therefore remain valid while it stays registered.

## Registering multiple policies

The factory pattern makes bulk registration straightforward:

```cpp
void POLICY::addPolicies()
{
    auto* pm =
        CGSim::get_policy_manager();

    pm->addPolicy(
        storage_rebalance_policy()
    );

    pm->addPolicy(
        network_aware_rebalance_policy()
    );

    pm->addPolicy(
        hotset_replication_policy()
    );
}
```

Or, if preferred:

```cpp
void POLICY::addPolicies()
{
    CGSim::get_policy_manager()->addPolicy(
        storage_rebalance_policy()
    );

    CGSim::get_policy_manager()->addPolicy(
        network_aware_rebalance_policy()
    );

    CGSim::get_policy_manager()->addPolicy(
        hotset_replication_policy()
    );
}
```

Both forms use the same manager.

## `addPolicy()`

Register a policy with:

```cpp
pm->addPolicy(
    policy_pointer
);
```

With a factory:

```cpp
pm->addPolicy(
    storage_rebalance_policy()
);
```

### Registration checks

Before registration succeeds, PolicyManager checks:

```text
policy pointer is not null
      |
      v
name is not already registered
      |
      v
policy is active
      |
      v
repeat interval is valid
      |
      v
start time has not elapsed
      |
      v
finite end time has not elapsed
      |
      v
finite end time is greater than start time
      |
      v
register policy
      |
      v
mark policy active
      |
      v
advance generation
      |
      v
schedule first execution
```

### Null policy

This is invalid:

```cpp
auto* pm =
    CGSim::get_policy_manager();

pm->addPolicy(
    nullptr
);
```

and throws:

```cpp
std::invalid_argument
```

### Duplicate name

A policy name may only be registered once.

For example:

```cpp
CGSim::Policy* POLICY::first_monitor()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Monitor";

    p->callback = []() {};

    return p;
}
```

and:

```cpp
CGSim::Policy* POLICY::second_monitor()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Monitor";

    p->callback = []() {};

    return p;
}
```

cannot both be registered because they use the same name.

Use unique names or reactivate the existing registered policy.

### Start-time validation

At registration:

```text
current simulated time > start_time
```

is rejected.

Therefore:

```text
start_time == current simulated time
```

is accepted.

### End-time validation

When:

```cpp
p->end_time > 0.0;
```

the policy must satisfy:

```text
end_time > start_time
```

and the end time must not already have elapsed.

Use:

```cpp
p->end_time =
    0.0;
```

when no explicit end-time boundary is required.

### Repeat-interval validation

This is valid:

```cpp
p->repeat_interval =
    0.0;
```

and creates a one-shot policy.

This is valid:

```cpp
p->repeat_interval =
    1000.0;
```

and creates a repeating policy.

A negative interval is invalid.

## One-shot policy example

A one-shot factory can omit `repeat_interval` because its default is zero:

```cpp
CGSim::Policy* POLICY::maintenance_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Site Maintenance";

    p->start_time =
        1000.0;

    p->callback = []()
    {
        auto* site =
            CGSim::get_site_manager()
                ->get_site("SiteA");

        site->job_assignment_enabled =
            false;
    };

    return p;
}
```

Register it with:

```cpp
CGSim::get_policy_manager()->addPolicy(
    maintenance_policy()
);
```

After the callback executes, the policy is deactivated.

## Repeating policy example

```cpp
CGSim::Policy* POLICY::monitoring_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Grid Monitor";

    p->start_time =
        0.0;

    p->end_time =
        0.0;

    p->repeat_interval =
        60.0;

    p->callback = []()
    {
        auto* sm =
            CGSim::get_site_manager();

        std::cout
            << sm->get_grid_cpu_utilization()
            << '\n';
    };

    return p;
}
```

Register it with:

```cpp
CGSim::get_policy_manager()->addPolicy(
    monitoring_policy()
);
```

## Finite repeating policy example

```cpp
CGSim::Policy* POLICY::finite_monitor_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Finite Grid Monitor";

    p->start_time =
        100.0;

    p->end_time =
        1000.0;

    p->repeat_interval =
        100.0;

    p->callback = []()
    {
        auto* sm =
            CGSim::get_site_manager();

        std::cout
            << sm->get_grid_cpu_utilization()
            << '\n';
    };

    return p;
}
```

This policy can execute at:

```text
100
200
300
400
500
600
700
800
900
1000
```

while policy execution remains enabled.


## Manual deactivation

### `deactivate_policy()`

Stop an active policy with:

```cpp
auto* pm =
    CGSim::get_policy_manager();

pm->deactivate_policy(
    "Grid Monitor"
);
```

Deactivation:

1. requires the policy to be active;
2. sets its active state to `false`;
3. advances its internal generation;
4. removes it from the active registry;
5. adds it to the deactivated registry.

The policy remains registered.

### Check before deactivating

```cpp
auto* pm =
    CGSim::get_policy_manager();

auto* p =
    pm->get_policy(
        "Grid Monitor"
    );

if (p->is_active()) {
    pm->deactivate_policy(
        p->name
    );
}
```

Trying to deactivate a policy that is not active throws:

```cpp
std::runtime_error
```

## Reactivation

### `reactivate_policy()`

A registered deactivated policy can be reactivated.

For example:

```cpp
auto* pm =
    CGSim::get_policy_manager();

auto* p =
    pm->get_policy(
        "Grid Monitor"
    );

p->start_time =
    2000.0;

p->end_time =
    3000.0;

p->repeat_interval =
    100.0;

pm->reactivate_policy(
    p->name
);
```

### Reactivation requirements

The policy must:

- be deactivated;
- have a non-negative repeat interval;
- have a start time that has not elapsed;
- have a finite end time that has not elapsed;
- have `end_time > start_time` when `end_time > 0`.

### Reactivating a one-shot policy

```cpp
auto* pm =
    CGSim::get_policy_manager();

auto* p =
    pm->get_policy(
        "Site Maintenance"
    );

p->start_time =
    2500.0;

pm->reactivate_policy(
    p->name
);
```

Because its repeat interval is zero, it executes once and becomes deactivated again.

### Reactivating a repeating policy

```cpp
auto* pm =
    CGSim::get_policy_manager();

auto* p =
    pm->get_policy(
        "Storage Rebalance Policy"
    );

p->start_time =
    5000.0;

p->end_time =
    10000.0;

p->repeat_interval =
    500.0;

pm->reactivate_policy(
    p->name
);
```

## Generation-based execution safety

Each policy has an internal generation number.

The generation changes when policy activation state changes.

Each scheduled execution records the generation associated with the activation that created it.

When that execution is processed:

```text
scheduled generation
        |
        v
compare with current generation
        |
        +--> same: continue
        |
        +--> different: ignore
```

This prevents scheduled work from an earlier activation from executing after a policy has been deactivated or reactivated.

Users do not configure the generation number.

## Looking up a policy

### `get_policy()`

```cpp
auto* pm =
    CGSim::get_policy_manager();

CGSim::Policy* p =
    pm->get_policy(
        "Storage Rebalance Policy"
    );
```

The returned pointer is the registered policy pointer.

It can be used to:

- inspect timing configuration;
- inspect active state;
- update timing before reactivation;
- update the callback;
- change the repeat interval.

### Unknown policy

If the policy name does not exist:

```cpp
pm->get_policy(
    "Missing Policy"
);
```

throws:

```cpp
std::runtime_error
```

## Checking whether a policy exists

### `exists()`

```cpp
auto* pm =
    CGSim::get_policy_manager();

if (pm->exists(
        "Storage Rebalance Policy"))
{
    // Policy is registered.
}
```

A deactivated policy still exists.

Therefore `exists()` checks registration, not active state.

For active state:

```cpp
auto* p =
    pm->get_policy(
        "Storage Rebalance Policy"
    );

if (p->is_active()) {
    // Active.
}
```

## Listing policies

### `get_policy_list()`

```cpp
auto* pm =
    CGSim::get_policy_manager();

auto names =
    pm->get_policy_list();

for (const auto& name : names) {
    std::cout
        << name
        << '\n';
}
```

Returns every registered policy name.

### `get_active_policy_list()`

```cpp
auto* pm =
    CGSim::get_policy_manager();

for (
    const auto& name :
    pm->get_active_policy_list()
)
{
    std::cout
        << "active: "
        << name
        << '\n';
}
```

### `get_deactivated_policy_list()`

```cpp
auto* pm =
    CGSim::get_policy_manager();

for (
    const auto& name :
    pm->get_deactivated_policy_list()
)
{
    std::cout
        << "deactivated: "
        << name
        << '\n';
}
```

### List ordering

The list methods return:

```cpp
std::unordered_set<std::string>
```

Iteration order is not guaranteed.

When deterministic output is useful:

```cpp
auto* pm =
    CGSim::get_policy_manager();

auto names =
    pm->get_policy_list();

std::vector<std::string> ordered(
    names.begin(),
    names.end()
);

std::sort(
    ordered.begin(),
    ordered.end()
);
```

## Automatic deactivation

A policy can become deactivated automatically.

### One-shot completion

When:

```cpp
p->repeat_interval ==
    0.0;
```

the policy is deactivated after its callback executes.

### Finite-window completion

If the current simulated time is greater than a finite `end_time`, the policy is deactivated without executing.

After a callback, if the next repeat would be greater than `end_time`, the policy is deactivated instead of being scheduled again.

### Policy execution shutdown

When CGSim disables policy execution, a later scheduled policy invocation is deactivated rather than executed.

### Callback error

If the callback throws an exception derived from:

```cpp
std::exception
```

PolicyManager deactivates the policy and propagates a `std::runtime_error` containing policy context.

## Callback error example

A factory can still use normal exception handling inside its callback:

```cpp
CGSim::Policy* POLICY::safe_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Safe Policy";

    p->start_time =
        0.0;

    p->repeat_interval =
        100.0;

    p->callback = []()
    {
        try {
            perform_optional_work();
        }
        catch (const std::exception& e) {
            std::cerr
                << e.what()
                << '\n';
        }
    };

    return p;
}
```

If a callback error should stop that policy, allow the exception to propagate.

## Empty callbacks

Always assign a callback before returning a policy from its factory.

For example:

```cpp
CGSim::Policy* POLICY::valid_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Valid Policy";

    p->start_time =
        0.0;

    p->callback = []()
    {
        // Policy logic.
    };

    return p;
}
```

## Policy execution lifetime

Policy execution remains enabled while CGSim is processing the workload's tracked execution phase.

The job executor disables policy execution after:

```text
all jobs have been activated
and
tracked pending activities have drained
```

A scheduled policy invocation processed after policy execution has been disabled is deactivated rather than executed.

For behavior that must occur at final simulation completion, use:

```cpp
onSimulationEnd()
```

## SiteManager policy example

```cpp
CGSim::Policy* POLICY::site_utilization_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Site Utilization Policy";

    p->start_time =
        0.0;

    p->repeat_interval =
        60.0;

    p->callback = []()
    {
        auto* sm =
            CGSim::get_site_manager();

        for (
            const auto& site_name :
            sm->get_all_sites()
        )
        {
            std::cout
                << site_name
                << ": "
                << sm->get_site_cpu_utilization(
                       site_name
                   )
                << '\n';
        }
    };

    return p;
}
```

Register it with:

```cpp
CGSim::get_policy_manager()->addPolicy(
    site_utilization_policy()
);
```

## Site admission policy example

```cpp
CGSim::Policy* POLICY::site_admission_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Site Admission Policy";

    p->start_time =
        0.0;

    p->repeat_interval =
        30.0;

    p->callback = []()
    {
        auto* sm =
            CGSim::get_site_manager();

        auto* site =
            sm->get_site("SiteA");

        const double utilization =
            sm->get_site_cpu_utilization(
                "SiteA"
            );

        if (utilization > 0.95) {
            site->job_assignment_enabled =
                false;
        }
        else if (utilization < 0.70) {
            site->job_assignment_enabled =
                true;
        }
    };

    return p;
}
```

## File replication policy example

```cpp
CGSim::Policy* POLICY::file_replication_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "File Replication Policy";

    p->start_time =
        100.0;

    const std::string policy_name =
        p->name;

    p->callback =
        [policy_name]()
        {
            auto* fm =
                CGSim::get_file_manager();

            const std::string filename =
                "popular.root";

            const std::string source =
                "SiteA";

            const std::string destination =
                "SiteB";

            if (!fm->exists(
                    filename,
                    source))
            {
                return;
            }

            if (fm->exists(
                    filename,
                    destination))
            {
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
                fm->request_file_size(
                    filename
                );

            if (
                fm->request_remaining_site_storage(
                    destination
                )
                < size
            )
            {
                return;
            }

            fm->transfer(
                filename,
                source,
                destination,
                CGSim::FileTransferDecisionMode::COPY,
                policy_name
            );
        };

    return p;
}
```

Register it with:

```cpp
CGSim::get_policy_manager()->addPolicy(
    file_replication_policy()
);
```

## Avoiding duplicate asynchronous work

A repeating policy can execute again while work started by an earlier invocation is still active.

A file policy can check current transfer state:

```cpp
CGSim::Policy* POLICY::guarded_replication_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Guarded Replication Policy";

    p->start_time =
        100.0;

    p->repeat_interval =
        300.0;

    p->callback = []()
    {
        auto* fm =
            CGSim::get_file_manager();

        const std::string filename =
            "input.root";

        const std::string source =
            "SiteA";

        const std::string destination =
            "SiteB";

        if (fm->is_in_flight(
                filename,
                source,
                destination))
        {
            return;
        }

        fm->transfer(
            filename,
            source,
            destination,
            CGSim::FileTransferDecisionMode::COPY,
            "Guarded Replication Policy"
        );
    };

    return p;
}
```

## Reconfiguring a registered policy

`get_policy()` returns the registered pointer.

This allows public configuration fields to be changed.

For predictable scheduling, timing changes are easiest to make while the policy is deactivated.

### Updating `start_time`

```cpp
auto* pm =
    CGSim::get_policy_manager();

auto* p =
    pm->get_policy(
        "Grid Monitor"
    );

p->start_time =
    5000.0;
```

For an active policy, changing `start_time` does not replace an already scheduled invocation.

For a deactivated policy, update it before reactivation.

### Updating `end_time`

```cpp
p->start_time =
    5000.0;

p->end_time =
    10000.0;
```

To remove the finite boundary:

```cpp
p->end_time =
    0.0;
```

### Updating `repeat_interval`

```cpp
p->repeat_interval =
    250.0;
```

For an active policy, a scheduled invocation remains scheduled.

The new interval is used when a later repeat is calculated.

### Updating `callback`

```cpp
p->callback = []()
{
    std::cout
        << "Updated behavior\n";
};
```

This can be useful before reactivation.

### Do not update `name`

Keep the registered policy name unchanged.

## Deactivate, reconfigure, and reactivate

```cpp
auto* pm =
    CGSim::get_policy_manager();

auto* p =
    pm->get_policy(
        "Storage Rebalance Policy"
    );

if (p->is_active()) {
    pm->deactivate_policy(
        p->name
    );
}

p->start_time =
    5000.0;

p->end_time =
    10000.0;

p->repeat_interval =
    500.0;

pm->reactivate_policy(
    p->name
);
```

## Policy state model

A registered policy is either active or deactivated:

```text
            addPolicy()
                |
                v
             ACTIVE
                |
       +--------+---------+
       |                  |
       | manual           | automatic
       | deactivation     | deactivation
       |                  |
       v                  v
           DEACTIVATED
                |
                |
       reactivate_policy()
                |
                v
             ACTIVE
```

The policy remains registered throughout these state changes.

## Registry relationships

Conceptually:

```text
all registered policies
        |
        +--> active policies
        |
        +--> deactivated policies
```

Use:

```cpp
pm->get_policy_list();
```

for all names.

Use:

```cpp
pm->get_active_policy_list();
```

for active names.

Use:

```cpp
pm->get_deactivated_policy_list();
```

for deactivated names.

## Execution algorithm

A scheduled policy invocation follows:

```text
scheduled invocation
      |
      v
generation still current?
      |
      +--> no: ignore
      |
      v
policy active?
      |
      +--> no: stop
      |
      v
finite end time exceeded?
      |
      +--> yes: deactivate
      |
      v
policy execution enabled?
      |
      +--> no: deactivate
      |
      v
execute callback
      |
      +--> callback error?
      |       |
      |       +--> deactivate
      |       +--> propagate policy error
      |
      v
policy still active?
      |
      +--> no: stop
      |
      v
repeat_interval == 0?
      |
      +--> yes: deactivate
      |
      v
calculate next execution
      |
      v
next execution beyond end time?
      |
      +--> yes: deactivate
      |
      v
schedule next execution
```

## Reactivation algorithm

Reactivation follows:

```text
reactivate_policy(name)
      |
      v
policy is deactivated?
      |
      +--> no: throw
      |
      v
repeat interval valid?
      |
      +--> no: throw
      |
      v
finite time window valid?
      |
      +--> no: throw
      |
      v
start time not elapsed?
      |
      +--> no: throw
      |
      v
finite end time not elapsed?
      |
      +--> no: throw
      |
      v
mark active
      |
      v
advance generation
      |
      v
move to active registry
      |
      v
schedule start time
```

## Timing examples

| `start_time` | `repeat_interval` | `end_time` | Execution times |
|---:|---:|---:|---|
| `100` | `0` | `0` | `100` |
| `100` | `50` | `0` | `100, 150, 200, ...` |
| `100` | `50` | `250` | `100, 150, 200, 250` |
| `0` | `10` | `30` | `0, 10, 20, 30` |
| `100` | `100` | `500` | `100, 200, 300, 400, 500` |

## Validation reference

### `addPolicy()`

| Condition | Result |
|---|---|
| policy pointer is null | `std::invalid_argument` |
| name already registered | `std::runtime_error` |
| policy is inactive | `std::invalid_argument` |
| `repeat_interval < 0` | `std::invalid_argument` |
| current time is greater than `start_time` | `std::runtime_error` |
| finite `end_time` has elapsed | `std::runtime_error` |
| finite `end_time <= start_time` | `std::invalid_argument` |

### `reactivate_policy()`

| Condition | Result |
|---|---|
| policy is not deactivated | `std::runtime_error` |
| `repeat_interval < 0` | `std::invalid_argument` |
| finite `end_time <= start_time` | `std::invalid_argument` |
| `start_time` has elapsed | `std::runtime_error` |
| finite `end_time` has elapsed | `std::runtime_error` |

### `deactivate_policy()`

| Condition | Result |
|---|---|
| policy is not active | `std::runtime_error` |

### `get_policy()`

| Condition | Result |
|---|---|
| name is not registered | `std::runtime_error` |

## API reference

### `CGSim::get_policy_manager()`

```cpp
auto* pm =
    CGSim::get_policy_manager();
```

Returns the global PolicyManager.

### `addPolicy()`

```cpp
pm->addPolicy(
    CGSim::Policy* policy
);
```

Registers the supplied policy pointer and schedules its first execution.

The pointed-to object must remain valid while PolicyManager may reference it.

### `deactivate_policy()`

```cpp
pm->deactivate_policy(
    const std::string& policy_name
);
```

Deactivates an active policy.

### `reactivate_policy()`

```cpp
pm->reactivate_policy(
    const std::string& policy_name
);
```

Reactivates a registered deactivated policy using its current configuration.

### `get_policy()`

```cpp
CGSim::Policy* p =
    pm->get_policy(
        policy_name
    );
```

Returns the registered policy pointer.

### `exists()`

```cpp
bool registered =
    pm->exists(
        policy_name
    );
```

Returns whether the policy name is registered.

### `get_policy_list()`

```cpp
auto names =
    pm->get_policy_list();
```

Returns all registered policy names.

### `get_active_policy_list()`

```cpp
auto names =
    pm->get_active_policy_list();
```

Returns active policy names.

### `get_deactivated_policy_list()`

```cpp
auto names =
    pm->get_deactivated_policy_list();
```

Returns deactivated policy names.

### `Policy::is_active()`

```cpp
bool active =
    p->is_active();
```

Returns the active state maintained by PolicyManager.

## Recommended usage

For policy creation and registration:

1. Define a factory returning `CGSim::Policy*`.
2. Allocate the policy with `new CGSim::Policy()`.
3. Configure its name and timing.
4. Copy any callback metadata you want to capture, such as `policy_name`.
5. Assign the callback.
6. Return the pointer.
7. Register it with `CGSim::get_policy_manager()->addPolicy(factory())`.
8. Keep any objects captured by the callback alive.
9. Do not delete the registered policy while PolicyManager may still reference it.
10. Use `get_policy()` for later inspection or reconfiguration.
11. Use `deactivate_policy()` and `reactivate_policy()` for lifecycle control.

A typical implementation is:

```cpp
void POLICY::addPolicies()
{
    CGSim::get_policy_manager()->addPolicy(
        storage_rebalance_policy()
    );

    CGSim::get_policy_manager()->addPolicy(
        network_aware_rebalance_policy()
    );

    CGSim::get_policy_manager()->addPolicy(
        hotset_replication_policy()
    );
}
```

with factories such as:

```cpp
CGSim::Policy* POLICY::storage_rebalance_policy()
{
    auto* p =
        new CGSim::Policy();

    p->start_time =
        0.0;

    p->end_time =
        0.0;

    p->repeat_interval =
        1000.0;

    p->name =
        "Storage Rebalance Policy";

    const std::string policy_name =
        p->name;

    p->callback =
        [this]()
        {
            run_storage_rebalance();
        };

    return p;
}
```

## Common mistakes

### Returning the address of a local policy

Do not do this:

```cpp
CGSim::Policy* POLICY::bad_policy()
{
    CGSim::Policy local;

    return &local;
}
```

`local` is destroyed when the factory returns.

Allocate the returned policy on the heap:

```cpp
CGSim::Policy* POLICY::good_policy()
{
    auto* p =
        new CGSim::Policy();

    p->name =
        "Good Policy";

    p->callback = []() {};

    return p;
}
```

### Deleting a registered policy too early

PolicyManager stores the pointer.

Do not delete the policy while it remains registered.

### Destroying an object captured by `this`

If a callback uses:

```cpp
[this]()
```

the owning object must remain valid whenever the callback can run.

### Re-registering the same policy name

A deactivated policy remains registered.

Use:

```cpp
pm->reactivate_policy(...)
```

instead of registering a second policy with the same name.

### Reactivating with an elapsed start time

Update the stored start time before reactivation.

### Treating `start_time` as a delay

`start_time` is an absolute simulated timestamp.

### Assuming the end boundary is excluded

A repeating policy may execute exactly at `end_time`.

### Assuming `exists()` means active

A deactivated policy still exists.

Use:

```cpp
p->is_active()
```

or:

```cpp
pm->get_active_policy_list()
```

for active state.

### Depending on policy-list order

The list APIs return unordered sets.

Sort the names if stable ordering matters.

### Changing `Policy::name` after registration

Keep the registered name unchanged.

## Quick reference

| Goal | API / pattern |
|---|---|
| Access PolicyManager | `CGSim::get_policy_manager()` |
| Create a policy | `auto* p = new CGSim::Policy()` |
| Factory return type | `CGSim::Policy*` |
| Register factory result | `pm->addPolicy(my_policy())` |
| Set name | `p->name` |
| Set first execution | `p->start_time` |
| Set optional end time | `p->end_time` |
| Set repeat cadence | `p->repeat_interval` |
| Set callback | `p->callback` |
| Look up policy | `pm->get_policy()` |
| Check registration | `pm->exists()` |
| Check active state | `p->is_active()` |
| Deactivate | `pm->deactivate_policy()` |
| Reactivate | `pm->reactivate_policy()` |
| List all policies | `pm->get_policy_list()` |
| List active policies | `pm->get_active_policy_list()` |
| List deactivated policies | `pm->get_deactivated_policy_list()` |

## Key points

1. **Use `CGSim::get_policy_manager()` to access PolicyManager.**

2. **Policy factory functions should return `CGSim::Policy*`.**

3. **Allocate factory-created policies with `new CGSim::Policy()`.**

4. **Return the configured pointer from the factory.**

5. **Register the returned pointer directly with `addPolicy()`.**

6. **PolicyManager stores the registered pointer rather than copying the Policy object.**

7. **The registered policy must remain alive while PolicyManager may reference it.**

8. **If a callback captures `this`, that object must also remain alive.**

9. **Policy names must be unique and should remain unchanged after registration.**

10. **`start_time` is an absolute simulated timestamp.**

11. **A start time equal to the current simulated time is accepted.**

12. **`repeat_interval = 0` creates a one-shot policy.**

13. **A positive repeat interval creates a repeating policy.**

14. **Negative repeat intervals are rejected.**

15. **`end_time = 0` means no explicit end-time boundary.**

16. **A finite `end_time` must be greater than `start_time`.**

17. **A repeating policy may execute exactly at `end_time`.**

18. **`deactivate_policy()` stops an active policy.**

19. **A deactivated policy remains registered.**

20. **Use `reactivate_policy()` to run a deactivated policy again.**

21. **Reactivation validates the policy's current timing configuration.**

22. **Generation numbers prevent scheduled work from another activation from executing.**

23. **`exists()` reports registration, not active state.**

24. **Use `is_active()` or the active-policy list for active-state checks.**

25. **Policy-list iteration order is not guaranteed.**

26. **Callback exceptions derived from `std::exception` deactivate the policy and are propagated with policy context.**

27. **Use `onSimulationEnd()` for behavior that must occur at final simulation completion.**

A consistent policy implementation can therefore follow one simple convention: every policy-definition function returns a heap-allocated `CGSim::Policy*`, and `addPolicies()` passes each returned pointer directly to `CGSim::get_policy_manager()->addPolicy(...)`.
