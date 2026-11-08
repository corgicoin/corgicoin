// Copyright (c) 2010 Satoshi Nakamoto
// Copyright (c) 2009-2012 The Bitcoin developers
// Copyright (c) 2013 Dogecoin Developers
// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "base58.h"
#include "corgicoinrpc.h"
#include "db.h"
#include "init.h"
#include "main.h"
#include "net.h"
#include "wallet.h"

using namespace std;
using namespace boost;
using namespace json_spirit;

// These are all in corgicoinrpc.cpp:
extern Object JSONRPCError(int code, const string& message);
extern int64 AmountFromValue(const Value& value);
extern Value ValueFromAmount(int64 amount);
extern std::string HelpRequiringPassphrase();
extern void EnsureWalletIsUnlocked();

void
ScriptPubKeyToJSON(const CScript& scriptPubKey, Object& out)
{
    txnouttype type;
    vector<CTxDestination> addresses;
    int nRequired;

    out.emplace_back("asm", scriptPubKey.ToString());
    out.emplace_back("hex", HexStr(scriptPubKey.begin(), scriptPubKey.end()));

    if (!ExtractDestinations(scriptPubKey, type, addresses, nRequired))
    {
        out.emplace_back("type", GetTxnOutputType(TX_NONSTANDARD));
        return;
    }

    out.emplace_back("reqSigs", nRequired);
    out.emplace_back("type", GetTxnOutputType(type));

    Array a;
    for (const CTxDestination& addr : addresses)
        a.push_back(CBitcoinAddress(addr).ToString());
    out.emplace_back("addresses", a);
}

void
TxToJSON(const CTransaction& tx, const uint256 hashBlock, Object& entry)
{
    entry.emplace_back("txid", tx.GetHash().GetHex());
    entry.emplace_back("version", tx.nVersion);
    entry.emplace_back("locktime", (int64_t)tx.nLockTime);
    Array vin;
    for (const CTxIn& txin : tx.vin)
    {
        Object in;
        if (tx.IsCoinBase())
            in.emplace_back("coinbase", HexStr(txin.scriptSig.begin(), txin.scriptSig.end()));
        else
        {
            in.emplace_back("txid", txin.prevout.hash.GetHex());
            in.emplace_back("vout", (int64_t)txin.prevout.n);
            Object o;
            o.emplace_back("asm", txin.scriptSig.ToString());
            o.emplace_back("hex", HexStr(txin.scriptSig.begin(), txin.scriptSig.end()));
            in.emplace_back("scriptSig", o);
        }
        in.emplace_back("sequence", (int64_t)txin.nSequence);
        vin.push_back(in);
    }
    entry.emplace_back("vin", vin);
    Array vout;
    for (unsigned int i = 0; i < tx.vout.size(); i++)
    {
        const CTxOut& txout = tx.vout[i];
        Object out;
        out.emplace_back("value", ValueFromAmount(txout.nValue));
        out.emplace_back("n", (int64_t)i);
        Object o;
        ScriptPubKeyToJSON(txout.scriptPubKey, o);
        out.emplace_back("scriptPubKey", o);
        vout.push_back(out);
    }
    entry.emplace_back("vout", vout);

    if (hashBlock != 0)
    {
        entry.emplace_back("blockhash", hashBlock.GetHex());
        auto mi = mapBlockIndex.find(hashBlock);
        if (mi != mapBlockIndex.end() && (*mi).second)
        {
            CBlockIndex* pindex = (*mi).second;
            if (pindex->IsInMainChain())
            {
                entry.emplace_back("confirmations", 1 + nBestHeight - pindex->nHeight);
                entry.emplace_back("time", (int64_t)pindex->nTime);
            }
            else
                entry.emplace_back("confirmations", 0);
        }
    }
}

Value getrawtransaction(const Array& params, bool fHelp)
{
    if (fHelp || params.size() < 1 || params.size() > 2)
        throw runtime_error(
            "getrawtransaction <txid> [verbose=0]\n"
            "If verbose=0, returns a string that is\n"
            "serialized, hex-encoded data for <txid>.\n"
            "If verbose is non-zero, returns an Object\n"
            "with information about <txid>.");

    uint256 hash;
    hash.SetHex(params[0].get_str());

    bool fVerbose = false;
    if (params.size() > 1)
        fVerbose = (params[1].get_int() != 0);

    CTransaction tx;
    uint256 hashBlock = 0;
    if (!GetTransaction(hash, tx, hashBlock))
        throw JSONRPCError(-5, "No information available about transaction");

    CDataStream ssTx(SER_NETWORK, PROTOCOL_VERSION);
    ssTx << tx;
    string strHex = HexStr(ssTx.begin(), ssTx.end());

    if (!fVerbose)
        return strHex;

    Object result;
    result.emplace_back("hex", strHex);
    TxToJSON(tx, hashBlock, result);
    return result;
}

Value gettxout(const Array& params, bool fHelp)
{
    if (fHelp || params.size() < 2 || params.size() > 3)
        throw runtime_error(
            "gettxout <txid> <n> [includemempool=true]\n"
            "Returns details about an unspent transaction output, or null if the output does not exist\n"
            "or has been spent. With includemempool (the default) an output spent by a transaction in the\n"
            "memory pool counts as spent, and outputs of unconfirmed transactions are found.\n"
            "Result: {bestblock, confirmations, value, scriptPubKey, version, coinbase}");

    RPCTypeCheck(params, {str_type, int_type, bool_type});

    uint256 hash;
    hash.SetHex(params[0].get_str());
    const int n = params[1].get_int();
    const bool fIncludeMempool = params.size() > 2 ? params[2].get_bool() : true;
    if (n < 0)
        throw JSONRPCError(-8, "Invalid parameter, vout must be positive");

    CTransaction tx;
    int nConfirmations = 0;
    {
        LOCK(mempool.cs);
        if (fIncludeMempool && mempool.exists(hash))
            tx = mempool.lookup(hash);
        else
            tx.SetNull();
    }
    if (tx.IsNull())
    {
        CTxDB txdb("r");
        CTxIndex txindex;
        if (!tx.ReadFromDisk(txdb, COutPoint(hash, 0), txindex))
            return Value::null;
        if (static_cast<unsigned int>(n) >= tx.vout.size() || static_cast<unsigned int>(n) >= txindex.vSpent.size())
            return Value::null;
        if (!txindex.vSpent[n].IsNull())
            return Value::null;                 // spent in the chain

        CBlock block;
        if (!block.ReadFromDisk(txindex.pos.nFile, txindex.pos.nBlockPos, false))
            return Value::null;
        auto mi = mapBlockIndex.find(block.GetHash());
        if (mi == mapBlockIndex.end() || !mi->second || !mi->second->IsInMainChain())
            return Value::null;
        nConfirmations = 1 + nBestHeight - mi->second->nHeight;
    }
    if (static_cast<unsigned int>(n) >= tx.vout.size())
        return Value::null;

    if (fIncludeMempool)
    {
        LOCK(mempool.cs);
        if (mempool.mapNextTx.count(COutPoint(hash, n)))
            return Value::null;                 // spent by a transaction waiting in the pool
    }

    Object ret;
    ret.emplace_back("bestblock", hashBestChain.GetHex());
    ret.emplace_back("confirmations", nConfirmations);
    ret.emplace_back("value", ValueFromAmount(tx.vout[n].nValue));
    Object o;
    ScriptPubKeyToJSON(tx.vout[n].scriptPubKey, o);
    ret.emplace_back("scriptPubKey", o);
    ret.emplace_back("version", tx.nVersion);
    ret.emplace_back("coinbase", tx.IsCoinBase());
    return ret;
}

Value listunspent(const Array& params, bool fHelp)
{
    if (fHelp || params.size() > 2)
        throw runtime_error(
            "listunspent [minconf=1] [maxconf=999999]\n"
            "Returns array of unspent transaction outputs\n"
            "with between minconf and maxconf (inclusive) confirmations.\n"
            "Results are an array of Objects, each of which has:\n"
            "{txid, vout, scriptPubKey, amount, confirmations}");

    RPCTypeCheck(params, {int_type, int_type});

    int nMinDepth = 1;
    if (params.size() > 0)
        nMinDepth = params[0].get_int();

    int nMaxDepth = 999999;
    if (params.size() > 1)
        nMaxDepth = params[1].get_int();

    Array results;
    vector<COutput> vecOutputs;
    pwalletMain->AvailableCoins(vecOutputs, false);
    for (const COutput& out : vecOutputs)
    {
        if (out.nDepth < nMinDepth || out.nDepth > nMaxDepth)
            continue;

        int64 nValue = out.tx->vout[out.i].nValue;
        const CScript& pk = out.tx->vout[out.i].scriptPubKey;
        Object entry;
        entry.emplace_back("txid", out.tx->GetHash().GetHex());
        entry.emplace_back("vout", out.i);
        entry.emplace_back("scriptPubKey", HexStr(pk.begin(), pk.end()));
        entry.emplace_back("amount",ValueFromAmount(nValue));
        entry.emplace_back("confirmations",out.nDepth);
        results.push_back(entry);
    }

    return results;
}

Value lockunspent(const Array& params, bool fHelp)
{
    if (fHelp || params.size() < 1 || params.size() > 2)
        throw runtime_error(
            "lockunspent <unlock> [[{\"txid\":txid,\"vout\":n},...]]\n"
            "Lock (unlock=false) or unlock (unlock=true) wallet outputs so coin\n"
            "selection won't spend them. With unlock=true and no list, unlocks\n"
            "everything. Locks are kept in memory only and cleared on restart.\n"
            "Locked outputs are left out of listunspent; see listlockunspent.");

    bool fUnlock = params[0].get_bool();

    if (params.size() == 1) {
        if (fUnlock)
            pwalletMain->UnlockAllCoins();
        return true;
    }

    const Array& outputs = params[1].get_array();
    vector<COutPoint> vOutpts;
    for (const Value& output : outputs) {
        if (output.type() != obj_type)
            throw JSONRPCError(-8, "Invalid parameter, expected object");
        const Object& o = output.get_obj();

        RPCTypeCheck(o, {{"txid", str_type}, {"vout", int_type}});

        string txid = find_value(o, "txid").get_str();
        if (!IsHex(txid) || txid.size() != 64)
            throw JSONRPCError(-8, "Invalid parameter, expected hex txid");
        int nOutput = find_value(o, "vout").get_int();
        if (nOutput < 0)
            throw JSONRPCError(-8, "Invalid parameter, vout must be positive");

        uint256 hash(txid);
        {
            LOCK(pwalletMain->cs_wallet);
            auto it = pwalletMain->mapWallet.find(hash);
            if (it == pwalletMain->mapWallet.end())
                throw JSONRPCError(-8, "Invalid parameter, unknown transaction");
            if ((unsigned int)nOutput >= it->second.vout.size())
                throw JSONRPCError(-8, "Invalid parameter, vout index out of bounds");
            if (it->second.IsSpent(nOutput))
                throw JSONRPCError(-8, "Invalid parameter, expected unspent output");
        }
        COutPoint outpt(hash, nOutput);
        bool fLocked = pwalletMain->IsLockedCoin(hash, nOutput);
        if (fUnlock && !fLocked)
            throw JSONRPCError(-8, "Invalid parameter, expected locked output");
        if (!fUnlock && fLocked)
            throw JSONRPCError(-8, "Invalid parameter, output already locked");
        vOutpts.push_back(outpt);
    }

    // Validate everything first so a bad entry leaves no partial change.
    for (const COutPoint& outpt : vOutpts) {
        if (fUnlock)
            pwalletMain->UnlockCoin(outpt);
        else
            pwalletMain->LockCoin(outpt);
    }
    return true;
}

Value listlockunspent(const Array& params, bool fHelp)
{
    if (fHelp || params.size() > 0)
        throw runtime_error(
            "listlockunspent\n"
            "Returns the wallet outputs locked with lockunspent, as\n"
            "[{\"txid\":txid,\"vout\":n},...]");

    vector<COutPoint> vOutpts;
    pwalletMain->ListLockedCoins(vOutpts);

    Array ret;
    for (const COutPoint& outpt : vOutpts) {
        Object o;
        o.emplace_back("txid", outpt.hash.GetHex());
        o.emplace_back("vout", (int)outpt.n);
        ret.push_back(o);
    }
    return ret;
}

Value createrawtransaction(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 2)
        throw runtime_error(
            "createrawtransaction [{\"txid\":txid,\"vout\":n},...] {address:amount,...}\n"
            "Create a transaction spending given inputs\n"
            "(array of objects containing transaction id and output number),\n"
            "sending to given address(es).\n"
            "Returns hex-encoded raw transaction.\n"
            "Note that the transaction's inputs are not signed, and\n"
            "it is not stored in the wallet or transmitted to the network.");

    RPCTypeCheck(params, {array_type, obj_type});

    Array inputs = params[0].get_array();
    Object sendTo = params[1].get_obj();

    CTransaction rawTx;

    for (Value& input : inputs)
    {
        const Object& o = input.get_obj();

        const Value& txid_v = find_value(o, "txid");
        if (txid_v.type() != str_type)
            throw JSONRPCError(-8, "Invalid parameter, missing txid key");
        string txid = txid_v.get_str();
        if (!IsHex(txid))
            throw JSONRPCError(-8, "Invalid parameter, expected hex txid");

        const Value& vout_v = find_value(o, "vout");
        if (vout_v.type() != int_type)
            throw JSONRPCError(-8, "Invalid parameter, missing vout key");
        int nOutput = vout_v.get_int();
        if (nOutput < 0)
            throw JSONRPCError(-8, "Invalid parameter, vout must be positive");

        CTxIn in(COutPoint(uint256(txid), nOutput));
        rawTx.vin.push_back(in);
    }

    set<CBitcoinAddress> setAddress;
    for (const Pair& s : sendTo)
    {
        CBitcoinAddress address(s.name_);
        if (!address.IsValid())
            throw JSONRPCError(-5, string("Invalid Bitcoin address:")+s.name_);

        if (setAddress.count(address))
            throw JSONRPCError(-8, string("Invalid parameter, duplicated address: ")+s.name_);
        setAddress.insert(address);

        CScript scriptPubKey;
        scriptPubKey.SetDestination(address.Get());
        int64 nAmount = AmountFromValue(s.value_);

        CTxOut out(nAmount, scriptPubKey);
        rawTx.vout.push_back(out);
    }

    CDataStream ss(SER_NETWORK, PROTOCOL_VERSION);
    ss << rawTx;
    return HexStr(ss.begin(), ss.end());
}

Value decoderawtransaction(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 1)
        throw runtime_error(
            "decoderawtransaction <hex string>\n"
            "Return a JSON object representing the serialized, hex-encoded transaction.");

    RPCTypeCheck(params, {str_type});

    vector<unsigned char> txData(ParseHex(params[0].get_str()));
    CDataStream ssData(txData, SER_NETWORK, PROTOCOL_VERSION);
    CTransaction tx;
    try {
        ssData >> tx;
    }
    catch (std::exception &e) {
        throw JSONRPCError(-22, "TX decode failed");
    }

    Object result;
    TxToJSON(tx, 0, result);

    return result;
}

Value signrawtransaction(const Array& params, bool fHelp)
{
    if (fHelp || params.size() < 1 || params.size() > 4)
        throw runtime_error(
            "signrawtransaction <hex string> [{\"txid\":txid,\"vout\":n,\"scriptPubKey\":hex},...] [<privatekey1>,...] [sighashtype=\"ALL\"]\n"
            "Sign inputs for raw transaction (serialized, hex-encoded).\n"
            "Second optional argument is an array of previous transaction outputs that\n"
            "this transaction depends on but may not yet be in the blockchain.\n"
            "Third optional argument is an array of base58-encoded private\n"
            "keys that, if given, will be the only keys used to sign the transaction.\n"
            "Fourth option is a string that is one of six values; ALL, NONE, SINGLE or\n"
            "ALL|ANYONECANPAY, NONE|ANYONECANPAY, SINGLE|ANYONECANPAY.\n"
            "Returns json object with keys:\n"
            "  hex : raw transaction with signature(s) (hex-encoded string)\n"
            "  complete : 1 if transaction has a complete set of signature (0 if not)"
            + HelpRequiringPassphrase());

    if (params.size() < 3)
        EnsureWalletIsUnlocked();

    RPCTypeCheck(params, {str_type, array_type, array_type});

    vector<unsigned char> txData(ParseHex(params[0].get_str()));
    CDataStream ssData(txData, SER_NETWORK, PROTOCOL_VERSION);
    vector<CTransaction> txVariants;
    while (!ssData.empty())
    {
        try {
            CTransaction tx;
            ssData >> tx;
            txVariants.push_back(tx);
        }
        catch (std::exception &e) {
            throw JSONRPCError(-22, "TX decode failed");
        }
    }

    if (txVariants.empty())
        throw JSONRPCError(-22, "Missing transaction");

    // mergedTx will end up with all the signatures; it
    // starts as a clone of the rawtx:
    CTransaction mergedTx(txVariants[0]);
    bool fComplete = true;

    // Fetch previous transactions (inputs):
    map<COutPoint, CScript> mapPrevOut;
    {
        MapPrevTx mapPrevTx;
        CTxDB txdb("r");
        map<uint256, CTxIndex> unused;
        bool fInvalid;
        mergedTx.FetchInputs(txdb, unused, false, false, mapPrevTx, fInvalid);

        // Copy results into mapPrevOut:
        for (const CTxIn& txin : mergedTx.vin)
        {
            const uint256& prevHash = txin.prevout.hash;
            if (mapPrevTx.count(prevHash))
                mapPrevOut[txin.prevout] = mapPrevTx[prevHash].second.vout[txin.prevout.n].scriptPubKey;
        }
    }

    // Add previous txouts given in the RPC call:
    if (params.size() > 1)
    {
        Array prevTxs = params[1].get_array();
        for (Value& p : prevTxs)
        {
            if (p.type() != obj_type)
                throw JSONRPCError(-22, "expected object with {\"txid'\",\"vout\",\"scriptPubKey\"}");

            Object prevOut = p.get_obj();

            RPCTypeCheck(prevOut, {{"txid", str_type}, {"vout", int_type}, {"scriptPubKey", str_type}});

            string txidHex = find_value(prevOut, "txid").get_str();
            if (!IsHex(txidHex))
                throw JSONRPCError(-22, "txid must be hexadecimal");
            uint256 txid;
            txid.SetHex(txidHex);

            int nOut = find_value(prevOut, "vout").get_int();
            if (nOut < 0)
                throw JSONRPCError(-22, "vout must be positive");

            string pkHex = find_value(prevOut, "scriptPubKey").get_str();
            if (!IsHex(pkHex))
                throw JSONRPCError(-22, "scriptPubKey must be hexadecimal");
            vector<unsigned char> pkData(ParseHex(pkHex));
            CScript scriptPubKey(pkData.begin(), pkData.end());

            COutPoint outpoint(txid, nOut);
            if (mapPrevOut.count(outpoint))
            {
                // Complain if scriptPubKey doesn't match
                if (mapPrevOut[outpoint] != scriptPubKey)
                {
                    string err("Previous output scriptPubKey mismatch:\n");
                    err = err + mapPrevOut[outpoint].ToString() + "\nvs:\n"+
                        scriptPubKey.ToString();
                    throw JSONRPCError(-22, err);
                }
            }
            else
                mapPrevOut[outpoint] = scriptPubKey;
        }
    }

    bool fGivenKeys = false;
    CBasicKeyStore tempKeystore;
    if (params.size() > 2)
    {
        fGivenKeys = true;
        Array keys = params[2].get_array();
        for (Value k : keys)
        {
            CBitcoinSecret vchSecret;
            bool fGood = vchSecret.SetString(k.get_str());
            if (!fGood)
                throw JSONRPCError(-5,"Invalid private key");
            CKey key;
            bool fCompressed;
            CSecret secret = vchSecret.GetSecret(fCompressed);
            key.SetSecret(secret, fCompressed);
            tempKeystore.AddKey(key);
        }
    }
    const CKeyStore& keystore = (fGivenKeys ? tempKeystore : *pwalletMain);

    int nHashType = SIGHASH_ALL;
    if (params.size() > 3)
    {
        static map<string, int> mapSigHashValues = {
            {"ALL", int(SIGHASH_ALL)},
            {"ALL|ANYONECANPAY", int(SIGHASH_ALL|SIGHASH_ANYONECANPAY)},
            {"NONE", int(SIGHASH_NONE)},
            {"NONE|ANYONECANPAY", int(SIGHASH_NONE|SIGHASH_ANYONECANPAY)},
            {"SINGLE", int(SIGHASH_SINGLE)},
            {"SINGLE|ANYONECANPAY", int(SIGHASH_SINGLE|SIGHASH_ANYONECANPAY)}
        };
        string strHashType = params[3].get_str();
        if (mapSigHashValues.count(strHashType))
            nHashType = mapSigHashValues[strHashType];
        else
            throw JSONRPCError(-8, "Invalid sighash param");
    }

    // Sign what we can:
    for (unsigned int i = 0; i < mergedTx.vin.size(); i++)
    {
        CTxIn& txin = mergedTx.vin[i];
        if (mapPrevOut.count(txin.prevout) == 0)
        {
            fComplete = false;
            continue;
        }
        const CScript& prevPubKey = mapPrevOut[txin.prevout];

        txin.scriptSig.clear();
        SignSignature(keystore, prevPubKey, mergedTx, i, nHashType);

        // ... and merge in other signatures:
        for (const CTransaction& txv : txVariants)
        {
            txin.scriptSig = CombineSignatures(prevPubKey, mergedTx, i, txin.scriptSig, txv.vin[i].scriptSig);
        }
        if (!VerifyScript(txin.scriptSig, prevPubKey, mergedTx, i, true, 0))
            fComplete = false;
    }

    Object result;
    CDataStream ssTx(SER_NETWORK, PROTOCOL_VERSION);
    ssTx << mergedTx;
    result.emplace_back("hex", HexStr(ssTx.begin(), ssTx.end()));
    result.emplace_back("complete", fComplete);

    return result;
}

Value testmempoolaccept(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 1)
        throw runtime_error(
            "testmempoolaccept [\"rawtx\"]\n"
            "Checks whether a raw transaction would be accepted into the memory pool, without adding it,\n"
            "relaying it or touching the wallet. The argument is an array holding one hex-encoded transaction.\n"
            "Result: [{txid, allowed, reject-reason (when not allowed), fee (when the inputs were found)}]");

    RPCTypeCheck(params, {array_type});
    const Array& txs = params[0].get_array();
    if (txs.size() != 1)
        throw JSONRPCError(-8, "Array must contain exactly one raw transaction for now");
    if (txs[0].type() != str_type)
        throw JSONRPCError(-3, "Expected a hex string");

    vector<unsigned char> txData(ParseHex(txs[0].get_str()));
    CDataStream ssData(txData, SER_NETWORK, PROTOCOL_VERSION);
    CTransaction tx;
    try {
        ssData >> tx;
    }
    catch (std::exception &e) {
        throw JSONRPCError(-22, "TX decode failed");
    }
    if (!ssData.empty())
        throw JSONRPCError(-22, "TX decode failed: trailing data");

    Object result;
    result.emplace_back("txid", tx.GetHash().GetHex());

    CTxAcceptCheck check;
    check.fTestOnly = true;
    bool fMissingInputs = false;
    CTxDB txdb("r");
    const bool fAllowed = tx.AcceptToMemoryPool(txdb, true, &fMissingInputs, &check);
    result.emplace_back("allowed", fAllowed);
    if (!fAllowed)
        result.emplace_back("reject-reason", check.strReject.empty() ? string("rejected") : check.strReject);
    if (check.nFees >= 0)
        result.emplace_back("fee", ValueFromAmount(check.nFees));

    Array ret;
    ret.push_back(result);
    return ret;
}

Value prioritisetransaction(const Array& params, bool fHelp)
{
    if (fHelp || params.size() != 3)
        throw runtime_error(
            "prioritisetransaction <txid> <priority delta> <fee delta>\n"
            "Adjusts how a transaction is treated when blocks are assembled, without changing the transaction.\n"
            "The priority delta is added to its priority; the fee delta (in base units, 1 coin = 100000000)\n"
            "counts as extra fee when checking the minimum fee, and also when the pool decides whether to\n"
            "accept it. The real fee is still what the miner collects. A negative delta holds a transaction\n"
            "back. Deltas are cumulative, apply to transactions not yet seen, and are forgotten on restart.");

    RPCTypeCheck(params, {str_type});
    if (params[1].type() != real_type && params[1].type() != int_type)
        throw JSONRPCError(-3, "priority delta must be a number");
    if (params[2].type() != int_type)
        throw JSONRPCError(-3, "fee delta must be an integer number of base units");

    const std::string strHash = params[0].get_str();
    if (!IsHex(strHash) || strHash.size() != 64)
        throw JSONRPCError(-8, "txid must be 64 hex characters");
    uint256 hash;
    hash.SetHex(strHash);

    const double dPriorityDelta = params[1].type() == int_type ? static_cast<double>(params[1].get_int64()) : params[1].get_real();
    mempool.PrioritiseTransaction(hash, dPriorityDelta, params[2].get_int64());
    return true;
}

Value sendrawtransaction(const Array& params, bool fHelp)
{
    if (fHelp || params.size() < 1 || params.size() > 1)
        throw runtime_error(
            "sendrawtransaction <hex string>\n"
            "Submits raw transaction (serialized, hex-encoded) to local node and network.");

    RPCTypeCheck(params, {str_type});

    // parse hex string from parameter
    vector<unsigned char> txData(ParseHex(params[0].get_str()));
    CDataStream ssData(txData, SER_NETWORK, PROTOCOL_VERSION);
    CTransaction tx;

    // deserialize binary data stream
    try {
        ssData >> tx;
    }
    catch (std::exception &e) {
        throw JSONRPCError(-22, "TX decode failed");
    }
    uint256 hashTx = tx.GetHash();

    // See if the transaction is already in a block
    // or in the memory pool:
    CTransaction existingTx;
    uint256 hashBlock = 0;
    if (GetTransaction(hashTx, existingTx, hashBlock))
    {
        if (hashBlock != 0)
            throw JSONRPCError(-5, string("transaction already in block ")+hashBlock.GetHex());
        // Not in block, but already in the memory pool; will drop
        // through to re-relay it.
    }
    else
    {
        // push to local node
        CTxDB txdb("r");
        if (!tx.AcceptToMemoryPool(txdb))
            throw JSONRPCError(-22, "TX rejected");

        SyncWithWallets(tx, nullptr, true);
    }
    RelayMessage(CInv(static_cast<int>(MsgType::Tx), hashTx), tx);

    return hashTx.GetHex();
}
