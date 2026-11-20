//
// Replacement in the pool: the refusals that are reached before any input is looked at.
//
#include <boost/test/unit_test.hpp>

#include "main.h"
#include "db.h"
#include "script.h"

namespace {

CScript PayToNobody(unsigned char n)
{
    std::vector<unsigned char> vch(20, n);
    return CScript() << OP_DUP << OP_HASH160 << vch << OP_EQUALVERIFY << OP_CHECKSIG;
}

CTransaction Spend(const COutPoint& prev, unsigned int nSequence, unsigned char nTag)
{
    CTransaction tx;
    tx.vin.push_back(CTxIn(prev, CScript(), nSequence));
    tx.vout.push_back(CTxOut(1 * COIN, PayToNobody(nTag)));
    return tx;
}

// the pool takes it as it is, with the fee it is said to have paid
void Put(CTransaction& tx, int64 nFee, bool fFeeKnown)
{
    LOCK(mempool.cs);
    const uint256 hash = tx.GetHash();
    mempool.addUnchecked(hash, tx);
    CTxMemPool::PoolEntry entry = { nFee, ::GetSerializeSize(tx, SER_NETWORK, PROTOCOL_VERSION), GetTime(), fFeeKnown, 0 };
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

}

BOOST_AUTO_TEST_SUITE(mempool_replace_tests)

// Without its inputs checked (a transaction put back after a reorganisation, the wallet's own resubmission, a client-mode node) a
// conflict is never a replacement: the fee rules are not run there, and the signalling transaction would go for nothing.
BOOST_AUTO_TEST_CASE(no_replacement_without_input_checks)
{
    Clear();
    mapArgs["-mempoolreplacement"] = "1";      // (off by default: with it on, this is the fee-rules path being skipped)
    const COutPoint coin(uint256(12345), 0);
    CTransaction signalling = Spend(coin, 0xfffffffd, 1);
    Put(signalling, 1000000, true);
    CTransaction newcomer = Spend(coin, 0xfffffffd, 2);
    // the database is not touched when the inputs are not checked: no file is opened for the test
    alignas(CTxDB) static unsigned char abDb[sizeof(CTxDB)];
    CTxDB& txdb = *reinterpret_cast<CTxDB*>(abDb);
    CTxAcceptCheck check;
    check.fTestOnly = true;
    BOOST_CHECK(!mempool.accept(txdb, newcomer, false, nullptr, &check));
    BOOST_CHECK_EQUAL(check.strReject, "txn-mempool-conflict");
    BOOST_CHECK(mempool.exists(signalling.GetHash()));
    Clear();
    mapArgs.erase("-mempoolreplacement");
}

BOOST_AUTO_TEST_SUITE_END()
