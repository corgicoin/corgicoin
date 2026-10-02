// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include "base58.h"
#include "bech32.h"
#include "key.h"

#include <string>
#include <vector>

using namespace std;

BOOST_AUTO_TEST_SUITE(bech32_tests)

BOOST_AUTO_TEST_CASE(bip173_valid_bech32)
{
    // Valid test vectors from BIP-173
    const char* valid[] = {
        "A12UEL5L",
        "a12uel5l",
        "abcdef1qpzry9x8gf2tvdw0s3jn54khce6mua7lmqqqxw",
        "split1checkupstagehandshakeupstreamerranterredcaperred2y9e3w",
    };
    for (const char* s : valid)
    {
        bech32::DecodeResult dec = bech32::Decode(s);
        BOOST_CHECK_MESSAGE(dec.encoding == bech32::Encoding::BECH32, s);
    }
}

BOOST_AUTO_TEST_CASE(bip350_valid_bech32m)
{
    // Valid test vectors from BIP-350
    const char* valid[] = {
        "A1LQFN3A",
        "a1lqfn3a",
        "abcdef1l7aum6echk45nj3s0wdvt2fg8x9yrzpqzd3ryx",
        "?1v759aa",
    };
    for (const char* s : valid)
    {
        bech32::DecodeResult dec = bech32::Decode(s);
        BOOST_CHECK_MESSAGE(dec.encoding == bech32::Encoding::BECH32M, s);
    }
}

BOOST_AUTO_TEST_CASE(invalid_strings)
{
    const char* invalid[] = {
        "A12UEL5M",      // bad checksum (bech32 string, corrupted last char)
        "A12uEL5L",      // mixed case
        "1qzzfhee",      // empty HRP
        "pzry9x0s0muk",  // no separator
        "a1qqqqq",       // checksum too short
        "an84characterslonghumanreadablepartthatcontainsthenumber1andtheexcludedcharactersbio1569pvx", // > 90 chars
    };
    for (const char* s : invalid)
    {
        bech32::DecodeResult dec = bech32::Decode(s);
        BOOST_CHECK_MESSAGE(dec.encoding == bech32::Encoding::INVALID, s);
    }
}

BOOST_AUTO_TEST_CASE(encode_decode_roundtrip)
{
    std::vector<uint8_t> data = {0, 1, 2, 3, 31, 30, 15, 7, 0, 0, 12};
    for (bech32::Encoding enc : {bech32::Encoding::BECH32, bech32::Encoding::BECH32M})
    {
        std::string s = bech32::Encode(enc, "corg", data);
        BOOST_CHECK(!s.empty());
        BOOST_CHECK_EQUAL(s.substr(0, 5), "corg1");
        bech32::DecodeResult dec = bech32::Decode(s);
        BOOST_CHECK(dec.encoding == enc);
        BOOST_CHECK(dec.hrp == "corg");
        BOOST_CHECK(dec.data == data);
    }
}

BOOST_AUTO_TEST_CASE(convertbits_roundtrip)
{
    std::vector<uint8_t> bytes;
    for (int i = 0; i < 20; i++) bytes.push_back((uint8_t)(i * 13 + 7));
    std::vector<uint8_t> five, eight;
    BOOST_CHECK(bech32::ConvertBits(8, 5, true, five, bytes));
    BOOST_CHECK(bech32::ConvertBits(5, 8, false, eight, five));
    BOOST_CHECK(eight == bytes);

    // A 20-byte payload is 160 bits = exactly 32 groups, so there is no
    // padding to tamper with. Use 19 bytes (152 bits -> 31 groups with 3
    // padding bits): non-zero padding must be rejected when pad=false
    std::vector<uint8_t> bytes19(bytes.begin(), bytes.end() - 1);
    std::vector<uint8_t> five19;
    BOOST_CHECK(bech32::ConvertBits(8, 5, true, five19, bytes19));
    std::vector<uint8_t> ok;
    BOOST_CHECK(bech32::ConvertBits(5, 8, false, ok, five19));
    BOOST_CHECK(ok == bytes19);
    five19.back() |= 1;
    std::vector<uint8_t> out;
    BOOST_CHECK(!bech32::ConvertBits(5, 8, false, out, five19));
}

BOOST_AUTO_TEST_CASE(address_roundtrip_keyid)
{
    // 20 deterministic pseudo-random key hashes round-trip through bech32
    for (int n = 0; n < 20; n++)
    {
        uint160 h = 0;
        for (int i = 0; i < 5; i++)
            h = (h << 32) | (uint32_t)(n * 2654435761u + i * 40503u + 12345u);
        CKeyID keyID(h);

        CBitcoinAddress addr;
        addr.Set(keyID);
        std::string b32 = addr.ToBech32();
        BOOST_CHECK_EQUAL(b32.substr(0, 5), "corg1");

        CBitcoinAddress decoded(b32);
        BOOST_CHECK(decoded.IsValid());
        BOOST_CHECK(!decoded.IsScript());
        BOOST_CHECK(decoded.Get() == addr.Get());
        // Same destination as the base58 path
        CBitcoinAddress viaBase58(addr.ToString());
        BOOST_CHECK(viaBase58.Get() == decoded.Get());
    }
}

BOOST_AUTO_TEST_CASE(address_roundtrip_scriptid)
{
    uint160 h = 0;
    for (int i = 0; i < 5; i++)
        h = (h << 32) | (uint32_t)(0xdeadbeefu + i);
    CScriptID scriptID(h);

    CBitcoinAddress addr;
    addr.Set(scriptID);
    std::string b32 = addr.ToBech32();
    BOOST_CHECK_EQUAL(b32.substr(0, 5), "corg1");

    CBitcoinAddress decoded(b32);
    BOOST_CHECK(decoded.IsValid());
    BOOST_CHECK(decoded.IsScript());
    BOOST_CHECK(decoded.Get() == addr.Get());
}

BOOST_AUTO_TEST_CASE(address_rejects_tampering)
{
    uint160 h = 42;
    CBitcoinAddress addr;
    addr.Set(CKeyID(h));
    std::string b32 = addr.ToBech32();

    // Flip one data character: checksum must catch it
    std::string bad = b32;
    size_t i = bad.size() - 10;
    bad[i] = (bad[i] == 'q') ? 'p' : 'q';
    BOOST_CHECK(!CBitcoinAddress(bad).IsValid());

    // Wrong HRP (testnet prefix on mainnet) must be rejected
    BOOST_CHECK(!CBitcoinAddress("t" + b32).IsValid());

    // Uppercase form is valid bech32 (all-upper), decodes to same destination
    std::string upper = b32;
    for (char& c : upper) c = toupper((unsigned char)c);
    BOOST_CHECK(CBitcoinAddress(upper).IsValid());
    BOOST_CHECK(CBitcoinAddress(upper).Get() == addr.Get());
}

BOOST_AUTO_TEST_SUITE_END()
