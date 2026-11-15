// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

// Do OpenSSL (what the node verifies signatures with) and libsecp256k1 accept exactly the same signatures?
//
//   secp_diff [iterations=200000] [seed=1]
//
// A signature check is consensus: a signature that one accepts and the other rejects, in a block that is already in the chain, would
// split upgraded nodes from the rest. This makes valid signatures and then damages them the ways old transactions are known to be
// odd (long-form lengths, extra leading zeros, a missing zero pad, bytes after the sequence, a high S, an S or R out of range,
// uncompressed / compressed / hybrid public keys with the wrong parity, a flipped bit anywhere) and asks both verifiers about each.
// Both read the signature with the node's own lax parser (ParseSignatureLax); what is compared is the rest: the public key
// parse, the range checks, the high-S rule, and the verification itself. Exit status 1 on any difference, with the case printed.

#include "key.h"
#include "main.h"
#include "ui_interface.h"
#include "wallet.h"

#include <secp256k1.h>

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

static Bytes EncodeSig(const unsigned char* r32, const unsigned char* s32, std::mt19937_64& rng)
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
        seqlen = rng() % 300;                   // a sequence length that is simply wrong: the lax parser ignores it
    PutLen(sig, seqlen, rng() % 8 == 0, rng);
    sig.insert(sig.end(), body.begin(), body.end());
    const unsigned trailing = rng() % 6 == 0 ? rng() % 4 + 1 : 0;   // bytes after the sequence, as a hash type byte would be
    for (unsigned i = 0; i < trailing; i++)
        sig.push_back((unsigned char)rng());
    return sig;
}

static bool OpenSSLAccepts(const Bytes& pub, const uint256& hash, const Bytes& sig)
{
    CKey key;
    if (!key.SetPubKey(CPubKey(pub)))
        return false;
    return key.Verify(hash, sig);
}

static bool SecpAccepts(const secp256k1_context* ctx, const Bytes& pub, const uint256& hash, const Bytes& sig)
{
    secp256k1_pubkey pk;
    if (pub.empty() || !secp256k1_ec_pubkey_parse(ctx, &pk, &pub[0], pub.size()))
        return false;
    unsigned char compact[64];
    if (!ParseSignatureLax(sig, compact))
        return false;
    secp256k1_ecdsa_signature sg;
    if (!secp256k1_ecdsa_signature_parse_compact(ctx, &sg, compact))
        return false;                           // r or s is not below the group order
    secp256k1_ecdsa_signature_normalize(ctx, &sg, &sg);     // OpenSSL does not insist on a low S; the library does until told
    return secp256k1_ecdsa_verify(ctx, &sg, (const unsigned char*)&hash, &pk) == 1;
}

int main(int argc, char** argv)
{
    const uint64_t nIter = argc > 1 ? strtoull(argv[1], nullptr, 10) : 200000;
    const uint64_t nSeed = argc > 2 ? strtoull(argv[2], nullptr, 10) : 1;
    std::mt19937_64 rng(nSeed);
    secp256k1_context* ctx = secp256k1_context_create(SECP256K1_CONTEXT_VERIFY);

    uint64_t nAccepted = 0, nRejected = 0, nDiff = 0;
    for (uint64_t it = 0; it < nIter; it++)
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
        unsigned char rs[64];
        if (!ParseSignatureLax(good, rs))
        {
            fprintf(stderr, "the node's own signature does not parse\n");
            return 2;
        }
        unsigned char r32[32], s32[32];
        memcpy(r32, rs, 32);
        memcpy(s32, rs + 32, 32);

        // damage it
        switch (rng() % 8)
        {
        case 0: NegateModOrder(rs + 32, s32); break;                            // the high-S twin of a valid signature
        case 1: memcpy(s32, ORDER, 32); break;                                  // s == n
        case 2: memcpy(r32, ORDER, 32); break;                                  // r == n
        case 3: memset(s32, 0, 32); break;                                      // s == 0
        case 4: for (int i = 0; i < 32; i++) r32[i] = (unsigned char)rng(); break;
        case 5: s32[rng() % 32] ^= (unsigned char)(1u << (rng() % 8)); break;   // one bit of s
        default: break;                                                         // untouched numbers, odd encoding only
        }
        Bytes sig = EncodeSig(r32, s32, rng);
        if (rng() % 5 == 0 && !sig.empty())
            sig[rng() % sig.size()] ^= (unsigned char)(1u << (rng() % 8));      // a bit anywhere in the encoding
        if (rng() % 17 == 0 && !sig.empty())
            sig.resize(rng() % sig.size());                                     // truncated

        // the public key in its other forms and wrong parity
        secp256k1_pubkey parsed;
        if (secp256k1_ec_pubkey_parse(ctx, &parsed, &pub[0], pub.size()))
        {
            unsigned char u[65];
            size_t ulen = 65;
            secp256k1_ec_pubkey_serialize(ctx, u, &ulen, &parsed, SECP256K1_EC_UNCOMPRESSED);
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
        if (rng() % 11 == 0)
            hash.begin()[rng() % 32] ^= (unsigned char)(1u << (rng() % 8));

        const bool fA = OpenSSLAccepts(pub, hash, sig);
        const bool fB = SecpAccepts(ctx, pub, hash, sig);
        (fA ? nAccepted : nRejected)++;
        if (fA != fB)
        {
            nDiff++;
            printf("DIFFERENT: openssl %s, libsecp256k1 %s\n  pubkey %s\n  hash   %s\n  sig    %s\n", fA ? "accepts" : "rejects", fB ? "accepts" : "rejects",
                   Hex(pub).c_str(), hash.GetHex().c_str(), Hex(sig).c_str());
            if (nDiff >= 20)
                break;
        }
    }
    printf("secp_diff: %llu cases (seed %llu): %llu accepted, %llu rejected, %llu different\n", (unsigned long long)nIter, (unsigned long long)nSeed,
           (unsigned long long)nAccepted, (unsigned long long)nRejected, (unsigned long long)nDiff);
    secp256k1_context_destroy(ctx);
    return nDiff ? 1 : 0;
}
