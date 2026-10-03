// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include "main.h"
#include "auxpow.h"

#include <algorithm>

using namespace std;

// AuxPoW merged-mining verification tests — see doc/auxpow-spec.md.
// These exercise CAuxPow::Check (the structural proof) and the version
// helpers. The parent-header Scrypt PoW (CheckProofOfWork on parentBlock)
// is validated separately and not constructed here.

BOOST_AUTO_TEST_SUITE(auxpow_tests)

BOOST_AUTO_TEST_CASE(version_bit_helpers)
{
    int32_t v = MakeVersion(1, AUXPOW_CHAIN_ID, true);
    BOOST_CHECK_EQUAL(GetBaseVersion(v), 1);
    BOOST_CHECK_EQUAL(GetChainId(v), AUXPOW_CHAIN_ID);
    BOOST_CHECK(IsAuxPowVersion(v));

    int32_t solo = MakeVersion(1, AUXPOW_CHAIN_ID, false);
    BOOST_CHECK_EQUAL(GetChainId(solo), AUXPOW_CHAIN_ID);
    BOOST_CHECK(!IsAuxPowVersion(solo));

    // Legacy v1 block: chain id 0, no auxpow bit
    BOOST_CHECK_EQUAL(GetChainId(1), 0);
    BOOST_CHECK(!IsAuxPowVersion(1));
}

BOOST_AUTO_TEST_CASE(pure_header_roundtrip)
{
    CPureBlockHeader h;
    h.nVersion = 0x00C60001;
    h.hashPrevBlock = uint256("0x1111111111111111111111111111111111111111111111111111111111111111");
    h.hashMerkleRoot = uint256("0x2222222222222222222222222222222222222222222222222222222222222222");
    h.nTime = 1700000000;
    h.nBits = 0x1e0ffff0;
    h.nNonce = 42;

    CDataStream ss(SER_NETWORK, PROTOCOL_VERSION);
    ss << h;
    CPureBlockHeader h2;
    ss >> h2;

    BOOST_CHECK_EQUAL(h2.nVersion, h.nVersion);
    BOOST_CHECK(h2.hashPrevBlock == h.hashPrevBlock);
    BOOST_CHECK(h2.hashMerkleRoot == h.hashMerkleRoot);
    BOOST_CHECK_EQUAL(h2.nTime, h.nTime);
    BOOST_CHECK_EQUAL(h2.nNonce, h.nNonce);
    BOOST_CHECK(h2.GetHash() == h.GetHash());
}

namespace {

static const unsigned char MM_MAGIC[4] = { 0xfa, 0xbe, 'm', 'm' };

// Append a little-endian uint32 to a script.
void PushLE32(CScript& s, uint32_t v)
{
    for (int i = 0; i < 4; i++)
        s.push_back((unsigned char)((v >> (8 * i)) & 0xff));
}

// Build a minimal valid AuxPoW committing hashAux for nChainId.
// With an empty chain merkle branch: root == hashAux, index 0, size 1.
// Options let individual tests break one field at a time.
struct AuxOpts {
    bool withMagic = true;
    bool makeCoinbase = true;
    int32_t parentVersion = 1;       // chain id 0, no auxpow bit
    bool tamperRoot = false;         // corrupt the committed root
    bool breakCoinbaseMerkle = false;// parent merkle root won't match coinbase
    uint32_t sizeOverride = 0;       // if non-zero, force this merkle size
};

CAuxPow BuildAuxPow(uint256 hashAux, int32_t nChainId, const AuxOpts& o)
{
    // Committed root = hashAux (empty chain branch), stored byte-reversed
    vector<unsigned char> vchRoot(hashAux.begin(), hashAux.end());
    reverse(vchRoot.begin(), vchRoot.end());
    if (o.tamperRoot && !vchRoot.empty())
        vchRoot[0] ^= 0xff;

    CScript scriptSig;
    if (o.withMagic)
        scriptSig.insert(scriptSig.end(), MM_MAGIC, MM_MAGIC + 4);
    scriptSig.insert(scriptSig.end(), vchRoot.begin(), vchRoot.end());
    PushLE32(scriptSig, o.sizeOverride ? o.sizeOverride : 1u); // merkle size = 1<<0
    PushLE32(scriptSig, 0);                                    // nonce

    CTransaction coinbase;
    coinbase.vin.resize(1);
    if (o.makeCoinbase)
        coinbase.vin[0].prevout.SetNull();
    else
        coinbase.vin[0].prevout = COutPoint(uint256("0x01"), 0);
    coinbase.vin[0].scriptSig = scriptSig;
    coinbase.vout.resize(1);
    coinbase.vout[0].nValue = 0;

    CAuxPow aux(coinbase);
    aux.vMerkleBranch.clear();           // coinbase is the whole tree
    aux.nIndex = 0;
    aux.vChainMerkleBranch.clear();      // aux root == aux block hash
    aux.nChainIndex = 0;
    aux.parentBlock.SetNull();
    aux.parentBlock.nVersion = o.parentVersion;
    aux.parentBlock.hashMerkleRoot =
        o.breakCoinbaseMerkle ? uint256("0xdead") : coinbase.GetHash();
    return aux;
}

} // namespace

BOOST_AUTO_TEST_CASE(auxpow_valid_proof_accepts)
{
    uint256 hashAux("0xabcabcabcabcabcabcabcabcabcabcabcabcabcabcabcabcabcabcabcabcabcab");
    CAuxPow aux = BuildAuxPow(hashAux, AUXPOW_CHAIN_ID, AuxOpts{});
    BOOST_CHECK(aux.Check(hashAux, AUXPOW_CHAIN_ID));
}

BOOST_AUTO_TEST_CASE(auxpow_valid_without_magic)
{
    // No magic: root must be within the first 20 bytes — it is (starts at 0)
    uint256 hashAux("0x0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f");
    AuxOpts o; o.withMagic = false;
    CAuxPow aux = BuildAuxPow(hashAux, AUXPOW_CHAIN_ID, o);
    BOOST_CHECK(aux.Check(hashAux, AUXPOW_CHAIN_ID));
}

BOOST_AUTO_TEST_CASE(auxpow_tampered_root_rejected)
{
    uint256 hashAux("0x1234123412341234123412341234123412341234123412341234123412341234");
    AuxOpts o; o.tamperRoot = true;
    CAuxPow aux = BuildAuxPow(hashAux, AUXPOW_CHAIN_ID, o);
    BOOST_CHECK(!aux.Check(hashAux, AUXPOW_CHAIN_ID));
}

BOOST_AUTO_TEST_CASE(auxpow_wrong_aux_hash_rejected)
{
    uint256 hashAux("0x5555555555555555555555555555555555555555555555555555555555555555");
    CAuxPow aux = BuildAuxPow(hashAux, AUXPOW_CHAIN_ID, AuxOpts{});
    uint256 other("0x6666666666666666666666666666666666666666666666666666666666666666");
    BOOST_CHECK(!aux.Check(other, AUXPOW_CHAIN_ID));
}

BOOST_AUTO_TEST_CASE(auxpow_non_coinbase_rejected)
{
    uint256 hashAux("0x7777777777777777777777777777777777777777777777777777777777777777");
    AuxOpts o; o.makeCoinbase = false;
    CAuxPow aux = BuildAuxPow(hashAux, AUXPOW_CHAIN_ID, o);
    BOOST_CHECK(!aux.Check(hashAux, AUXPOW_CHAIN_ID));
}

BOOST_AUTO_TEST_CASE(auxpow_parent_same_chainid_rejected)
{
    uint256 hashAux("0x8888888888888888888888888888888888888888888888888888888888888888");
    AuxOpts o; o.parentVersion = MakeVersion(1, AUXPOW_CHAIN_ID, false);
    CAuxPow aux = BuildAuxPow(hashAux, AUXPOW_CHAIN_ID, o);
    BOOST_CHECK(!aux.Check(hashAux, AUXPOW_CHAIN_ID));
}

BOOST_AUTO_TEST_CASE(auxpow_parent_is_auxpow_rejected)
{
    uint256 hashAux("0x9999999999999999999999999999999999999999999999999999999999999999");
    AuxOpts o; o.parentVersion = MakeVersion(1, 0x0042, true);
    CAuxPow aux = BuildAuxPow(hashAux, AUXPOW_CHAIN_ID, o);
    BOOST_CHECK(!aux.Check(hashAux, AUXPOW_CHAIN_ID));
}

BOOST_AUTO_TEST_CASE(auxpow_coinbase_merkle_mismatch_rejected)
{
    uint256 hashAux("0xaaaabbbbccccddddaaaabbbbccccddddaaaabbbbccccddddaaaabbbbccccdddd0");
    AuxOpts o; o.breakCoinbaseMerkle = true;
    CAuxPow aux = BuildAuxPow(hashAux, AUXPOW_CHAIN_ID, o);
    BOOST_CHECK(!aux.Check(hashAux, AUXPOW_CHAIN_ID));
}

BOOST_AUTO_TEST_CASE(auxpow_bad_merkle_size_rejected)
{
    uint256 hashAux("0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    AuxOpts o; o.sizeOverride = 2; // branch is empty so expected size is 1
    CAuxPow aux = BuildAuxPow(hashAux, AUXPOW_CHAIN_ID, o);
    BOOST_CHECK(!aux.Check(hashAux, AUXPOW_CHAIN_ID));
}

BOOST_AUTO_TEST_CASE(auxpow_serialization_roundtrip)
{
    uint256 hashAux("0xcccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc0");
    CAuxPow aux = BuildAuxPow(hashAux, AUXPOW_CHAIN_ID, AuxOpts{});

    CDataStream ss(SER_NETWORK, PROTOCOL_VERSION);
    ss << aux;
    CAuxPow aux2;
    ss >> aux2;
    BOOST_CHECK(aux2.Check(hashAux, AUXPOW_CHAIN_ID));
}

BOOST_AUTO_TEST_SUITE_END()
