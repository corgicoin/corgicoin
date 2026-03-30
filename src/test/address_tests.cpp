// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include "base58.h"
#include "key.h"
#include "util.h"

using namespace std;

BOOST_AUTO_TEST_SUITE(address_tests)

BOOST_AUTO_TEST_CASE(address_prefix)
{
    // CorgiCoin mainnet addresses should start with 'C' (PUBKEY_ADDRESS = 28)
    CKey key;
    key.MakeNewKey(true);
    CPubKey pubkey = key.GetPubKey();
    CBitcoinAddress addr(pubkey.GetID());

    BOOST_CHECK(addr.IsValid());
    string strAddr = addr.ToString();
    BOOST_CHECK_MESSAGE(strAddr[0] == 'C',
        "CorgiCoin address should start with 'C', got: " + strAddr);
}

BOOST_AUTO_TEST_CASE(address_prefix_uncompressed)
{
    CKey key;
    key.MakeNewKey(false);
    CPubKey pubkey = key.GetPubKey();
    CBitcoinAddress addr(pubkey.GetID());

    BOOST_CHECK(addr.IsValid());
    string strAddr = addr.ToString();
    BOOST_CHECK_MESSAGE(strAddr[0] == 'C',
        "Uncompressed CorgiCoin address should start with 'C', got: " + strAddr);
}

BOOST_AUTO_TEST_CASE(address_roundtrip)
{
    // Generate address, convert to string, parse back, verify match
    CKey key;
    key.MakeNewKey(true);
    CPubKey pubkey = key.GetPubKey();
    CKeyID keyID = pubkey.GetID();
    CBitcoinAddress addr(keyID);

    string strAddr = addr.ToString();

    CBitcoinAddress addr2(strAddr);
    BOOST_CHECK(addr2.IsValid());
    BOOST_CHECK(addr.Get() == addr2.Get());
}

BOOST_AUTO_TEST_CASE(address_invalid)
{
    // Empty and garbage strings should not be valid
    CBitcoinAddress bad1("");
    BOOST_CHECK(!bad1.IsValid());

    CBitcoinAddress bad2("notanaddress");
    BOOST_CHECK(!bad2.IsValid());

    // Bitcoin address (prefix 1) should not be valid for CorgiCoin
    CBitcoinAddress bad3("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa");
    BOOST_CHECK(!bad3.IsValid());
}

BOOST_AUTO_TEST_CASE(privkey_prefix)
{
    // Private key WIF encoding should round-trip through CBitcoinSecret
    CKey key;
    key.MakeNewKey(true);

    bool fCompressed;
    CSecret secret = key.GetSecret(fCompressed);
    BOOST_CHECK(fCompressed == true);

    CBitcoinSecret bsecret;
    bsecret.SetSecret(secret, true);
    string strSecret = bsecret.ToString();

    // Parse it back
    CBitcoinSecret bsecret2;
    BOOST_CHECK(bsecret2.SetString(strSecret));

    bool fCompressed2;
    CSecret secret2 = bsecret2.GetSecret(fCompressed2);
    BOOST_CHECK(fCompressed2 == true);
    BOOST_CHECK(secret == secret2);
}

BOOST_AUTO_TEST_SUITE_END()
