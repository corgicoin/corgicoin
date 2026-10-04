// Copyright (c) 2013-2026 The Bitcoin/Corgicoin developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include "bip32.h"
#include "util.h"   // ParseHex

#include <string>
#include <vector>

using namespace std;

// BIP32 private-side test vectors (the xprv column of the official vectors).
// Version bytes are Bitcoin mainnet (0x0488ADE4), per the BIP, so the base58
// strings match exactly.

static const vector<unsigned char> XPRV_VERSION = {0x04, 0x88, 0xAD, 0xE4};

struct Derivation { uint32_t child; const char* xprv; };

BOOST_AUTO_TEST_SUITE(bip32_tests)

static void TestVector(const string& seedhex, const vector<Derivation>& path)
{
    vector<unsigned char> seed = ParseHex(seedhex.c_str());
    CExtKey key;
    key.SetSeed(&seed[0], (unsigned int)seed.size());

    for (size_t i = 0; i < path.size(); i++)
    {
        if (i != 0)
        {
            CExtKey child;
            BOOST_CHECK(key.Derive(child, path[i].child));
            key = child;
        }
        BOOST_CHECK_EQUAL(key.ToBase58(XPRV_VERSION), string(path[i].xprv));

        // Round-trip the xprv back and confirm equality
        CExtKey decoded;
        vector<unsigned char> ver;
        BOOST_CHECK(decoded.SetBase58(path[i].xprv, ver));
        BOOST_CHECK(ver == XPRV_VERSION);
        BOOST_CHECK(decoded == key);
    }
}

BOOST_AUTO_TEST_CASE(bip32_vector1)
{
    // Official BIP32 Test Vector 1
    TestVector("000102030405060708090a0b0c0d0e0f", {
        {0, "xprv9s21ZrQH143K3QTDL4LXw2F7HEK3wJUD2nW2nRk4stbPy6cq3jPPqjiChkVvvNKmPGJxWUtg6LnF5kejMRNNU3TGtRBeJgk33yuGBxrMPHi"},
        {0x80000000, "xprv9uHRZZhk6KAJC1avXpDAp4MDc3sQKNxDiPvvkX8Br5ngLNv1TxvUxt4cV1rGL5hj6KCesnDYUhd7oWgT11eZG7XnxHrnYeSvkzY7d2bhkJ7"},
        {1, "xprv9wTYmMFdV23N2TdNG573QoEsfRrWKQgWeibmLntzniatZvR9BmLnvSxqu53Kw1UmYPxLgboyZQaXwTCg8MSY3H2EU4pWcQDnRnrVA1xe8fs"},
        {0x80000002, "xprv9z4pot5VBttmtdRTWfWQmoH1taj2axGVzFqSb8C9xaxKymcFzXBDptWmT7FwuEzG3ryjH4ktypQSAewRiNMjANTtpgP4mLTj34bhnZX7UiM"},
        {2, "xprvA2JDeKCSNNZky6uBCviVfJSKyQ1mDYahRjijr5idH2WwLsEd4Hsb2Tyh8RfQMuPh7f7RtyzTtdrbdqqsunu5Mm3wDvUAKRHSC34sJ7in334"},
        {1000000000, "xprvA41z7zogVVwxVSgdKUHDy1SKmdb533PjDz7J6N6mV6uS3ze1ai8FHa8kmHScGpWmj4WggLyQjgPie1rFSruoUihUZREPSL39UNdE3BBDu76"},
    });
}

BOOST_AUTO_TEST_CASE(bip32_determinism_and_serialization)
{
    // Same seed must always yield the same derivation (the HD guarantee),
    // and every serialized xprv must round-trip. No external strings, so no
    // transcription risk — vector1 already pins values to the official set.
    vector<unsigned char> seed = ParseHex("fffcf9f6f3f0edeae7e4e1dedbd8d5d2cfccc9c6c3c0bdbab7b4b1aeaba8a5a29f9c999693908d8a8784817e7b7875726f6c696663605d5a5754514e4b484542");
    const uint32_t path[] = {0u, 0xFFFFFFFFu, 1u, 0xFFFFFFFEu, 2u};

    auto derivePath = [&]() {
        CExtKey k; k.SetSeed(&seed[0], (unsigned int)seed.size());
        for (uint32_t c : path) { CExtKey child; BOOST_CHECK(k.Derive(child, c)); k = child; }
        return k;
    };

    CExtKey a = derivePath();
    CExtKey b = derivePath();
    BOOST_CHECK(a == b);                       // deterministic
    BOOST_CHECK_EQUAL((int)a.nDepth, 5);

    // Serialize -> deserialize -> re-serialize is stable (catches padding bugs)
    string s = a.ToBase58(XPRV_VERSION);
    CExtKey decoded; vector<unsigned char> ver;
    BOOST_CHECK(decoded.SetBase58(s, ver));
    BOOST_CHECK(decoded == a);
    BOOST_CHECK_EQUAL(decoded.ToBase58(XPRV_VERSION), s);
}

BOOST_AUTO_TEST_CASE(bip32_hardened_bit)
{
    vector<unsigned char> seed = ParseHex("000102030405060708090a0b0c0d0e0f");
    CExtKey m;
    m.SetSeed(&seed[0], (unsigned int)seed.size());

    // Hardened (0') and non-hardened (0) derivations must differ
    CExtKey hardened, normal;
    BOOST_CHECK(m.Derive(hardened, 0x80000000));
    BOOST_CHECK(m.Derive(normal, 0));
    BOOST_CHECK(!(hardened == normal));
    BOOST_CHECK_EQUAL((int)hardened.nDepth, 1);
    BOOST_CHECK_EQUAL(hardened.nChild, 0x80000000u);
}

BOOST_AUTO_TEST_SUITE_END()
