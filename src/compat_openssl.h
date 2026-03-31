// Copyright (c) 2025 CorgiCoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_COMPAT_OPENSSL_H
#define BITCOIN_COMPAT_OPENSSL_H

#include <openssl/opensslv.h>

#include "logging.h"

// Compatibility layer for OpenSSL 3.x
// OpenSSL 3.0+ deprecated many functions used in older crypto code

// Check OpenSSL version at compile time
#if OPENSSL_VERSION_NUMBER < 0x10100000L
    #error "OpenSSL 1.0.x is no longer supported. Please upgrade to OpenSSL 1.1.0+ or 3.0+"
#elif OPENSSL_VERSION_NUMBER < 0x30000000L
    // OpenSSL 1.1.x — functional but consider upgrading to 3.0+
#endif

// Version-specific compatibility macros
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
    #define OPENSSL_3_0_OR_LATER
    #define OPENSSL_1_1_OR_LATER
#elif OPENSSL_VERSION_NUMBER >= 0x10100000L
    #define OPENSSL_1_1_OR_LATER
#endif

// Print OpenSSL version info
inline void PrintOpenSSLVersion()
{
#ifdef OPENSSL_VERSION_TEXT
    LogPrintf("OpenSSL version: %s\n", OPENSSL_VERSION_TEXT);
#else
    LogPrintf("OpenSSL version: %08x\n", OPENSSL_VERSION_NUMBER);
#endif
}

#endif // BITCOIN_COMPAT_OPENSSL_H
