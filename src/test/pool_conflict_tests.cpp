//
// A pool transaction that spends a coin a block's transaction spends otherwise is removed with what is built on it (CTxMemPool::RemoveConflicts).
//
#include <boost/test/unit_test.hpp>

#include "main.h"
#include "script.h"

namespace {

CScript PayToNobody(unsigned char n)
{
    std::vector<unsigned char> vch(20, n);
    return CScript() << OP_DUP << OP_HASH160 << vch << OP_EQUALVERIFY << OP_CHECKSIG;
}

CTransaction Spend(const std::vector<COutPoint>& prevs, unsigned char nTag)
{
    CTransaction tx;
    for (const COutPoint& prev : prevs)
        tx.vin.push_back(CTxIn(prev, CScript(), 0xffffffff));
    tx.vout.push_back(CTxOut(1 * COIN, PayToNobody(nTag)));
    return tx;
}

CTransaction Spend(const COutPoint& prev, unsigned char nTag)
{
    return Spend(std::vector<COutPoint>(1, prev), nTag);
}

void Put(const CTransaction& txIn)
{
    CTransaction tx = txIn;
    LOCK(mempool.cs);
    const uint256 hash = tx.GetHash();
    mempool.addUnchecked(hash, tx);
    CTxMemPool::PoolEntry entry = { 1000, ::GetSerializeSize(tx, SER_NETWORK, PROTOCOL_VERSION), GetTime(), true, 0 };
    mempool.mapEntry[hash] = entry;
    mempool.nPoolBytes += entry.nSize;
}

void Clear()
{
    LOCK(mempool.cs);
    mempool.mapTx.clear();
    mempool.mapNextTx.clear();
    mempool.mapEntry.clear();
    mempool.nPoolBytes = 0;
}

bool In(const CTransaction& tx)
{
    return mempool.exists(tx.GetHash());
}

}

BOOST_AUTO_TEST_SUITE(pool_conflict_tests)

BOOST_AUTO_TEST_CASE(a_conflict_goes_with_its_children_and_nothing_else)
{
    Clear();
    const COutPoint coinA(uint256(1001), 0), coinB(uint256(1002), 0), coinZ(uint256(1003), 0);
    CTransaction t1 = Spend(coinA, 1);                 // spends A
    CTransaction c1 = Spend(COutPoint(t1.GetHash(), 0), 2);          // built on t1
    CTransaction g1 = Spend(COutPoint(c1.GetHash(), 0), 3);          // built on c1
    CTransaction t2 = Spend(coinB, 4);                 // spends B
    CTransaction z = Spend(coinZ, 5);                  // unrelated
    for (const CTransaction* t : {&t1, &c1, &g1, &t2, &z})
        Put(*t);

    CTransaction mined = Spend(std::vector<COutPoint>{coinA, coinB}, 9);        // a block's transaction: spends A and B
    mempool.RemoveConflicts(mined);
    BOOST_CHECK(!In(t1) && !In(c1) && !In(g1));        // t1 and everything built on it
    BOOST_CHECK(!In(t2));                              // the second conflict too
    BOOST_CHECK(In(z));                                // not touched
    BOOST_CHECK_EQUAL(mempool.mapTx.size(), 1u);
    BOOST_CHECK(mempool.mapNextTx.count(coinZ) == 1 && mempool.mapNextTx.count(coinA) == 0 && mempool.mapNextTx.count(COutPoint(t1.GetHash(), 0)) == 0);
    Clear();
}

BOOST_AUTO_TEST_CASE(the_same_transaction_is_not_a_conflict)
{
    Clear();
    const COutPoint coinA(uint256(2001), 0);
    CTransaction t1 = Spend(coinA, 1);
    CTransaction c1 = Spend(COutPoint(t1.GetHash(), 0), 2);
    Put(t1);
    Put(c1);
    mempool.RemoveConflicts(t1);                       // the block carries t1 itself: remove() takes it, and its child stays (it can still be mined)
    BOOST_CHECK(In(t1) && In(c1));
    mempool.remove(t1);
    BOOST_CHECK(!In(t1));
    BOOST_CHECK(In(c1));
    Clear();
}

BOOST_AUTO_TEST_CASE(no_conflict_no_change)
{
    Clear();
    CTransaction a = Spend(COutPoint(uint256(3001), 0), 1), b = Spend(COutPoint(uint256(3002), 1), 2);
    Put(a);
    Put(b);
    CTransaction other = Spend(COutPoint(uint256(3003), 0), 3);
    mempool.RemoveConflicts(other);
    BOOST_CHECK(In(a) && In(b));
    BOOST_CHECK_EQUAL(mempool.mapTx.size(), 2u);
    Clear();
}

BOOST_AUTO_TEST_SUITE_END()
