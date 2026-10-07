#pragma once
#include <iostream>
#include <iomanip>
#include <string>
#include "resource_manager.h"
#include "version.h"
#include <sstream>
#include <algorithm>

namespace CGSim {

namespace Utilities {

inline std::string get_grid_name()
{
    return CGSim::GlobalManagers::get_resource_manager()->get_custom_parameter("Grid Name");
}

inline void print_CGSim_Logo()
{
    constexpr int WIDTH = 62;

    std::ostringstream title;
    title << "Computing Grid Simulator  [v" << MAJOR_VERSION << "." << MINOR_VERSION << "]";

    const int titlePad = std::max(0, (WIDTH - static_cast<int>(title.str().size())) / 2);

    std::cout
        << "\033[1;36m"
        << R"(
           ██████╗  ██████╗ ███████╗██╗███╗   ███╗
          ██╔════╝ ██╔════╝ ██╔════╝██║████╗ ████║
          ██║      ██║  ███╗███████╗██║██╔████╔██║
          ██║      ██║   ██║╚════██║██║██║╚██╔╝██║
          ╚██████╗ ╚██████╔╝███████║██║██║ ╚═╝ ██║
           ╚═════╝  ╚═════╝ ╚══════╝╚═╝╚═╝     ╚═╝
)"
        << "\033[0m\n"
        << "\033[90m"
        << "══════════════════════════════════════════════════════════════\n"
        << "\033[0m"
        << std::string(titlePad, ' ')
        << "\033[1;37mComputing Grid Simulator\033[0m  "
        << "\033[90m[v\033[1;33m"
        << MAJOR_VERSION << "." << MINOR_VERSION
        << "\033[90m]\033[0m\n"
        << "\033[90m"
        << "══════════════════════════════════════════════════════════════\n"
        << "\033[0m\n";
}

inline void print_site(const std::string& siteName)
{
    static bool headerPrinted = false;
    constexpr int INNER_WIDTH = 60, SITE_WIDTH = 37;

    if (!headerPrinted)
    {
        headerPrinted = true;

        const std::string gridName = get_grid_name();
        const int left  = std::max(0, (INNER_WIDTH - static_cast<int>(gridName.size())) / 2);
        const int right = std::max(0, INNER_WIDTH - static_cast<int>(gridName.size()) - left);

        std::cout
            << "\n\033[1;36m"
            << "╔════════════════════════════════════════════════════════════╗\n"
            << "║" << std::string(left, ' ')
            << "\033[1;37m" << gridName << "\033[1;36m"
            << std::string(right, ' ') << "║\n"
            << "╠═══════════════════════════════════════╦════════════════════╣\n"
            << "\033[0m";
    }

    std::cout
        << "\033[1;36m║\033[0m "
        << "\033[1;37m" << std::left << std::setw(SITE_WIDTH) << siteName
        << "\033[0m "
        << "\033[1;36m║\033[0m "
        << "\033[1;32m● REGISTERED\033[0m"
        << std::string(7, ' ')
        << "\033[1;36m║\033[0m\n"
        << std::right;
}

inline void printSimulationDashBoard(std::size_t dispatchedJobs,
                                     std::size_t totalJobs,
                                     std::size_t activatedJobs,
                                     std::size_t finishedJobs,
                                     std::size_t pendingGlobalJobs,
                                     std::size_t pendingSiteJobs,
                                     std::size_t pendingActivities,
                                     double simulatedTime,
                                     double gridCpuUsage)
{
    static bool first = true;

    static bool cursorSetup = [] {
        std::cout << "\033[?25l" << std::flush; // hide cursor

        std::atexit([] {
            std::cout << "\033[?25h" << std::flush; // restore cursor
        });

        return true;
    }();

    (void)cursorSetup;

    constexpr int BAR = 27;
    constexpr int LINES = 16;
    constexpr int LABEL_WIDTH = 16;
    constexpr int BAR_LABEL_WIDTH = 16;

    // -------------------------------------------------------------------------
    // Simulated time
    // -------------------------------------------------------------------------

    auto s = static_cast<unsigned long long>(simulatedTime);

    const auto d = s / 86400;
    s %= 86400;

    const auto h = s / 3600;
    s %= 3600;

    const auto m = s / 60;
    const auto sec = s % 60;

    std::ostringstream time;

    if (d)
        time << d << "d ";

    time << std::setfill('0')
         << std::setw(2) << h << "h "
         << std::setw(2) << m << "m "
         << std::setw(2) << sec << "s";

    // -------------------------------------------------------------------------
    // Progress
    // -------------------------------------------------------------------------

    double progress = totalJobs
        ? static_cast<double>(dispatchedJobs) /
              static_cast<double>(totalJobs)
        : 0.0;

    progress = std::clamp(progress, 0.0, 1.0);

    const double cpu =
        std::clamp(gridCpuUsage * 100.0, 0.0, 100.0);

    const int jobFilled =
        static_cast<int>(progress * BAR);

    const int cpuFilled =
        static_cast<int>((cpu / 100.0) * BAR);

    // -------------------------------------------------------------------------
    // Build frame
    // -------------------------------------------------------------------------

    std::ostringstream out;

    if (!first)
    {
        /*
         * Cursor is currently on the line immediately below the dashboard.
         *
         * CSI n F = move cursor up n lines and place it at column 1.
         */
        out << "\033[" << LINES << "F";
    }

    first = false;

    /*
     * Finish a variable-width row.
     *
     * \033[K clears only from the current cursor position to the end of
     * the line. This removes leftovers when a number becomes shorter,
     * without clearing/repainting the entire line first.
     *
     * Then the right border is placed at column 62.
     */
    auto border = [&] {
        out << "\033[K"
            << "\033[62G"
            << "\033[1;36m│\033[0m"
            << '\n';
    };

    // -------------------------------------------------------------------------
    // Top
    // -------------------------------------------------------------------------

    out << "\033[1;36m"
        << "╭────────────────────────────────────────────────────────────╮"
        << "\033[0m\n";

    out << "\033[1;36m"
        << "│                                                            │"
        << "\033[0m\n";

    // -------------------------------------------------------------------------
    // Job progress
    // -------------------------------------------------------------------------

    out << "\033[1;36m│\033[0m  "
        << "\033[90m"
        << std::left
        << std::setw(BAR_LABEL_WIDTH)
        << "JOB PROGRESS"
        << "\033[0m[";

    for (int i = 0; i < BAR; ++i)
    {
        out << (i < jobFilled
            ? "\033[1;32m█\033[0m"
            : "\033[90m░\033[0m");
    }

    out << "] "
        << "\033[1;37m"
        << std::right
        << std::fixed
        << std::setprecision(1)
        << std::setw(5)
        << progress * 100.0
        << "%"
        << "\033[0m";

    border();

    // Dispatched
    out << "\033[1;36m│\033[0m  "
        << std::left
        << std::setw(BAR_LABEL_WIDTH)
        << ""
        << "\033[1;37m"
        << dispatchedJobs
        << "\033[90m / \033[1;37m"
        << totalJobs
        << "\033[0m dispatched";

    border();

    // -------------------------------------------------------------------------
    // Job statistics
    // -------------------------------------------------------------------------

    out << "\033[1;36m"
        << "│                                                            │"
        << "\033[0m\n";

    out << "\033[1;36m│\033[0m  "
        << "\033[1;32m●\033[0m  "
        << std::left
        << std::setw(LABEL_WIDTH)
        << "Running"
        << "\033[1;37m"
        << activatedJobs
        << "\033[0m";

    border();

    out << "\033[1;36m│\033[0m  "
        << "\033[1;32m✓\033[0m  "
        << std::left
        << std::setw(LABEL_WIDTH)
        << "Finished"
        << "\033[1;37m"
        << finishedJobs
        << "\033[0m";

    border();

    out << "\033[1;36m│\033[0m  "
        << "\033[1;33m◇\033[0m  "
        << std::left
        << std::setw(LABEL_WIDTH)
        << "Global Queue"
        << "\033[1;37m"
        << pendingGlobalJobs
        << "\033[0m";

    border();

    out << "\033[1;36m│\033[0m  "
        << "\033[1;33m◇\033[0m  "
        << std::left
        << std::setw(LABEL_WIDTH)
        << "Site Queues"
        << "\033[1;37m"
        << pendingSiteJobs
        << "\033[0m";

    border();

    out << "\033[1;36m│\033[0m  "
        << "\033[1;36m◆\033[0m  "
        << std::left
        << std::setw(LABEL_WIDTH)
        << "Activities"
        << "\033[1;37m"
        << pendingActivities
        << "\033[0m";

    border();

    // -------------------------------------------------------------------------
    // Simulated time
    // -------------------------------------------------------------------------

    out << "\033[1;36m"
        << "│                                                            │"
        << "\033[0m\n";

    out << "\033[1;36m│\033[0m  "
        << "\033[1;36m◆\033[0m  "
        << std::left
        << std::setw(LABEL_WIDTH)
        << "Simulated Time"
        << "\033[1;37m"
        << time.str()
        << "\033[0m";

    border();

    // -------------------------------------------------------------------------
    // CPU
    // -------------------------------------------------------------------------

    out << "\033[1;36m"
        << "│                                                            │"
        << "\033[0m\n";

    out << "\033[1;36m│\033[0m  "
        << "\033[90m"
        << std::left
        << std::setw(BAR_LABEL_WIDTH)
        << "GRID CPU UTIL"
        << "\033[0m[";

    for (int i = 0; i < BAR; ++i)
    {
        out << (i < cpuFilled
            ? "\033[1;35m█\033[0m"
            : "\033[90m░\033[0m");
    }

    out << "] "
        << "\033[1;35m"
        << std::right
        << std::fixed
        << std::setprecision(1)
        << std::setw(5)
        << cpu
        << "%"
        << "\033[0m";

    border();

    // -------------------------------------------------------------------------
    // Bottom
    // -------------------------------------------------------------------------

    out << "\033[1;36m"
        << "│                                                            │"
        << "\033[0m\n";

    out << "\033[1;36m"
        << "╰────────────────────────────────────────────────────────────╯"
        << "\033[0m\n";

    // Single terminal write per frame
    std::cout << out.str() << std::flush;
}

}

}