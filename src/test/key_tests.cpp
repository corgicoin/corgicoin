#include <boost/test/unit_test.hpp>

#include <cstring>
#include <new>
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

BOOST_AUTO_TEST_CASE(key_copy_keeps_compression_flag)
{
    CKey a;
    a.MakeNewKey(true);
    BOOST_CHECK(a.IsCompressed());

    CKey assigned; // a default-constructed key is uncompressed
    assigned = a;
    BOOST_CHECK_MESSAGE(assigned.IsCompressed(), "operator= dropped the compressed flag");
    BOOST_CHECK(assigned.GetPubKey() == a.GetPubKey());

    // copy-construct into zeroed storage, so a flag the copy constructor forgets reads as false
    alignas(CKey) unsigned char buf[sizeof(CKey)];
    memset(buf, 0, sizeof(buf));
    CKey* copy = new (buf) CKey(a);
    BOOST_CHECK_MESSAGE(copy->IsCompressed(), "copy constructor did not copy the compressed flag");
    copy->~CKey();

    // and an uncompressed key stays uncompressed
    CKey u;
    u.MakeNewKey(false);
    CKey u2(u);
    BOOST_CHECK(!u2.IsCompressed());
}

BOOST_AUTO_TEST_CASE(key_public_only_key_is_safe)
{
    CKey full;
    full.MakeNewKey(false);
    CKey pubonly;
    BOOST_REQUIRE(pubonly.SetPubKey(full.GetPubKey()));

    bool fCompr = false;
    BOOST_CHECK_THROW(pubonly.GetSecret(fCompr), key_error); // used to dereference NULL
    BOOST_CHECK(!pubonly.IsValid());                         // used to dereference NULL
    BOOST_CHECK(full.IsValid());
}

BOOST_AUTO_TEST_CASE(key_empty_inputs_are_rejected)
{
    CKey k;
    BOOST_CHECK(!k.SetPrivKey(CPrivKey()));
    BOOST_CHECK(!k.SetPubKey(CPubKey()));
    CKey full;
    full.MakeNewKey(true);
    BOOST_CHECK(!full.Verify(uint256(1), std::vector<unsigned char>()));
}

BOOST_AUTO_TEST_CASE(key_compact_signature_roundtrip_and_failure)
{
    CKey key;
    key.MakeNewKey(true);
    uint256 hash(12345);
    std::vector<unsigned char> sig;
    BOOST_REQUIRE(key.SignCompact(hash, sig));
    CKey rec;
    BOOST_CHECK(rec.SetCompactSignature(hash, sig));
    BOOST_CHECK(rec.GetPubKey() == key.GetPubKey());

    // bad shapes and signatures that do not recover a key must be rejected without leaking
    // (the leak itself is only visible to a leak checker: failing calls used to leak an ECDSA_SIG each,
    //  and the CI sanitizers job runs this test under LeakSanitizer)
    CKey bad;
    BOOST_CHECK(!bad.SetCompactSignature(hash, std::vector<unsigned char>(64, 1)));
    for (int i = 0; i < 200; i++)
    {
        std::vector<unsigned char> junk(65, (unsigned char)(0x11 + (i & 0x3f)));
        junk[0] = 27 + (i & 3);
        CKey k;
        k.SetCompactSignature(hash, junk);
    }
}


BOOST_AUTO_TEST_CASE(key_failed_compact_signature_leaves_the_key_unset)
{
    CKey key;
    key.MakeNewKey(true);
    BOOST_REQUIRE(!key.IsNull());
    uint256 hash(777);
    bool fFailed = false;
    // junk of the right shape; some of it does not recover a key
    for (int i = 0; i < 200 && !fFailed; i++)
    {
        std::vector<unsigned char> junk(65, (unsigned char)(0x11 + (i & 0x3f)));
        junk[0] = 27 + (i & 3);
        if (!key.SetCompactSignature(hash, junk))
            fFailed = true;
        else
            key.MakeNewKey(true);
    }
    BOOST_REQUIRE(fFailed);
    // the failed attempt replaced the underlying key, so the object must not claim to hold one
    BOOST_CHECK(key.IsNull());
}

BOOST_AUTO_TEST_CASE(key_setpubkey_resets_the_compression_flag)
{
    CKey compressed, uncompressed;
    compressed.MakeNewKey(true);
    uncompressed.MakeNewKey(false);
    BOOST_CHECK(compressed.IsCompressed());
    BOOST_REQUIRE(compressed.SetPubKey(uncompressed.GetPubKey()));
    BOOST_CHECK(!compressed.IsCompressed());
    BOOST_CHECK(compressed.GetPubKey() == uncompressed.GetPubKey());
}

BOOST_AUTO_TEST_CASE(key_getsecret_pads_a_small_secret)
{
    // a secret with one significant byte must come back as 32 bytes, left-padded with zeros (zero itself is not a key)
    CKey key;
    CSecret one(32, 0);
    one[31] = 1;
    BOOST_REQUIRE(key.SetSecret(one, false));
    bool fCompr = true;
    CSecret secret = key.GetSecret(fCompr);
    BOOST_REQUIRE_EQUAL(secret.size(), 32u);
    for (int i = 0; i < 31; i++)
        BOOST_CHECK_EQUAL((int)secret[i], 0);
    BOOST_CHECK_EQUAL((int)secret[31], 1);
}

BOOST_AUTO_TEST_CASE(key_secret_must_be_in_range)
{
    // a private key is 1 .. n-1, n being the order of the curve
    const char* pszOrder = "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141";
    auto secretFromHex = [](const char* psz) {
        std::vector<unsigned char> v = ParseHex(psz);
        return CSecret(v.begin(), v.end());
    };

    CKey key;
    BOOST_CHECK_THROW(key.SetSecret(CSecret(32, 0), true), key_error);                                                    // zero
    BOOST_CHECK_THROW(key.SetSecret(secretFromHex(pszOrder), true), key_error);                                           // n
    BOOST_CHECK_THROW(key.SetSecret(secretFromHex("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364142"), true), key_error);   // n + 1
    BOOST_CHECK_THROW(key.SetSecret(secretFromHex("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"), true), key_error);   // 2^256 - 1

    CKey low, high;
    BOOST_CHECK(low.SetSecret(secretFromHex("0000000000000000000000000000000000000000000000000000000000000001"), true));              // 1
    BOOST_CHECK(low.GetPubKey().Raw().size() == 33);
    BOOST_CHECK(high.SetSecret(secretFromHex("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140"), true));              // n - 1
    BOOST_CHECK(high.GetPubKey().Raw().size() == 33);
    BOOST_CHECK(low.GetPubKey() != high.GetPubKey());
}

// Signature validity must not depend on the strictness of the linked OpenSSL: Verify reads the encoding leniently, as
// the first OpenSSL releases did and as Bitcoin Core does, and hands OpenSSL the numbers.
BOOST_AUTO_TEST_CASE(verify_accepts_lax_der_encodings_alike_on_every_build)
{
    CKey key;
    key.MakeNewKey(true);
    const uint256 hash = GetRandHash();
    vector<unsigned char> sig;
    BOOST_REQUIRE(key.Sign(hash, sig));
    BOOST_CHECK(key.Verify(hash, sig));

    // take the signature apart: 30 len 02 rlen R 02 slen S
    BOOST_REQUIRE(sig.size() > 8 && sig[0] == 0x30 && sig[2] == 0x02);
    const size_t rlen = sig[3];
    const vector<unsigned char> R(sig.begin() + 4, sig.begin() + 4 + rlen);
    BOOST_REQUIRE(sig[4 + rlen] == 0x02);
    const size_t slen = sig[5 + rlen];
    const vector<unsigned char> S(sig.begin() + 6 + rlen, sig.begin() + 6 + rlen + slen);

    auto Build = [](const vector<unsigned char>& seqLen, const vector<unsigned char>& rLen, const vector<unsigned char>& r,
                    const vector<unsigned char>& sLen, const vector<unsigned char>& s, const vector<unsigned char>& tail) {
        vector<unsigned char> out;
        out.push_back(0x30);
        out.insert(out.end(), seqLen.begin(), seqLen.end());
        out.push_back(0x02);
        out.insert(out.end(), rLen.begin(), rLen.end());
        out.insert(out.end(), r.begin(), r.end());
        out.push_back(0x02);
        out.insert(out.end(), sLen.begin(), sLen.end());
        out.insert(out.end(), s.begin(), s.end());
        out.insert(out.end(), tail.begin(), tail.end());
        return out;
    };
    auto L = [](size_t n) { return vector<unsigned char>(1, static_cast<unsigned char>(n)); };
    const vector<unsigned char> none;
    const size_t body = 2 + rlen + 2 + slen;

    // the plain encoding, rebuilt, still verifies
    BOOST_CHECK(key.Verify(hash, Build(L(body), L(rlen), R, L(slen), S, none)));
    // sequence length in long form, and wrong
    BOOST_CHECK(key.Verify(hash, Build(vector<unsigned char>{0x81, static_cast<unsigned char>(body)}, L(rlen), R, L(slen), S, none)));
    BOOST_CHECK(key.Verify(hash, Build(L(0x7f), L(rlen), R, L(slen), S, none)));
    // integer lengths in long form
    BOOST_CHECK(key.Verify(hash, Build(L(body), vector<unsigned char>{0x81, static_cast<unsigned char>(rlen)}, R, L(slen), S, none)));
    BOOST_CHECK(key.Verify(hash, Build(L(body), L(rlen), R, vector<unsigned char>{0x82, 0x00, static_cast<unsigned char>(slen)}, S, none)));
    // leading zeros in R and S (not minimal)
    vector<unsigned char> Rz(R), Sz(S);
    Rz.insert(Rz.begin(), 2, 0x00);
    Sz.insert(Sz.begin(), 1, 0x00);
    BOOST_CHECK(key.Verify(hash, Build(L(body + 3), L(Rz.size()), Rz, L(Sz.size()), Sz, none)));
    // bytes after the signature
    BOOST_CHECK(key.Verify(hash, Build(L(body), L(rlen), R, L(slen), S, vector<unsigned char>{0x00, 0x01, 0x02})));
    // a value with its first bit set where the encoding needed a zero byte in front: read as unsigned
    vector<unsigned char> Rhigh(R);
    if (Rhigh[0] == 0x00 && Rhigh.size() > 1)
    {
        Rhigh.erase(Rhigh.begin());
        BOOST_CHECK(key.Verify(hash, Build(L(body - 1), L(Rhigh.size()), Rhigh, L(slen), S, none)));
    }

    // and what is not a signature is refused
    BOOST_CHECK(!key.Verify(hash, vector<unsigned char>()));
    BOOST_CHECK(!key.Verify(hash, vector<unsigned char>{0x30}));
    BOOST_CHECK(!key.Verify(hash, vector<unsigned char>{0x30, 0x00}));
    BOOST_CHECK(!key.Verify(hash, vector<unsigned char>{0x31, 0x06, 0x02, 0x01, 0x01, 0x02, 0x01, 0x01}));
    BOOST_CHECK(!key.Verify(hash, Build(L(6), L(1), vector<unsigned char>{0}, L(1), vector<unsigned char>{0}, none)));     // r = s = 0
    BOOST_CHECK(!key.Verify(hash, Build(L(body), L(rlen), R, L(slen + 5), S, none)));                                    // s runs past the end
    vector<unsigned char> Rbig(33, 0x7f);                                                                                // 33 bytes: more than 256 bits
    BOOST_CHECK(!key.Verify(hash, Build(L(2 + 33 + 2 + slen), L(33), Rbig, L(slen), S, none)));
    // another message or another key
    BOOST_CHECK(!key.Verify(GetRandHash(), sig));
    CKey other;
    other.MakeNewKey(true);
    BOOST_CHECK(!other.Verify(hash, sig));
}

BOOST_AUTO_TEST_SUITE_END()
