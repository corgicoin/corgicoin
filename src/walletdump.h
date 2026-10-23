// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef CORGICOIN_WALLETDUMP_H
#define CORGICOIN_WALLETDUMP_H

#include <filesystem>
#include <string>

class CWallet;

// Shared by the dumpwallet/importwallet/importprivkey RPCs and the Qt wallet.
// The wallet must be unlocked. Each returns false with strError set on failure.

/** Write every private key in the wallet to path, one per line.
 *  Refuses to touch an existing file unless fOverwrite is set. */
bool DumpWalletToFile(CWallet* pwallet, const std::filesystem::path& path, bool fOverwrite, std::string& strError);

/** Add the keys from a dump file (skipping ones already present), restore
 *  their labels, then rescan the chain. nImported receives the new key count. */
bool ImportWalletFromFile(CWallet* pwallet, const std::filesystem::path& path, int& nImported, std::string& strError);

/** Add one WIF private key with a label, then rescan the chain.
 *  fAlreadyHad is set if the wallet already held it (no rescan is done). */
bool ImportPrivateKey(CWallet* pwallet, const std::string& strSecret, const std::string& strLabel, bool& fAlreadyHad, std::string& strError);

std::string EncodeDumpString(const std::string& str);
std::string DecodeDumpString(const std::string& str);

#endif // CORGICOIN_WALLETDUMP_H
