// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include "main.h"
#include "util.h"

extern "C" {
    void scrypt_1024_1_1_256(const char *input, char *output);
}

using namespace std;

BOOST_AUTO_TEST_SUITE(scrypt_tests)

BOOST_AUTO_TEST_CASE(scrypt_hashtest)
{
    // Scrypt(1024,1,1) should produce deterministic 256-bit output
    const char input[] = "CorgiCoin scrypt test vector";
    char output1[32], output2[32];

    scrypt_1024_1_1_256(input, output1);
    scrypt_1024_1_1_256(input, output2);

    // Same input must produce same output
    BOOST_CHECK(memcmp(output1, output2, 32) == 0);

    // Different input must produce different output
    const char input2[] = "CorgiCoin scrypt test vector!";
    char output3[32];
    scrypt_1024_1_1_256(input2, output3);
    BOOST_CHECK(memcmp(output1, output3, 32) != 0);

    // Output should not be all zeros
    char zeros[32] = {};
    BOOST_CHECK(memcmp(output1, zeros, 32) != 0);
}

BOOST_AUTO_TEST_CASE(scrypt_80byte_header)
{
    // Real block headers are 80 bytes — verify scrypt handles that size
    char header[80];
    memset(header, 0xAB, sizeof(header));

    char hash[32];
    scrypt_1024_1_1_256(header, hash);

    char zeros[32] = {};
    BOOST_CHECK(memcmp(hash, zeros, 32) != 0);
}

BOOST_AUTO_TEST_SUITE_END()
