// Copyright (c) 2013 The Bitcoin Core developers
// Copyright (c) 2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

// BIP32 hierarchical-deterministic key derivation (private side).
// Stage 1 of the HD wallet (doc/hd-wallet-spec.md): the crypto core, with no
// wallet changes. Public (xpub / CKDpub) derivation is a later stage.

#ifndef CORGICOIN_BIP32_H
#define CORGICOIN_BIP32_H

#include "key.h"

#include <cstdint>
#include <string>
#include <vector>

// Hardened child indices have the high bit set.
static constexpr uint32_t BIP32_HARDENED = 0x80000000u;

/** A BIP32 extended private key: a CKey plus the chain code and the metadata
 *  needed to derive children and serialize to the xprv base58 form. */
struct CExtKey
{
    unsigned char nDepth = 0;
    unsigned char vchFingerprint[4] = {0, 0, 0, 0};
    uint32_t nChild = 0;
    unsigned char vchChainCode[32] = {0};
    CKey key;

    // Master key from a seed: I = HMAC-SHA512("Bitcoin seed", seed),
    // key = I[0:32], chain code = I[32:64].
    void SetSeed(const unsigned char* seed, unsigned int nSeedLen);

    // CKDpriv: derive the child at nChildIn (hardened if >= BIP32_HARDENED).
    // Returns false only on the (cryptographically negligible) invalid-child case.
    bool Derive(CExtKey& out, uint32_t nChildIn) const;

    // Base58Check xprv string. vchVersion is the 4-byte version prefix
    // (e.g. Bitcoin mainnet {0x04,0x88,0xAD,0xE4}); CorgiCoin picks its own
    // for wallet use, but the version is a parameter so tests can match the
    // official BIP32 vectors.
    std::string ToBase58(const std::vector<unsigned char>& vchVersion) const;
    bool SetBase58(const std::string& str, std::vector<unsigned char>& vchVersionOut);

    bool operator==(const CExtKey& b) const;
};

#endif // CORGICOIN_BIP32_H
