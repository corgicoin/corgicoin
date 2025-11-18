// Copyright (c) 2025 CorgiCoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_COMPAT_OPENSSL_H
#define BITCOIN_COMPAT_OPENSSL_H

#include <openssl/opensslv.h>

// Compatibility layer for OpenSSL 3.x
// OpenSSL 3.0+ deprecated many functions used in older crypto code

// Check OpenSSL version at compile time
#if OPENSSL_VERSION_NUMBER < 0x10100000L
    #warning "OpenSSL version < 1.1.0 detected - CRITICAL SECURITY VULNERABILITY"
    #warning "OpenSSL 1.0.x is end-of-life and contains known security issues"
    #warning "Please upgrade to OpenSSL 3.0 or later immediately"
#elif OPENSSL_VERSION_NUMBER < 0x30000000L
    #warning "OpenSSL version < 3.0 detected - please consider upgrading"
    #warning "OpenSSL 1.1.x will reach end-of-life soon"
#endif

// Version-specific compatibility macros
#if OPENSSL_VERSION_NUMBER >= 0x30000000L
    // OpenSSL 3.0+ specific compatibility
    #define OPENSSL_3_0_OR_LATER
#elif OPENSSL_VERSION_NUMBER >= 0x10100000L
    // OpenSSL 1.1.x specific compatibility
    #define OPENSSL_1_1_OR_LATER
#else
    // OpenSSL 1.0.x (legacy, insecure)
    #define OPENSSL_1_0_LEGACY
#endif

// Helper macros for version-dependent code
#ifdef OPENSSL_3_0_OR_LATER
    // Use OpenSSL 3.x API
    #define USE_OPENSSL_3_API
#endif

// Print OpenSSL version info
inline void PrintOpenSSLVersion()
{
#ifdef OPENSSL_VERSION_TEXT
    printf("OpenSSL version: %s\n", OPENSSL_VERSION_TEXT);
#else
    printf("OpenSSL version: %08x\n", OPENSSL_VERSION_NUMBER);
#endif

#ifdef OPENSSL_1_0_LEGACY
    printf("WARNING: OpenSSL 1.0.x detected - CRITICAL SECURITY RISK\n");
    printf("WARNING: This version contains Heartbleed and other vulnerabilities\n");
    printf("WARNING: Upgrade to OpenSSL 3.0+ immediately\n");
#endif
}

#endif // BITCOIN_COMPAT_OPENSSL_H
