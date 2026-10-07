// logger.h
#pragma once

#include <chrono>
#include <filesystem>
#include <fstream>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>


namespace minilog {

// ---------- log levels ----------
enum class level { trace, debug, info, warn, error, critical, off };

inline const char* level_name(level l) {
    switch (l) {
        case level::trace: return "trace";
        case level::debug: return "debug";
        case level::info: return "info";
        case level::warn: return "warn";
        case level::error: return "error";
        case level::critical: return "critical";
        default: return "off";
    }
}

// ---------- tiny "{}" formatter (no external deps) ----------
namespace detail {

template <typename T>
inline void append_one(std::ostringstream& oss, T&& v) {
    if constexpr (std::is_same_v<std::decay_t<T>, std::string>) {
        oss << v;
    } else if constexpr (std::is_same_v<std::decay_t<T>, const char*> ||
                         std::is_same_v<std::decay_t<T>, char*>) {
        oss << (v ? v : "(null)");
    } else {
        oss << std::forward<T>(v);
    }
}

// Finds next unescaped "{}" placeholder.
// Supports escaping "{{" -> "{", "}}" -> "}".
inline void append_literal_with_escapes(std::ostringstream& oss, std::string_view s) {
    for (size_t i = 0; i < s.size(); ++i) {
        char c = s[i];
        if (c == '{' && i + 1 < s.size() && s[i + 1] == '{') {
            oss << '{';
            ++i;
        } else if (c == '}' && i + 1 < s.size() && s[i + 1] == '}') {
            oss << '}';
            ++i;
        } else {
            oss << c;
        }
    }
}

// Core formatter: replaces "{}" with args in order.
// - "{{" and "}}" become literal braces
// - unmatched extra args are ignored
// - unmatched "{}" remain "{}"
template <typename... Args>
inline std::string format_braces(std::string_view fmt, Args&&... args) {
    std::ostringstream oss;

    // Store args into a callable pack expander.
    // We'll consume args one by one when we hit "{}".
    size_t pos = 0;

    auto emit_rest = [&](size_t from) {
        append_literal_with_escapes(oss, fmt.substr(from));
    };

    // Helper: emits next literal segment up to placeholder (handling escapes).
    auto emit_literal_segment = [&](size_t from, size_t to) {
        append_literal_with_escapes(oss, fmt.substr(from, to - from));
    };

    // We consume arguments by index using a fold over an initializer list.
    // This keeps it header-only and dependency-free.
    bool consumed_any = false;

    auto consume_one = [&](auto&& value) {
        // Find next placeholder "{}" that is not escaped as "{{" or "}}".
        while (true) {
            auto p = fmt.find('{', pos);
            if (p == std::string_view::npos) {
                // no placeholder; append rest and stop
                emit_rest(pos);
                pos = fmt.size();
                return false; // no placeholder consumed
            }
            // Handle escaped "{{"
            if (p + 1 < fmt.size() && fmt[p + 1] == '{') {
                // Append up to p, then a literal '{', advance past "{{"
                emit_literal_segment(pos, p);
                oss << '{';
                pos = p + 2;
                continue; // keep searching
            }
            // If it's a placeholder "{}", consume it
            if (p + 1 < fmt.size() && fmt[p + 1] == '}') {
                emit_literal_segment(pos, p);
                append_one(oss, std::forward<decltype(value)>(value));
                pos = p + 2;
                return true; // consumed a placeholder
            }
            // It's a single '{' not part of "{}", treat as literal '{'
            emit_literal_segment(pos, p);
            oss << '{';
            pos = p + 1;
        }
    };

    // Consume args in order
    (void)std::initializer_list<int>{
        (consumed_any = consume_one(std::forward<Args>(args)) || consumed_any, 0)...
    };

    // Append remaining format string (also handles "}}")
    if (pos < fmt.size()) {
        // Convert escaped "}}" into "}"
        // Our append_literal_with_escapes already does that.
        emit_rest(pos);
    }

    return oss.str();
}

} // namespace detail

// ---------- sink ----------
class sink {
public:
    virtual ~sink() = default;
    virtual void log(const std::string& msg) = 0;
    virtual void flush() {}
};

class file_sink final : public sink {
public:
    explicit file_sink(const std::string& path, bool append = true)
        : out_(path, append ? std::ios::app : std::ios::trunc) {}

    void log(const std::string& msg) override {
        std::lock_guard<std::mutex> lock(mu_);
        out_ << msg << '\n';
    }

    void flush() override {
        std::lock_guard<std::mutex> lock(mu_);
        out_.flush();
    }

private:
    std::ofstream out_;
    std::mutex mu_;
};

// ---------- logger ----------
class logger {
public:
    explicit logger(std::string name)
        : name_(std::move(name)) {}

    void add_sink(std::shared_ptr<sink> s) {
        sinks_.push_back(std::move(s));
    }

    void set_level(level l) { level_ = l; }
    void set_flush_level(level l) { flush_level_ = l; }

    // spdlog-like API (format string + variadic args)
    template <typename... Args>
    void trace(std::string_view fmt, Args&&... args) {
        log(level::trace, fmt, std::forward<Args>(args)...);
    }

    template <typename... Args>
    void debug(std::string_view fmt, Args&&... args) {
        log(level::debug, fmt, std::forward<Args>(args)...);
    }

    template <typename... Args>
    void info(std::string_view fmt, Args&&... args) {
        log(level::info, fmt, std::forward<Args>(args)...);
    }

    template <typename... Args>
    void warn(std::string_view fmt, Args&&... args) {
        log(level::warn, fmt, std::forward<Args>(args)...);
    }

    template <typename... Args>
    void error(std::string_view fmt, Args&&... args) {
        log(level::error, fmt, std::forward<Args>(args)...);
    }

    template <typename... Args>
    void critical(std::string_view fmt, Args&&... args) {
        log(level::critical, fmt, std::forward<Args>(args)...);
    }

private:
    template <typename... Args>
    void log(level l, std::string_view fmt, Args&&... args) {
        if (l < level_ || level_ == level::off) return;

        const std::string user_msg = detail::format_braces(fmt, std::forward<Args>(args)...);
        const std::string final_msg = format_prefix(l, user_msg);

        for (auto& s : sinks_) s->log(final_msg);
        if (l >= flush_level_) {
            for (auto& s : sinks_) s->flush();
        }
    }

    static std::string format_prefix(level l, const std::string& msg) {
        using clock = std::chrono::system_clock;
        auto now = clock::now();
        auto t = clock::to_time_t(now);
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            now.time_since_epoch()) % 1000;

        std::tm tm{};
    #if defined(_WIN32)
        localtime_s(&tm, &t);
    #else
        localtime_r(&t, &tm);
    #endif

        std::ostringstream oss;
        oss << (tm.tm_year + 1900) << '-'
            << (tm.tm_mon + 1 < 10 ? "0" : "") << (tm.tm_mon + 1) << '-'
            << (tm.tm_mday < 10 ? "0" : "") << tm.tm_mday << ' '
            << (tm.tm_hour < 10 ? "0" : "") << tm.tm_hour << ':'
            << (tm.tm_min < 10 ? "0" : "") << tm.tm_min << ':'
            << (tm.tm_sec < 10 ? "0" : "") << tm.tm_sec << '.'
            << (ms.count() < 100 ? (ms.count() < 10 ? "00" : "0") : "") << ms.count()
            << " [" << level_name(l) << "] "
            << msg;
        return oss.str();
    }

private:
    std::string name_;
    level level_ = level::info;
    level flush_level_ = level::off;
    std::vector<std::shared_ptr<sink>> sinks_;
};

} // namespace minilog


namespace CGSim::Utilities::logger {

    inline std::shared_ptr<minilog::logger> logger_instance;

    // Initializes the logger. Must be called at the beginning of main().
    inline void init() {
        std::filesystem::create_directories("logs");

        logger_instance = std::make_shared<minilog::logger>("CGSim");
        logger_instance->add_sink(
            std::make_shared<minilog::file_sink>(
                "logs/CGSim.log", true));

        // Equivalent to your spdlog setup (pattern fixed in this simple impl)
        logger_instance->set_level(minilog::level::debug);
        logger_instance->set_flush_level(minilog::level::debug);
    }

    // Returns a reference to the global logger instance.
    inline std::shared_ptr<minilog::logger>& getLogger() {
        return logger_instance;
    }
}

#define CG_SIM_LOG_TRACE(fmt, ...)    \
    CGSim::Utilities::logger::getLogger()->trace("[{}:{} {}] " fmt, \
    __FILE__, __LINE__, __FUNCTION__, ##__VA_ARGS__)

#define CG_SIM_LOG_DEBUG(fmt, ...)    \
    CGSim::Utilities::logger::getLogger()->debug("[{}:{} {}] " fmt, \
    __FILE__, __LINE__, __FUNCTION__, ##__VA_ARGS__)

#define CG_SIM_LOG_INFO(fmt, ...)     \
    CGSim::Utilities::logger::getLogger()->info(fmt, ##__VA_ARGS__)

#define CG_SIM_LOG_WARN(fmt, ...)     \
    CGSim::Utilities::logger::getLogger()->warn("[{}:{} {}] " fmt, \
    __FILE__, __LINE__, __FUNCTION__, ##__VA_ARGS__)

#define CG_SIM_LOG_ERROR(fmt, ...)    \
    CGSim::Utilities::logger::getLogger()->error("[{}:{} {}] " fmt, \
    __FILE__, __LINE__, __FUNCTION__, ##__VA_ARGS__)

#define CG_SIM_LOG_CRITICAL(fmt, ...) \
    CGSim::Utilities::logger::getLogger()->critical("[{}:{} {}] " fmt, \
    __FILE__, __LINE__, __FUNCTION__, ##__VA_ARGS__)
