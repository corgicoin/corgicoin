// Copyright (c) 2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include "bip39.h"
#include "util.h"   // ParseHex, HexStr

#include <string>
#include <vector>

using namespace std;

// Official BIP39 (Trezor) English vectors — generated from the reference
// vectors.json to avoid transcription error. Passphrase is "TREZOR".
struct Bip39Vec { const char* entropy; const char* mnemonic; const char* seed; };

static const Bip39Vec VECTORS[] = {
    {"00000000000000000000000000000000",
     "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
     "c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04"},
    {"80808080808080808080808080808080",
     "letter advice cage absurd amount doctor acoustic avoid letter advice cage above",
     "d71de856f81a8acc65e6fc851a38d4d7ec216fd0796d0a6827a3ad6ed5511a30fa280f12eb2e47ed2ac03b5c462a0358d18d69fe4f985ec81778c1b370b652a8"},
    {"7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f",
     "legal winner thank year wave sausage worth useful legal winner thank year wave sausage worth useful legal will",
     "f2b94508732bcbacbcc020faefecfc89feafa6649a5491b8c952cede496c214a0c7b3c392d168748f2d4a612bada0753b52a1c7ac53c1e93abd5c6320b9e95dd"},
    {"7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f",
     "legal winner thank year wave sausage worth useful legal winner thank year wave sausage worth useful legal winner thank year wave sausage worth title",
     "bc09fca1804f7e69da93c2f2028eb238c227f2e9dda30cd63699232578480a4021b146ad717fbb7e451ce9eb835f43620bf5c514db0f8add49f5d121449d3e87"},
    {"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
     "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo vote",
     "dd48c104698c30cfe2b6142103248622fb7bb0ff692eebb00089b32d22484e1613912f0a5b694407be899ffd31ed3992c456cdf60f5d4564b8ba3f05a69890ad"},
};

BOOST_AUTO_TEST_SUITE(bip39_tests)

BOOST_AUTO_TEST_CASE(bip39_official_vectors)
{
    for (const Bip39Vec& v : VECTORS)
    {
        vector<unsigned char> entropy = ParseHex(v.entropy);

        // entropy -> mnemonic
        BOOST_CHECK_EQUAL(bip39::MnemonicFromEntropy(entropy), string(v.mnemonic));
        // the mnemonic validates
        BOOST_CHECK(bip39::CheckMnemonic(v.mnemonic));
        // mnemonic + "TREZOR" -> seed
        vector<unsigned char> seed = bip39::MnemonicToSeed(v.mnemonic, "TREZOR");
        BOOST_CHECK_EQUAL(HexStr(seed), string(v.seed));
    }
}

BOOST_AUTO_TEST_CASE(bip39_rejects_bad_mnemonic)
{
    // A valid 12-word mnemonic with its last word swapped breaks the checksum.
    BOOST_CHECK(bip39::CheckMnemonic(
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"));
    BOOST_CHECK(!bip39::CheckMnemonic(
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon"));
    // A word not in the list
    BOOST_CHECK(!bip39::CheckMnemonic(
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon notaword"));
    // Wrong word count
    BOOST_CHECK(!bip39::CheckMnemonic("abandon abandon abandon"));
}

BOOST_AUTO_TEST_CASE(bip39_generate_roundtrip)
{
    // Generated mnemonics validate, at both strengths.
    for (int bits : {128, 256})
    {
        string m = bip39::GenerateMnemonic(bits);
        BOOST_CHECK(!m.empty());
        BOOST_CHECK(bip39::CheckMnemonic(m));
        BOOST_CHECK_EQUAL(bip39::MnemonicToSeed(m).size(), 64u);
    }
    // Bad strengths rejected
    BOOST_CHECK(bip39::GenerateMnemonic(100).empty());
    BOOST_CHECK(bip39::MnemonicFromEntropy(vector<unsigned char>(15, 0)).empty());
}

BOOST_AUTO_TEST_SUITE_END()
