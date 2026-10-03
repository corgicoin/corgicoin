// Copyright (c) 2011 Vince Durham
// Copyright (c) 2009-2014 The Bitcoin/Namecoin/Dogecoin developers
// Copyright (c) 2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

// AuxPoW (merged mining) primitives — see doc/auxpow-spec.md.
// CPureBlockHeader + version helpers live here (no dependency on CBlock).
// CAuxPow itself is declared in main.h, after CMerkleTx which it extends.

#ifndef CORGICOIN_AUXPOW_H
#define CORGICOIN_AUXPOW_H

#include "serialize.h"
#include "uint256.h"
#include "util.h"     // Hash(), BEGIN/END
#include "scrypt.h"

// --- Consensus parameters (doc/auxpow-spec.md) ------------------------------

// CorgiCoin's merged-mining chain ID (mnemonic "C6"). Occupies bits 16-31 of
// the block nVersion. Fixed forever once activated.
static constexpr int32_t AUXPOW_CHAIN_ID = 0x00C6;

// Height at which the AuxPoW rules activate.
static constexpr int AUXPOW_FORK_HEIGHT_MAINNET = 50000;
static constexpr int AUXPOW_FORK_HEIGHT_TESTNET = 200;

// --- Block version partitioning ---------------------------------------------
// bits  0- 7 : base block version
// bit   8    : AuxPoW flag
// bits 16-31 : chain ID

static constexpr int32_t VERSION_AUXPOW_BIT = (1 << 8);
static constexpr int32_t VERSION_CHAIN_START = (1 << 16);

inline int32_t GetBaseVersion(int32_t nVersion) { return nVersion & 0xff; }
inline int32_t GetChainId(int32_t nVersion)     { return nVersion >> 16; }
inline bool    IsAuxPowVersion(int32_t nVersion) { return (nVersion & VERSION_AUXPOW_BIT) != 0; }

// Compose a block version with base version, chain ID and optional AuxPoW bit.
inline int32_t MakeVersion(int32_t nBaseVersion, int32_t nChainId, bool fAuxPow)
{
    return (nChainId << 16) | (fAuxPow ? VERSION_AUXPOW_BIT : 0) | (nBaseVersion & 0xff);
}

int GetAuxPowForkHeight();  // defined in main.cpp (depends on fTestNet)

// --- CPureBlockHeader -------------------------------------------------------
// The bare 80-byte block header, standalone so the AuxPoW parent block can be
// carried and Scrypt-hashed without pulling in (or recursing into) an AuxPoW.
// Field layout and hashing are byte-identical to CBlock's header.

class CPureBlockHeader
{
public:
    int nVersion;
    uint256 hashPrevBlock;
    uint256 hashMerkleRoot;
    unsigned int nTime;
    unsigned int nBits;
    unsigned int nNonce;

    CPureBlockHeader() { SetNull(); }

    IMPLEMENT_SERIALIZE
    (
        READWRITE(this->nVersion);
        nVersion = this->nVersion;
        READWRITE(hashPrevBlock);
        READWRITE(hashMerkleRoot);
        READWRITE(nTime);
        READWRITE(nBits);
        READWRITE(nNonce);
    )

    void SetNull()
    {
        nVersion = 0;
        hashPrevBlock = 0;
        hashMerkleRoot = 0;
        nTime = 0;
        nBits = 0;
        nNonce = 0;
    }

    uint256 GetHash() const
    {
        return Hash(BEGIN(nVersion), END(nNonce));
    }

    uint256 GetPoWHash() const
    {
        uint256 thash;
        scrypt_1024_1_1_256(BEGIN(nVersion), BEGIN(thash));
        return thash;
    }

    int32_t GetChainId() const { return ::GetChainId(nVersion); }
    bool IsAuxPow() const      { return ::IsAuxPowVersion(nVersion); }
};

#endif // CORGICOIN_AUXPOW_H
