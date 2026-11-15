// Copyright (c) 2009-2012 Bitcoin Developers
// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "walletdump.h"
#include "wallet.h"
#include "walletdb.h"
#include "base58.h"
#include "util.h"
#include "main.h"
#include "json/json_compat.h"
#include <openssl/crypto.h>
#include <openssl/evp.h>

#include <fstream>
#ifndef WIN32
#include <fcntl.h>
#include <unistd.h>
#endif
#include <set>
#include <sstream>
#include <vector>

using namespace std;
using namespace json_spirit;

// Percent-encode a label so it fits in one space-separated dump field.
string EncodeDumpString(const string& str)
{
    string ret;
    for (unsigned char c : str) {
        if (c <= 32 || c >= 128 || c == '%')
            ret += strprintf("%%%02x", c);
        else
            ret += c;
    }
    return ret;
}

string DecodeDumpString(const string& str)
{
    string ret;
    for (size_t i = 0; i < str.size(); i++) {
        unsigned char c = str[i];
        if (c == '%' && i + 2 < str.size() && IsHex(str.substr(i + 1, 2))) {
            c = (unsigned char)strtol(str.substr(i + 1, 2).c_str(), nullptr, 16);
            i += 2;
        }
        ret += c;
    }
    return ret;
}

bool DumpWalletToFile(CWallet* pwallet, const std::filesystem::path& path, bool fOverwrite, string& strError)
{
    if (pwallet->IsLocked()) {
        strError = "Wallet is locked";
        return false;
    }
    if (!fOverwrite && std::filesystem::exists(path)) {
        strError = path.string() + " already exists. Choose a new filename so an existing file is never overwritten.";
        return false;
    }

    LOCK2(cs_main, pwallet->cs_wallet);

    set<CKeyID> setKeys, setReserve;
    pwallet->GetKeys(setKeys);
    pwallet->GetAllReserveKeys(setReserve);

    // Write to a temporary file next to the target and move it into place only when it is complete, so a failure
    // part way leaves no half-written backup that looks like a real one. Owner-only permissions where the platform
    // has them: the file holds every private key.
    // A fresh name, so a file of the user's called <path>.tmp is never truncated, and (not on Windows) created owner-only
    // and exclusively: never written first and chmod-ed after, and never through a symlink someone left there.
    const std::filesystem::path pathTmp = path.string() + strprintf(".tmp%08x", (unsigned int)GetRand(0xffffffff));
#ifndef WIN32
    {
        int fd = open(pathTmp.string().c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        if (fd < 0) {
            strError = "Cannot create the wallet dump file";
            return false;
        }
        close(fd);
    }
#endif
    std::ofstream file(pathTmp, std::ios::out | std::ios::trunc);
    if (!file.is_open()) {
        std::error_code ec;
        std::filesystem::remove(pathTmp, ec);
        strError = "Cannot open wallet dump file";
        return false;
    }
    auto Abort = [&](const std::string& strWhy) {
        file.close();
        std::error_code ec;
        std::filesystem::remove(pathTmp, ec);
        strError = strWhy;
        return false;
    };

    file << strprintf("# Wallet dump created by CorgiCoin %s\n", FormatFullVersion().c_str());
    file << strprintf("# * Created on %s\n", DateTimeStrFormat("%Y-%m-%dT%H:%M:%SZ", GetTime()).c_str());
    file << strprintf("# * Best block at time of backup was %d (%s),\n", nBestHeight, hashBestChain.GetHex().c_str());
    if (pwallet->IsHDEnabled())
        file << strprintf("# * HD seed id %s. The recovery phrase is not in this file;\n"
                          "#   keys derived after this dump are only recoverable from the phrase.\n",
                          pwallet->GetHDSeedId().GetHex().c_str());
    file << "\n";

    // Key birth times aren't recorded in this wallet format, so every key
    // gets the earliest time and an import rescans from genesis.
    const string strTime = "1970-01-01T00:00:01Z";
    for (const CKeyID& keyid : setKeys) {
        CSecret secret;
        bool fCompressed;
        if (!pwallet->GetSecret(keyid, secret, fCompressed))
            return Abort("Could not read the private key of " + CBitcoinAddress(keyid).ToString() +
                         " (the wallet may have been locked while it was being dumped). Nothing was written.");
        string strAddr = CBitcoinAddress(keyid).ToString();
        string strSecret = CBitcoinSecret(secret, fCompressed).ToString();
        string strKind;
        auto it = pwallet->mapAddressBook.find(keyid);
        if (it != pwallet->mapAddressBook.end())
            strKind = "label=" + EncodeDumpString(it->second);
        else if (setReserve.count(keyid))
            strKind = "reserve=1";
        else
            strKind = "change=1";
        file << strprintf("%s %s %s # addr=%s\n", strSecret.c_str(), strTime.c_str(), strKind.c_str(), strAddr.c_str());
    }
    file << "\n# End of dump\n";
    file.close();
    if (file.fail())
        return Abort("Error writing wallet dump file");
    {
        std::error_code ec;
        if (!fOverwrite && std::filesystem::exists(path))
            return Abort(path.string() + " appeared while the dump was being written. Choose a new filename.");
        std::filesystem::rename(pathTmp, path, ec);
        if (ec)
            return Abort("Cannot move the wallet dump into place: " + ec.message());
    }
    return true;
}

// nStartTime: the time the oldest key being looked for was made (0: unknown, so from the first block). The scan begins two
// hours before it, as block times are only roughly in order, and a key made later than the newest block has nothing to find.
static void RescanWallet(CWallet* pwallet, int64 nStartTime = 0)
{
    CBlockIndex* pindexStart = pindexGenesisBlock;
    if (nStartTime > 0)
    {
        pindexStart = pindexBest;
        while (pindexStart && pindexStart->pprev && pindexStart->GetBlockTime() >= nStartTime - 2 * 60 * 60)
            pindexStart = pindexStart->pprev;
    }
    pwallet->ScanForWalletTransactions(pindexStart, true);
    pwallet->ReacceptWalletTransactions();
}


// ---------------------------------------------------------------------------------------------------------------------------
// Encrypted backup: everything needed to rebuild the wallet's keys, in one file that is safe to keep anywhere.
//
//   "CORGIBK1" | log2(N) (1 byte) | salt (16) | nonce (12) | ciphertext | GCM tag (16)
//
// The key is scrypt(passphrase, salt, N, r = 8, p = 1); the cipher is AES-256-GCM with the header as additional data, so a wrong
// passphrase and a changed file (a flipped bit anywhere, a different cost) are both refused, not decrypted into garbage. The
// plain text inside is JSON. Nothing about the keys is in the clear, not even how many there are beyond the file's size.
// ---------------------------------------------------------------------------------------------------------------------------

static const unsigned char BACKUP_MAGIC[8] = {'C', 'O', 'R', 'G', 'I', 'B', 'K', '1'};
static const unsigned int BACKUP_LOG2N = 15;                   // 32 MiB to derive the key: slow for a thief, a tenth of a second for you
static const unsigned int BACKUP_LOG2N_MIN = 14, BACKUP_LOG2N_MAX = 20;
static const size_t BACKUP_SALT = 16, BACKUP_NONCE = 12, BACKUP_TAG = 16, BACKUP_HEADER = 8 + 1 + BACKUP_SALT + BACKUP_NONCE;
static const size_t BACKUP_MIN_PASSPHRASE = 8;

static bool BackupKey(const std::string& strPass, const unsigned char* pSalt, unsigned int nLog2N, unsigned char* pKeyOut)
{
    const uint64_t N = (uint64_t)1 << nLog2N;
    const uint64_t nMaxMem = 128 * N * 8 + (16u << 20);
    return EVP_PBE_scrypt(strPass.data(), strPass.size(), pSalt, BACKUP_SALT, N, 8, 1, nMaxMem, pKeyOut, 32) == 1;
}

static bool BackupEncrypt(const std::string& strPass, const std::string& strPlain, std::vector<unsigned char>& vchOut)
{
    std::vector<unsigned char> header(BACKUP_HEADER);
    memcpy(&header[0], BACKUP_MAGIC, 8);
    header[8] = (unsigned char)BACKUP_LOG2N;
    if (!GetRandBytesChecked(&header[9], BACKUP_SALT + BACKUP_NONCE))
        return false;
    unsigned char key[32];
    if (!BackupKey(strPass, &header[9], BACKUP_LOG2N, key))
        return false;

    bool fOk = false;
    std::vector<unsigned char> ct(strPlain.size() + BACKUP_TAG);
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    int nLen = 0, nTotal = 0;
    if (ctx && EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) == 1 &&
        EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, (int)BACKUP_NONCE, nullptr) == 1 &&
        EVP_EncryptInit_ex(ctx, nullptr, nullptr, key, &header[9 + BACKUP_SALT]) == 1 &&
        EVP_EncryptUpdate(ctx, nullptr, &nLen, &header[0], (int)header.size()) == 1 &&          // the header is authenticated
        EVP_EncryptUpdate(ctx, ct.data(), &nLen, (const unsigned char*)strPlain.data(), (int)strPlain.size()) == 1)
    {
        nTotal = nLen;
        if (EVP_EncryptFinal_ex(ctx, ct.data() + nTotal, &nLen) == 1)
        {
            nTotal += nLen;
            if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, (int)BACKUP_TAG, ct.data() + nTotal) == 1)
            {
                vchOut = header;
                vchOut.insert(vchOut.end(), ct.begin(), ct.begin() + nTotal + BACKUP_TAG);
                fOk = true;
            }
        }
    }
    if (ctx)
        EVP_CIPHER_CTX_free(ctx);
    OPENSSL_cleanse(key, sizeof(key));
    return fOk;
}

// false with strError set if the file is not a backup, the passphrase is wrong, or the file has been changed
static bool BackupDecrypt(const std::string& strPass, const std::vector<unsigned char>& vchIn, std::string& strPlain, std::string& strError)
{
    if (vchIn.size() < BACKUP_HEADER + BACKUP_TAG || memcmp(&vchIn[0], BACKUP_MAGIC, 8) != 0)
    {
        strError = "This is not a CorgiCoin encrypted backup";
        return false;
    }
    const unsigned int nLog2N = vchIn[8];
    if (nLog2N < BACKUP_LOG2N_MIN || nLog2N > BACKUP_LOG2N_MAX)
    {
        strError = "The backup asks for a key derivation this wallet will not do";
        return false;
    }
    unsigned char key[32];
    if (!BackupKey(strPass, &vchIn[9], nLog2N, key))
    {
        strError = "Could not derive the key from the passphrase";
        return false;
    }
    const size_t nCt = vchIn.size() - BACKUP_HEADER - BACKUP_TAG;
    std::vector<unsigned char> plain(nCt + 16);
    EVP_CIPHER_CTX* ctx = EVP_CIPHER_CTX_new();
    int nLen = 0, nTotal = 0;
    bool fOk = false;
    if (ctx && EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), nullptr, nullptr, nullptr) == 1 &&
        EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, (int)BACKUP_NONCE, nullptr) == 1 &&
        EVP_DecryptInit_ex(ctx, nullptr, nullptr, key, &vchIn[9 + BACKUP_SALT]) == 1 &&
        EVP_DecryptUpdate(ctx, nullptr, &nLen, &vchIn[0], (int)BACKUP_HEADER) == 1 &&
        EVP_DecryptUpdate(ctx, plain.data(), &nLen, &vchIn[BACKUP_HEADER], (int)nCt) == 1)
    {
        nTotal = nLen;
        unsigned char tag[BACKUP_TAG];
        memcpy(tag, &vchIn[BACKUP_HEADER + nCt], BACKUP_TAG);
        if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, (int)BACKUP_TAG, tag) == 1 &&
            EVP_DecryptFinal_ex(ctx, plain.data() + nTotal, &nLen) == 1)
        {
            nTotal += nLen;
            strPlain.assign((const char*)plain.data(), (size_t)nTotal);
            fOk = true;
        }
    }
    if (ctx)
        EVP_CIPHER_CTX_free(ctx);
    OPENSSL_cleanse(key, sizeof(key));
    OPENSSL_cleanse(plain.data(), plain.size());
    if (!fOk)
        strError = "Wrong passphrase, or the backup has been changed or damaged";
    return fOk;
}

static const char* BackupChainName() { return fRegTest ? "regtest" : fTestNet ? "test" : "main"; }

bool ExportEncryptedBackup(CWallet* pwallet, const std::filesystem::path& path, const std::string& strPass, std::string& strError)
{
    if (pwallet->IsLocked()) {
        strError = "Wallet is locked";
        return false;
    }
    if (strPass.size() < BACKUP_MIN_PASSPHRASE) {
        strError = strprintf("The backup passphrase must be at least %d characters", (int)BACKUP_MIN_PASSPHRASE);
        return false;
    }
    if (std::filesystem::exists(path)) {
        strError = path.string() + " already exists. Choose a new filename so an existing file is never overwritten.";
        return false;
    }

    std::string strPlain;
    {
        LOCK2(cs_main, pwallet->cs_wallet);
        Object root;
        root.emplace_back("version", 1);
        root.emplace_back("created", (int64_t)GetTime());
        root.emplace_back("chain", std::string(BackupChainName()));
        root.emplace_back("hdmnemonic", pwallet->IsHDEnabled() ? pwallet->GetHDMnemonic() : std::string());
        root.emplace_back("hdindex", (int64_t)pwallet->nHDExternalIndex);

        std::set<CKeyID> setKeys;
        pwallet->GetKeys(setKeys);
        Array keys;
        for (const CKeyID& keyid : setKeys) {
            CSecret secret;
            bool fCompressed;
            if (!pwallet->GetSecret(keyid, secret, fCompressed)) {
                strError = "Could not read the private key of " + CBitcoinAddress(keyid).ToString() + ". Nothing was written.";
                return false;
            }
            Object k;
            k.emplace_back("secret", CBitcoinSecret(secret, fCompressed).ToString());
            auto itMeta = pwallet->mapKeyMetadata.find(keyid);
            k.emplace_back("time", (int64_t)(itMeta != pwallet->mapKeyMetadata.end() ? itMeta->second.nCreateTime : 0));
            k.emplace_back("hdkeypath", itMeta != pwallet->mapKeyMetadata.end() ? itMeta->second.strHDKeypath : std::string());
            keys.push_back(k);
        }
        root.emplace_back("keys", keys);

        Array labels;
        for (const auto& item : pwallet->mapAddressBook) {
            Object l;
            l.emplace_back("address", CBitcoinAddress(item.first).ToString());
            l.emplace_back("label", item.second);
            labels.push_back(l);
        }
        root.emplace_back("labels", labels);

        Array watch;
        for (const CScript& script : pwallet->setWatchOnly)
            watch.push_back(HexStr(script.begin(), script.end()));
        root.emplace_back("watchonly", watch);

        strPlain = write_string(Value(root), false);
    }

    std::vector<unsigned char> vchFile;
    const bool fEncrypted = BackupEncrypt(strPass, strPlain, vchFile);
    OPENSSL_cleanse(&strPlain[0], strPlain.size());
    if (!fEncrypted) {
        strError = "Could not encrypt the backup";
        return false;
    }

    const std::filesystem::path pathTmp = path.string() + ".tmp";
    {
        std::ofstream file(pathTmp, std::ios::out | std::ios::trunc | std::ios::binary);
        if (!file.is_open()) {
            strError = "Cannot open the backup file";
            return false;
        }
        file.write((const char*)vchFile.data(), (std::streamsize)vchFile.size());
        file.close();
        if (file.fail()) {
            std::error_code ec;
            std::filesystem::remove(pathTmp, ec);
            strError = "Error writing the backup file";
            return false;
        }
    }
    std::error_code ec;
    std::filesystem::permissions(pathTmp, std::filesystem::perms::owner_read | std::filesystem::perms::owner_write,
                                 std::filesystem::perm_options::replace, ec);
    std::filesystem::rename(pathTmp, path, ec);
    if (ec) {
        std::filesystem::remove(pathTmp, ec);
        strError = "Cannot move the backup into place";
        return false;
    }
    return true;
}

bool ImportEncryptedBackup(CWallet* pwallet, const std::filesystem::path& path, const std::string& strPass,
                           int& nKeysAdded, int& nLabels, std::string& strError)
{
    nKeysAdded = nLabels = 0;
    if (pwallet->IsLocked()) {
        strError = "Wallet is locked";
        return false;
    }
    std::ifstream file(path, std::ios::in | std::ios::binary);
    if (!file.is_open()) {
        strError = "Cannot open the backup file";
        return false;
    }
    std::vector<unsigned char> vchFile((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    if (vchFile.size() > 64u * 1024 * 1024) {
        strError = "That file is too big to be a backup";
        return false;
    }
    std::string strPlain;
    if (!BackupDecrypt(strPass, vchFile, strPlain, strError))
        return false;

    Value root;
    const bool fParsed = read_string(strPlain, root);
    OPENSSL_cleanse(&strPlain[0], strPlain.size());
    if (!fParsed || root.type() != obj_type) {
        strError = "The backup decrypts but its contents are not understood";
        return false;
    }
    const Object obj = root.get_obj();
    const Value& vChain = find_value(obj, "chain");
    if (vChain.type() != str_type || vChain.get_str() != BackupChainName()) {
        strError = std::string("This backup is for another network (this node is on ") + BackupChainName() + ")";
        return false;
    }

    LOCK2(cs_main, pwallet->cs_wallet);

    // the recovery phrase: a wallet without one takes it; one that has a different one is not touched
    const Value& vMnemonic = find_value(obj, "hdmnemonic");
    if (vMnemonic.type() == str_type && !vMnemonic.get_str().empty()) {
        const std::string strMnemonic = vMnemonic.get_str();
        if (!pwallet->IsHDEnabled()) {
            std::string strHDError;
            if (!pwallet->SetHDSeedFromMnemonic(strMnemonic, strHDError)) {
                strError = "Could not set the recovery phrase from the backup: " + strHDError;
                return false;
            }
        } else if (pwallet->GetHDMnemonic() != strMnemonic) {
            strError = "This wallet already has a different recovery phrase: restore a backup into an empty wallet, or one with the same phrase";
            return false;
        }
    }

    // The next address made from the phrase must be one the old wallet had not handed out: take the index it had reached.
    const Value& vIndex = find_value(obj, "hdindex");
    if (vIndex.type() == int_type && pwallet->IsHDEnabled()) {
        const uint32_t nIndex = (uint32_t)std::max<int64>(0, std::min<int64>(vIndex.get_int64(), 1000000));
        if (nIndex > pwallet->nHDExternalIndex) {
            pwallet->nHDExternalIndex = nIndex;
            if (pwallet->fFileBacked)
                CWalletDB(pwallet->strWalletFile).WriteHDChain(nIndex);
        }
    }

    int64 nOldest = std::numeric_limits<int64>::max();
    bool fUnknownTime = false;
    const Value& vKeys = find_value(obj, "keys");
    if (vKeys.type() == array_type) {
        for (const Value& vKey : vKeys.get_array()) {
            if (vKey.type() != obj_type)
                continue;
            const Object k = vKey.get_obj();
            const Value& vSecret = find_value(k, "secret");
            if (vSecret.type() != str_type)
                continue;
            CBitcoinSecret secret;
            if (!secret.SetString(vSecret.get_str()))
                continue;
            bool fCompressed;
            CSecret vchSecret = secret.GetSecret(fCompressed);
            CKey key;
            try {
                key.SetSecret(vchSecret, fCompressed);
            } catch (const key_error&) {
                continue;
            }
            const CKeyID keyid = key.GetPubKey().GetID();
            int64 nTime = 0;
            const Value& vTime = find_value(k, "time");
            if (vTime.type() == int_type)
                nTime = vTime.get_int64();
            if (nTime > 0)
                nOldest = std::min(nOldest, nTime);
            else
                fUnknownTime = true;
            if (pwallet->HaveKey(keyid))
                continue;
            if (!pwallet->AddKey(key)) {
                strError = "Error adding a key from the backup to the wallet";
                return false;
            }
            CKeyMetadata meta(nTime);
            const Value& vPath = find_value(k, "hdkeypath");
            if (vPath.type() == str_type)
                meta.strHDKeypath = vPath.get_str();
            pwallet->SetKeyMetadata(key.GetPubKey(), meta);
            nKeysAdded++;
        }
    }

    const Value& vLabels = find_value(obj, "labels");
    if (vLabels.type() == array_type) {
        for (const Value& vLabel : vLabels.get_array()) {
            if (vLabel.type() != obj_type)
                continue;
            const Object l = vLabel.get_obj();
            const Value& vAddr = find_value(l, "address");
            const Value& vText = find_value(l, "label");
            if (vAddr.type() != str_type || vText.type() != str_type)
                continue;
            CBitcoinAddress address(vAddr.get_str());
            if (!address.IsValid())
                continue;
            pwallet->SetAddressBookName(address.Get(), vText.get_str());
            nLabels++;
        }
    }

    const Value& vWatch = find_value(obj, "watchonly");
    if (vWatch.type() == array_type) {
        for (const Value& vScript : vWatch.get_array()) {
            if (vScript.type() != str_type || !IsHex(vScript.get_str()))
                continue;
            std::vector<unsigned char> v = ParseHex(vScript.get_str());
            pwallet->AddWatchOnly(CScript(v.begin(), v.end()));
        }
    }

    // the chain is searched from when the oldest key was made (from the first block if any key's date is not known)
    CBlockIndex* pindexStart = pindexGenesisBlock;
    if (!fUnknownTime && nOldest != std::numeric_limits<int64>::max()) {
        pindexStart = pindexBest;
        while (pindexStart && pindexStart->pprev && pindexStart->GetBlockTime() >= nOldest - 2 * 60 * 60)
            pindexStart = pindexStart->pprev;
    }
    if (nKeysAdded > 0 || pwallet->IsHDEnabled()) {
        pwallet->ScanForWalletTransactions(pindexStart, true);
        pwallet->ReacceptWalletTransactions();
    }
    return true;
}

bool ImportWalletFromFile(CWallet* pwallet, const std::filesystem::path& path, int& nImported, string& strError)
{
    nImported = 0;
    if (pwallet->IsLocked()) {
        strError = "Wallet is locked";
        return false;
    }

    std::ifstream file(path);
    if (!file.is_open()) {
        strError = "Cannot open wallet dump file";
        return false;
    }

    LOCK2(cs_main, pwallet->cs_wallet);

    bool fGood = true;
    string line;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#')
            continue;

        vector<string> vstr;
        std::istringstream ss(line);
        for (string tok; ss >> tok; )
            vstr.push_back(tok);
        if (vstr.size() < 2)
            continue;

        CBitcoinSecret vchSecret;
        if (!vchSecret.SetString(vstr[0])) {
            fGood = false;
            continue;
        }
        CKey key;
        bool fCompressed;
        CSecret secret = vchSecret.GetSecret(fCompressed);
        key.SetSecret(secret, fCompressed);
        CKeyID keyid = key.GetPubKey().GetID();
        if (pwallet->HaveKey(keyid))
            continue;

        bool fLabel = false;
        string strLabel;
        for (size_t i = 2; i < vstr.size(); i++) {
            if (vstr[i][0] == '#')
                break;
            if (vstr[i].compare(0, 6, "label=") == 0) {
                strLabel = DecodeDumpString(vstr[i].substr(6));
                fLabel = true;
            }
        }
        pwallet->SetKeyMetadata(key.GetPubKey(), CKeyMetadata(0));     // when the key was made is not known here: not the day of the import
        if (!pwallet->AddKey(key)) {
            fGood = false;
            continue;
        }
        if (fLabel)
            pwallet->SetAddressBookName(keyid, strLabel);
        nImported++;
    }
    file.close();

    pwallet->MarkDirty();
    if (nImported > 0)
        RescanWallet(pwallet);

    if (!fGood) {
        strError = "Error adding some keys to wallet";
        return false;
    }
    return true;
}

bool ImportPrivateKey(CWallet* pwallet, const string& strSecret, const string& strLabel, bool& fAlreadyHad, string& strError, int64 nTimestamp)
{
    fAlreadyHad = false;
    CBitcoinSecret vchSecret;
    if (!vchSecret.SetString(strSecret)) {
        strError = "Invalid private key";
        return false;
    }
    if (pwallet->IsLocked()) {
        strError = "Wallet is locked";
        return false;
    }

    CKey key;
    bool fCompressed;
    CSecret secret = vchSecret.GetSecret(fCompressed);
    try {
        key.SetSecret(secret, fCompressed);
    } catch (const key_error&) {
        strError = "Invalid private key: the value is not a valid secret (zero or at least the curve order)";
        return false;
    }
    CKeyID keyid = key.GetPubKey().GetID();

    LOCK2(cs_main, pwallet->cs_wallet);

    pwallet->MarkDirty();
    pwallet->SetAddressBookName(keyid, strLabel);
    if (pwallet->HaveKey(keyid)) {
        fAlreadyHad = true;
        return true;
    }
    // the key's own date, or 0 (unknown) if none was given: never the day it was imported, which a later backup would take for its birth
    // (set before the key is added, which stamps "now" only on a key with no metadata)
    pwallet->SetKeyMetadata(key.GetPubKey(), CKeyMetadata(nTimestamp > 0 ? nTimestamp : 0));
    if (!pwallet->AddKey(key)) {
        strError = "Error adding key to wallet";
        return false;
    }
    if (nTimestamp > 0)
        pwallet->SetKeyMetadata(key.GetPubKey(), CKeyMetadata(nTimestamp));      // the key's own date, not the day it was imported
    RescanWallet(pwallet, nTimestamp);
    return true;
}
