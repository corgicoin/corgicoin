===============================================================================
⚠️  WARNING: OUTDATED DEPENDENCIES (2014-era Qt 4 DLLs)
===============================================================================

This release folder contains OUTDATED Windows DLLs from 2014:
- Qt 4.x DLLs (END-OF-LIFE since 2015 - 9+ years without security updates)
- MinGW GCC 4.x runtime (2013 - lacks modern security features)
- PThreads-Win32 (deprecated)

The CorgiCoin codebase has been modernized to support Qt 5 (v1.4.1.57),
but these distribution assets have NOT been updated yet.

⚠️  DO NOT USE THESE DLLs FOR PRODUCTION BUILDS!

See RELEASE_FOLDER_MODERNIZATION.md for:
- Complete list of required updates
- Step-by-step Qt 5 migration guide
- Security implications of outdated dependencies

===============================================================================

TROUBLESHOOTING (Historical - for Qt 4 builds only):

If you're getting "(Out of sync)" message, wait ~1-2 minutes, and the client should start syncing.
If you are still having trouble, copy corgicoin.conf to your user's roaming CorgiCoin directory and restart the client.

That directory is located @ (Windows 7) -- C:\Users\[YOUR_USER]\AppData\Roaming\CorgiCoin