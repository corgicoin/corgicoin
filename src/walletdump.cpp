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
#include "bip39.h"
#include "json/json_compat.h"
#include <openssl/crypto.h>
#include <openssl/evp.h>

#include <fstream>
#ifndef WIN32
#include <fcntl.h>
#include <unistd.h>
#endif
#include <cerrno>
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
static const unsigned int BACKUP_LOG2N = 17;                   // 128 MiB to derive the key: slow for a thief, under a second for you
// What a file may ask for: 2^18 is 256 MiB, as much as this wallet will spend on a file it was handed (the file chooses the cost,
// and the RPC runs with the wallet and the chain locked). Backups made at 2^15 by the first version still open.
static const unsigned int BACKUP_LOG2N_MIN = 14, BACKUP_LOG2N_MAX = 18;
static const size_t BACKUP_SALT = 16, BACKUP_NONCE = 12, BACKUP_TAG = 16, BACKUP_HEADER = 8 + 1 + BACKUP_SALT + BACKUP_NONCE;
static const size_t BACKUP_MIN_PASSPHRASE = 12;
static const uintmax_t BACKUP_MAX_FILE = 8u * 1024 * 1024;      // a backup of tens of thousands of keys is a few MB
static const size_t BACKUP_MAX_PLAIN = 4u * 1024 * 1024;        // what it decrypts to, before it is parsed
static const int BACKUP_MAX_NESTING = 8;                        // the format nests three deep (object, array, object)

// Overwrites every string of a JSON tree in place (the tree held the keys and the recovery phrase of a backup). The JSON shim's accessors
// (get_str, get_obj, get_array) return copies, so each tree that was built or copied is wiped itself; strings copied out of it one at a time
// (a single key's text while it is imported) are not reached from here.
static void WipeJsonStrings(const Value& v) { v.wipe_strings(); }
static void WipeJsonStrings(const Object& o)
{
    for (const Pair& p : o)
        p.value_.wipe_strings();
}
static void WipeJsonStrings(const Array& a)
{
    for (const Value& v : a)
        v.wipe_strings();
}
struct JsonWiper {
    const Value& v;
    explicit JsonWiper(const Value& vIn) : v(vIn) {}
    ~JsonWiper() { WipeJsonStrings(v); }
};
struct JsonObjectWiper {
    const Object& o;
    explicit JsonObjectWiper(const Object& oIn) : o(oIn) {}
    ~JsonObjectWiper() { WipeJsonStrings(o); }
};

// Whether the JSON text nests no deeper than nMax levels of [ and { (outside strings), checked without parsing it
static bool JsonNestingOk(const std::string& str, int nMax)
{
    int nDepth = 0;
    bool fInString = false;
    for (size_t i = 0; i < str.size(); i++) {
        const char c = str[i];
        if (fInString) {
            if (c == '\\')
                i++;
            else if (c == '"')
                fInString = false;
        } else if (c == '"')
            fInString = true;
        else if (c == '[' || c == '{') {
            if (++nDepth > nMax)
                return false;
        } else if (c == ']' || c == '}')
            nDepth--;
    }
    return true;
}

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
        // A wallet with an HD seed whose phrase cannot be read (it did not decrypt when the wallet was unlocked) would give a backup
        // with no phrase, which restores none of the keys made after it: refuse rather than write that.
        if (pwallet->IsHDEnabled() && (!pwallet->IsHDSeedAvailable() || pwallet->GetHDMnemonic().empty())) {
            strError = "This wallet has an HD seed whose recovery phrase is not available (it could not be decrypted), so a backup would not hold it. Nothing was written.";
            return false;
        }
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
            WipeJsonStrings(k);         // (pushed as a copy)
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

        // redeem scripts (pay-to-script-hash, multisig): without them the coins sent to them cannot be spent after a restore
        std::vector<CScript> vRedeem;
        pwallet->GetCScripts(vRedeem);
        Array cscripts;
        for (const CScript& script : vRedeem)
            cscripts.push_back(HexStr(script.begin(), script.end()));
        root.emplace_back("cscript", cscripts);

        // every key and the phrase are in each of these: the tree, the list it was built from, and the keys array
        const Value vRoot(root);
        strPlain = write_string(vRoot, false);
        WipeJsonStrings(vRoot);
        WipeJsonStrings(root);
        WipeJsonStrings(keys);
    }

    std::vector<unsigned char> vchFile;
    const bool fEncrypted = BackupEncrypt(strPass, strPlain, vchFile);
    OPENSSL_cleanse(&strPlain[0], strPlain.size());
    if (!fEncrypted) {
        strError = "Could not encrypt the backup";
        return false;
    }

    // A fresh name next to the target (a file of the user's called <path>.tmp is never truncated), created owner-only and
    // exclusively, and not through a symlink someone left there, as DumpWalletToFile does it: never written first and
    // chmod-ed after. (Windows has no such flags; there the file is created new, and the directory's permissions apply.)
    const std::filesystem::path pathTmp = path.string() + strprintf(".tmp%08x", (unsigned int)GetRand(0xffffffff));
    auto Remove = [&]() {
        std::error_code ec;
        std::filesystem::remove(pathTmp, ec);
    };
#ifndef WIN32
    {
        int fd = open(pathTmp.string().c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        if (fd < 0) {
            strError = "Cannot create the backup file";
            return false;
        }
        size_t nDone = 0;
        while (nDone < vchFile.size()) {
            ssize_t n = write(fd, vchFile.data() + nDone, vchFile.size() - nDone);
            if (n <= 0) {
                close(fd);
                Remove();
                strError = "Error writing the backup file";
                return false;
            }
            nDone += (size_t)n;
        }
        if (fsync(fd) != 0 || close(fd) != 0) {
            Remove();
            strError = "Error writing the backup file";
            return false;
        }
    }
#else
    {
        std::ofstream file(pathTmp, std::ios::out | std::ios::binary);
        if (!file.is_open()) {
            strError = "Cannot create the backup file";
            return false;
        }
        file.write((const char*)vchFile.data(), (std::streamsize)vchFile.size());
        file.close();
        if (file.fail()) {
            Remove();
            strError = "Error writing the backup file";
            return false;
        }
    }
#endif
    // the check at the top and the move are apart: look again, so a file that appeared in between is not replaced
    std::error_code ec;
    if (std::filesystem::exists(path, ec)) {
        Remove();
        strError = path.string() + " appeared while the backup was being written. Choose a new filename.";
        return false;
    }
#ifndef WIN32
    // link() fails if the name is taken, where rename() would replace it; a file system without hard links falls back to rename
    if (link(pathTmp.string().c_str(), path.string().c_str()) == 0) {
        Remove();
        return true;
    }
    if (errno == EEXIST) {
        Remove();
        strError = path.string() + " appeared while the backup was being written. Choose a new filename.";
        return false;
    }
#endif
    std::filesystem::rename(pathTmp, path, ec);
    if (ec) {
        Remove();
        strError = "Cannot move the backup into place";
        return false;
    }
    return true;
}

// An HD key path from a file, "m/44'/<coin>'/0'/0/<index>": the index, or -1 if it is not one (a file is not trusted to say anything else)
static int64 HDIndexFromPath(const std::string& strPath)
{
    if (strPath.size() > 64 || strPath.compare(0, 2, "m/") != 0)
        return -1;
    const size_t nSlash = strPath.rfind('/');
    const std::string strIndex = strPath.substr(nSlash + 1);
    if (strIndex.empty() || strIndex.size() > 9 || strIndex.find_first_not_of("0123456789") != std::string::npos)
        return -1;
    for (char c : strPath)
        if (!((c >= '0' && c <= '9') || c == 'm' || c == '/' || c == '\''))
            return -1;
    return atoll(strIndex.c_str());
}

bool ImportEncryptedBackup(CWallet* pwallet, const std::filesystem::path& path, const std::string& strPass, bool fAdoptPhrase,
                           int& nKeysAdded, int& nLabels, bool& fPhraseAdopted, std::string& strError)
{
    nKeysAdded = nLabels = 0;
    fPhraseAdopted = false;
    if (pwallet->IsLocked()) {
        strError = "Wallet is locked";
        return false;
    }
    // The file is looked at before it is read: a pipe or a device would be read for ever, and a big file into memory. (A backup of
    // thousands of keys is a few hundred kB.)
    std::error_code ec;
    if (!std::filesystem::is_regular_file(path, ec) || ec) {
        strError = "The backup is not a regular file";
        return false;
    }
    const uintmax_t nFileSize = std::filesystem::file_size(path, ec);
    if (ec || nFileSize > BACKUP_MAX_FILE) {
        strError = "That file is too big to be a backup";
        return false;
    }
    std::ifstream file(path, std::ios::in | std::ios::binary);
    if (!file.is_open()) {
        strError = "Cannot open the backup file";
        return false;
    }
    std::vector<unsigned char> vchFile((size_t)nFileSize);
    if (nFileSize > 0)
        file.read((char*)&vchFile[0], (std::streamsize)nFileSize);
    if (file.gcount() != (std::streamsize)nFileSize) {
        strError = "Cannot read the backup file";
        return false;
    }
    std::string strPlain;
    if (!BackupDecrypt(strPass, vchFile, strPlain, strError))
        return false;
    // What decrypts is whatever the person who made the file chose (anyone who knows its passphrase): it is bounded before it is parsed,
    // in size and in how deeply it nests (the parser is recursive, and a long run of "[" would use up the stack of this thread)
    if (strPlain.size() > BACKUP_MAX_PLAIN || !JsonNestingOk(strPlain, BACKUP_MAX_NESTING)) {
        OPENSSL_cleanse(&strPlain[0], strPlain.size());
        strError = "The backup decrypts but its contents are not understood";
        return false;
    }

    Value root;
    const bool fParsed = read_string(strPlain, root);
    OPENSSL_cleanse(&strPlain[0], strPlain.size());
    JsonWiper wiper(root);          // every string of the parsed tree (the keys, the phrase) is overwritten on the way out, whichever way that is
    if (!fParsed || root.type() != obj_type) {
        strError = "The backup decrypts but its contents are not understood";
        return false;
    }
    const Object& obj = root.get_obj();         // a copy of the tree (the shim's get_obj copies), with every secret in it: wiped too
    JsonObjectWiper objWiper(obj);
    // Only the format this node writes (version 1) is read: a file of another version (a newer node's, or one that says nothing or
    // something that is not a number) may mean things this code does not know, and is not read as if it were version 1.
    const Value& vVersion = find_value(obj, "version");
    if (vVersion.type() != int_type || vVersion.get_int64() != 1) {
        strError = "This backup is of a version this node does not read (it reads version 1)";
        return false;
    }
    const Value& vChain = find_value(obj, "chain");
    if (vChain.type() != str_type || vChain.get_str() != BackupChainName()) {
        strError = std::string("This backup is for another network (this node is on ") + BackupChainName() + ")";
        return false;
    }

    LOCK2(cs_main, pwallet->cs_wallet);
    if (pwallet->IsLocked()) {         // looked at again under the locks: it may have been locked while the file was read and decrypted
        strError = "Wallet is locked";
        return false;
    }

    // The recovery phrase. Every address the wallet makes from now on comes from it, so a wallet takes a backup's phrase only when
    // it is told to (adoptphrase): a file someone talked you into restoring must not be able to choose where your next deposits go.
    // A wallet that has a phrase keeps it, and refuses a backup of another one.
    const Value& vMnemonic = find_value(obj, "hdmnemonic");
    if (vMnemonic.type() == str_type && !vMnemonic.get_str().empty()) {
        std::string strMnemonic = bip39::NormaliseMnemonic(vMnemonic.get_str());    // as the wallet stores it: the file's spacing is not the phrase
        bool fOk = true;
        if (!pwallet->IsHDEnabled()) {
            if (fAdoptPhrase) {
                std::string strHDError;
                if (!pwallet->SetHDSeedFromMnemonic(strMnemonic, strHDError)) {
                    strError = "Could not set the recovery phrase from the backup: " + strHDError;
                    fOk = false;
                } else
                    fPhraseAdopted = true;
            }
        } else if (pwallet->GetHDMnemonic() != strMnemonic) {
            strError = "This wallet already has a different recovery phrase: restore a backup into an empty wallet, or one with the same phrase";
            fOk = false;
        }
        OPENSSL_cleanse(&strMnemonic[0], strMnemonic.size());
        if (!fOk)
            return false;
    }
    const bool fHD = pwallet->IsHDEnabled();

    // what the file's keys say about the HD indices they hold (so the index below can be held to what is there)
    int64 nHighestIndex = -1;
    const Value& vKeys = find_value(obj, "keys");
    if (vKeys.type() == array_type)
        for (const Value& vKey : vKeys.get_array()) {
            if (vKey.type() != obj_type)
                continue;
            const Object& kObj = vKey.get_obj();      // a reference into the tree (the tree is wiped on the way out; a copy would not be)
            const Value& vPath = find_value(kObj, "hdkeypath");
            const Value& vSecret = find_value(kObj, "secret");
            if (vPath.type() != str_type || vSecret.type() != str_type || !fHD)
                continue;
            // a path is the file's word: it counts only if the key really is the one the wallet's phrase makes at that index
            const int64 nPathIndex = HDIndexFromPath(vPath.get_str());
            CBitcoinSecret secret;
            if (nPathIndex < 0 || !secret.SetString(vSecret.get_str()))
                continue;
            bool fCompressed;
            CKey keyPath;
            try {
                keyPath.SetSecret(secret.GetSecret(fCompressed), fCompressed);
            } catch (const key_error&) {
                continue;
            }
            if (pwallet->HDKeyAtIndexIs((uint32_t)nPathIndex, keyPath.GetPubKey().GetID()))
                nHighestIndex = std::max(nHighestIndex, nPathIndex);
        }

    // The next address made from the phrase must be one the old wallet had not handed out: take the index it had reached, but no
    // further than the keys in the file reach plus the gap a restore from the phrase looks ahead. A higher one (a file can say any
    // number) would put new deposits where a restore from the phrase never looks.
    // Only a backup that holds this wallet's own phrase (checked or adopted above) says anything about its indices, and only as far as
    // its own keys reach: a restore from the phrase looks a gap past the highest key it finds paid, so the next address must not be
    // past the highest key that exists plus one (a gap on top of that put the next deposit one key beyond what a restore reaches).
    const Value& vIndex = find_value(obj, "hdindex");
    const bool fOwnPhrase = vMnemonic.type() == str_type && !vMnemonic.get_str().empty();
    if (vIndex.type() == int_type && fHD && fOwnPhrase) {
        const int64 nCap = std::max<int64>(nHighestIndex + 1, (int64)pwallet->nHDExternalIndex);
        const uint32_t nIndex = (uint32_t)std::max<int64>(0, std::min<int64>(vIndex.get_int64(), nCap));
        if (nIndex > pwallet->nHDExternalIndex) {
            pwallet->nHDExternalIndex = nIndex;
            if (pwallet->fFileBacked)
                CWalletDB(pwallet->strWalletFile).WriteHDChain(nIndex);
        }
    }
    // A phrase taken from the backup: the key pool still holds the wallet's old random keys, which the phrase does not cover, and the
    // next receive and change addresses would come from them. Make it again from the phrase, from the index just settled.
    if (fPhraseAdopted && !pwallet->NewKeyPool()) {
        strError = "The recovery phrase was taken from the backup, but the key pool could not be made again from it";
        return false;
    }

    int64 nOldest = std::numeric_limits<int64>::max();
    bool fUnknownTime = false;
    bool fAddedOther = false;       // watch-only entries or redeem scripts, which also need a look at the chain
    const bool fBackupPhrase = vMnemonic.type() == str_type && !vMnemonic.get_str().empty();

    // The chain is searched for what the new keys received, from when the oldest key was made: from the first block if any key's date is
    // not known, if watch-only entries or scripts came (they have no date), or if the backup holds a recovery phrase (the keys a phrase
    // makes are dated when this wallet derived them, which for a restored phrase is today, not when they were first used).
    // This runs on every way out once something was added, so a failure half way through does not leave coins that are not found.
    auto FinishAndRescan = [&]() {
        pwallet->MarkDirty();
        CBlockIndex* pindexStart = pindexGenesisBlock;
        if (!fUnknownTime && !fAddedOther && !fBackupPhrase && nOldest != std::numeric_limits<int64>::max()) {
            pindexStart = pindexBest;
            while (pindexStart && pindexStart->pprev && pindexStart->GetBlockTime() >= nOldest - 2 * 60 * 60)
                pindexStart = pindexStart->pprev;
        }
        if (nKeysAdded > 0 || fAddedOther || fHD) {
            pwallet->ScanForWalletTransactions(pindexStart, true);
            pwallet->ReacceptWalletTransactions();
        }
    };
    if (vKeys.type() == array_type) {
        for (const Value& vKey : vKeys.get_array()) {
            if (vKey.type() != obj_type)
                continue;
            const Object& k = vKey.get_obj();
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
            CKeyMetadata meta(nTime > 0 ? nTime : 0);
            const Value& vPath = find_value(k, "hdkeypath");
            if (vPath.type() == str_type && HDIndexFromPath(vPath.get_str()) >= 0)
                meta.strHDKeypath = vPath.get_str();
            if (!pwallet->AddKeyWithMetadata(key, meta)) {
                strError = "Error adding a key from the backup to the wallet (the keys before it were added and the chain was searched for them: run the import again to add the rest)";
                FinishAndRescan();
                return false;
            }
            nKeysAdded++;
        }
    }

    const Value& vWatch = find_value(obj, "watchonly");
    if (vWatch.type() == array_type) {
        for (const Value& vScript : vWatch.get_array()) {
            if (vScript.type() != str_type || !IsHex(vScript.get_str()))
                continue;
            std::vector<unsigned char> v = ParseHex(vScript.get_str());
            if (pwallet->AddWatchOnly(CScript(v.begin(), v.end())))
                fAddedOther = true;
        }
    }

    const Value& vRedeem = find_value(obj, "cscript");
    if (vRedeem.type() == array_type) {
        for (const Value& vScript : vRedeem.get_array()) {
            if (vScript.type() != str_type || !IsHex(vScript.get_str()))
                continue;
            std::vector<unsigned char> v = ParseHex(vScript.get_str());
            if (v.empty() || v.size() > 520)        // MAX_SCRIPT_ELEMENT_SIZE: a larger one cannot be a redeem script
                continue;
            const CScript script(v.begin(), v.end());
            if (!pwallet->HaveCScript(script.GetID())) {
                if (!pwallet->AddCScript(script)) {
                    strError = "Error adding a redeem script from the backup to the wallet (what came before it was added: run the import again)";
                    FinishAndRescan();
                    return false;
                }
                fAddedOther = true;
            }
        }
    }

    // A label is added only to an address the wallet can spend or now watches (after the keys, watch-only entries and scripts above),
    // and only if it has none: a file cannot rename an address the wallet knows, nor add an attacker's address as a contact you
    // would trust ("Exchange deposit")
    const Value& vLabels = find_value(obj, "labels");
    if (vLabels.type() == array_type) {
        for (const Value& vLabel : vLabels.get_array()) {
            if (vLabel.type() != obj_type)
                continue;
            const Object& l = vLabel.get_obj();
            const Value& vAddr = find_value(l, "address");
            const Value& vText = find_value(l, "label");
            if (vAddr.type() != str_type || vText.type() != str_type)
                continue;
            CBitcoinAddress address(vAddr.get_str());
            if (!address.IsValid() || pwallet->mapAddressBook.count(address.Get()))
                continue;
            CTxOut txoutLabel;
            txoutLabel.scriptPubKey.SetDestination(address.Get());
            if (!::IsMine(*pwallet, txoutLabel.scriptPubKey) && !pwallet->IsWatchOnly(txoutLabel))
                continue;
            pwallet->SetAddressBookName(address.Get(), vText.get_str());
            nLabels++;
        }
    }

    // the balance and the cached amounts are worked out again, and the chain is searched (see FinishAndRescan)
    FinishAndRescan();
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
        try {
            key.SetSecret(secret, fCompressed);
        } catch (const key_error&) {
            // a zero secret, or one at or above the curve order: a bad line, not a reason to leave with the earlier keys added and not searched for
            fGood = false;
            continue;
        }
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
        // when the key was made is not known here: not the day of the import
        if (!pwallet->AddKeyWithMetadata(key, CKeyMetadata(0))) {
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
    // (the key is written first and its metadata after it: a key that cannot be added leaves no metadata record)
    if (!pwallet->AddKeyWithMetadata(key, CKeyMetadata(nTimestamp > 0 ? nTimestamp : 0))) {
        strError = "Error adding key to wallet";
        return false;
    }
    RescanWallet(pwallet, nTimestamp);
    return true;
}
