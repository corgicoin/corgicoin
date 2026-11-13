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
// Returns "" if the strength is invalid or the random source fails. rng defaults to the OpenSSL generator;
// it is a parameter so tests can inject a failing one.
std::string GenerateMnemonic(int nStrengthBits = 128, bool (*rng)(unsigned char*, int) = nullptr);

// The canonical form of a typed or pasted phrase: words separated by exactly one ASCII space, no leading or
// trailing whitespace. Whitespace is ASCII space/tab/newline/etc. plus the Unicode spaces that NFKD maps to U+0020
// (U+00A0, U+2000-200A, U+202F, U+205F, U+3000). The seed is a hash of the exact string, so "a  b" and "a b" are
// different wallets; any phrase entered by a user must go through this before MnemonicToSeed.
// Not a full NFKD: the wordlist is ASCII, so other compatibility characters (full-width letters, ...) are left alone
// and the phrase then fails CheckMnemonic instead of silently producing another wallet.
std::string NormaliseMnemonic(const std::string& mnemonic);

// Validate a mnemonic: every word in the list and the checksum matches. Whitespace is normalised first, so a
// phrase with extra or unusual spacing is accepted; derive its seed from NormaliseMnemonic(mnemonic).
bool CheckMnemonic(const std::string& mnemonic);

// Mnemonic -> 64-byte seed via PBKDF2-HMAC-SHA512, 2048 iterations,
// salt = "mnemonic" + passphrase (BIP39). Does not validate or normalise: it hashes the exact bytes it is given,
// because wallets already on disk hold their phrase as stored and must keep deriving the same keys.
std::vector<unsigned char> MnemonicToSeed(const std::string& mnemonic,
                                          const std::string& passphrase = "");

} // namespace bip39

#endif // CORGICOIN_BIP39_H
