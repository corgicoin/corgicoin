// Copyright (c) 2025 CorgiCoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_COMPAT_BOOST_H
#define BITCOIN_COMPAT_BOOST_H

#include <boost/version.hpp>

// Compatibility layer for modern Boost versions
// Boost 1.70+ changes some APIs and behavior

// Check Boost version at compile time
#if BOOST_VERSION < 105500
    #error "Boost version < 1.55.0 is too old - minimum 1.55.0 required"
#elif BOOST_VERSION < 107000
    #warning "Boost version < 1.70 detected - consider upgrading for C++11/14/17 support"
#endif

// Version-specific compatibility macros
#if BOOST_VERSION >= 107000
    #define BOOST_1_70_OR_LATER
#endif

#if BOOST_VERSION >= 108000
    #define BOOST_1_80_OR_LATER
#endif

// Print Boost version info
inline void PrintBoostVersion()
{
    printf("Boost version: %d.%d.%d\n",
           BOOST_VERSION / 100000,
           (BOOST_VERSION / 100) % 1000,
           BOOST_VERSION % 100);

#if BOOST_VERSION < 107000
    printf("INFO: Boost version is older than 1.70 - consider upgrading\n");
#endif
}

#endif // BITCOIN_COMPAT_BOOST_H
