// Copyright (c) 2009-2012 The Bitcoin Developers
// Copyright (c) 2011-2012 Litecoin Developers
// Copyright (c) 2013 Dogecoin Developers
// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <openssl/aes.h>
#include <openssl/evp.h>
#include <vector>
#include <string>
#include "compat_openssl.h"
#ifdef WIN32
#include <windows.h>
#endif

#include "crypter.h"

// Derivation method 0, as defined by Bitcoin: EVP_BytesToKey(EVP_aes_256_cbc(), EVP_sha512(), salt, passphrase,
// nRounds), i.e. D = SHA512^nRounds(passphrase || salt), key = D[0..32), IV = D[32..48). One SHA-512 output covers
// both, so this is all EVP_BytesToKey computes for AES-256-CBC. Written out here so every OpenSSL version gives
// the same result.
static bool DeriveKeyBytesToKeySHA512(const SecureString& strKeyData, const std::vector<unsigned char>& chSalt,
                                      unsigned int nRounds, unsigned char* chKey, unsigned char* chIV)
{
    unsigned char buf[64];
    unsigned int nLen = 0;
    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (ctx == nullptr)
        return false;
    bool fOk = EVP_DigestInit_ex(ctx, EVP_sha512(), nullptr) &&
               EVP_DigestUpdate(ctx, strKeyData.data(), strKeyData.size()) &&
               EVP_DigestUpdate(ctx, chSalt.data(), chSalt.size()) &&
               EVP_DigestFinal_ex(ctx, buf, &nLen);
    for (unsigned int i = 1; fOk && i < nRounds; i++)
        fOk = EVP_DigestInit_ex(ctx, EVP_sha512(), nullptr) &&
              EVP_DigestUpdate(ctx, buf, sizeof(buf)) &&
              EVP_DigestFinal_ex(ctx, buf, &nLen);
    EVP_MD_CTX_free(ctx);
    if (fOk && nLen == sizeof(buf))
    {
        memcpy(chKey, buf, WALLET_CRYPTO_KEY_SIZE);
        memcpy(chIV, buf + WALLET_CRYPTO_KEY_SIZE, 16);
    }
    OPENSSL_cleanse(buf, sizeof(buf));
    return fOk && nLen == sizeof(buf);
}

// What CorgiCoin v4.2 to v4.7 built against OpenSSL 3 used, and recorded as method 0: PBKDF2-HMAC-SHA512 with
// key = out[0..32), IV = out[32..48).
static bool DeriveKeyPBKDF2SHA512(const SecureString& strKeyData, const std::vector<unsigned char>& chSalt,
                                  unsigned int nRounds, unsigned char* chKey, unsigned char* chIV)
{
    unsigned char derived[WALLET_CRYPTO_KEY_SIZE + WALLET_CRYPTO_KEY_SIZE];
    bool fOk = PKCS5_PBKDF2_HMAC(strKeyData.data(), strKeyData.size(), chSalt.data(), chSalt.size(),
                                 nRounds, EVP_sha512(), sizeof(derived), derived) == 1;
    if (fOk)
    {
        memcpy(chKey, derived, WALLET_CRYPTO_KEY_SIZE);
        memcpy(chIV, derived + WALLET_CRYPTO_KEY_SIZE, WALLET_CRYPTO_KEY_SIZE);
    }
    OPENSSL_cleanse(derived, sizeof(derived));
    return fOk;
}

bool CCrypter::SetKeyFromPassphrase(const SecureString& strKeyData, const std::vector<unsigned char>& chSalt, const unsigned int nRounds, const unsigned int nDerivationMethod)
{
    if (nRounds < 1 || chSalt.size() != WALLET_CRYPTO_SALT_SIZE)
        return false;
    if (nDerivationMethod != WALLET_DERIVATION_BYTESTOKEY_SHA512 && nDerivationMethod != WALLET_DERIVATION_PBKDF2_SHA512_V4)
        return false;

    // Try to keep the keydata out of swap (and be a bit over-careful to keep the IV that we don't even use out of swap)
    // Note that this does nothing about suspend-to-disk (which will put all our key data on disk)
    // Note as well that at no point in this program is any attempt made to prevent stealing of keys by reading the memory of the running process.  
    mlock(&chKey[0], sizeof chKey);
    mlock(&chIV[0], sizeof chIV);
    memset(&chIV, 0, sizeof chIV);

    bool fOk = (nDerivationMethod == WALLET_DERIVATION_BYTESTOKEY_SHA512)
        ? DeriveKeyBytesToKeySHA512(strKeyData, chSalt, nRounds, chKey, chIV)
        : DeriveKeyPBKDF2SHA512(strKeyData, chSalt, nRounds, chKey, chIV);
    if (!fOk)
    {
        memset(&chKey, 0, sizeof chKey);
        memset(&chIV, 0, sizeof chIV);
        return false;
    }

    fKeySet = true;
    return true;
}

bool CCrypter::SetKey(const CKeyingMaterial& chNewKey, const std::vector<unsigned char>& chNewIV)
{
    if (chNewKey.size() != WALLET_CRYPTO_KEY_SIZE || chNewIV.size() != WALLET_CRYPTO_KEY_SIZE)
        return false;

    // Try to keep the keydata out of swap
    // Note that this does nothing about suspend-to-disk (which will put all our key data on disk)
    // Note as well that at no point in this program is any attempt made to prevent stealing of keys by reading the memory of the running process.  
    mlock(&chKey[0], sizeof chKey);
    mlock(&chIV[0], sizeof chIV);

    memcpy(&chKey[0], &chNewKey[0], sizeof chKey);
    memcpy(&chIV[0], &chNewIV[0], sizeof chIV);

    fKeySet = true;
    return true;
}

bool CCrypter::Encrypt(const CKeyingMaterial& vchPlaintext, std::vector<unsigned char> &vchCiphertext)
{
    if (!fKeySet)
        return false;

    // max ciphertext len for a n bytes of plaintext is
    // n + AES_BLOCK_SIZE - 1 bytes
    int nLen = vchPlaintext.size();
    int nCLen = nLen + AES_BLOCK_SIZE, nFLen = 0;
    vchCiphertext = std::vector<unsigned char> (nCLen);

    bool fOk = true;

    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return false;

    if (fOk) fOk = EVP_EncryptInit_ex(ctx, EVP_aes_256_cbc(), nullptr, chKey, chIV);
    if (fOk) fOk = EVP_EncryptUpdate(ctx, &vchCiphertext[0], &nCLen, &vchPlaintext[0], nLen);
    if (fOk) fOk = EVP_EncryptFinal_ex(ctx, (&vchCiphertext[0])+nCLen, &nFLen);

    EVP_CIPHER_CTX_free(ctx);

    if (!fOk) return false;

    vchCiphertext.resize(nCLen + nFLen);
    return true;
}

bool CCrypter::Decrypt(const std::vector<unsigned char>& vchCiphertext, CKeyingMaterial& vchPlaintext)
{
    if (!fKeySet)
        return false;

    // plaintext will always be equal to or lesser than length of ciphertext
    int nLen = vchCiphertext.size();
    int nPLen = nLen, nFLen = 0;

    vchPlaintext = CKeyingMaterial(nPLen);

    bool fOk = true;

    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    if (!ctx) return false;

    if (fOk) fOk = EVP_DecryptInit_ex(ctx, EVP_aes_256_cbc(), nullptr, chKey, chIV);
    if (fOk) fOk = EVP_DecryptUpdate(ctx, &vchPlaintext[0], &nPLen, &vchCiphertext[0], nLen);
    if (fOk) fOk = EVP_DecryptFinal_ex(ctx, (&vchPlaintext[0])+nPLen, &nFLen);

    EVP_CIPHER_CTX_free(ctx);

    if (!fOk) return false;

    vchPlaintext.resize(nPLen + nFLen);
    return true;
}


bool EncryptSecret(CKeyingMaterial& vMasterKey, const CSecret &vchPlaintext, const uint256& nIV, std::vector<unsigned char> &vchCiphertext)
{
    CCrypter cKeyCrypter;
    std::vector<unsigned char> chIV(WALLET_CRYPTO_KEY_SIZE);
    memcpy(&chIV[0], &nIV, WALLET_CRYPTO_KEY_SIZE);
    if(!cKeyCrypter.SetKey(vMasterKey, chIV))
        return false;
    return cKeyCrypter.Encrypt((CKeyingMaterial)vchPlaintext, vchCiphertext);
}

bool DecryptSecret(const CKeyingMaterial& vMasterKey, const std::vector<unsigned char>& vchCiphertext, const uint256& nIV, CSecret& vchPlaintext)
{
    CCrypter cKeyCrypter;
    std::vector<unsigned char> chIV(WALLET_CRYPTO_KEY_SIZE);
    memcpy(&chIV[0], &nIV, WALLET_CRYPTO_KEY_SIZE);
    if(!cKeyCrypter.SetKey(vMasterKey, chIV))
        return false;
    return cKeyCrypter.Decrypt(vchCiphertext, *reinterpret_cast<CKeyingMaterial*>(&vchPlaintext));
}
