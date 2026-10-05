// Copyright (c) 2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

// BIP39 mnemonic codes. Stage 2 of the HD wallet (doc/hd-wallet-spec.md):
// convert between entropy, a mnemonic phrase, and the 64-byte seed that
// feeds CExtKey::SetSeed. Standalone — no wallet changes.

#ifndef CORGICOIN_BIP39_H
#define CORGICOIN_BIP39_H

#include <string>
#include <vector>

namespace bip39
{

// Build a mnemonic from entropy. entropy length must be 16/20/24/28/32 bytes
// (128..256 bits, multiple of 32 bits); returns "" otherwise.
std::string MnemonicFromEntropy(const std::vector<unsigned char>& entropy);

// Generate a fresh mnemonic with the given entropy strength in bits
// (128 = 12 words, 256 = 24 words). Uses the library's secure RNG.
std::string GenerateMnemonic(int nStrengthBits = 128);

// Validate a mnemonic: every word in the list and the checksum matches.
bool CheckMnemonic(const std::string& mnemonic);

// Mnemonic -> 64-byte seed via PBKDF2-HMAC-SHA512, 2048 iterations,
// salt = "mnemonic" + passphrase (BIP39). Does not validate the mnemonic.
std::vector<unsigned char> MnemonicToSeed(const std::string& mnemonic,
                                          const std::string& passphrase = "");

} // namespace bip39

#endif // CORGICOIN_BIP39_H
