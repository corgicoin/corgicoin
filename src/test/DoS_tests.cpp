//
// Unit tests for denial-of-service detection/prevention code
//
#include <algorithm>

#include <chrono>
#include <boost/test/unit_test.hpp>

#include "main.h"
#include "wallet.h"
#include "net.h"
#include "util.h"

#include <stdint.h>
#include <memory>

// Tests this internal-to-main.cpp method:
extern bool AddOrphanTx(const CDataStream& vMsg);
extern unsigned int LimitOrphanTxSize(unsigned int nMaxOrphans);
extern std::map<uint256, CDataStream*> mapOrphanTransactions;
extern std::map<uint256, std::map<uint256, CDataStream*> > mapOrphanTransactionsByPrev;
// ... and the orphan-block pool
extern std::map<uint256, std::shared_ptr<CBlock> > mapOrphanBlocks;
extern std::multimap<uint256, std::shared_ptr<CBlock> > mapOrphanBlocksByPrev;

CService ip(uint32_t i)
{
    struct in_addr s;
    s.s_addr = i;
    return CService(CNetAddr(s), GetDefaultPort());
}

BOOST_AUTO_TEST_SUITE(DoS_tests)

BOOST_AUTO_TEST_CASE(DoS_banning)
{
    CNode::ClearBanned();
    CAddress addr1(ip(0xa0b0c001));
    CNode dummyNode1(INVALID_SOCKET, addr1, "", true);
    dummyNode1.Misbehaving(100); // Should get banned
    BOOST_CHECK(CNode::IsBanned(addr1));
    BOOST_CHECK(!CNode::IsBanned(ip(0xa0b0c001|0x0000ff00))); // Different ip, not banned

    CAddress addr2(ip(0xa0b0c002));
    CNode dummyNode2(INVALID_SOCKET, addr2, "", true);
    dummyNode2.Misbehaving(50);
    BOOST_CHECK(!CNode::IsBanned(addr2)); // 2 not banned yet...
    BOOST_CHECK(CNode::IsBanned(addr1));  // ... but 1 still should be
    dummyNode2.Misbehaving(50);
    BOOST_CHECK(CNode::IsBanned(addr2));
}    

BOOST_AUTO_TEST_CASE(DoS_banscore)
{
    CNode::ClearBanned();
    mapArgs["-banscore"] = "111"; // because 11 is my favorite number
    CAddress addr1(ip(0xa0b0c001));
    CNode dummyNode1(INVALID_SOCKET, addr1, "", true);
    dummyNode1.Misbehaving(100);
    BOOST_CHECK(!CNode::IsBanned(addr1));
    dummyNode1.Misbehaving(10);
    BOOST_CHECK(!CNode::IsBanned(addr1));
    dummyNode1.Misbehaving(1);
    BOOST_CHECK(CNode::IsBanned(addr1));
    mapArgs.erase("-banscore");
}

BOOST_AUTO_TEST_CASE(DoS_bantime)
{
    CNode::ClearBanned();
    int64 nStartTime = GetTime();
    SetMockTime(nStartTime); // Overrides future calls to GetTime()

    CAddress addr(ip(0xa0b0c001));
    CNode dummyNode(INVALID_SOCKET, addr, "", true);

    dummyNode.Misbehaving(100);
    BOOST_CHECK(CNode::IsBanned(addr));

    SetMockTime(nStartTime+60*60);
    BOOST_CHECK(CNode::IsBanned(addr));

    SetMockTime(nStartTime+60*60*24+1);
    BOOST_CHECK(!CNode::IsBanned(addr));
}

BOOST_AUTO_TEST_CASE(DoS_ban_management)
{
    // Backs the setban / listbanned / clearbanned RPCs.
    CNode::ClearBanned();
    int64 nStartTime = GetTime();
    SetMockTime(nStartTime);

    CNetAddr a1 = ip(0xa0b0c011), a2 = ip(0xa0b0c012);

    CNode::Ban(a1, nStartTime + 100);
    CNode::Ban(a2, nStartTime + 1000);
    BOOST_CHECK(CNode::IsBanned(a1));
    BOOST_CHECK(CNode::IsBanned(a2));

    // Without overwrite the later expiry wins; with overwrite it's replaced.
    CNode::Ban(a2, nStartTime + 50);
    std::map<CNetAddr, int64> banMap;
    CNode::GetBanned(banMap);
    BOOST_CHECK_EQUAL(banMap.size(), 2U);
    BOOST_CHECK_EQUAL(banMap[a2], nStartTime + 1000);
    CNode::Ban(a2, nStartTime + 50, true);
    CNode::GetBanned(banMap);
    BOOST_CHECK_EQUAL(banMap[a2], nStartTime + 50);

    // Expired bans are swept from the listing.
    SetMockTime(nStartTime + 60);
    CNode::GetBanned(banMap);
    BOOST_CHECK_EQUAL(banMap.size(), 1U);
    BOOST_CHECK(banMap.count(a1));
    BOOST_CHECK(!CNode::IsBanned(a2));

    // Unban reports whether anything was removed.
    BOOST_CHECK(CNode::Unban(a1));
    BOOST_CHECK(!CNode::Unban(a1));
    BOOST_CHECK(!CNode::IsBanned(a1));

    CNode::Ban(a1, nStartTime + 1000);
    CNode::ClearBanned();
    CNode::GetBanned(banMap);
    BOOST_CHECK(banMap.empty());

    SetMockTime(0);
}

BOOST_AUTO_TEST_CASE(DoS_peer_stats_defaults)
{
    // A fresh peer reports no ping measurement and no traffic, so
    // getpeerinfo omits pingtime/minping/pingwait rather than showing junk.
    CAddress addr(ip(0xa0b0c021));
    CNode node(INVALID_SOCKET, addr, "", true);
    CNodeStats stats;
    node.copyStats(stats);
    BOOST_CHECK_EQUAL(stats.nSendBytes, 0U);
    BOOST_CHECK_EQUAL(stats.nRecvBytes, 0U);
    BOOST_CHECK_EQUAL(stats.dPingTime, 0.0);
    BOOST_CHECK_EQUAL(stats.dMinPing, 0.0);
    BOOST_CHECK_EQUAL(stats.dPingWait, 0.0);

    // After a measured round trip, minping tracks the best value.
    node.nPingUsecTime = 250000;
    node.nMinPingUsecTime = 120000;
    node.copyStats(stats);
    BOOST_CHECK_CLOSE(stats.dPingTime, 0.25, 1e-9);
    BOOST_CHECK_CLOSE(stats.dMinPing, 0.12, 1e-9);
}

static bool CheckNBits(unsigned int nbits1, int64 time1, unsigned int nbits2, int64 time2)\
{
    if (time1 > time2)
        return CheckNBits(nbits2, time2, nbits1, time1);
    int64 deltaTime = time2-time1;

    CBigNum required;
    required.SetCompact(ComputeMinWork(nbits1, deltaTime));
    CBigNum have;
    have.SetCompact(nbits2);
    return (have <= required);
}

BOOST_AUTO_TEST_CASE(DoS_checknbits)
{
    // Timestamps,nBits from the bitcoin blockchain.
    // These are the block-chain checkpoint blocks
    using BlockData = std::map<int64, unsigned int>;
    BlockData chainData = {
        {1239852051, 486604799}, {1262749024, 486594666},
        {1279305360, 469854461}, {1280200847, 469830746}, {1281678674, 469809688},
        {1296207707, 453179945}, {1302624061, 453036989}, {1309640330, 437004818},
        {1313172719, 436789733}
    };

    // Make sure CheckNBits considers every combination of block-chain-lock-in-points
    // "sane":
    for (const BlockData::value_type& i : chainData)
    {
        for (const BlockData::value_type& j : chainData)
        {
            BOOST_CHECK(CheckNBits(i.second, i.first, j.second, j.first));
        }
    }

    // Test a couple of insane combinations:
    BlockData::value_type firstcheck = *(chainData.begin());
    BlockData::value_type lastcheck = *(chainData.rbegin());

    // First checkpoint difficulty shortly after last checkpoint time should fail
    // (10 minutes is too short for this much difficulty change)
    BOOST_CHECK(!CheckNBits(firstcheck.second, lastcheck.first+60*10, lastcheck.second, lastcheck.first));

    // ... but OK if enough time passed for difficulty to adjust downward:
    // CorgiCoin retargets every 4 hours, so 4 years is more than enough
    BOOST_CHECK(CheckNBits(firstcheck.second, lastcheck.first+60*60*24*365*4, lastcheck.second, lastcheck.first));

}

CTransaction RandomOrphan()
{
    auto it = mapOrphanTransactions.lower_bound(GetRandHash());
    if (it == mapOrphanTransactions.end())
        it = mapOrphanTransactions.begin();
    const CDataStream* pvMsg = it->second;
    CTransaction tx;
    CDataStream(*pvMsg) >> tx;
    return tx;
}

BOOST_AUTO_TEST_CASE(DoS_mapOrphans)
{
    CKey key;
    key.MakeNewKey(true);
    CBasicKeyStore keystore;
    keystore.AddKey(key);

    // 50 orphan transactions:
    for (int i = 0; i < 50; i++)
    {
        CTransaction tx;
        tx.vin.resize(1);
        tx.vin[0].prevout.n = 0;
        tx.vin[0].prevout.hash = GetRandHash();
        tx.vin[0].scriptSig << OP_1;
        tx.vout.resize(1);
        tx.vout[0].nValue = 1*CENT;
        tx.vout[0].scriptPubKey.SetDestination(key.GetPubKey().GetID());

        CDataStream ds(SER_DISK, CLIENT_VERSION);
        ds << tx;
        AddOrphanTx(ds);
    }

    // ... and 50 that depend on other orphans:
    for (int i = 0; i < 50; i++)
    {
        CTransaction txPrev = RandomOrphan();

        CTransaction tx;
        tx.vin.resize(1);
        tx.vin[0].prevout.n = 0;
        tx.vin[0].prevout.hash = txPrev.GetHash();
        tx.vout.resize(1);
        tx.vout[0].nValue = 1*CENT;
        tx.vout[0].scriptPubKey.SetDestination(key.GetPubKey().GetID());
        SignSignature(keystore, txPrev, tx, 0);

        CDataStream ds(SER_DISK, CLIENT_VERSION);
        ds << tx;
        AddOrphanTx(ds);
    }

    // This really-big orphan should be ignored:
    for (int i = 0; i < 10; i++)
    {
        CTransaction txPrev = RandomOrphan();

        CTransaction tx;
        tx.vout.resize(1);
        tx.vout[0].nValue = 1*CENT;
        tx.vout[0].scriptPubKey.SetDestination(key.GetPubKey().GetID());
        tx.vin.resize(500);
        for (unsigned int j = 0; j < tx.vin.size(); j++)
        {
            tx.vin[j].prevout.n = j;
            tx.vin[j].prevout.hash = txPrev.GetHash();
        }
        SignSignature(keystore, txPrev, tx, 0);
        // Re-use same signature for other inputs
        // (they don't have to be valid for this test)
        for (unsigned int j = 1; j < tx.vin.size(); j++)
            tx.vin[j].scriptSig = tx.vin[0].scriptSig;

        CDataStream ds(SER_DISK, CLIENT_VERSION);
        ds << tx;
        BOOST_CHECK(!AddOrphanTx(ds));
    }

    // Test LimitOrphanTxSize() function:
    LimitOrphanTxSize(40);
    BOOST_CHECK(mapOrphanTransactions.size() <= 40);
    LimitOrphanTxSize(10);
    BOOST_CHECK(mapOrphanTransactions.size() <= 10);
    LimitOrphanTxSize(0);
    BOOST_CHECK(mapOrphanTransactions.empty());
    BOOST_CHECK(mapOrphanTransactionsByPrev.empty());
}

BOOST_AUTO_TEST_CASE(DoS_checkSig)
{
    // Test signature caching code (see key.cpp Verify() methods)

    CKey key;
    key.MakeNewKey(true);
    CBasicKeyStore keystore;
    keystore.AddKey(key);

    // 100 orphan transactions:
    static const int NPREV=100;
    CTransaction orphans[NPREV];
    for (int i = 0; i < NPREV; i++)
    {
        CTransaction& tx = orphans[i];
        tx.vin.resize(1);
        tx.vin[0].prevout.n = 0;
        tx.vin[0].prevout.hash = GetRandHash();
        tx.vin[0].scriptSig << OP_1;
        tx.vout.resize(1);
        tx.vout[0].nValue = 1*CENT;
        tx.vout[0].scriptPubKey.SetDestination(key.GetPubKey().GetID());

        CDataStream ds(SER_DISK, CLIENT_VERSION);
        ds << tx;
        AddOrphanTx(ds);
    }

    // Create a transaction that depends on orphans:
    CTransaction tx;
    tx.vout.resize(1);
    tx.vout[0].nValue = 1*CENT;
    tx.vout[0].scriptPubKey.SetDestination(key.GetPubKey().GetID());
    tx.vin.resize(NPREV);
    for (unsigned int j = 0; j < tx.vin.size(); j++)
    {
        tx.vin[j].prevout.n = 0;
        tx.vin[j].prevout.hash = orphans[j].GetHash();
    }
    // Creating signatures primes the cache:
    auto mst1 = std::chrono::steady_clock::now();
    for (unsigned int j = 0; j < tx.vin.size(); j++)
        BOOST_CHECK(SignSignature(keystore, orphans[j], tx, j));
    auto mst2 = std::chrono::steady_clock::now();
    long nOneValidate = std::chrono::duration_cast<std::chrono::milliseconds>(mst2 - mst1).count();
    if (fDebug) printf("DoS_Checksig sign: %ld\n", nOneValidate);

    // ... now validating repeatedly should be quick:
    // 2.8GHz machine, -g build: Sign takes ~760ms,
    // uncached Verify takes ~250ms, cached Verify takes ~50ms
    // (for 100 single-signature inputs)
    mst1 = std::chrono::steady_clock::now();
    for (unsigned int i = 0; i < 5; i++)
        for (unsigned int j = 0; j < tx.vin.size(); j++)
            BOOST_CHECK(VerifySignature(orphans[j], tx, j, true, SIGHASH_ALL));
    mst2 = std::chrono::steady_clock::now();
    long nManyValidate = std::chrono::duration_cast<std::chrono::milliseconds>(mst2 - mst1).count();
    if (fDebug) printf("DoS_Checksig five: %ld\n", nManyValidate);

    BOOST_CHECK_MESSAGE(nManyValidate < nOneValidate, "Signature cache timing failed");

    // Empty a signature, validation should fail:
    CScript save = tx.vin[0].scriptSig;
    tx.vin[0].scriptSig = CScript();
    BOOST_CHECK(!VerifySignature(orphans[0], tx, 0, true, SIGHASH_ALL));
    tx.vin[0].scriptSig = save;

    // Swap signatures, validation should fail:
    std::swap(tx.vin[0].scriptSig, tx.vin[1].scriptSig);
    BOOST_CHECK(!VerifySignature(orphans[0], tx, 0, true, SIGHASH_ALL));
    BOOST_CHECK(!VerifySignature(orphans[1], tx, 1, true, SIGHASH_ALL));
    std::swap(tx.vin[0].scriptSig, tx.vin[1].scriptSig);

    // Exercise -maxsigcachesize code:
    mapArgs["-maxsigcachesize"] = "10";
    // Generate a new, different signature for vin[0] to trigger cache clear:
    CScript oldSig = tx.vin[0].scriptSig;
    BOOST_CHECK(SignSignature(keystore, orphans[0], tx, 0));
    BOOST_CHECK(tx.vin[0].scriptSig != oldSig);
    for (unsigned int j = 0; j < tx.vin.size(); j++)
        BOOST_CHECK(VerifySignature(orphans[j], tx, j, true, SIGHASH_ALL));
    mapArgs.erase("-maxsigcachesize");

    LimitOrphanTxSize(0);
}


// ---- orphan blocks ----------------------------------------------------------------------------

static std::shared_ptr<CBlock> MakeOrphanBlock(unsigned int nPadBytes, const uint256& hashPrev = GetRandHash())
{
    auto block = std::make_shared<CBlock>();
    block->nVersion = 1;
    block->hashPrevBlock = hashPrev;       // a parent the node does not have
    block->nTime = 1;
    block->nBits = 0x1f00ffff;
    block->nNonce = (unsigned int)GetRand(0xffffffffULL);   // different hash for every block
    CTransaction coinbase;
    coinbase.vin.resize(1);
    coinbase.vin[0].prevout.SetNull();
    coinbase.vin[0].scriptSig << OP_1;
    coinbase.vout.resize(1);
    coinbase.vout[0].nValue = 1;
    coinbase.vout[0].scriptPubKey << std::vector<unsigned char>(nPadBytes, 'x');
    block->vtx.push_back(coinbase);
    return block;
}

// both maps agree, and the running byte total equals the real total
static void CheckOrphanBlockPool()
{
    BOOST_CHECK_EQUAL(mapOrphanBlocks.size(), mapOrphanBlocksByPrev.size());
    uint64 nBytes = 0;
    for (const auto& item : mapOrphanBlocks)
    {
        nBytes += ::GetSerializeSize(*item.second, SER_NETWORK, PROTOCOL_VERSION);
        auto range = mapOrphanBlocksByPrev.equal_range(item.second->hashPrevBlock);
        bool fFound = false;
        for (auto mi = range.first; mi != range.second; ++mi)
            if (mi->second == item.second)
                fFound = true;
        BOOST_CHECK(fFound);
    }
    BOOST_CHECK_EQUAL(GetOrphanBlockBytes(), nBytes);
}

BOOST_AUTO_TEST_CASE(DoS_orphan_blocks_under_the_limits_are_kept)
{
    LimitOrphanBlocks(0, 0);
    for (int i = 0; i < 10; i++)
        AddOrphanBlock(MakeOrphanBlock(50));
    BOOST_CHECK_EQUAL(LimitOrphanBlocks(MAX_ORPHAN_BLOCKS, MAX_ORPHAN_BLOCKS_BYTES), 0u);
    BOOST_CHECK_EQUAL(mapOrphanBlocks.size(), 10u);
    CheckOrphanBlockPool();
    LimitOrphanBlocks(0, 0);
}

BOOST_AUTO_TEST_CASE(DoS_orphan_blocks_count_limit)
{
    LimitOrphanBlocks(0, 0);
    for (int i = 0; i < 300; i++)
        AddOrphanBlock(MakeOrphanBlock(50));
    BOOST_CHECK_EQUAL(LimitOrphanBlocks(100, 0xffffffffu), 200u);
    BOOST_CHECK_EQUAL(mapOrphanBlocks.size(), 100u);
    CheckOrphanBlockPool();

    BOOST_CHECK_EQUAL(LimitOrphanBlocks(0, 0), 100u);
    BOOST_CHECK(mapOrphanBlocks.empty());
    BOOST_CHECK(mapOrphanBlocksByPrev.empty());
    BOOST_CHECK_EQUAL(GetOrphanBlockBytes(), 0u);
}

BOOST_AUTO_TEST_CASE(DoS_orphan_blocks_byte_limit)
{
    LimitOrphanBlocks(0, 0);
    for (int i = 0; i < 40; i++)
        AddOrphanBlock(MakeOrphanBlock(10000));       // about 10 kB each, 400 kB in total
    BOOST_CHECK(GetOrphanBlockBytes() > 400000);
    LimitOrphanBlocks(1000, 100000);
    BOOST_CHECK(GetOrphanBlockBytes() <= 100000);
    BOOST_CHECK(mapOrphanBlocks.size() >= 5u);        // it evicts down to the limit, not to nothing
    CheckOrphanBlockPool();

    // a single block larger than the whole budget cannot be kept
    LimitOrphanBlocks(0, 0);
    AddOrphanBlock(MakeOrphanBlock(20000));
    BOOST_CHECK_EQUAL(LimitOrphanBlocks(10, 1000), 1u);
    BOOST_CHECK(mapOrphanBlocks.empty());
    BOOST_CHECK_EQUAL(GetOrphanBlockBytes(), 0u);
}

BOOST_AUTO_TEST_CASE(DoS_orphan_blocks_a_flood_stays_bounded)
{
    LimitOrphanBlocks(0, 0);
    // what ProcessBlock does for every orphan it receives: add it, then enforce the limits
    for (int i = 0; i < 3000; i++)
    {
        AddOrphanBlock(MakeOrphanBlock(100));
        LimitOrphanBlocks(MAX_ORPHAN_BLOCKS, MAX_ORPHAN_BLOCKS_BYTES);
        BOOST_REQUIRE(mapOrphanBlocks.size() <= MAX_ORPHAN_BLOCKS);
        BOOST_REQUIRE(GetOrphanBlockBytes() <= MAX_ORPHAN_BLOCKS_BYTES);
    }
    BOOST_CHECK_EQUAL(mapOrphanBlocks.size(), (size_t)MAX_ORPHAN_BLOCKS);
    CheckOrphanBlockPool();
    LimitOrphanBlocks(0, 0);
}

BOOST_AUTO_TEST_CASE(DoS_orphan_blocks_taken_when_the_parent_arrives)
{
    LimitOrphanBlocks(0, 0);
    uint256 hashParent = GetRandHash();
    for (int i = 0; i < 3; i++)
        AddOrphanBlock(MakeOrphanBlock(200, hashParent));   // three children of the same missing parent
    for (int i = 0; i < 5; i++)
        AddOrphanBlock(MakeOrphanBlock(200));                // unrelated orphans
    BOOST_CHECK_EQUAL(mapOrphanBlocks.size(), 8u);

    auto vTaken = TakeOrphanBlocksByPrev(hashParent);
    BOOST_CHECK_EQUAL(vTaken.size(), 3u);
    for (const auto& pblock : vTaken)
        BOOST_CHECK(pblock->hashPrevBlock == hashParent);
    BOOST_CHECK_EQUAL(mapOrphanBlocks.size(), 5u);
    CheckOrphanBlockPool();                                  // byte total still exact

    BOOST_CHECK(TakeOrphanBlocksByPrev(hashParent).empty()); // nothing left for that parent
    LimitOrphanBlocks(0, 0);
    BOOST_CHECK_EQUAL(GetOrphanBlockBytes(), 0u);
}

BOOST_AUTO_TEST_SUITE_END()
