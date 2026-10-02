// Copyright (c) 2017, 2021 Pieter Wuille
// Copyright (c) 2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "bech32.h"

namespace
{

const char* CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";

// CHARSET position for each ASCII char, -1 if not in the charset
const int8_t CHARSET_REV[128] = {
    -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
    15, -1, 10, 17, 21, 20, 26, 30,  7,  5, -1, -1, -1, -1, -1, -1,
    -1, 29, -1, 24, 13, 25,  9,  8, 23, -1, 18, 22, 31, 27, 19, -1,
     1,  0,  3, 16, 11, 28, 12, 14,  6,  4,  2, -1, -1, -1, -1, -1,
    -1, 29, -1, 24, 13, 25,  9,  8, 23, -1, 18, 22, 31, 27, 19, -1,
     1,  0,  3, 16, 11, 28, 12, 14,  6,  4,  2, -1, -1, -1, -1, -1
};

constexpr uint32_t BECH32_CONST = 1;
constexpr uint32_t BECH32M_CONST = 0x2bc830a3;

uint32_t PolyMod(const std::vector<uint8_t>& v)
{
    uint32_t c = 1;
    for (uint8_t v_i : v)
    {
        uint8_t c0 = c >> 25;
        c = ((c & 0x1ffffff) << 5) ^ v_i;
        if (c0 & 1)  c ^= 0x3b6a57b2;
        if (c0 & 2)  c ^= 0x26508e6d;
        if (c0 & 4)  c ^= 0x1ea119fa;
        if (c0 & 8)  c ^= 0x3d4233dd;
        if (c0 & 16) c ^= 0x2a1462b3;
    }
    return c;
}

std::vector<uint8_t> ExpandHRP(const std::string& hrp)
{
    std::vector<uint8_t> ret;
    ret.reserve(hrp.size() * 2 + 1);
    for (char c : hrp) ret.push_back(c >> 5);
    ret.push_back(0);
    for (char c : hrp) ret.push_back(c & 0x1f);
    return ret;
}

bech32::Encoding VerifyChecksum(const std::string& hrp, const std::vector<uint8_t>& values)
{
    std::vector<uint8_t> enc = ExpandHRP(hrp);
    enc.insert(enc.end(), values.begin(), values.end());
    uint32_t check = PolyMod(enc);
    if (check == BECH32_CONST) return bech32::Encoding::BECH32;
    if (check == BECH32M_CONST) return bech32::Encoding::BECH32M;
    return bech32::Encoding::INVALID;
}

std::vector<uint8_t> CreateChecksum(bech32::Encoding encoding, const std::string& hrp,
                                    const std::vector<uint8_t>& values)
{
    std::vector<uint8_t> enc = ExpandHRP(hrp);
    enc.insert(enc.end(), values.begin(), values.end());
    enc.resize(enc.size() + 6, 0);
    uint32_t mod = PolyMod(enc) ^ (encoding == bech32::Encoding::BECH32M ? BECH32M_CONST : BECH32_CONST);
    std::vector<uint8_t> ret(6);
    for (size_t i = 0; i < 6; i++)
        ret[i] = (mod >> (5 * (5 - i))) & 0x1f;
    return ret;
}

} // namespace

namespace bech32
{

std::string Encode(Encoding encoding, const std::string& hrp, const std::vector<uint8_t>& values)
{
    if (encoding == Encoding::INVALID || hrp.empty())
        return "";
    // HRP must be lowercase, printable US-ASCII
    for (char c : hrp)
        if (c < 33 || c > 126 || (c >= 'A' && c <= 'Z'))
            return "";
    if (hrp.size() + 1 + values.size() + 6 > 90)
        return "";
    for (uint8_t v : values)
        if (v >> 5)
            return "";

    std::vector<uint8_t> checksum = CreateChecksum(encoding, hrp, values);
    std::string ret = hrp + '1';
    ret.reserve(ret.size() + values.size() + 6);
    for (uint8_t v : values) ret += CHARSET[v];
    for (uint8_t v : checksum) ret += CHARSET[v];
    return ret;
}

DecodeResult Decode(const std::string& str)
{
    if (str.size() > 90)
        return {};
    bool lower = false, upper = false;
    for (char c : str)
    {
        unsigned char uc = c;
        if (uc < 33 || uc > 126) return {};
        if (c >= 'a' && c <= 'z') lower = true;
        if (c >= 'A' && c <= 'Z') upper = true;
    }
    if (lower && upper)
        return {};

    size_t pos = str.rfind('1');
    if (pos == std::string::npos || pos == 0 || pos + 7 > str.size())
        return {};

    DecodeResult res;
    res.hrp.reserve(pos);
    for (size_t i = 0; i < pos; i++)
        res.hrp += (char)tolower((unsigned char)str[i]);

    std::vector<uint8_t> values;
    values.reserve(str.size() - pos - 1);
    for (size_t i = pos + 1; i < str.size(); i++)
    {
        int8_t rev = CHARSET_REV[(unsigned char)str[i]];
        if (rev == -1) return {};
        values.push_back((uint8_t)rev);
    }

    res.encoding = VerifyChecksum(res.hrp, values);
    if (res.encoding == Encoding::INVALID)
        return {};
    res.data.assign(values.begin(), values.end() - 6);
    return res;
}

bool ConvertBits(int frombits, int tobits, bool pad,
                 std::vector<uint8_t>& out, const std::vector<uint8_t>& in)
{
    uint32_t acc = 0;
    int bits = 0;
    const uint32_t maxv = (1u << tobits) - 1;
    const uint32_t max_acc = (1u << (frombits + tobits - 1)) - 1;
    for (uint8_t value : in)
    {
        if (value >> frombits)
            return false;
        acc = ((acc << frombits) | value) & max_acc;
        bits += frombits;
        while (bits >= tobits)
        {
            bits -= tobits;
            out.push_back((acc >> bits) & maxv);
        }
    }
    if (pad)
    {
        if (bits)
            out.push_back((acc << (tobits - bits)) & maxv);
    }
    else if (bits >= frombits || ((acc << (tobits - bits)) & maxv))
    {
        return false;
    }
    return true;
}

} // namespace bech32
