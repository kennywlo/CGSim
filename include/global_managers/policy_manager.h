#pragma once
#include <functional>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <simgrid/kernel/Timer.hpp>
#include <simgrid/s4u.hpp>
#include <memory>

namespace sg4 = simgrid::s4u;

namespace CGSim::Core {class JOB_EXECUTOR;}

namespace CGSim {

namespace GlobalManagers {class PolicyManager;}

class Policy
{
public:
    std::string name;
    double start_time      = 0.0;
    double end_time        = 0.0;
    double repeat_interval = 0.0;
    std::function<void()> callback;
    bool is_active() const{ return active;}

private:
    std::size_t generation_number = 0;
    bool active = true;
    friend class GlobalManagers::PolicyManager;
};

namespace GlobalManagers {

class PolicyManager
{
public:
    PolicyManager(const PolicyManager&) = delete;
    PolicyManager& operator=(const PolicyManager&) = delete;

    static PolicyManager& instance();

    static void                             addPolicy(CGSim::Policy* policy);
    static void                             reactivate_policy(const std::string& policy_name);
    static void                             deactivate_policy(const std::string& policy_name);
    static CGSim::Policy*                   get_policy(const std::string& policy_name);
    static bool                             exists(const std::string& policy_name);
    static std::unordered_set<std::string>  get_policy_list();
    static std::unordered_set<std::string>  get_active_policy_list();
    static std::unordered_set<std::string>  get_deactivated_policy_list();

private:
    PolicyManager() = default;
    static void run_policy(CGSim::Policy* policy, std::size_t generation_number);
    static std::unordered_map<std::string, CGSim::Policy*> policies;
    static std::unordered_map<std::string, CGSim::Policy*> active_policies;
    static std::unordered_map<std::string, CGSim::Policy*> deactivated_policies;
    friend class CGSim::Core::JOB_EXECUTOR;
    inline static bool RUNNING = true;
};

inline PolicyManager* get_policy_manager() {
    return &PolicyManager::instance();
} 

}

}