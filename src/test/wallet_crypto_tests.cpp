#include <boost/test/unit_test.hpp>

#include <cstring>
#include <string>
#include <vector>

#include "crypter.h"
#include "util.h"
#include "wallet.h"

using namespace std;

// Passphrase derivation compatibility. Derivation method 0 is Bitcoin's EVP_BytesToKey(SHA-512) on every build;
// CorgiCoin v4.2 to v4.7 built against OpenSSL 3 wrote PBKDF2-derived master keys under the same number, and
// those must keep unlocking.

BOOST_AUTO_TEST_SUITE(wallet_crypto_tests)

namespace {

vector<unsigned char> Salt() { return ParseHex("a1b2c3d4e5f60718"); }

CKeyingMaterial Plaintext()
{
    CKeyingMaterial p(32);
    for (size_t i = 0; i < p.size(); i++)
        p[i] = (unsigned char)i;
    return p;
}

string EncryptHex(const SecureString& passphrase, unsigned int nMethod)
{
    CCrypter crypter;
    BOOST_REQUIRE(crypter.SetKeyFromPassphrase(passphrase, Salt(), 25000, nMethod));
    vector<unsigned char> ciphertext;
    BOOST_REQUIRE(crypter.Encrypt(Plaintext(), ciphertext));
    return HexStr(ciphertext.begin(), ciphertext.end());
}

// A wallet with one key, encrypted in memory under a master key whose passphrase key is derived with nMethod
// and recorded as derivation method 0 (exactly what v4.2-v4.7 wrote for PBKDF2)
class TestCryptoWallet : public CWallet
{
public:
    using CCryptoKeyStore::Lock;          // protected in the base; the tests lock again between unlocks
    CKey key;
    CKeyingMaterial vMasterKeyPlain;

    TestCryptoWallet(const SecureString& passphrase, unsigned int nMethod)
    {
        key.MakeNewKey(true);
        BOOST_REQUIRE(AddKey(key));
        vMasterKeyPlain.resize(WALLET_CRYPTO_KEY_SIZE);
        uint256 r = GetRandHash();
        memcpy(&vMasterKeyPlain[0], &r, WALLET_CRYPTO_KEY_SIZE);
        BOOST_REQUIRE(EncryptKeys(vMasterKeyPlain));

        CMasterKey kMasterKey;
        kMasterKey.vchSalt = Salt();
        kMasterKey.nDeriveIterations = 1000;
        kMasterKey.nDerivationMethod = 0;
        CCrypter crypter;
        BOOST_REQUIRE(crypter.SetKeyFromPassphrase(passphrase, kMasterKey.vchSalt, kMasterKey.nDeriveIterations, nMethod));
        BOOST_REQUIRE(crypter.Encrypt(vMasterKeyPlain, kMasterKey.vchCryptedKey));
        mapMasterKeys[1] = kMasterKey;
        BOOST_REQUIRE(Lock());
    }

    bool CanSign()
    {
        CKey k;
        return GetKey(key.GetPubKey().GetID(), k) && k.GetPubKey() == key.GetPubKey();
    }
};

} // namespace

BOOST_AUTO_TEST_CASE(method0_is_bytestokey_on_every_build)
{
    // Computed independently (Python hashlib + the openssl CLI): SHA512^25000(passphrase || salt) -> key, IV
    BOOST_CHECK_EQUAL(EncryptHex("correct horse battery staple", WALLET_DERIVATION_BYTESTOKEY_SHA512),
        "17cad2e3728b490016599a0ddac1ba44efe80fb5703ce840d8d7c04a441ea6a14704427ef7c554c886b746288dd34e3f");
}

BOOST_AUTO_TEST_CASE(v4_pbkdf2_derivation_is_pinned)
{
    // PKCS5_PBKDF2_HMAC(SHA-512, 25000 rounds, 64 bytes) -> key, IV, as v4.2-v4.7 did on OpenSSL 3
    BOOST_CHECK_EQUAL(EncryptHex("correct horse battery staple", WALLET_DERIVATION_PBKDF2_SHA512_V4),
        "a14a548b0dfe0b183b7cef56c0f931048d4f7986979785548e850ca97567a46c3b02eef2ca950ef035844676a85d5138");
}

BOOST_AUTO_TEST_CASE(unknown_derivation_methods_are_rejected)
{
    CCrypter crypter;
    BOOST_CHECK(!crypter.SetKeyFromPassphrase("x", Salt(), 100, 1));
    BOOST_CHECK(!crypter.SetKeyFromPassphrase("x", Salt(), 0, 0));
    BOOST_CHECK(!crypter.SetKeyFromPassphrase("x", vector<unsigned char>(7, 1), 100, 0));
}

BOOST_AUTO_TEST_CASE(unlock_standard_method0_wallet)
{
    TestCryptoWallet wallet("passphrase", WALLET_DERIVATION_BYTESTOKEY_SHA512);
    BOOST_CHECK(wallet.IsLocked());
    BOOST_CHECK(!wallet.CanSign());
    BOOST_CHECK(!wallet.Unlock("wrong passphrase"));
    BOOST_CHECK(wallet.IsLocked());
    BOOST_CHECK(wallet.Unlock("passphrase"));
    BOOST_CHECK(!wallet.IsLocked());
    BOOST_CHECK(wallet.CanSign());
}

BOOST_AUTO_TEST_CASE(unlock_v4_pbkdf2_wallet)
{
    TestCryptoWallet wallet("passphrase", WALLET_DERIVATION_PBKDF2_SHA512_V4);
    BOOST_CHECK(!wallet.Unlock("wrong passphrase"));
    BOOST_CHECK(wallet.IsLocked());
    BOOST_CHECK(wallet.Unlock("passphrase"));
    BOOST_CHECK(wallet.CanSign());
}

BOOST_AUTO_TEST_CASE(unlock_rejects_unknown_stored_method)
{
    TestCryptoWallet wallet("passphrase", WALLET_DERIVATION_BYTESTOKEY_SHA512);
    wallet.mapMasterKeys[1].nDerivationMethod = 1;
    BOOST_CHECK(!wallet.Unlock("passphrase"));
    BOOST_CHECK(wallet.IsLocked());
}

// What a v4.5-v4.7 HD wallet looked like after encryptwallet: plaintext "key" records (which load first) next to
// encrypted ones. Loading used to fail with "LoadCryptedKey failed"; now the plaintext keys are recognised while
// locked and encrypted on unlock.
BOOST_AUTO_TEST_CASE(leftover_plaintext_keys_load_and_are_encrypted_on_unlock)
{
    TestCryptoWallet source("passphrase", WALLET_DERIVATION_BYTESTOKEY_SHA512);
    // the encrypted record of source's key, as it sits in wallet.dat
    bool fCompressed = false;
    CSecret secret = source.key.GetSecret(fCompressed);
    vector<unsigned char> vchCrypted;
    BOOST_REQUIRE(EncryptSecret(source.vMasterKeyPlain, secret, source.key.GetPubKey().GetHash(), vchCrypted));

    CKey stray;
    stray.MakeNewKey(true);
    const CKeyID strayID = stray.GetPubKey().GetID();

    CWallet wallet;
    BOOST_REQUIRE(wallet.LoadKey(stray));                                  // "key" sorts before "ckey"
    BOOST_REQUIRE(wallet.LoadCryptedKey(source.key.GetPubKey(), vchCrypted));   // used to fail here
    wallet.mapMasterKeys = source.mapMasterKeys;
    BOOST_CHECK(wallet.IsCrypted());
    BOOST_CHECK(wallet.IsLocked());

    // recognised while locked (so balances and IsMine are right), but not usable
    BOOST_CHECK(wallet.HaveKey(strayID));
    CPubKey pub;
    BOOST_CHECK(wallet.GetPubKey(strayID, pub) && pub == stray.GetPubKey());
    std::set<CKeyID> ids;
    wallet.GetKeys(ids);
    BOOST_CHECK(ids.count(strayID) && ids.count(source.key.GetPubKey().GetID()));
    CKey out;
    BOOST_CHECK(!wallet.GetKey(strayID, out));

    BOOST_REQUIRE(wallet.Unlock("passphrase"));
    BOOST_CHECK(wallet.mapUnencryptedKeys.empty());                        // now an ordinary encrypted key
    BOOST_CHECK(wallet.GetKey(strayID, out) && out.GetPubKey() == stray.GetPubKey() && out.IsCompressed());

    BOOST_REQUIRE(wallet.Lock());
    BOOST_CHECK(wallet.HaveKey(strayID));
    BOOST_CHECK(!wallet.GetKey(strayID, out));
}

BOOST_AUTO_TEST_CASE(passphrase_change_that_cannot_be_written_restores_the_old_key)
{
    // An in-memory wallet has no database file, so the new master key cannot be persisted (the database throws when
    // it tries to open it). The change must not leave the unwritten key in memory: before, the old passphrase stopped
    // working in this process while the file still held the old key.
    struct CloseDbEnv { ~CloseDbEnv() { bitdb.Close(); } } closeDbEnv;   // the attempt opens the shared environment

    TestCryptoWallet wallet("old passphrase", WALLET_DERIVATION_PBKDF2_SHA512_V4);
    const CMasterKey before = wallet.mapMasterKeys[1];

    bool fChanged = true;
    try { fChanged = wallet.ChangeWalletPassphrase("old passphrase", "new passphrase"); } catch (const std::exception&) { fChanged = false; }
    BOOST_CHECK(!fChanged);

    const CMasterKey& after = wallet.mapMasterKeys[1];
    BOOST_CHECK(after.vchCryptedKey == before.vchCryptedKey);
    BOOST_CHECK(after.vchSalt == before.vchSalt);
    BOOST_CHECK_EQUAL(after.nDeriveIterations, before.nDeriveIterations);
    BOOST_CHECK_EQUAL(after.nDerivationMethod, before.nDerivationMethod);

    BOOST_CHECK(wallet.IsLocked());
    BOOST_CHECK(!wallet.Unlock("new passphrase"));
    BOOST_CHECK(wallet.Unlock("old passphrase"));
    BOOST_CHECK(wallet.CanSign());
}

BOOST_AUTO_TEST_CASE(passphrase_change_with_the_wrong_old_passphrase_fails)
{
    TestCryptoWallet wallet("old passphrase", WALLET_DERIVATION_BYTESTOKEY_SHA512);
    BOOST_CHECK(!wallet.ChangeWalletPassphrase("not the passphrase", "new passphrase"));
    BOOST_CHECK(wallet.Unlock("old passphrase"));
}

BOOST_AUTO_TEST_CASE(unlock_tries_every_master_key)
{
    // A wallet can hold several master keys. A passphrase that does not open the first one must still be tried
    // against the rest (the loop used to give up at the first failure).
    TestCryptoWallet wallet("first passphrase", WALLET_DERIVATION_BYTESTOKEY_SHA512);
    CMasterKey other = wallet.mapMasterKeys[1];
    CCrypter crypter;
    BOOST_REQUIRE(crypter.SetKeyFromPassphrase("second passphrase", other.vchSalt, other.nDeriveIterations, WALLET_DERIVATION_PBKDF2_SHA512_V4));
    BOOST_REQUIRE(crypter.Encrypt(wallet.vMasterKeyPlain, other.vchCryptedKey));
    wallet.mapMasterKeys[2] = other;      // the same master key under a second passphrase, made the v4 way

    BOOST_CHECK(!wallet.Unlock("neither"));
    BOOST_CHECK(wallet.Unlock("second passphrase"));   // opens only the second entry
    BOOST_CHECK(wallet.CanSign());
    BOOST_CHECK(wallet.Lock());
    BOOST_CHECK(wallet.Unlock("first passphrase"));
}

BOOST_AUTO_TEST_SUITE_END()
