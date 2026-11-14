// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef CORGICOIN_LOGGING_H
#define CORGICOIN_LOGGING_H

#include <string>
#include <cstdarg>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

// Log levels
enum class LogLevel {
    NONE,
    ERR,      // "ERROR" is a macro on Windows
    WARNING,
    INFO,
    DEBUG
};

// Log categories (bit flags for fine-grained control)
enum LogCategory : uint32_t {
    LOG_NONE        = 0,
    LOG_NET         = (1 << 0),
    LOG_MEMPOOL     = (1 << 1),
    LOG_RPC         = (1 << 2),
    LOG_DB          = (1 << 3),
    LOG_WALLET      = (1 << 4),
    LOG_MINING      = (1 << 5),
    LOG_ADDRMAN     = (1 << 6),
    LOG_SELECTCOINS = (1 << 7),
    LOG_ALL         = 0xFFFFFFFF
};

// Global logging state
extern LogLevel nLogLevel;
extern uint32_t nLogCategories;

// Tell the compiler these take a printf format, so that -Wformat checks every call: a wrong specifier in a log line that
// is rarely run is a crash or a memory disclosure waiting for the day it is.
#if defined(__GNUC__) || defined(__clang__)
#define CORGI_PRINTF(fmt, args) __attribute__((format(printf, fmt, args)))
#else
#define CORGI_PRINTF(fmt, args)
#endif

// Core logging function (replaces OutputDebugStringF)
int LogPrintStr(const std::string& str);

// Formatted logging — always logs (for important messages)
int LogPrintf(const char* fmt, ...) CORGI_PRINTF(1, 2);

// Formatted error logging — prefixes with "ERROR: "
bool LogError(const char* fmt, ...) CORGI_PRINTF(1, 2);

// Category-gated logging — only logs if category is enabled
// Usage: LogPrint(LOG_NET, "connected to %s\n", addr.c_str());
#define LogPrint(category, ...) do { \
    if (nLogCategories & (category)) LogPrintf(__VA_ARGS__); \
} while(0)

// Debug-level logging — only logs if debug is enabled
#define LogDebug(...) do { \
    if (nLogLevel >= LogLevel::DEBUG) LogPrintf(__VA_ARGS__); \
} while(0)

// The categories a running node can switch (the `logging` RPC): name and whether it is on
std::vector<std::pair<std::string, bool> > GetLogCategories();
// Switch one on or off by name; false if the name is not a category
bool SetLogCategory(const std::string& strName, bool fOn);

// Helper to set log categories from command-line string
void InitLogging(const std::string& debugCategories, bool printToConsole, bool logTimestamps);

#endif // CORGICOIN_LOGGING_H
