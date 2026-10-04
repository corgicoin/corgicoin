// Copyright (c) 2013 The Bitcoin Core developers
// Copyright (c) 2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "bip32.h"

#include "base58.h"
#include "util.h"   // Hash160

#include <cstring>

#include <openssl/hmac.h>
#include <openssl/evp.h>
#include <openssl/bn.h>
#include <openssl/crypto.h>

namespace {

// secp256k1 group order n (the modulus for scalar key arithmetic).
const char* SECP256K1_ORDER_HEX =
    "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141";

void HmacSha512(const unsigned char* key, int keylen,
                const unsigned char* data, int datalen,
                unsigned char out[64])
{
    unsigned int len = 64;
    HMAC(EVP_sha512(), key, keylen, data, datalen, out, &len);
}

// Big-endian 32-byte serialization of a BIGNUM, left-padded with zeros.
void BNToBytes32(const BIGNUM* bn, unsigned char out[32])
{
    memset(out, 0, 32);
    int n = BN_num_bytes(bn);
    if (n > 32) n = 32;
    BN_bn2bin(bn, out + (32 - n));
}

void WriteBE32(unsigned char* p, uint32_t x)
{
    p[0] = (x >> 24) & 0xff;
    p[1] = (x >> 16) & 0xff;
    p[2] = (x >> 8) & 0xff;
    p[3] = x & 0xff;
}

uint32_t ReadBE32(const unsigned char* p)
{
    return (uint32_t(p[0]) << 24) | (uint32_t(p[1]) << 16) |
           (uint32_t(p[2]) << 8) | uint32_t(p[3]);
}

} // namespace

void CExtKey::SetSeed(const unsigned char* seed, unsigned int nSeedLen)
{
    static const unsigned char hashkey[] = {'B','i','t','c','o','i','n',' ','s','e','e','d'};
    unsigned char I[64];
    HmacSha512(hashkey, sizeof(hashkey), seed, (int)nSeedLen, I);

    CSecret secret(I, I + 32);
    key.SetSecret(secret, true); // HD keys are always compressed
    memcpy(vchChainCode, I + 32, 32);
    nDepth = 0;
    nChild = 0;
    memset(vchFingerprint, 0, 4);
    OPENSSL_cleanse(I, sizeof(I));
}

bool CExtKey::Derive(CExtKey& out, uint32_t nChildIn) const
{
    out.nDepth = nDepth + 1;

    // Parent fingerprint = first 4 bytes of Hash160(parent compressed pubkey)
    CPubKey pub = key.GetPubKey();
    std::vector<unsigned char> pubbytes = pub.Raw();
    uint160 h = Hash160(pubbytes);
    memcpy(out.vchFingerprint, &h, 4);
    out.nChild = nChildIn;

    // Build the HMAC data
    unsigned char data[37];
    bool fHardened = (nChildIn & BIP32_HARDENED) != 0;
    bool fCompressed = false;
    CSecret parentSecret = key.GetSecret(fCompressed);
    if (fHardened)
    {
        data[0] = 0x00;
        memcpy(data + 1, &parentSecret[0], 32);
    }
    else
    {
        // serP(point(k_par)) = the 33-byte compressed public key
        if (pubbytes.size() != 33)
            return false;
        memcpy(data, &pubbytes[0], 33);
    }
    WriteBE32(data + 33, nChildIn);

    unsigned char I[64];
    HmacSha512(vchChainCode, 32, data, 37, I);

    // child key = (IL + parent key) mod n
    BN_CTX* ctx = BN_CTX_new();
    BIGNUM* n = nullptr;
    BN_hex2bn(&n, SECP256K1_ORDER_HEX);
    BIGNUM* il = BN_bin2bn(I, 32, nullptr);
    BIGNUM* kpar = BN_bin2bn(&parentSecret[0], 32, nullptr);
    BIGNUM* child = BN_new();

    bool ok = true;
    // Invalid (negligible) if IL >= n or resulting key is zero
    if (BN_cmp(il, n) >= 0)
        ok = false;
    if (ok)
        BN_mod_add(child, il, kpar, n, ctx);
    if (ok && BN_is_zero(child))
        ok = false;

    if (ok)
    {
        unsigned char childBytes[32];
        BNToBytes32(child, childBytes);
        CSecret childSecret(childBytes, childBytes + 32);
        out.key.SetSecret(childSecret, true);
        memcpy(out.vchChainCode, I + 32, 32);
        OPENSSL_cleanse(childBytes, sizeof(childBytes));
    }

    OPENSSL_cleanse(I, sizeof(I));
    OPENSSL_cleanse(data, sizeof(data));
    BN_clear_free(child);
    BN_clear_free(kpar);
    BN_free(il);
    BN_free(n);
    BN_CTX_free(ctx);
    return ok;
}

std::string CExtKey::ToBase58(const std::vector<unsigned char>& vchVersion) const
{
    // version(4) || depth(1) || fingerprint(4) || child(4) || chaincode(32) || 0x00||key(33)
    std::vector<unsigned char> v;
    v.insert(v.end(), vchVersion.begin(), vchVersion.end());
    v.push_back(nDepth);
    v.insert(v.end(), vchFingerprint, vchFingerprint + 4);
    unsigned char child[4];
    WriteBE32(child, nChild);
    v.insert(v.end(), child, child + 4);
    v.insert(v.end(), vchChainCode, vchChainCode + 32);
    v.push_back(0x00);
    bool fCompressed = false;
    CSecret secret = key.GetSecret(fCompressed);
    v.insert(v.end(), secret.begin(), secret.end());
    return EncodeBase58Check(v);
}

bool CExtKey::SetBase58(const std::string& str, std::vector<unsigned char>& vchVersionOut)
{
    std::vector<unsigned char> v;
    if (!DecodeBase58Check(str, v) || v.size() != 4 + 1 + 4 + 4 + 32 + 33)
        return false;
    vchVersionOut.assign(v.begin(), v.begin() + 4);
    const unsigned char* p = &v[4];
    nDepth = p[0];
    memcpy(vchFingerprint, p + 1, 4);
    nChild = ReadBE32(p + 5);
    memcpy(vchChainCode, p + 9, 32);
    // p[41] is the 0x00 private-key marker; p[42..73] is the 32-byte key
    CSecret secret(p + 42, p + 74);
    key.SetSecret(secret, true);
    return true;
}

bool CExtKey::operator==(const CExtKey& b) const
{
    if (nDepth != b.nDepth || nChild != b.nChild)
        return false;
    if (memcmp(vchFingerprint, b.vchFingerprint, 4) != 0)
        return false;
    if (memcmp(vchChainCode, b.vchChainCode, 32) != 0)
        return false;
    bool c1 = false, c2 = false;
    return key.GetSecret(c1) == b.key.GetSecret(c2);
}
