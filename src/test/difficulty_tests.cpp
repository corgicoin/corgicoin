// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include "main.h"
#include "bignum.h"

#include <vector>

using namespace std;

// LWMA-1 retarget tests — see doc/lwma-retarget-spec.md.
// CalculateNextWorkRequiredLWMA only reads nHeight/nTime/nBits/pprev, so
// synthetic CBlockIndex chains are enough.

static constexpr int64 T = 60;               // target spacing
static constexpr int64 N = LWMA_WINDOW;      // 90
static constexpr unsigned int STEADY_BITS = 0x1d0fffff; // well below pow limit

namespace {

// Chain of `count` headers: block i is `spacing` seconds after block i-1,
// all at `nBits`. Returned vector owns the indices; pprev points inside it.
vector<CBlockIndex> BuildChain(int count, unsigned int nBits, int64 spacing)
{
    vector<CBlockIndex> chain(count);
    for (int i = 0; i < count; i++)
    {
        chain[i].nHeight = i;
        chain[i].nTime = 1000000000u + (unsigned int)(i * spacing);
        chain[i].nBits = nBits;
        chain[i].pprev = (i > 0) ? &chain[i - 1] : nullptr;
    }
    return chain;
}

CBigNum TargetOf(unsigned int nBits)
{
    CBigNum bn;
    bn.SetCompact(nBits);
    return bn;
}

} // namespace

BOOST_AUTO_TEST_SUITE(difficulty_tests)

BOOST_AUTO_TEST_CASE(lwma_insufficient_history_returns_pow_limit)
{
    vector<CBlockIndex> chain = BuildChain((int)N, STEADY_BITS, T);
    // Tip height N-1 < N: not enough history
    unsigned int nBits = CalculateNextWorkRequiredLWMA(&chain.back());
    CBigNum bnLimit(~uint256(0) >> 20);
    BOOST_CHECK_EQUAL(nBits, bnLimit.GetCompact());
    BOOST_CHECK_EQUAL(CalculateNextWorkRequiredLWMA(nullptr), bnLimit.GetCompact());
}

BOOST_AUTO_TEST_CASE(lwma_steady_state_holds_difficulty)
{
    // Exact T spacing: weighted solvetime sum equals k, so the next target
    // is exactly the (uniform) average target
    vector<CBlockIndex> chain = BuildChain(200, STEADY_BITS, T);
    unsigned int nBits = CalculateNextWorkRequiredLWMA(&chain.back());
    BOOST_CHECK_EQUAL(nBits, STEADY_BITS);
}

BOOST_AUTO_TEST_CASE(lwma_hashrate_arrival_drops_target)
{
    // Whole window solved 10x too fast: next target must be ~1/10th
    vector<CBlockIndex> chain = BuildChain(200, STEADY_BITS, T / 10);
    unsigned int nBits = CalculateNextWorkRequiredLWMA(&chain.back());
    CBigNum bnNew = TargetOf(nBits);
    CBigNum bnOld = TargetOf(STEADY_BITS);
    BOOST_CHECK(bnNew < bnOld / 9);
    BOOST_CHECK(bnNew > bnOld / 11);
}

BOOST_AUTO_TEST_CASE(lwma_hashrate_departure_raises_target_every_block)
{
    // Slow blocks (at the 6*T solvetime cap): target must rise ~6x, and it
    // must keep rising as more slow blocks are appended — the property the
    // legacy interval retarget lacks between boundaries
    vector<CBlockIndex> slow = BuildChain(200, STEADY_BITS, 6 * T);
    unsigned int nBits1 = CalculateNextWorkRequiredLWMA(&slow[150]);
    unsigned int nBits2 = CalculateNextWorkRequiredLWMA(&slow[151]);
    CBigNum bnOld = TargetOf(STEADY_BITS);
    BOOST_CHECK(TargetOf(nBits1) > bnOld * 5);
    BOOST_CHECK(TargetOf(nBits1) < bnOld * 7);
    // (equal is allowed at the cap plateau; must never decrease)
    BOOST_CHECK(TargetOf(nBits2) >= TargetOf(nBits1));
}

BOOST_AUTO_TEST_CASE(lwma_partial_arrival_moves_target_between_bounds)
{
    // Second half of the window fast, first half steady: next target lands
    // strictly between the all-steady and all-fast outcomes, closer to fast
    // because recent blocks carry the higher weights
    vector<CBlockIndex> chain = BuildChain(200, STEADY_BITS, T);
    for (int i = 155; i < 200; i++)
    {
        chain[i].nTime = chain[i - 1].nTime + (unsigned int)(T / 10);
    }
    unsigned int nBits = CalculateNextWorkRequiredLWMA(&chain.back());
    CBigNum bnNew = TargetOf(nBits);
    CBigNum bnOld = TargetOf(STEADY_BITS);
    BOOST_CHECK(bnNew < bnOld);
    BOOST_CHECK(bnNew > bnOld / 10);
    // More than half the weighted mass is in the fast half (weights 46..90)
    BOOST_CHECK(bnNew < bnOld / 2);
}

BOOST_AUTO_TEST_CASE(lwma_non_monotonic_timestamps_bounded)
{
    // Alternating far-forward and backward timestamps: the monotonic view
    // plus the 6*T cap keep the result within sane bounds of steady state
    vector<CBlockIndex> chain = BuildChain(200, STEADY_BITS, T);
    for (int i = 120; i < 200; i += 2)
    {
        chain[i].nTime += 7200;                 // forward jump
        if (i + 1 < 200)
            chain[i + 1].nTime -= 7000;         // then backward
    }
    unsigned int nBits = CalculateNextWorkRequiredLWMA(&chain.back());
    CBigNum bnNew = TargetOf(nBits);
    CBigNum bnOld = TargetOf(STEADY_BITS);
    BOOST_CHECK(bnNew <= bnOld * 6);
    BOOST_CHECK(bnNew >= bnOld / 6);
}

BOOST_AUTO_TEST_CASE(lwma_clamps_to_pow_limit)
{
    // Already at minimum difficulty with slow blocks: cannot exceed limit
    CBigNum bnLimit(~uint256(0) >> 20);
    vector<CBlockIndex> chain = BuildChain(200, bnLimit.GetCompact(), 6 * T);
    unsigned int nBits = CalculateNextWorkRequiredLWMA(&chain.back());
    BOOST_CHECK_EQUAL(nBits, bnLimit.GetCompact());
}

BOOST_AUTO_TEST_SUITE_END()
