// Copyright (c) 2010 Satoshi Nakamoto
// Copyright (c) 2009-2012 The Bitcoin developers
// Copyright (c) 2011-2012 Litecoin Developers
// Copyright (c) 2013 Dogecoin Developers
// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "ui_interface.h"
#include "init.h"
#include "corgicoinrpc.h"

#include <string>

static int noui_ThreadSafeMessageBox(const std::string& message, const std::string& caption, int style)
{
    // also in debug.log: what a daemon has to say when it cannot start (a port it could not bind, an option it refuses) went only to
    // stdout and stderr, which a service manager or a test run may not keep, and the log said the node had simply shut down
    LogPrintf("%s: %s\n", caption.c_str(), message.c_str());
    if (!fPrintToConsole)       // (with -printtoconsole the log line above is already on stdout)
        printf("%s: %s\n", caption.c_str(), message.c_str());
    fprintf(stderr, "%s: %s\n", caption.c_str(), message.c_str());
    return 4;
}

static bool noui_ThreadSafeAskFee(int64 nFeeRequired, const std::string& strCaption)
{
    return true;
}

void noui_connect()
{
    // Connect bitcoind signal handlers
    uiInterface.ThreadSafeMessageBox.connect(noui_ThreadSafeMessageBox);
    uiInterface.ThreadSafeAskFee.connect(noui_ThreadSafeAskFee);
}
