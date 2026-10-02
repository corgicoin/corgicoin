// Copyright (c) 2017, 2021 Pieter Wuille
// Copyright (c) 2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

// Bech32 / Bech32m string encoding (BIP-173 / BIP-350), adapted from the
// reference implementation. CorgiCoin has no segwit; we use bech32m purely
// as a modern *address encoding* for the existing P2PKH/P2SH destinations
// (HRP "corg" mainnet, "tcorg" testnet) — see CBitcoinAddress in base58.h.

#ifndef CORGICOIN_BECH32_H
#define CORGICOIN_BECH32_H

#include <cstdint>
#include <string>
#include <vector>

namespace bech32
{

enum class Encoding {
    INVALID,
    BECH32,  // checksum constant 1 (BIP-173)
    BECH32M, // checksum constant 0x2bc830a3 (BIP-350)
};

struct DecodeResult
{
    Encoding encoding = Encoding::INVALID;
    std::string hrp;
    std::vector<uint8_t> data; // 5-bit values, checksum stripped

    explicit operator bool() const { return encoding != Encoding::INVALID; }
};

/** Encode hrp + 5-bit data values into a bech32/bech32m string (lowercase).
 *  Returns "" if any value is out of range or the result would exceed 90 chars. */
std::string Encode(Encoding encoding, const std::string& hrp, const std::vector<uint8_t>& values);

/** Decode a bech32/bech32m string. encoding == INVALID on any failure
 *  (bad charset, mixed case, bad checksum, bad structure). */
DecodeResult Decode(const std::string& str);

/** Re-pack a bit stream between group sizes (e.g. 8-bit bytes <-> 5-bit
 *  values). With pad=true appends a final padded group; with pad=false
 *  rejects incomplete or non-zero padding. Appends to out. */
bool ConvertBits(int frombits, int tobits, bool pad,
                 std::vector<uint8_t>& out, const std::vector<uint8_t>& in);

} // namespace bech32

#endif // CORGICOIN_BECH32_H
