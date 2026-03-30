#include <boost/test/unit_test.hpp>

#include <string>
#include <vector>

#include "key.h"
#include "base58.h"
#include "uint256.h"
#include "util.h"

using namespace std;

BOOST_AUTO_TEST_SUITE(key_tests)

BOOST_AUTO_TEST_CASE(key_test1)
{
    // Generate fresh keys for testing rather than using hardcoded values
    // (avoids dependency on specific address prefix bytes)
    // Generate two random private keys, then create compressed/uncompressed variants
    // from the same secret (so cross-verification works)
    CKey key1tmp, key2tmp;
    key1tmp.MakeNewKey(false);
    key2tmp.MakeNewKey(false);

    bool fCompressedTmp;
    CSecret secret1 = key1tmp.GetSecret(fCompressedTmp);
    CSecret secret2 = key2tmp.GetSecret(fCompressedTmp);

    CKey key1, key2, key1C, key2C;
    key1.SetSecret(secret1, false);   // uncompressed
    key2.SetSecret(secret2, false);   // uncompressed
    key1C.SetSecret(secret1, true);   // compressed (same private key as key1)
    key2C.SetSecret(secret2, true);   // compressed (same private key as key2)

    CSecret secret1C = secret1;

    CBitcoinSecret bsecret1;
    bsecret1.SetSecret(secret1, false);
    string strSecret1 = bsecret1.ToString();

    CBitcoinSecret bsecret1C;
    bsecret1C.SetSecret(secret1C, true);
    string strSecret1C = bsecret1C.ToString();

    // Parse back from string
    CBitcoinSecret bsecret1_parsed;
    BOOST_CHECK(bsecret1_parsed.SetString(strSecret1));
    bool fCompressed;
    CSecret secret1_roundtrip = bsecret1_parsed.GetSecret(fCompressed);
    BOOST_CHECK(fCompressed == false);
    BOOST_CHECK(secret1 == secret1_roundtrip);

    CBitcoinSecret bsecret1C_parsed;
    BOOST_CHECK(bsecret1C_parsed.SetString(strSecret1C));
    CSecret secret1C_roundtrip = bsecret1C_parsed.GetSecret(fCompressed);
    BOOST_CHECK(fCompressed == true);
    BOOST_CHECK(secret1C == secret1C_roundtrip);

    // Verify address round-trip
    CPubKey pubkey1 = key1.GetPubKey();
    CPubKey pubkey1C = key1C.GetPubKey();

    CBitcoinAddress addr1(pubkey1.GetID());
    CBitcoinAddress addr2(pubkey1C.GetID());

    BOOST_CHECK(addr1.IsValid());
    BOOST_CHECK(addr2.IsValid());
    BOOST_CHECK(addr1.Get() == CTxDestination(pubkey1.GetID()));
    BOOST_CHECK(addr2.Get() == CTxDestination(pubkey1C.GetID()));

    // Verify CorgiCoin address prefix (addresses should start with 'C')
    string strAddr1 = addr1.ToString();
    BOOST_CHECK(strAddr1[0] == 'C');

    // Sign and verify
    for (int n = 0; n < 16; n++)
    {
        string strMsg = strprintf("Very secret message %i: 11", n);
        uint256 hashMsg = Hash(strMsg.begin(), strMsg.end());

        // normal signatures
        vector<unsigned char> sign1, sign2, sign1C, sign2C;

        BOOST_CHECK(key1.Sign (hashMsg, sign1));
        BOOST_CHECK(key2.Sign (hashMsg, sign2));
        BOOST_CHECK(key1C.Sign(hashMsg, sign1C));
        BOOST_CHECK(key2C.Sign(hashMsg, sign2C));

        BOOST_CHECK( key1.Verify(hashMsg, sign1));
        BOOST_CHECK(!key1.Verify(hashMsg, sign2));
        BOOST_CHECK( key1.Verify(hashMsg, sign1C));
        BOOST_CHECK(!key1.Verify(hashMsg, sign2C));

        BOOST_CHECK(!key2.Verify(hashMsg, sign1));
        BOOST_CHECK( key2.Verify(hashMsg, sign2));
        BOOST_CHECK(!key2.Verify(hashMsg, sign1C));
        BOOST_CHECK( key2.Verify(hashMsg, sign2C));

        BOOST_CHECK( key1C.Verify(hashMsg, sign1));
        BOOST_CHECK(!key1C.Verify(hashMsg, sign2));
        BOOST_CHECK( key1C.Verify(hashMsg, sign1C));
        BOOST_CHECK(!key1C.Verify(hashMsg, sign2C));

        BOOST_CHECK(!key2C.Verify(hashMsg, sign1));
        BOOST_CHECK( key2C.Verify(hashMsg, sign2));
        BOOST_CHECK(!key2C.Verify(hashMsg, sign1C));
        BOOST_CHECK( key2C.Verify(hashMsg, sign2C));

        // compact signatures (with key recovery)
        vector<unsigned char> csign1, csign2, csign1C, csign2C;

        BOOST_CHECK(key1.SignCompact (hashMsg, csign1));
        BOOST_CHECK(key2.SignCompact (hashMsg, csign2));
        BOOST_CHECK(key1C.SignCompact(hashMsg, csign1C));
        BOOST_CHECK(key2C.SignCompact(hashMsg, csign2C));

        CKey rkey1, rkey2, rkey1C, rkey2C;

        BOOST_CHECK(rkey1.SetCompactSignature (hashMsg, csign1));
        BOOST_CHECK(rkey2.SetCompactSignature (hashMsg, csign2));
        BOOST_CHECK(rkey1C.SetCompactSignature(hashMsg, csign1C));
        BOOST_CHECK(rkey2C.SetCompactSignature(hashMsg, csign2C));

        BOOST_CHECK(rkey1.GetPubKey()  == key1.GetPubKey());
        BOOST_CHECK(rkey2.GetPubKey()  == key2.GetPubKey());
        BOOST_CHECK(rkey1C.GetPubKey() == key1C.GetPubKey());
        BOOST_CHECK(rkey2C.GetPubKey() == key2C.GetPubKey());
    }
}

BOOST_AUTO_TEST_SUITE_END()
