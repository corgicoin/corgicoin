// Copyright (c) 2025 CorgiCoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_COMPAT_BOOST_H
#define BITCOIN_COMPAT_BOOST_H

#include <boost/version.hpp>

// Compatibility layer for modern Boost versions
// This codebase is compatible with Boost 1.55.0 through 1.80+

// Check Boost version at compile time
#if BOOST_VERSION < 105500
    #error "Boost version < 1.55.0 is too old - minimum 1.55.0 required"
#elif BOOST_VERSION < 107000
    #warning "Boost version < 1.70 detected - upgrade recommended for improved C++11/14/17 support"
    #warning "Boost 1.55.0-1.69 are supported but consider upgrading to 1.70+ for better performance"
#endif

// Version-specific compatibility macros
#if BOOST_VERSION >= 107000
    #define BOOST_1_70_OR_LATER
#endif

#if BOOST_VERSION >= 108000
    #define BOOST_1_80_OR_LATER
#endif

// Boost library usage in this codebase:
//
// ESSENTIAL (cannot be replaced without major refactoring):
// - boost::filesystem        - File operations (C++17 has std::filesystem but we target C++11/14)
// - boost::asio             - Async I/O for RPC server
// - boost::interprocess     - Inter-process communication
// - boost::program_options  - Command-line argument parsing
// - boost::signals2         - Observer pattern (keystore)
//
// SERIALIZATION (must maintain binary compatibility):
// - boost::tuple            - Used in serialization code
// - boost::variant          - Used in transaction destination types
//
// THIRD-PARTY (json_spirit library):
// - boost::bind             - JSON parser callbacks
// - boost::function         - JSON parser callbacks
// - boost::spirit           - JSON parser framework
//
// REMOVED (replaced with C++11 standard library):
// ✅ boost::thread          → std::thread (v1.4.1.48)
// ✅ boost::mutex           → std::mutex (v1.4.1.48)
// ✅ boost::shared_ptr      → std::shared_ptr (v1.4.1.45, v1.4.1.50)
// ✅ boost::array           → std::array (v1.4.1.47)
// ✅ boost::bind (most)     → C++11 lambdas (v1.4.1.49)
// ✅ boost::foreach         → Range-based for loops (v1.4.1.x)

// Print Boost version info
inline void PrintBoostVersion()
{
    printf("Boost version: %d.%d.%d\n",
           BOOST_VERSION / 100000,
           (BOOST_VERSION / 100) % 1000,
           BOOST_VERSION % 100);

#if BOOST_VERSION >= 107000
    printf("INFO: Using modern Boost %d.%d+ with excellent C++11/14 support\n",
           BOOST_VERSION / 100000,
           (BOOST_VERSION / 100) % 1000);
#else
    printf("INFO: Using Boost %d.%d (upgrade to 1.70+ recommended)\n",
           BOOST_VERSION / 100000,
           (BOOST_VERSION / 100) % 1000);
#endif
}

#endif // BITCOIN_COMPAT_BOOST_H
