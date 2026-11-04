#include <boost/test/unit_test.hpp>

#include <string>
#include <vector>

#include "compat_openssl.h"
#include "crypter.h"
#include "util.h"

using namespace std;

BOOST_AUTO_TEST_SUITE(crypter_tests)

namespace {

const unsigned int ROUNDS = 25000;

vector<unsigned char> Salt() { return ParseHex("a1b2c3d4e5f60718"); }

CKeyingMaterial Plaintext()
{
    CKeyingMaterial p(32);
    for (size_t i = 0; i < p.size(); i++)
        p[i] = (unsigned char)i;
    return p;
}

// AES-256-CBC of Plaintext() under the key and IV derived from "correct horse battery staple",
// Salt() and ROUNDS. Both values were computed independently of this code (Python hashlib + the openssl CLI).
//
// The wallet stores only "derivation method 0" for BOTH of these, so a wallet encrypted by a build
// using one cannot be unlocked by a build using the other. See feature_cross_binary.py.
const char* const PBKDF2_HMAC_SHA512_CIPHERTEXT =
    "a14a548b0dfe0b183b7cef56c0f931048d4f7986979785548e850ca97567a46c3b02eef2ca950ef035844676a85d5138";
const char* const EVP_BYTESTOKEY_CIPHERTEXT =
    "17cad2e3728b490016599a0ddac1ba44efe80fb5703ce840d8d7c04a441ea6a14704427ef7c554c886b746288dd34e3f";

} // namespace

BOOST_AUTO_TEST_CASE(passphrase_derivation_is_pinned)
{
    CCrypter crypter;
    SecureString passphrase("correct horse battery staple");
    BOOST_REQUIRE(crypter.SetKeyFromPassphrase(passphrase, Salt(), ROUNDS, 0));

    vector<unsigned char> ciphertext;
    BOOST_REQUIRE(crypter.Encrypt(Plaintext(), ciphertext));

#ifdef OPENSSL_3_0_OR_LATER
    // OpenSSL 3.x builds derive the key with PBKDF2-HMAC-SHA512
    BOOST_CHECK_EQUAL(HexStr(ciphertext.begin(), ciphertext.end()), PBKDF2_HMAC_SHA512_CIPHERTEXT);
#else
    // older builds use EVP_BytesToKey: a different key for the same passphrase
    BOOST_CHECK_EQUAL(HexStr(ciphertext.begin(), ciphertext.end()), EVP_BYTESTOKEY_CIPHERTEXT);
#endif
}

BOOST_AUTO_TEST_CASE(encrypt_decrypt_roundtrip)
{
    CCrypter crypter;
    SecureString passphrase("correct horse battery staple");
    BOOST_REQUIRE(crypter.SetKeyFromPassphrase(passphrase, Salt(), ROUNDS, 0));

    vector<unsigned char> ciphertext;
    BOOST_REQUIRE(crypter.Encrypt(Plaintext(), ciphertext));
    BOOST_CHECK_EQUAL(ciphertext.size(), 48u); // 32 bytes + one block of padding

    CKeyingMaterial decrypted;
    BOOST_REQUIRE(crypter.Decrypt(ciphertext, decrypted));
    BOOST_CHECK(decrypted == Plaintext());
}

BOOST_AUTO_TEST_CASE(different_passphrases_give_different_keys)
{
    vector<unsigned char> c1, c2;
    CCrypter a, b;
    BOOST_REQUIRE(a.SetKeyFromPassphrase(SecureString("passphrase one"), Salt(), 1000, 0));
    BOOST_REQUIRE(b.SetKeyFromPassphrase(SecureString("passphrase two"), Salt(), 1000, 0));
    BOOST_REQUIRE(a.Encrypt(Plaintext(), c1));
    BOOST_REQUIRE(b.Encrypt(Plaintext(), c2));
    BOOST_CHECK(c1 != c2);
}

BOOST_AUTO_TEST_CASE(derivation_rejects_bad_parameters)
{
    CCrypter crypter;
    SecureString passphrase("x");
    BOOST_CHECK(!crypter.SetKeyFromPassphrase(passphrase, Salt(), 0, 0));                           // no rounds
    BOOST_CHECK(!crypter.SetKeyFromPassphrase(passphrase, vector<unsigned char>(7, 1), 100, 0));    // wrong salt size
    BOOST_CHECK(!crypter.SetKeyFromPassphrase(passphrase, Salt(), 100, 1));                         // unknown method
    vector<unsigned char> out;
    BOOST_CHECK(!crypter.Encrypt(Plaintext(), out));                                                // no key set
}


BOOST_AUTO_TEST_CASE(empty_plaintext_and_empty_ciphertext)
{
    CCrypter crypter;
    SecureString passphrase("correct horse battery staple");
    BOOST_REQUIRE(crypter.SetKeyFromPassphrase(passphrase, Salt(), 1000, 0));

    // Encrypting nothing gives one padding block, which decrypts back to nothing
    vector<unsigned char> ciphertext;
    BOOST_REQUIRE(crypter.Encrypt(CKeyingMaterial(), ciphertext));
    BOOST_CHECK_EQUAL(ciphertext.size(), 16u);
    CKeyingMaterial decrypted(5, 1);
    BOOST_REQUIRE(crypter.Decrypt(ciphertext, decrypted));
    BOOST_CHECK(decrypted.empty());

    // Decrypting nothing is an error, not a crash: a corrupt wallet can hold an empty encrypted key
    CKeyingMaterial out;
    BOOST_CHECK(!crypter.Decrypt(vector<unsigned char>(), out));
}

BOOST_AUTO_TEST_SUITE_END()
