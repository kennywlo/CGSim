#pragma once
#include <chrono>
#include <simgrid/s4u.hpp>

int main(int argc, char** argv);

namespace CGSim {

namespace Utilities {

inline double get_simulation_clock(){return simgrid::s4u::Engine::get_clock();}
  
class Statistics {
public:
    using Clock = std::chrono::steady_clock;
    static unsigned long get_pending_activities_size();
    static double get_system_clock();
    
private:
    inline static Clock::time_point start_ = Clock::now();
    static void start() {start_ = Clock::now();}
  
    friend int ::main(int argc, char** argv);

};

}

}
