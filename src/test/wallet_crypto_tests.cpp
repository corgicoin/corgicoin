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

BOOST_AUTO_TEST_SUITE_END()
