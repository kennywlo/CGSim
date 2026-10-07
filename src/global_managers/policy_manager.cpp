#include "policy_manager.h"
#include <stdexcept>

//Helper
namespace {template <typename T>std::unordered_set<std::string>getKeys(const std::unordered_map<std::string, T>& m){std::unordered_set<std::string> result;
    for (const auto& [key, value] : m) result.insert(key); return result;}}

namespace CGSim {

namespace GlobalManagers {

std::unordered_map<std::string, CGSim::Policy*>  PolicyManager::policies;
std::unordered_map<std::string, CGSim::Policy*>  PolicyManager::active_policies;
std::unordered_map<std::string, CGSim::Policy*>  PolicyManager::deactivated_policies;

PolicyManager& PolicyManager::instance()
{
    static PolicyManager pm;
    return pm;
}

void PolicyManager::addPolicy(CGSim::Policy* policy)
{
  if (policy == nullptr) throw std::invalid_argument("Cannot add a null policy");
  if (policies.count(policy->name) > 0) throw std::runtime_error( "Policy already exists: " + policy->name);
  if (!policy->active) throw std::invalid_argument("Cannot add an inactive policy");
  if (policy->repeat_interval < 0.0) throw std::invalid_argument("repeat_interval cannot be negative");
  const double now = sg4::Engine::get_clock();
  if (now > policy->start_time) throw std::runtime_error("Policy " + policy->name + " unable to start as start time has elapsed.");
  if (now > policy->end_time && policy->end_time > 0.0) throw std::runtime_error("Policy " + policy->name + " unable to start as end time has elapsed.");
  if (policy->end_time > 0.0 && policy->end_time <= policy->start_time) {throw std::invalid_argument("Policy end_time must be greater than start_time");}
  policies.emplace(policy->name, policy);
  active_policies.emplace(policy->name, policy);
  ++policy->generation_number;
  const std::size_t generation_number = policy->generation_number;
  simgrid::kernel::timer::Timer::set(policy->start_time,[policy,generation_number]() {PolicyManager::run_policy(policy, generation_number);});
}

void PolicyManager::run_policy(CGSim::Policy* policy, std::size_t generation_number)
{

  if (generation_number != policy->generation_number) return;

  const double now = sg4::Engine::get_clock();
  if (!policy->active) {if (active_policies.count(policy->name) > 0) deactivate_policy(policy->name);return;}
  if (now > policy->end_time && policy->end_time > 0.0) {deactivate_policy(policy->name); return;}
  if (!RUNNING) {deactivate_policy(policy->name); return;}

  try {policy->callback();}
  catch (const std::exception& e) {deactivate_policy(policy->name); throw std::runtime_error("Policy " + policy->name + " caused an error: " + e.what());}


  if (!policy->active) {if (active_policies.count(policy->name) > 0) deactivate_policy(policy->name);return;}
  if (policy->repeat_interval == 0.0) {deactivate_policy(policy->name); return;}
  const double next_time = sg4::Engine::get_clock() + policy->repeat_interval;
  if (next_time > policy->end_time  && policy->end_time > 0.0) {deactivate_policy(policy->name); return;}
  simgrid::kernel::timer::Timer::set(next_time,[policy,generation_number]() {PolicyManager::run_policy(policy, generation_number);});
}

void PolicyManager::deactivate_policy(const std::string& policy_name)
{
  if (active_policies.count(policy_name) == 0) throw std::runtime_error("Trying to deactivate policy " + policy_name + 
    " which is not active.");
  auto* policy = active_policies.at(policy_name);
  policy->active = false;
  ++policy->generation_number;   // Invalidating any timers belonging to this activation.
  active_policies.erase(policy->name);
  deactivated_policies.emplace(policy->name, policy);
}

void PolicyManager::reactivate_policy(const std::string& policy_name)
{
  if (deactivated_policies.count(policy_name) == 0) throw std::runtime_error("Trying to reactivate policy " + policy_name + " which is not deactivated.");
    auto* policy = deactivated_policies.at(policy_name);
  if (policy->repeat_interval < 0.0)throw std::invalid_argument("repeat_interval cannot be negative");
  if (policy->end_time > 0.0 &&policy->end_time <= policy->start_time)throw std::invalid_argument("Policy end_time must be greater than start_time");
  const double now = sg4::Engine::get_clock();
  if (now > policy->start_time) throw std::runtime_error("Please re-configure policy " + policy->name + 
    " start time again before reactivating policy.");
  if (now > policy->end_time && policy->end_time > 0.0) throw std::runtime_error("Please re-configure policy " 
    + policy->name + " end time again before reactivating policy.");

  policy->active = true;
  ++policy->generation_number;
  const std::size_t generation_number = policy->generation_number;
  active_policies.emplace(policy_name, policy);
  deactivated_policies.erase(policy_name);
  simgrid::kernel::timer::Timer::set(policy->start_time,[policy,generation_number]() {PolicyManager::run_policy(policy,generation_number);});
}

CGSim::Policy* PolicyManager::get_policy(const std::string& policy_name)
{
  if(!exists(policy_name)) throw std::runtime_error("Policy " + policy_name + " does not exist.");
  return policies.at(policy_name);
}

bool PolicyManager::exists(const std::string& policy_name)
{
  return policies.count(policy_name) > 0;
}

std::unordered_set<std::string>  PolicyManager::get_policy_list()
{
  return getKeys(policies);
}

std::unordered_set<std::string>  PolicyManager::get_active_policy_list()
{
  return getKeys(active_policies);
}

std::unordered_set<std::string>  PolicyManager::get_deactivated_policy_list()
{
  return getKeys(deactivated_policies);
}

}

}