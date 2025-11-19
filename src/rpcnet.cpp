// Copyright (c) 2009-2012 Bitcoin Developers
// Copyright (c) 2011-2012 Litecoin Developers
// Copyright (c) 2013 Dogecoin Developers
// Copyright (c) 2014 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "net.h"
#include "bitcoinrpc.h"

using namespace json_spirit;
using namespace std;

Value getconnectioncount(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 0)
        throw runtime_error(
            "getconnectioncount\n"
            "Returns the number of connections to other nodes.");

    LOCK(cs_vNodes);
    return (int)vNodes.size();
}

static void CopyNodeStats(std::vector<CNodeStats>& vstats)
{
    vstats.clear();

    LOCK(cs_vNodes);
    vstats.reserve(vNodes.size());
    for (CNode* pnode : vNodes) {
        CNodeStats stats;
        pnode->copyStats(stats);
        vstats.push_back(stats);
    }
}

Value getpeerinfo(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 0)
        throw runtime_error(
            "getpeerinfo\n"
            "Returns data about each connected network node.");

    vector<CNodeStats> vstats;
    CopyNodeStats(vstats);

    Array ret;

    for (const CNodeStats& stats : vstats) {
        Object obj;

        obj.emplace_back("addr", stats.addrName);
        obj.emplace_back("services", strprintf("%08"PRI64x, stats.nServices));
        obj.emplace_back("lastsend", (boost::int64_t)stats.nLastSend);
        obj.emplace_back("lastrecv", (boost::int64_t)stats.nLastRecv);
        obj.emplace_back("conntime", (boost::int64_t)stats.nTimeConnected);
        obj.emplace_back("version", stats.nVersion);
        obj.emplace_back("subver", stats.strSubVer);
        obj.emplace_back("inbound", stats.fInbound);
        obj.emplace_back("releasetime", (boost::int64_t)stats.nReleaseTime);
        obj.emplace_back("startingheight", stats.nStartingHeight);
        obj.emplace_back("banscore", stats.nMisbehavior);

        ret.push_back(obj);
    }
    
    return ret;
}

