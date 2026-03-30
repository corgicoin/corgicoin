// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include "main.h"

extern "C" {
    void scrypt_1024_1_1_256(const char *input, char *output);
}

BOOST_AUTO_TEST_SUITE(scrypt_tests)

BOOST_AUTO_TEST_CASE(scrypt_hashtest)
{
    // Scrypt operates on 80-byte block headers
    char input[80];
    memset(input, 0xAA, sizeof(input));

    char output1[32], output2[32];
    scrypt_1024_1_1_256(input, output1);
    scrypt_1024_1_1_256(input, output2);

    // Same input must produce same output
    BOOST_CHECK(memcmp(output1, output2, 32) == 0);

    // Different input must produce different output
    char input2[80];
    memset(input2, 0xBB, sizeof(input2));

    char output3[32];
    scrypt_1024_1_1_256(input2, output3);
    BOOST_CHECK(memcmp(output1, output3, 32) != 0);

    // Output should not be all zeros
    char zeros[32] = {};
    BOOST_CHECK(memcmp(output1, zeros, 32) != 0);
}

BOOST_AUTO_TEST_CASE(scrypt_single_bit_change)
{
    // Flipping one bit in input should produce completely different output
    char input1[80], input2[80];
    memset(input1, 0x00, sizeof(input1));
    memset(input2, 0x00, sizeof(input2));
    input2[0] = 0x01;

    char hash1[32], hash2[32];
    scrypt_1024_1_1_256(input1, hash1);
    scrypt_1024_1_1_256(input2, hash2);

    BOOST_CHECK(memcmp(hash1, hash2, 32) != 0);
}

BOOST_AUTO_TEST_SUITE_END()
