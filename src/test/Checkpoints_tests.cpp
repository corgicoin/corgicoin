//
// Unit tests for block-chain checkpoints
//
#include <boost/test/unit_test.hpp>

#include "../checkpoints.h"
#include "../main.h"

using namespace std;

BOOST_AUTO_TEST_SUITE(Checkpoints_tests)

BOOST_AUTO_TEST_CASE(sanity)
{
    // CorgiCoin only has a genesis block checkpoint (block 0)
    BOOST_CHECK(Checkpoints::CheckBlock(0, hashGenesisBlockOfficial));

    // Any hash at a non-checkpoint height should succeed:
    uint256 dummyHash = uint256("0x0000000000000000000000000000000000000000000000000000000000000001");
    BOOST_CHECK(Checkpoints::CheckBlock(1, dummyHash));
    BOOST_CHECK(Checkpoints::CheckBlock(1000, dummyHash));

    // Wrong hash at checkpoint 0 should fail:
    BOOST_CHECK(!Checkpoints::CheckBlock(0, dummyHash));

    // Total blocks estimate should be at least 0 (genesis)
    BOOST_CHECK(Checkpoints::GetTotalBlocksEstimate() >= 0);
}

BOOST_AUTO_TEST_SUITE_END()
