// Copyright (c) 2009-2012 Bitcoin Developers
// Copyright (c) 2011-2012 Litecoin Developers
// Copyright (c) 2013 Dogecoin Developers
// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "net.h"
#include "corgicoinrpc.h"

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

// Error codes match upstream Bitcoin Core so existing tooling recognizes them.
static const int RPC_MISC_ERROR                 = -1;
static const int RPC_INVALID_PARAMETER          = -8;
static const int RPC_CLIENT_NODE_ALREADY_ADDED  = -23;
static const int RPC_CLIENT_NODE_NOT_ADDED      = -24;
static const int RPC_CLIENT_NODE_NOT_CONNECTED  = -29;
static const int RPC_CLIENT_INVALID_IP          = -30;

Value getpeerinfo(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 0)
        throw runtime_error(
            "getpeerinfo\n"
            "Returns data about each connected network node.\n"
            "Times are seconds; pingtime/minping are omitted until the first\n"
            "pong arrives, pingwait is present while a ping is outstanding.");

    vector<CNodeStats> vstats;
    CopyNodeStats(vstats);

    Array ret;

    for (const CNodeStats& stats : vstats) {
        Object obj;

        obj.emplace_back("addr", stats.addrName);
        if (!stats.addrLocal.empty())
            obj.emplace_back("addrlocal", stats.addrLocal);
        obj.emplace_back("services", strprintf("%08" PRI64x, stats.nServices));
        obj.emplace_back("lastsend", (int64_t)stats.nLastSend);
        obj.emplace_back("lastrecv", (int64_t)stats.nLastRecv);
        obj.emplace_back("bytessent", (int64_t)stats.nSendBytes);
        obj.emplace_back("bytesrecv", (int64_t)stats.nRecvBytes);
        obj.emplace_back("conntime", (int64_t)stats.nTimeConnected);
        if (stats.dPingTime > 0.0)
            obj.emplace_back("pingtime", stats.dPingTime);
        if (stats.dMinPing > 0.0)
            obj.emplace_back("minping", stats.dMinPing);
        if (stats.dPingWait > 0.0)
            obj.emplace_back("pingwait", stats.dPingWait);
        obj.emplace_back("version", stats.nVersion);
        obj.emplace_back("subver", stats.strSubVer);
        obj.emplace_back("inbound", stats.fInbound);
        obj.emplace_back("releasetime", (int64_t)stats.nReleaseTime);
        obj.emplace_back("startingheight", stats.nStartingHeight);
        obj.emplace_back("banscore", stats.nMisbehavior);

        ret.push_back(obj);
    }

    return ret;
}

Value ping(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 0)
        throw runtime_error(
            "ping\n"
            "Requests that a ping be sent to all peers, to measure ping time.\n"
            "Results appear in getpeerinfo's pingtime/minping/pingwait fields.\n"
            "Pre-BIP31 peers (protocol <= 60000) are not pinged.");

    LOCK(cs_vNodes);
    for (CNode* pnode : vNodes)
        pnode->fPingQueued = true;
    return Value::null;
}

Value getnettotals(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 0)
        throw runtime_error(
            "getnettotals\n"
            "Returns network traffic totals since startup:\n"
            "{ \"totalbytesrecv\", \"totalbytessent\", \"timemillis\" }");

    Object obj;
    obj.emplace_back("totalbytesrecv", (int64_t)GetTotalBytesRecv());
    obj.emplace_back("totalbytessent", (int64_t)GetTotalBytesSent());
    obj.emplace_back("timemillis", (int64_t)GetTimeMillis());
    return obj;
}

// Parse an IP for the ban RPCs. Numeric only: bans are keyed by address,
// and resolving a hostname here would ban whatever DNS said at that moment.
static CNetAddr ParseBanAddress(const string& strIp)
{
    vector<CNetAddr> vIP;
    if (!LookupHostNumeric(strIp.c_str(), vIP, 1) || vIP.empty() || !vIP[0].IsValid())
        throw JSONRPCError(RPC_CLIENT_INVALID_IP, "Error: Invalid IP address: " + strIp);
    return vIP[0];
}

Value setban(const Array& params, bool fHelp)
{
    string strCommand;
    if (params.size() >= 2)
        strCommand = params[1].get_str();
    if (fHelp || params.size() < 2 || params.size() > 4 ||
        (strCommand != "add" && strCommand != "remove"))
        throw runtime_error(
            "setban <ip> <add|remove> [bantime] [absolute]\n"
            "Add or remove an IP from the ban list.\n"
            "bantime: seconds to ban for (default: -bantime, 86400); with\n"
            "absolute=true it is a unix timestamp to ban until instead.\n"
            "Adding a ban disconnects any current connections from that IP.");

    CNetAddr ip = ParseBanAddress(params[0].get_str());

    if (strCommand == "remove") {
        if (!CNode::Unban(ip))
            throw JSONRPCError(RPC_MISC_ERROR, "Error: IP was not banned");
        DumpBanlist();
        return Value::null;
    }

    if (CNode::IsBanned(ip))
        throw JSONRPCError(RPC_CLIENT_NODE_ALREADY_ADDED, "Error: IP already banned");

    int64 nBanTime = GetArg("-bantime", 60*60*24);
    if (params.size() >= 3) {
        int64 n = params[2].get_int64();
        if (n > 0)
            nBanTime = n;
    }
    bool fAbsolute = params.size() >= 4 && params[3].get_bool();
    int64 nBanUntil = fAbsolute ? nBanTime : GetTime() + nBanTime;
    if (nBanUntil <= GetTime())
        throw JSONRPCError(RPC_INVALID_PARAMETER, "Error: absolute bantime is in the past");

    CNode::Ban(ip, nBanUntil, true);
    DumpBanlist(); // persist manual bans right away, not on the next periodic dump

    {
        LOCK(cs_vNodes);
        for (CNode* pnode : vNodes)
            if ((CNetAddr)pnode->addr == ip)
                pnode->fDisconnect = true;
    }
    return Value::null;
}

Value listbanned(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 0)
        throw runtime_error(
            "listbanned\n"
            "List all banned IPs with the unix time each ban expires.");

    map<CNetAddr, int64> banMap;
    CNode::GetBanned(banMap);

    Array ret;
    for (const auto& entry : banMap) {
        Object obj;
        obj.emplace_back("address", entry.first.ToString());
        obj.emplace_back("banned_until", (int64_t)entry.second);
        ret.push_back(obj);
    }
    return ret;
}

Value clearbanned(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 0)
        throw runtime_error(
            "clearbanned\n"
            "Clear all banned IPs.");

    CNode::ClearBanned();
    DumpBanlist();
    return Value::null;
}

Value addnode(const Array& params, bool fHelp)
{
    string strCommand;
    if (params.size() == 2)
        strCommand = params[1].get_str();
    if (fHelp || params.size() != 2 ||
        (strCommand != "onetry" && strCommand != "add" && strCommand != "remove"))
        throw runtime_error(
            "addnode <node> <add|remove|onetry>\n"
            "Attempts to add or remove a node from the addnode list,\n"
            "or try a connection to a node once.\n"
            "Nodes on the list are reconnected every 2 minutes if dropped.");

    string strNode = params[0].get_str();

    if (strCommand == "onetry") {
        CAddress addr;
        OpenNetworkConnection(addr, nullptr, strNode.c_str());
        return Value::null;
    }

    LOCK(cs_vAddedNodes);
    auto it = std::find(vAddedNodes.begin(), vAddedNodes.end(), strNode);
    if (strCommand == "add") {
        if (it != vAddedNodes.end())
            throw JSONRPCError(RPC_CLIENT_NODE_ALREADY_ADDED, "Error: Node already added");
        vAddedNodes.push_back(strNode);
    } else {
        if (it == vAddedNodes.end())
            throw JSONRPCError(RPC_CLIENT_NODE_NOT_ADDED, "Error: Node has not been added.");
        vAddedNodes.erase(it);
    }
    return Value::null;
}

Value getaddednodeinfo(const Array& params, bool fHelp)
{
    if (fHelp || params.size() > 1)
        throw runtime_error(
            "getaddednodeinfo [node]\n"
            "Returns information about added nodes (-addnode or the addnode RPC):\n"
            "whether each is connected, and if so the peer address and direction.");

    vector<string> vInfo;
    {
        LOCK(cs_vAddedNodes);
        vInfo = vAddedNodes;
    }
    if (params.size() == 1) {
        string strNode = params[0].get_str();
        if (std::find(vInfo.begin(), vInfo.end(), strNode) == vInfo.end())
            throw JSONRPCError(RPC_CLIENT_NODE_NOT_ADDED, "Error: Node has not been added.");
        vInfo.assign(1, strNode);
    }

    Array ret;
    for (const string& strNode : vInfo) {
        Object obj;
        obj.emplace_back("addednode", strNode);

        // Match a peer either by the name we dialed or by any resolved IP.
        vector<CService> vserv;
        Lookup(strNode.c_str(), vserv, GetDefaultPort(), false, 0);

        Array addresses;
        {
            LOCK(cs_vNodes);
            for (CNode* pnode : vNodes) {
                bool fMatch = pnode->addrName == strNode;
                for (const CService& serv : vserv)
                    if (pnode->addr == serv)
                        fMatch = true;
                if (!fMatch)
                    continue;
                Object addr;
                addr.emplace_back("address", pnode->addr.ToStringIPPort());
                addr.emplace_back("connected", pnode->fInbound ? "inbound" : "outbound");
                addresses.push_back(addr);
            }
        }
        obj.emplace_back("connected", !addresses.empty());
        obj.emplace_back("addresses", addresses);
        ret.push_back(obj);
    }
    return ret;
}

Value disconnectnode(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 1)
        throw runtime_error(
            "disconnectnode <address>\n"
            "Immediately disconnects from the peer with the given address\n"
            "(as shown in getpeerinfo's \"addr\" field).");

    string strNode = params[0].get_str();
    LOCK(cs_vNodes);
    for (CNode* pnode : vNodes) {
        if (pnode->addrName == strNode || pnode->addr.ToStringIPPort() == strNode) {
            pnode->fDisconnect = true;
            return Value::null;
        }
    }
    throw JSONRPCError(RPC_CLIENT_NODE_NOT_CONNECTED, "Node not found in connected nodes");
}
