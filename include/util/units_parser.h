#pragma once
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <unordered_map>

namespace CGSim {

namespace Utilities {

inline unsigned long long parse_units_size(std::string s) {
    s.erase(std::remove_if(s.begin(), s.end(), [](unsigned char c){ return std::isspace(c); }), s.end());

    size_t i = 0;
    while (i < s.size() && (std::isdigit((unsigned char)s[i]) || s[i] == '.')) ++i;
    if (!i) throw std::invalid_argument("Invalid Size Units");

    double n = std::stod(s.substr(0, i));
    std::string u = s.substr(i);
    std::transform(u.begin(), u.end(), u.begin(), [](unsigned char c){ return std::toupper(c); });

    static const std::unordered_map<std::string, std::uint64_t> units{
        {"", 1ULL}, {"B",1ULL}, {"KB",1000ULL}, {"MB",1000000ULL}, {"GB",1000000000ULL}, {"TB",1000000000000ULL}, {"PB",1000000000000000ULL},
        {"KIB",1ULL<<10}, {"MIB",1ULL<<20}, {"GIB",1ULL<<30}, {"TIB",1ULL<<40}, {"PIB",1ULL<<50}
    };

    auto it = units.find(u);
    if (it == units.end() || n < 0) throw std::invalid_argument("Invalid Size Units");
    return static_cast<unsigned long long>(n * it->second);
}

inline unsigned long long parse_units_time(std::string s) {
    s.erase(std::remove_if(s.begin(), s.end(), [](unsigned char c){ return std::isspace(c); }), s.end());
    size_t i = 0; while (i < s.size() && (std::isdigit((unsigned char)s[i]) || s[i] == '.' || s[i] == 'e' || s[i] == 'E' || ((s[i] == '+' || s[i] == '-') && i > 0 && (s[i-1] == 'e' || s[i-1] == 'E'))) ) ++i;
    if (!i) throw std::invalid_argument("Invalid Time Units");
    double n = std::stod(s.substr(0, i)); std::string u = s.substr(i);
    std::transform(u.begin(), u.end(), u.begin(), [](unsigned char c){ return std::tolower(c); });
    static const std::unordered_map<std::string, double> units{
        {"ms",0.001},{"s",1.0},{"m",60.0},{"h",3600.0},{"d",86400.0},
        {"w",604800.0},{"y",31536000.0}
    };
    auto it = units.find(u);
    if (it == units.end() || n < 0) throw std::invalid_argument("Invalid Time Units");
    return static_cast<unsigned long long>(n * it->second);
}
  
}

}
