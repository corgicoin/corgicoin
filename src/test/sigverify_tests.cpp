//
// Signature verification (CKey::Verify): what is accepted and what is not, the same under OpenSSL and under libsecp256k1 (USE_LIBSECP256K1).
//
// Master's check is OpenSSL's ECDSA_verify on the raw bytes, which decodes the DER, checks it by encoding it again and comparing the bytes, and
// accepts a high S. These vectors are those edges: a good signature is accepted (also with its S made high, and with the key written in the
// hybrid 06/07 form), and every encoding that is not what OpenSSL itself would write is refused.
//
#include <boost/test/unit_test.hpp>

#include <openssl/bn.h>
#include <openssl/ecdsa.h>

#include <vector>

#include "key.h"
#include "uint256.h"

namespace {

typedef std::vector<unsigned char> Bytes;

uint256 HashOf(unsigned char n)
{
    uint256 h;
    for (int i = 0; i < 32; i++)
        h.begin()[i] = (unsigned char)(n * 31 + i * 7 + 1);
    return h;
}

bool VerifyWith(const CPubKey& pub, const uint256& hash, const Bytes& sig)
{
    CKey key;
    if (!key.SetPubKey(pub))
        return false;
    return key.Verify(hash, sig);
}

// 0x30 len 0x02 len r 0x02 len s, taken apart (the input is what OpenSSL wrote, so canonical)
void Split(const Bytes& sig, Bytes& r, Bytes& s)
{
    BOOST_REQUIRE(sig.size() > 8 && sig[0] == 0x30 && sig[2] == 0x02);
    const size_t lr = sig[3];
    r.assign(sig.begin() + 4, sig.begin() + 4 + lr);
    BOOST_REQUIRE(sig[4 + lr] == 0x02);
    const size_t ls = sig[5 + lr];
    s.assign(sig.begin() + 6 + lr, sig.begin() + 6 + lr + ls);
}

// DER of two integers given as their content bytes (as they are to be written, padding and all), with a short-form length
Bytes Der(const Bytes& r, const Bytes& s)
{
    Bytes out;
    out.push_back(0x30);
    out.push_back((unsigned char)(2 + r.size() + 2 + s.size()));
    out.push_back(0x02);
    out.push_back((unsigned char)r.size());
    out.insert(out.end(), r.begin(), r.end());
    out.push_back(0x02);
    out.push_back((unsigned char)s.size());
    out.insert(out.end(), s.begin(), s.end());
    return out;
}

const unsigned char ORDER_N[32] = {
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFE,
    0xBA, 0xAE, 0xDC, 0xE6, 0xAF, 0x48, 0xA0, 0x3B, 0xBF, 0xD2, 0x5E, 0x8C, 0xD0, 0x36, 0x41, 0x41};

}

BOOST_AUTO_TEST_SUITE(sigverify_tests)

BOOST_AUTO_TEST_CASE(good_signatures_and_the_forms_of_a_good_key)
{
    for (unsigned char i = 0; i < 6; i++)
    {
        CKey key;
        key.MakeNewKey(i & 1);                                   // compressed and uncompressed
        const uint256 hash = HashOf(i);
        Bytes sig;
        BOOST_REQUIRE(key.Sign(hash, sig));
        const CPubKey pub = key.GetPubKey();
        BOOST_CHECK(VerifyWith(pub, hash, sig));
        BOOST_CHECK(!VerifyWith(pub, HashOf(i + 100), sig));     // not for another hash

        // the high-S twin of the signature: OpenSSL accepts it, and so must the build that normalises
        const unsigned char* p = &sig[0];
        ECDSA_SIG* parsed = d2i_ECDSA_SIG(nullptr, &p, (long)sig.size());
        BOOST_REQUIRE(parsed != nullptr);
        const BIGNUM *pr, *ps;
        ECDSA_SIG_get0(parsed, &pr, &ps);
        BIGNUM* n = BN_bin2bn(ORDER_N, 32, nullptr);
        BIGNUM* high = BN_new();
        BN_sub(high, n, ps);
        BIGNUM* r2 = BN_dup(pr);
        ECDSA_SIG_set0(parsed, r2, high);                       // (the old r and s are freed by the call)
        Bytes twin(80);
        unsigned char* q = &twin[0];
        const int len = i2d_ECDSA_SIG(parsed, &q);
        BOOST_REQUIRE(len > 0);
        twin.resize(len);
        BN_free(n);
        ECDSA_SIG_free(parsed);
        BOOST_CHECK_MESSAGE(VerifyWith(pub, hash, twin), "the high-S form of a good signature is accepted");

        // the key in the hybrid form (06/07, as 04 with the parity of y in the prefix): the same key to OpenSSL
        if (!(i & 1))
        {
            Bytes hybrid = pub.Raw();
            BOOST_REQUIRE_EQUAL(hybrid.size(), 65u);
            hybrid[0] = 0x06 | (hybrid[64] & 1);
            BOOST_CHECK_MESSAGE(VerifyWith(CPubKey(hybrid), hash, sig), "a good signature under the hybrid form of its key");
        }
    }
}

BOOST_AUTO_TEST_CASE(encodings_that_are_not_what_openssl_writes_are_refused)
{
    CKey key;
    key.MakeNewKey(true);
    const uint256 hash = HashOf(7);
    Bytes sig;
    BOOST_REQUIRE(key.Sign(hash, sig));
    const CPubKey pub = key.GetPubKey();
    BOOST_REQUIRE(VerifyWith(pub, hash, sig));
    Bytes r, s;
    Split(sig, r, s);

    // a byte after the sequence (a hash type byte left on)
    Bytes trailing = sig;
    trailing.push_back(0x01);
    BOOST_CHECK(!VerifyWith(pub, hash, trailing));

    // the length of the sequence in the long form
    Bytes longform;
    longform.push_back(0x30);
    longform.push_back(0x81);
    longform.insert(longform.end(), sig.begin() + 1, sig.end());
    BOOST_CHECK(!VerifyWith(pub, hash, longform));

    // r with a pad it does not need (or a second one), s with the same
    Bytes padded_r(1, 0x00);
    padded_r.insert(padded_r.end(), r.begin(), r.end());
    BOOST_CHECK(!VerifyWith(pub, hash, Der(padded_r, s)));
    Bytes padded_s(1, 0x00);
    padded_s.insert(padded_s.end(), s.begin(), s.end());
    BOOST_CHECK(!VerifyWith(pub, hash, Der(r, padded_s)));

    // r or s negative (the pad that its high bit needs taken away), when it has one
    if (r[0] == 0x00 && r.size() > 1)
        BOOST_CHECK(!VerifyWith(pub, hash, Der(Bytes(r.begin() + 1, r.end()), s)));
    if (s[0] == 0x00 && s.size() > 1)
        BOOST_CHECK(!VerifyWith(pub, hash, Der(r, Bytes(s.begin() + 1, s.end()))));

    // zero r, zero s, a negative one-byte number, a number that is too long
    const Bytes one(1, 0x01), zero(1, 0x00), minus(1, 0x80);
    BOOST_CHECK(!VerifyWith(pub, hash, Der(zero, one)));
    BOOST_CHECK(!VerifyWith(pub, hash, Der(one, zero)));
    BOOST_CHECK(!VerifyWith(pub, hash, Der(minus, one)));
    BOOST_CHECK(!VerifyWith(pub, hash, Der(one, minus)));
    BOOST_CHECK(!VerifyWith(pub, hash, Der(Bytes(40, 0x01), one)));

    // r = n and s = n (out of range: 33 bytes, the 00 pad then n)
    Bytes n_enc(1, 0x00);
    n_enc.insert(n_enc.end(), ORDER_N, ORDER_N + 32);
    BOOST_CHECK(!VerifyWith(pub, hash, Der(n_enc, one)));
    BOOST_CHECK(!VerifyWith(pub, hash, Der(one, n_enc)));

    // nothing, and too little
    BOOST_CHECK(!VerifyWith(pub, hash, Bytes()));
    BOOST_CHECK(!VerifyWith(pub, hash, Bytes(sig.begin(), sig.begin() + 7)));
    BOOST_CHECK(!VerifyWith(pub, hash, Bytes(sig.begin(), sig.end() - 1)));

    // and the signature itself is still good
    BOOST_CHECK(VerifyWith(pub, hash, sig));
}

BOOST_AUTO_TEST_SUITE_END()
