// Fuzz targets: what a peer, an RPC caller or a file can hand the node as bytes.
//
// One binary, the target picked by the FUZZ_TARGET environment variable:
//   block tx auxpow script json base58 bech32 burn address rpcauth
// Each target takes arbitrary bytes and must come back (any answer is fine) without a crash, a sanitizer report, a hang or an
// uncaught exception that the real code would not catch. Built with clang and -fsanitize=fuzzer this is a libFuzzer binary
// (-DBUILD_FUZZ=ON); built with anything else it is a small driver that replays a corpus and mutates it at random (see
// fuzz_driver.cpp), which is how the targets are run where there is no libFuzzer.

#include "main.h"
#include "script.h"
#include "base58.h"
#include "bech32.h"
#include "burnpayload.h"
#include "corgicoinrpc.h"
#include "json/json_compat.h"
#include "serialize.h"

#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

using namespace json_spirit;

#include "ui_interface.h"
#include "wallet.h"
#include <memory>

CClientUIInterface uiInterface;     // defined in init.cpp, which is left out
std::unique_ptr<CWallet> pwalletMain;   // likewise

// what the node's own code expects of the program it is linked into (init.cpp is left out, as it is for the unit tests)
void Shutdown(void* parg) { exit(0); }
void StartShutdown() { exit(0); }

static void FuzzBlock(const std::vector<unsigned char>& v)
{
    CDataStream ss(v, SER_NETWORK, PROTOCOL_VERSION);
    CBlock block;
    try { ss >> block; } catch (const std::exception&) { return; }
    block.GetHash();
    block.GetPoWHash();
    block.BuildMerkleTree();
    block.CheckBlock();
    if (block.auxpow)
        block.auxpow->Check(block.GetHash(), block.GetChainId());
}

static void FuzzTx(const std::vector<unsigned char>& v)
{
    CDataStream ss(v, SER_NETWORK, PROTOCOL_VERSION);
    CTransaction tx;
    try { ss >> tx; } catch (const std::exception&) { return; }
    tx.GetHash();
    tx.CheckTransaction();
    tx.GetLegacySigOpCount();
    std::string reason;
    tx.IsStandard();
    tx.ToString();
    for (const CTxOut& out : tx.vout)
    {
        txnouttype type;
        std::vector<std::vector<unsigned char> > solutions;
        Solver(out.scriptPubKey, type, solutions);
        CTxDestination dest;
        ExtractDestination(out.scriptPubKey, dest);
        out.scriptPubKey.ToString();
    }
}

static void FuzzAuxPow(const std::vector<unsigned char>& v)
{
    CDataStream ss(v, SER_NETWORK, PROTOCOL_VERSION);
    CAuxPow proof;
    try { ss >> proof; } catch (const std::exception&) { return; }
    uint256 hash = 0;
    if (v.size() >= 32)
        memcpy(&hash, &v[0], 32);
    proof.Check(hash, 0xC6);
}

// the input is a scriptSig and a scriptPubKey, split at the byte named by its first byte
static void FuzzScript(const std::vector<unsigned char>& v)
{
    if (v.empty())
        return;
    const size_t nSplit = 1 + (size_t)v[0] % std::max<size_t>(1, v.size() - 1);
    CScript scriptSig(v.begin() + 1, v.begin() + std::min(nSplit + 0, v.size()));
    CScript scriptPubKey(v.begin() + std::min(nSplit, v.size()), v.end());
    CTransaction tx;
    tx.vin.resize(1);
    tx.vin[0].scriptSig = scriptSig;
    tx.vout.resize(1);
    tx.vout[0].scriptPubKey = scriptPubKey;
    VerifyScript(scriptSig, scriptPubKey, tx, 0, true, 0);
    std::vector<std::vector<unsigned char> > stack;
    EvalScript(stack, scriptSig, tx, 0, 0);
    scriptSig.ToString();
    scriptPubKey.ToString();
    scriptPubKey.GetSigOpCount(true);
    scriptPubKey.IsPayToScriptHash();
    std::vector<CTxDestination> dests;
    txnouttype type;
    int nRequired;
    ExtractDestinations(scriptPubKey, type, dests, nRequired);
}

static void FuzzJson(const std::vector<unsigned char>& v)
{
    Value value;
    const std::string s(v.begin(), v.end());
    if (read_string(s, value))
    {
        write_string(value, false);
        write_string(value, true);
    }
}

static void FuzzBase58(const std::vector<unsigned char>& v)
{
    const std::string s(v.begin(), v.end());
    std::vector<unsigned char> out;
    DecodeBase58(s, out);
    DecodeBase58Check(s, out);
    CBitcoinAddress address;
    if (address.SetString(s))
    {
        address.Get();
        address.ToString();
    }
}

static void FuzzBech32(const std::vector<unsigned char>& v)
{
    const std::string s(v.begin(), v.end());
    bech32::DecodeResult r = bech32::Decode(s);
    if (r)
    {
        std::vector<uint8_t> bytes;
        bech32::ConvertBits(5, 8, false, r.data, bytes);
        bech32::Encode(r.encoding, r.hrp, r.data);
    }
    CBitcoinAddress address;
    address.SetString(s);
}

static void FuzzBurn(const std::vector<unsigned char>& v)
{
    std::string partner;
    std::vector<unsigned char> dest;
    burnpayload::DecodePayload(v, partner, dest);
    CScript script(v.begin(), v.end());
    burnpayload::DecodeScript(script, partner, dest);
}

// -rpcauth lines and the Authorization header of a request: up to 8 lines of input, each a -rpcauth value, and the rest is the
// Authorization header; the lines go to the -rpcauth parser, then the header to the login check
static void FuzzRPCAuth(const std::vector<unsigned char>& v)
{
    const std::string s(v.begin(), v.end());
    ClearRPCAuth();
    size_t pos = 0;
    int n = 0;
    while (pos < s.size() && n++ < 8)
    {
        size_t nl = s.find('\n', pos);
        if (nl == std::string::npos)
            break;
        AddRPCAuth(s.substr(pos, nl - pos));
        pos = nl + 1;
    }
    std::map<std::string, std::string> headers;
    headers["authorization"] = s.substr(pos);
    HTTPAuthorized(headers);
    ClearRPCAuth();
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size)
{
    static const char* pszTarget = getenv("FUZZ_TARGET");
    const std::string target = pszTarget ? pszTarget : "";
    const std::vector<unsigned char> v(data, data + size);
    try
    {
        if (target == "block") FuzzBlock(v);
        else if (target == "tx") FuzzTx(v);
        else if (target == "auxpow") FuzzAuxPow(v);
        else if (target == "script") FuzzScript(v);
        else if (target == "json") FuzzJson(v);
        else if (target == "base58" || target == "address") FuzzBase58(v);
        else if (target == "bech32") FuzzBech32(v);
        else if (target == "burn") FuzzBurn(v);
        else if (target == "rpcauth") FuzzRPCAuth(v);
        else
        {
            fprintf(stderr, "set FUZZ_TARGET to one of: block tx auxpow script json base58 bech32 burn rpcauth\n");
            exit(2);
        }
    }
    catch (const std::exception&)
    {
        // what the real code catches too (a short or malformed message): not a finding
    }
    return 0;
}
