// Copyright (c) 2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "bip39.h"
#include "bip39_wordlist.h"

#include <cstring>
#include <map>
#include <sstream>

#include <openssl/sha.h>
#include <openssl/evp.h>
#include <openssl/rand.h>

namespace {

// word -> index lookup, built once from BIP39_WORDLIST.
const std::map<std::string, int>& WordIndex()
{
    static const std::map<std::string, int> m = [] {
        std::map<std::string, int> r;
        for (int i = 0; i < 2048; i++)
            r[BIP39_WORDLIST[i]] = i;
        return r;
    }();
    return m;
}

std::vector<std::string> Split(const std::string& s)
{
    std::vector<std::string> words;
    std::istringstream iss(s);
    std::string w;
    while (iss >> w)
        words.push_back(w);
    return words;
}

} // namespace

namespace bip39
{

std::string MnemonicFromEntropy(const std::vector<unsigned char>& entropy)
{
    size_t entBytes = entropy.size();
    if (entBytes < 16 || entBytes > 32 || entBytes % 4 != 0)
        return "";

    // checksum = first (ENT/32) bits of SHA256(entropy)
    unsigned char hash[SHA256_DIGEST_LENGTH];
    SHA256(entropy.data(), entBytes, hash);

    int entBits = (int)entBytes * 8;
    int csBits = entBits / 32;
    int totalBits = entBits + csBits; // multiple of 11

    // bit-reader over entropy||checksum
    auto bitAt = [&](int i) -> int {
        if (i < entBits)
            return (entropy[i / 8] >> (7 - (i % 8))) & 1;
        int j = i - entBits;
        return (hash[j / 8] >> (7 - (j % 8))) & 1;
    };

    std::string out;
    for (int i = 0; i < totalBits; i += 11)
    {
        int idx = 0;
        for (int b = 0; b < 11; b++)
            idx = (idx << 1) | bitAt(i + b);
        if (!out.empty())
            out += ' ';
        out += BIP39_WORDLIST[idx];
    }
    return out;
}

std::string GenerateMnemonic(int nStrengthBits)
{
    if (nStrengthBits < 128 || nStrengthBits > 256 || nStrengthBits % 32 != 0)
        return "";
    std::vector<unsigned char> entropy(nStrengthBits / 8);
    RAND_bytes(entropy.data(), (int)entropy.size());
    return MnemonicFromEntropy(entropy);
}

bool CheckMnemonic(const std::string& mnemonic)
{
    std::vector<std::string> words = Split(mnemonic);
    size_t n = words.size();
    if (n < 12 || n > 24 || n % 3 != 0)
        return false;

    // Re-pack the words' 11-bit indices into the bit stream.
    int totalBits = (int)n * 11;
    int csBits = totalBits / 33;
    int entBits = totalBits - csBits;
    std::vector<unsigned char> bits((totalBits + 7) / 8, 0);

    int pos = 0;
    const auto& wi = WordIndex();
    for (const std::string& w : words)
    {
        auto it = wi.find(w);
        if (it == wi.end())
            return false;
        int idx = it->second;
        for (int b = 10; b >= 0; b--)
        {
            if ((idx >> b) & 1)
                bits[pos / 8] |= (1 << (7 - (pos % 8)));
            pos++;
        }
    }

    int entBytes = entBits / 8;
    unsigned char hash[SHA256_DIGEST_LENGTH];
    SHA256(bits.data(), entBytes, hash);

    // Compare the csBits checksum bits.
    for (int i = 0; i < csBits; i++)
    {
        int haveBit = (bits[(entBits + i) / 8] >> (7 - ((entBits + i) % 8))) & 1;
        int wantBit = (hash[i / 8] >> (7 - (i % 8))) & 1;
        if (haveBit != wantBit)
            return false;
    }
    return true;
}

std::vector<unsigned char> MnemonicToSeed(const std::string& mnemonic,
                                          const std::string& passphrase)
{
    std::string salt = "mnemonic" + passphrase;
    std::vector<unsigned char> seed(64);
    PKCS5_PBKDF2_HMAC(mnemonic.c_str(), (int)mnemonic.size(),
                      reinterpret_cast<const unsigned char*>(salt.data()), (int)salt.size(),
                      2048, EVP_sha512(), 64, seed.data());
    return seed;
}

} // namespace bip39
