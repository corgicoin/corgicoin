// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include "main.h"
#include "util.h"

using namespace std;

// Declared in main.cpp
extern int64 GetBlockValue(int nHeight, int64 nFees, uint256 prevHash);

BOOST_AUTO_TEST_SUITE(blockreward_tests)

BOOST_AUTO_TEST_CASE(reward_tiers)
{
    // Use a fixed prevHash for deterministic testing
    uint256 prevHash("0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890");

    // Tier 1: blocks 0-99999, max 1,000,000 CORG
    int64 reward1 = GetBlockValue(50000, 0, prevHash);
    BOOST_CHECK(reward1 >= 1 * COIN);
    BOOST_CHECK(reward1 <= 1000000 * COIN);

    // Tier 2: blocks 100000-199999, max 500,000 CORG
    int64 reward2 = GetBlockValue(150000, 0, prevHash);
    BOOST_CHECK(reward2 >= 1 * COIN);
    BOOST_CHECK(reward2 <= 500000 * COIN);

    // Tier 3: blocks 200000-299999, max 250,000 CORG
    int64 reward3 = GetBlockValue(250000, 0, prevHash);
    BOOST_CHECK(reward3 >= 1 * COIN);
    BOOST_CHECK(reward3 <= 250000 * COIN);

    // Tier 4: blocks 300000-399999, max 125,000 CORG
    int64 reward4 = GetBlockValue(350000, 0, prevHash);
    BOOST_CHECK(reward4 >= 1 * COIN);
    BOOST_CHECK(reward4 <= 125000 * COIN);

    // Tier 5: blocks 400000-499999, max 62,500 CORG
    int64 reward5 = GetBlockValue(450000, 0, prevHash);
    BOOST_CHECK(reward5 >= 1 * COIN);
    BOOST_CHECK(reward5 <= 62500 * COIN);

    // Tier 6: blocks 500000-599999, max 31,250 CORG
    int64 reward6 = GetBlockValue(550000, 0, prevHash);
    BOOST_CHECK(reward6 >= 1 * COIN);
    BOOST_CHECK(reward6 <= 31250 * COIN);

    // Tier 7: blocks 600000+, flat 10,000 CORG
    int64 reward7 = GetBlockValue(700000, 0, prevHash);
    BOOST_CHECK_EQUAL(reward7, 10000 * COIN);
}

BOOST_AUTO_TEST_CASE(reward_flat_after_600k)
{
    uint256 hash1("0x1111111111111111111111111111111111111111111111111111111111111111");
    uint256 hash2("0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff");

    // After block 600000, reward is always 10000 CORG regardless of hash
    BOOST_CHECK_EQUAL(GetBlockValue(600000, 0, hash1), 10000 * COIN);
    BOOST_CHECK_EQUAL(GetBlockValue(600000, 0, hash2), 10000 * COIN);
    BOOST_CHECK_EQUAL(GetBlockValue(1000000, 0, hash1), 10000 * COIN);
}

BOOST_AUTO_TEST_CASE(reward_includes_fees)
{
    uint256 prevHash("0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890");
    int64 fees = 5 * COIN;

    int64 reward_no_fees = GetBlockValue(700000, 0, prevHash);
    int64 reward_with_fees = GetBlockValue(700000, fees, prevHash);

    BOOST_CHECK_EQUAL(reward_with_fees, reward_no_fees + fees);
}

BOOST_AUTO_TEST_CASE(reward_deterministic)
{
    // Same height + same prevHash = same reward
    uint256 prevHash("0xdeadbeef12345678deadbeef12345678deadbeef12345678deadbeef12345678");

    int64 r1 = GetBlockValue(50000, 0, prevHash);
    int64 r2 = GetBlockValue(50000, 0, prevHash);
    BOOST_CHECK_EQUAL(r1, r2);

    // Different prevHash = likely different reward (random seed differs)
    uint256 prevHash2("0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef");
    int64 r3 = GetBlockValue(50000, 0, prevHash2);
    // Not guaranteed to differ, but with 1M possible values it's extremely likely
    // Just check both are in valid range
    BOOST_CHECK(r3 >= 1 * COIN);
    BOOST_CHECK(r3 <= 1000000 * COIN);
}

BOOST_AUTO_TEST_CASE(chain_constants)
{
    // Verify key chain parameters
    BOOST_CHECK_EQUAL(COIN, 100000000LL);
    BOOST_CHECK_EQUAL(CENT, 1000000LL);
    BOOST_CHECK_EQUAL(COINBASE_MATURITY, 30);
    BOOST_CHECK_EQUAL(MAX_MONEY, 10000000000LL * COIN);
}

BOOST_AUTO_TEST_SUITE_END()
