// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "logging.h"
#include "util.h"

#include <cstdio>
#include <cstdarg>
#include <string>

// Global logging state
LogLevel nLogLevel = LogLevel::INFO;
uint32_t nLogCategories = LOG_NONE;

int LogPrintf(const char* fmt, ...)
{
    va_list arg_ptr;
    va_start(arg_ptr, fmt);
    std::string str = vstrprintf(fmt, arg_ptr);
    va_end(arg_ptr);
    return LogPrintStr(str);
}

int LogPrintStr(const std::string& str)
{
    // Delegate to the existing OutputDebugStringF infrastructure
    // which handles debug.log, console output, timestamps, etc.
    return OutputDebugStringF("%s", str.c_str());
}

bool LogError(const char* fmt, ...)
{
    va_list arg_ptr;
    va_start(arg_ptr, fmt);
    std::string str = vstrprintf(fmt, arg_ptr);
    va_end(arg_ptr);
    LogPrintStr("ERROR: " + str + "\n");
    return false;
}

static const struct { const char* pszName; uint32_t nFlag; } LOG_CATEGORY_NAMES[] = {
    {"net", LOG_NET}, {"mempool", LOG_MEMPOOL}, {"rpc", LOG_RPC}, {"db", LOG_DB}, {"wallet", LOG_WALLET},
    {"mining", LOG_MINING}, {"addrman", LOG_ADDRMAN}, {"selectcoins", LOG_SELECTCOINS},
};

std::vector<std::pair<std::string, bool> > GetLogCategories()
{
    std::vector<std::pair<std::string, bool> > v;
    const uint32_t nNow = __atomic_load_n(&nLogCategories, __ATOMIC_RELAXED);
    for (const auto& c : LOG_CATEGORY_NAMES)
        v.emplace_back(c.pszName, (nNow & c.nFlag) != 0);
    return v;
}

bool SetLogCategory(const std::string& strName, bool fOn)
{
    for (const auto& c : LOG_CATEGORY_NAMES)
    {
        if (strName != c.pszName)
            continue;
        uint32_t nNew = __atomic_load_n(&nLogCategories, __ATOMIC_RELAXED);
        nNew = fOn ? (nNew | c.nFlag) : (nNew & ~c.nFlag);
        if (c.nFlag == LOG_NET)
            fDebugNet = fOn;
        if (nNew != LOG_NONE)
            nLogLevel = LogLevel::DEBUG;
        __atomic_store_n(&nLogCategories, nNew, __ATOMIC_RELAXED);
        fDebug = (nNew != LOG_NONE);
        return true;
    }
    return false;
}

void InitLogging(const std::string& debugCategories, bool printToConsole, bool logTimestamps)
{
    fPrintToConsole = printToConsole;
    fLogTimestamps = logTimestamps;

    if (debugCategories.empty() || debugCategories == "0") {
        nLogLevel = LogLevel::INFO;
        nLogCategories = LOG_NONE;
        return;
    }

    if (debugCategories == "1" || debugCategories == "all") {
        nLogLevel = LogLevel::DEBUG;
        nLogCategories = LOG_ALL;
        fDebug = true;
        fDebugNet = true;
        return;
    }

    // Parse comma-separated categories
    nLogLevel = LogLevel::DEBUG;
    std::string cats = debugCategories;
    while (!cats.empty()) {
        std::string cat;
        auto pos = cats.find(',');
        if (pos != std::string::npos) {
            cat = cats.substr(0, pos);
            cats = cats.substr(pos + 1);
        } else {
            cat = cats;
            cats.clear();
        }

        if (cat == "net")          { nLogCategories |= LOG_NET; fDebugNet = true; }
        else if (cat == "mempool") nLogCategories |= LOG_MEMPOOL;
        else if (cat == "rpc")     nLogCategories |= LOG_RPC;
        else if (cat == "db")      nLogCategories |= LOG_DB;
        else if (cat == "wallet")  nLogCategories |= LOG_WALLET;
        else if (cat == "mining")  nLogCategories |= LOG_MINING;
        else if (cat == "addrman") nLogCategories |= LOG_ADDRMAN;
        else if (cat == "selectcoins") nLogCategories |= LOG_SELECTCOINS;
    }

    fDebug = (nLogCategories != LOG_NONE);
}
