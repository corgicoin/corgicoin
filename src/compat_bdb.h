// Copyright (c) 2025 CorgiCoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_COMPAT_BDB_H
#define BITCOIN_COMPAT_BDB_H

#include <db_cxx.h>

// Compatibility layer for Berkeley DB versions
// This codebase is compatible with Berkeley DB 4.8+ through 6.2+
//
// Berkeley DB version history:
// - 4.8.x (2009): Stable, widely used
// - 5.0.x (2010): License change to AGPL (problematic for many projects)
// - 5.1.x (2011): Bug fixes
// - 5.3.x (2012): Current recommended version for Bitcoin-based projects
// - 6.0.x (2013): Major version, API compatible with 5.x
// - 6.1.x (2015): Updates
// - 6.2.x (2016): Latest stable, API compatible

// Check Berkeley DB version at compile time
#if DB_VERSION_MAJOR < 4 || (DB_VERSION_MAJOR == 4 && DB_VERSION_MINOR < 8)
    #error "Berkeley DB version < 4.8 is too old - minimum 4.8.x required"
#elif DB_VERSION_MAJOR == 5 && DB_VERSION_MINOR == 0
    #warning "Berkeley DB 5.0.x uses AGPL license - consider using 4.8.x, 5.1+, or 6.x"
#endif

// Version detection for compatibility
#if DB_VERSION_MAJOR >= 6
    #define BDB_6_OR_LATER
#elif DB_VERSION_MAJOR == 5
    #define BDB_5_X
    #if DB_VERSION_MINOR >= 3
        #define BDB_5_3_OR_LATER
    #endif
#elif DB_VERSION_MAJOR == 4
    #define BDB_4_X
#endif

// Berkeley DB API used in this codebase:
//
// CORE OPERATIONS:
// - DbEnv: Database environment management
// - Db: Database file operations
// - DbTxn: Transaction management
// - Dbc: Database cursor operations
// - DbException: Exception handling
//
// ENVIRONMENT OPERATIONS (all stable across versions):
// - set_lg_dir(), set_cachesize(), set_lg_bsize(), set_lg_max()
// - set_lk_max_locks(), set_lk_max_objects()
// - set_errfile(), set_flags()
// - log_set_config()
// - open(), close()
// - txn_begin(), txn_checkpoint()
// - lsn_reset()
//
// DATABASE OPERATIONS (all stable across versions):
// - open(), close()
// - get(), put(), del()
// - cursor()
//
// COMPATIBILITY NOTES:
// - The C++ API (db_cxx.h) has been very stable across BDB versions
// - No breaking changes between 4.8 and 6.2 for the APIs we use
// - Main compatibility concern is wallet file format:
//   * BDB 4.8 and 5.x can read each other's files
//   * BDB 6.x can read 4.8/5.x files but should be tested
//   * Always backup wallet before upgrading BDB version!
//
// WALLET COMPATIBILITY:
// - Critical: Wallet files MUST remain compatible across versions
// - Recommendation: Test with backup wallet before production use
// - Berkeley DB uses forward-compatible file formats
// - Downgrading BDB version after upgrade may not be safe

// Print Berkeley DB version info
inline void PrintBerkeleyDBVersion()
{
    printf("Berkeley DB version: %d.%d.%d\n",
           DB_VERSION_MAJOR,
           DB_VERSION_MINOR,
           DB_VERSION_PATCH);

#if DB_VERSION_MAJOR >= 6
    printf("INFO: Using Berkeley DB 6.x - latest stable API\n");
#elif DB_VERSION_MAJOR == 5 && DB_VERSION_MINOR >= 3
    printf("INFO: Using Berkeley DB 5.3+ - recommended version\n");
#elif DB_VERSION_MAJOR == 5 && DB_VERSION_MINOR == 0
    printf("WARNING: Berkeley DB 5.0.x uses AGPL license!\n");
    printf("WARNING: Consider using 4.8.x, 5.1+, or 6.x for licensing compatibility\n");
#elif DB_VERSION_MAJOR == 4 && DB_VERSION_MINOR >= 8
    printf("INFO: Using Berkeley DB 4.8+ - stable and widely used\n");
#else
    printf("WARNING: Using older Berkeley DB version - upgrade recommended\n");
#endif

    printf("INFO: Wallet files should be backed up before any BDB version change\n");
}

// Wallet compatibility check
inline void WarnWalletCompatibility()
{
#if DB_VERSION_MAJOR >= 6
    printf("IMPORTANT: Using Berkeley DB 6.x\n");
    printf("  - Can read wallet files from BDB 4.8/5.x\n");
    printf("  - Wallet files may not be readable by older BDB versions after modification\n");
    printf("  - ALWAYS backup your wallet before upgrading Berkeley DB!\n");
#elif DB_VERSION_MAJOR == 5
    printf("INFO: Using Berkeley DB 5.x - compatible with 4.8.x wallet files\n");
#endif
}

#endif // BITCOIN_COMPAT_BDB_H
