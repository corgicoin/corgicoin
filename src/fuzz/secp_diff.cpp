// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

// Does the node's signature check (CKey::Verify) accept exactly the signatures that master accepts?
//
//   secp_diff [iterations=200000] [seed=1]
//
// Master asks OpenSSL: o2i_ECPublicKey for the public key and ECDSA_verify on the raw signature bytes (which reads the signature, writes it again
// and refuses it if the bytes differ). That is the reference here, called directly, not through CKey. It is compared with CKey::Verify, which
// with -DUSE_LIBSECP256K1=ON is libsecp256k1 behind a canonical-DER check, and with it off is OpenSSL again (then the run only tests this harness).
// Valid signatures are made and then damaged the ways old transactions are known to be odd: long-form lengths, extra leading zeros, a missing
// zero pad, bytes after the sequence, a wrong sequence length, a high S, an S or R out of range, uncompressed / compressed / hybrid public keys with
// the wrong parity, a flipped bit anywhere, a truncated signature. Then a fixed list of public keys that are not points (the single byte 0x00,
// which OpenSSL reads as the point at infinity) with signatures made to verify under them. Exit status 1 on any difference, with the case printed.

#include "key.h"
#include "main.h"
#include "ui_interface.h"
#include "wallet.h"

#include <openssl/bn.h>
#include <openssl/ec.h>
#include <openssl/ecdsa.h>
#include <openssl/err.h>
#include <openssl/obj_mac.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <random>
#include <string>
#include <vector>

CClientUIInterface uiInterface;         // defined in init.cpp, which is left out
std::unique_ptr<CWallet> pwalletMain;   // likewise
void Shutdown(void* parg) { exit(0); }
void StartShutdown() { exit(0); }

typedef std::vector<unsigned char> Bytes;

static const unsigned char ORDER[32] = {
    0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0xFE,
    0xBA,0xAE,0xDC,0xE6,0xAF,0x48,0xA0,0x3B,0xBF,0xD2,0x5E,0x8C,0xD0,0x36,0x41,0x41};

static std::string Hex(const Bytes& v)
{
    std::string s;
    char b[3];
    for (unsigned char c : v) { snprintf(b, sizeof(b), "%02x", c); s += b; }
    return s;
}

// n - x (x in [1, n-1]), big endian, 32 bytes
static void NegateModOrder(const unsigned char* x, unsigned char* out)
{
    int borrow = 0;
    for (int i = 31; i >= 0; i--)
    {
        int d = (int)ORDER[i] - (int)x[i] - borrow;
        borrow = d < 0;
        out[i] = (unsigned char)(d & 0xff);
    }
}

static Bytes EncodeInt(const unsigned char* v32, std::mt19937_64& rng, bool fPadHigh)
{
    // minimal big-endian, with a 0x00 in front when the high bit is set (the right way) unless told not to, and sometimes extra zeros
    size_t first = 0;
    while (first < 31 && v32[first] == 0)
        first++;
    Bytes out;
    const unsigned extra = rng() % 5 == 0 ? rng() % 3 + 1 : 0;
    for (unsigned i = 0; i < extra; i++)
        out.push_back(0);
    if ((v32[first] & 0x80) && fPadHigh && extra == 0)
        out.push_back(0);
    if (rng() % 7 == 0 && first > 0)                                // sometimes keep leading zeros that minimal encoding drops
        first -= (size_t)(rng() % (first + 1));
    out.insert(out.end(), v32 + first, v32 + 32);
    return out;
}

static void PutLen(Bytes& out, size_t len, bool fLong, std::mt19937_64& rng)
{
    if (!fLong && len < 128)
    {
        out.push_back((unsigned char)len);
        return;
    }
    const unsigned width = 1 + rng() % 2;                           // one or two length bytes, long form
    out.push_back((unsigned char)(0x80 | width));
    if (width == 2)
        out.push_back((unsigned char)(len >> 8));
    out.push_back((unsigned char)(len & 0xff));
}

// the numbers in a form that is mostly odd (see the list at the top)
static Bytes EncodeSigOdd(const unsigned char* r32, const unsigned char* s32, std::mt19937_64& rng)
{
    const bool fPad = rng() % 6 != 0;           // now and then leave out the pad that a high first bit needs
    Bytes r = EncodeInt(r32, rng, fPad), s = EncodeInt(s32, rng, fPad);
    Bytes body;
    body.push_back(0x02); PutLen(body, r.size(), rng() % 8 == 0, rng); body.insert(body.end(), r.begin(), r.end());
    body.push_back(0x02); PutLen(body, s.size(), rng() % 8 == 0, rng); body.insert(body.end(), s.begin(), s.end());
    Bytes sig;
    sig.push_back(0x30);
    size_t seqlen = body.size();
    if (rng() % 9 == 0)
        seqlen = rng() % 300;                   // a sequence length that is simply wrong
    PutLen(sig, seqlen, rng() % 8 == 0, rng);
    sig.insert(sig.end(), body.begin(), body.end());
    const unsigned trailing = rng() % 6 == 0 ? rng() % 4 + 1 : 0;   // bytes after the sequence, as a hash type byte would be
    for (unsigned i = 0; i < trailing; i++)
        sig.push_back((unsigned char)rng());
    return sig;
}

// the canonical DER of two numbers (what OpenSSL writes), from big-endian 32-byte values
static Bytes EncodeSigDER(const unsigned char* r32, const unsigned char* s32)
{
    ECDSA_SIG* sig = ECDSA_SIG_new();
    BIGNUM* r = BN_bin2bn(r32, 32, nullptr);
    BIGNUM* s = BN_bin2bn(s32, 32, nullptr);
    ECDSA_SIG_set0(sig, r, s);
    Bytes out(80);
    unsigned char* p = &out[0];
    const int len = i2d_ECDSA_SIG(sig, &p);
    ECDSA_SIG_free(sig);
    out.resize(len > 0 ? len : 0);
    return out;
}

// the signature as master reads it: OpenSSL, on the raw bytes
static bool ReferenceAccepts(const Bytes& pub, const uint256& hash, const Bytes& sig)
{
    if (pub.empty() || sig.empty())
        return false;
    EC_KEY* key = EC_KEY_new_by_curve_name(NID_secp256k1);
    const unsigned char* p = &pub[0];
    bool fOk = false;
    if (o2i_ECPublicKey(&key, &p, (long)pub.size()))
        fOk = ECDSA_verify(0, (const unsigned char*)&hash, sizeof(hash), &sig[0], (int)sig.size(), key) == 1;
    EC_KEY_free(key);
    return fOk;
}

// the signature as this build of the node reads it
static bool NodeAccepts(const Bytes& pub, const uint256& hash, const Bytes& sig)
{
    CKey key;
    if (!key.SetPubKey(CPubKey(pub)))
        return false;
    return key.Verify(hash, sig);
}

static uint64_t nDiff = 0;
static uint64_t nAccepted = 0, nRejected = 0;

static void Compare(const char* what, const Bytes& pub, const uint256& hash, const Bytes& sig)
{
    const bool fA = ReferenceAccepts(pub, hash, sig);
    const bool fB = NodeAccepts(pub, hash, sig);
    (fA ? nAccepted : nRejected)++;
    if (fA != fB)
    {
        nDiff++;
        printf("DIFFERENT (%s): master (OpenSSL) %s, this build %s\n  pubkey %s\n  hash   %s\n  sig    %s\n", what, fA ? "accepts" : "rejects", fB ? "accepts" : "rejects",
               Hex(pub).c_str(), hash.GetHex().c_str(), Hex(sig).c_str());
    }
}

// Signatures that verify under the point at infinity: with s = 1 the check is r == x(hash * G) (mod n), whatever the "public key" is
static void InfinityVectors(std::mt19937_64& rng)
{
    EC_GROUP* group = EC_GROUP_new_by_curve_name(NID_secp256k1);
    BN_CTX* ctx = BN_CTX_new();
    BIGNUM* order = BN_new();
    EC_GROUP_get_order(group, order, ctx);
    const Bytes keys[] = { Bytes{0x00}, Bytes{0x00, 0x00}, Bytes{0x04}, Bytes{0x02}, Bytes{0x06} };
    for (int i = 0; i < 20; i++)
    {
        uint256 hash;
        for (int j = 0; j < 32; j++)
            hash.begin()[j] = (unsigned char)rng();
        BIGNUM* z = BN_bin2bn((const unsigned char*)&hash, 32, nullptr);
        BN_mod(z, z, order, ctx);
        EC_POINT* R = EC_POINT_new(group);
        EC_POINT_mul(group, R, z, nullptr, nullptr, ctx);              // z * G
        BIGNUM* x = BN_new();
        EC_POINT_get_affine_coordinates(group, R, x, nullptr, ctx);
        BN_mod(x, x, order, ctx);
        unsigned char r32[32], s32[32];
        BN_bn2binpad(x, r32, 32);
        memset(s32, 0, 32);
        s32[31] = 1;
        const Bytes sig = EncodeSigDER(r32, s32);
        for (const Bytes& k : keys)
            Compare("a key that is not a point", k, hash, sig);
        // with s = n - 1 (high S) the same r verifies under infinity too, and so with odd encodings of the same numbers
        unsigned char hs32[32];
        NegateModOrder(s32, hs32);
        const Bytes sigHigh = EncodeSigDER(r32, hs32);
        for (const Bytes& k : keys)
        {
            Compare("infinity, high S", k, hash, sigHigh);
            Compare("infinity, odd encoding", k, hash, EncodeSigOdd(r32, s32, rng));
            Compare("infinity, odd encoding, high S", k, hash, EncodeSigOdd(r32, hs32, rng));
        }
        BN_free(x);
        EC_POINT_free(R);
        BN_free(z);
    }
    BN_free(order);
    BN_CTX_free(ctx);
    EC_GROUP_free(group);
}

// hand-written signatures with the one-byte numbers DER can get wrong (a zero, a negative), under a real key
static void SmallNumberVectors(std::mt19937_64& rng)
{
    const Bytes sigs[] = {
        Bytes{0x30, 0x06, 0x02, 0x01, 0x00, 0x02, 0x01, 0x00},      // r = 0, s = 0
        Bytes{0x30, 0x06, 0x02, 0x01, 0x80, 0x02, 0x01, 0x01},      // r = -128 (a negative integer)
        Bytes{0x30, 0x06, 0x02, 0x01, 0x01, 0x02, 0x01, 0x80},      // s = -128
        Bytes{0x30, 0x06, 0x02, 0x01, 0x01, 0x02, 0x01, 0x00},      // s = 0
        Bytes{0x30, 0x06, 0x02, 0x01, 0x00, 0x02, 0x01, 0x01},      // r = 0
        Bytes{0x30, 0x06, 0x02, 0x01, 0x01, 0x02, 0x01, 0x01},      // r = 1, s = 1
        Bytes{0x30, 0x08, 0x02, 0x02, 0x00, 0x01, 0x02, 0x02, 0x00, 0x01},    // a pad on a number that does not need one
    };
    for (int i = 0; i < 20; i++)
    {
        CKey key;
        key.MakeNewKey(i & 1);
        const Bytes pub = key.GetPubKey().Raw();
        uint256 hash;
        for (int j = 0; j < 32; j++)
            hash.begin()[j] = (unsigned char)rng();
        for (const Bytes& s : sigs)
            Compare("small numbers", pub, hash, s);
    }
}

// r in [n, p): the signature is valid if r is taken mod n, and neither side may take it. Pick x = n + t on the curve, R = (x, y), s = 1,
// and derive Q = (R - hash * G) / r, so that the check would pass for r mod n.
static void RangeVectors(std::mt19937_64& rng)
{
    EC_GROUP* group = EC_GROUP_new_by_curve_name(NID_secp256k1);
    BN_CTX* ctx = BN_CTX_new();
    BIGNUM* order = BN_new();
    EC_GROUP_get_order(group, order, ctx);
    for (int i = 0; i < 10; i++)
    {
        uint256 hash;
        for (int j = 0; j < 32; j++)
            hash.begin()[j] = (unsigned char)rng();
        BIGNUM* z = BN_bin2bn((const unsigned char*)&hash, 32, nullptr);
        BN_mod(z, z, order, ctx);
        BIGNUM* nz = BN_new();
        BN_sub(nz, order, z);                                       // n - z, so that (n - z) * G = -z * G
        BIGNUM* t = BN_new();
        BN_set_word(t, 1 + rng() % 1000);
        BIGNUM* x = BN_new();
        EC_POINT* R = EC_POINT_new(group);
        for (;;)
        {
            BN_add(x, order, t);
            if (EC_POINT_set_compressed_coordinates(group, R, x, 0, ctx) == 1)
                break;
            ERR_clear_error();
            BN_add_word(t, 1);
        }
        BIGNUM* one = BN_new();
        BN_one(one);
        EC_POINT* P = EC_POINT_new(group);
        EC_POINT_mul(group, P, nz, R, one, ctx);                    // R - z * G
        BIGNUM* rinv = BN_mod_inverse(nullptr, t, order, ctx);      // x mod n is t
        EC_POINT* Q = EC_POINT_new(group);
        EC_POINT_mul(group, Q, nullptr, P, rinv, ctx);
        unsigned char pub[65];
        const size_t len = EC_POINT_point2oct(group, Q, POINT_CONVERSION_UNCOMPRESSED, pub, sizeof(pub), ctx);
        unsigned char r32[32], s32[32];
        BN_bn2binpad(x, r32, 32);
        memset(s32, 0, 32);
        s32[31] = 1;
        Compare("r in [n, p)", Bytes(pub, pub + len), hash, EncodeSigDER(r32, s32));
        // and the same with r reduced, which is a valid signature that both must accept
        unsigned char rr32[32];
        BN_bn2binpad(t, rr32, 32);
        Compare("r reduced mod n", Bytes(pub, pub + len), hash, EncodeSigDER(rr32, s32));
        EC_POINT_free(Q);
        BN_free(rinv);
        EC_POINT_free(P);
        BN_free(one);
        EC_POINT_free(R);
        BN_free(x);
        BN_free(t);
        BN_free(nz);
        BN_free(z);
    }
    BN_free(order);
    BN_CTX_free(ctx);
    EC_GROUP_free(group);
}

int main(int argc, char** argv)
{
    const uint64_t nIter = argc > 1 ? strtoull(argv[1], nullptr, 10) : 200000;
    const uint64_t nSeed = argc > 2 ? strtoull(argv[2], nullptr, 10) : 1;
    std::mt19937_64 rng(nSeed);

    InfinityVectors(rng);
    SmallNumberVectors(rng);
    RangeVectors(rng);

    for (uint64_t it = 0; it < nIter && nDiff < 20; it++)
    {
        // a key, a hash, a valid signature
        CKey key;
        key.MakeNewKey(rng() & 1);
        CPubKey cpub = key.GetPubKey();
        Bytes pub = cpub.Raw();
        uint256 hash;
        for (int i = 0; i < 32; i++)
            hash.begin()[i] = (unsigned char)rng();
        Bytes good;
        if (!key.Sign(hash, good))
            continue;
        const unsigned char* pg = &good[0];
        ECDSA_SIG* parsed = d2i_ECDSA_SIG(nullptr, &pg, (long)good.size());
        if (parsed == nullptr)
        {
            fprintf(stderr, "the node's own signature does not parse\n");
            return 2;
        }
        const BIGNUM *pr, *ps;
        ECDSA_SIG_get0(parsed, &pr, &ps);
        unsigned char r32[32], s32[32];
        BN_bn2binpad(pr, r32, 32);
        BN_bn2binpad(ps, s32, 32);
        ECDSA_SIG_free(parsed);

        // damage the numbers
        switch (rng() % 8)
        {
        case 0: { unsigned char t[32]; NegateModOrder(s32, t); memcpy(s32, t, 32); } break;     // the high-S twin of a valid signature
        case 1: memcpy(s32, ORDER, 32); break;                                  // s == n
        case 2: memcpy(r32, ORDER, 32); break;                                  // r == n
        case 3: memset(s32, 0, 32); break;                                      // s == 0
        case 4: for (int i = 0; i < 32; i++) r32[i] = (unsigned char)rng(); break;
        case 5: s32[rng() % 32] ^= (unsigned char)(1u << (rng() % 8)); break;   // one bit of s
        default: break;                                                         // untouched numbers
        }
        // half of the cases are canonical DER (so the arithmetic is what differs), half odd encodings
        Bytes sig = rng() % 2 ? EncodeSigDER(r32, s32) : EncodeSigOdd(r32, s32, rng);
        if (rng() % 5 == 0 && !sig.empty())
            sig[rng() % sig.size()] ^= (unsigned char)(1u << (rng() % 8));      // a bit anywhere in the encoding
        if (rng() % 17 == 0 && !sig.empty())
            sig.resize(rng() % sig.size());                                     // truncated

        // the public key in its other forms and wrong parity
        {
            EC_KEY* ek = EC_KEY_new_by_curve_name(NID_secp256k1);
            const unsigned char* pp = &pub[0];
            if (o2i_ECPublicKey(&ek, &pp, (long)pub.size()))
            {
                unsigned char u[65];
                unsigned char* pu = u;
                EC_KEY_set_conv_form(ek, POINT_CONVERSION_UNCOMPRESSED);
                if (i2o_ECPublicKey(ek, &pu) == 65)
                {
                    switch (rng() % 8)
                    {
                    case 0: pub.assign(u, u + 65); break;                                           // uncompressed
                    case 1: u[0] = 0x06 | (u[64] & 1); pub.assign(u, u + 65); break;                // hybrid, right parity
                    case 2: u[0] = 0x06 | ((u[64] & 1) ^ 1); pub.assign(u, u + 65); break;          // hybrid, wrong parity
                    case 3: if (pub.size() == 33) pub[0] ^= 1; break;                               // compressed, other parity
                    case 4: if (!pub.empty()) pub[rng() % pub.size()] ^= (unsigned char)(1u << (rng() % 8)); break;
                    case 5: if (pub.size() > 1) pub.resize(pub.size() - 1); break;
                    case 6: pub[0] = (unsigned char)rng(); break;                                   // some other prefix byte
                    default: break;
                    }
                }
            }
            EC_KEY_free(ek);
        }
        if (rng() % 11 == 0)
            hash.begin()[rng() % 32] ^= (unsigned char)(1u << (rng() % 8));

        Compare("fuzz", pub, hash, sig);
    }
    printf("secp_diff: %llu cases (seed %llu): %llu accepted, %llu rejected, %llu different\n", (unsigned long long)nIter, (unsigned long long)nSeed,
           (unsigned long long)nAccepted, (unsigned long long)nRejected, (unsigned long long)nDiff);
    return nDiff ? 1 : 0;
}
