// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
//
// Cross-chain burn payload helpers. See doc/burn-payload-spec.md for the
// on-chain layout this file implements.

#ifndef BITCOIN_BURNPAYLOAD_H
#define BITCOIN_BURNPAYLOAD_H

#include <cstddef>
#include <stdexcept>
#include <string>
#include <vector>

#include "script.h"

namespace burnpayload {

static constexpr char     MAGIC[3]         = {'S', 'O', 'L'};
static constexpr size_t   MAGIC_LEN        = 3;
static constexpr size_t   PARTNER_LEN      = 4;
static constexpr size_t   SOL_DEST_LEN     = 32;
static constexpr size_t   PAYLOAD_LEN      = MAGIC_LEN + PARTNER_LEN + SOL_DEST_LEN; // 39

inline bool IsValidPartnerTag(const std::string& tag)
{
    if (tag.size() != PARTNER_LEN) return false;
    for (char c : tag) {
        unsigned char uc = static_cast<unsigned char>(c);
        if (uc < 0x21 || uc > 0x7E) return false;
    }
    return true;
}

inline std::vector<unsigned char> Encode(const std::string& partner,
                                         const std::vector<unsigned char>& solDest)
{
    if (!IsValidPartnerTag(partner))
        throw std::invalid_argument("partner tag must be 4 printable ASCII chars");
    if (solDest.size() != SOL_DEST_LEN)
        throw std::invalid_argument("sol_dest must be exactly 32 bytes");

    std::vector<unsigned char> out;
    out.reserve(PAYLOAD_LEN);
    out.insert(out.end(), MAGIC, MAGIC + MAGIC_LEN);
    out.insert(out.end(), partner.begin(), partner.end());
    out.insert(out.end(), solDest.begin(), solDest.end());
    return out;
}

// Returns true if the raw payload bytes match the bridge spec. On success,
// partnerOut is the 4-char tag and solDestOut is the 32-byte raw pubkey.
inline bool DecodePayload(const std::vector<unsigned char>& payload,
                          std::string& partnerOut,
                          std::vector<unsigned char>& solDestOut)
{
    if (payload.size() != PAYLOAD_LEN) return false;
    if (payload[0] != MAGIC[0] || payload[1] != MAGIC[1] || payload[2] != MAGIC[2])
        return false;

    std::string partner(payload.begin() + MAGIC_LEN,
                        payload.begin() + MAGIC_LEN + PARTNER_LEN);
    if (!IsValidPartnerTag(partner)) return false;

    partnerOut = std::move(partner);
    solDestOut.assign(payload.begin() + MAGIC_LEN + PARTNER_LEN, payload.end());
    return true;
}

// Extracts the OP_RETURN push data from a scriptPubKey and runs it through
// DecodePayload. Returns false for any script that is not a bridge burn.
inline bool DecodeScript(const CScript& script,
                         std::string& partnerOut,
                         std::vector<unsigned char>& solDestOut)
{
    if (script.empty() || script[0] != OP_RETURN) return false;

    CScript::const_iterator pc = script.begin();
    opcodetype opcode;
    std::vector<unsigned char> vch;

    if (!script.GetOp(pc, opcode, vch)) return false;
    if (opcode != OP_RETURN) return false;

    if (!script.GetOp(pc, opcode, vch)) return false;
    return DecodePayload(vch, partnerOut, solDestOut);
}

} // namespace burnpayload

#endif // BITCOIN_BURNPAYLOAD_H
