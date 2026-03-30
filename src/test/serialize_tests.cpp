// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include "main.h"
#include "serialize.h"
#include "util.h"

using namespace std;

BOOST_AUTO_TEST_SUITE(serialize_tests)

BOOST_AUTO_TEST_CASE(datastream_basic)
{
    // CDataStream write and read back
    CDataStream ss(SER_DISK, CLIENT_VERSION);
    int val = 42;
    ss << val;

    int val2 = 0;
    ss >> val2;
    BOOST_CHECK_EQUAL(val, val2);
}

BOOST_AUTO_TEST_CASE(datastream_string)
{
    CDataStream ss(SER_DISK, CLIENT_VERSION);
    string str = "CorgiCoin";
    ss << str;

    string str2;
    ss >> str2;
    BOOST_CHECK_EQUAL(str, str2);
}

BOOST_AUTO_TEST_CASE(datastream_vector)
{
    CDataStream ss(SER_DISK, CLIENT_VERSION);
    vector<unsigned char> vec = {0xDE, 0xAD, 0xBE, 0xEF};
    ss << vec;

    vector<unsigned char> vec2;
    ss >> vec2;
    BOOST_CHECK(vec == vec2);
}

BOOST_AUTO_TEST_CASE(transaction_serialize_roundtrip)
{
    // Create a simple transaction and verify serialization round-trip
    CTransaction tx;
    tx.nVersion = 1;
    tx.nLockTime = 0;

    CTxIn txin;
    txin.prevout.hash = 0;
    txin.prevout.n = 0xFFFFFFFF;
    txin.nSequence = 0xFFFFFFFF;
    tx.vin.push_back(txin);

    CTxOut txout;
    txout.nValue = 50 * COIN;
    tx.vout.push_back(txout);

    // Serialize
    CDataStream ss(SER_DISK, CLIENT_VERSION);
    ss << tx;

    // Deserialize
    CTransaction tx2;
    ss >> tx2;

    BOOST_CHECK_EQUAL(tx.nVersion, tx2.nVersion);
    BOOST_CHECK_EQUAL(tx.nLockTime, tx2.nLockTime);
    BOOST_CHECK_EQUAL(tx.vin.size(), tx2.vin.size());
    BOOST_CHECK_EQUAL(tx.vout.size(), tx2.vout.size());
    BOOST_CHECK_EQUAL(tx.vout[0].nValue, tx2.vout[0].nValue);
    BOOST_CHECK(tx.GetHash() == tx2.GetHash());
}

BOOST_AUTO_TEST_CASE(block_header_serialize_roundtrip)
{
    CBlock block;
    block.nVersion = 1;
    block.nTime = 1700000000;
    block.nBits = 0x1e0ffff0;
    block.nNonce = 12345;

    CDataStream ss(SER_DISK, CLIENT_VERSION);
    ss << block;

    CBlock block2;
    ss >> block2;

    BOOST_CHECK_EQUAL(block.nVersion, block2.nVersion);
    BOOST_CHECK_EQUAL(block.nTime, block2.nTime);
    BOOST_CHECK_EQUAL(block.nBits, block2.nBits);
    BOOST_CHECK_EQUAL(block.nNonce, block2.nNonce);
}

BOOST_AUTO_TEST_SUITE_END()
