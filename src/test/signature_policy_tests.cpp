#include <boost/test/unit_test.hpp>

#include "bignum.h"
#include "key.h"
#include "keystore.h"
#include "main.h"
#include "script.h"
#include "util.h"

using namespace std;

extern uint256 SignatureHash(CScript scriptCode, const CTransaction& txTo, unsigned int nIn, int nHashType);

BOOST_AUTO_TEST_SUITE(signature_policy_tests)

namespace {

typedef vector<unsigned char> valtype;

valtype Hex(const char* psz) { return ParseHex(psz); }

// A strict DER signature with a hash type byte: R = 1, S = the given big-endian bytes
valtype SigWithS(const valtype& s, unsigned char nHashType = 1)
{
    valtype sig = {0x30, static_cast<unsigned char>(5 + s.size()), 0x02, 0x01, 0x01, 0x02, static_cast<unsigned char>(s.size())};
    sig.insert(sig.end(), s.begin(), s.end());
    sig.push_back(nHashType);
    return sig;
}

// A one-input transaction spending output 0 of a one-output transaction that pays scriptPubKey
struct SpendFixture
{
    CTransaction txFrom, txTo;
    CKey key;

    SpendFixture()
    {
        key.MakeNewKey(true);
        txFrom.vout.resize(1);
        txFrom.vout[0].scriptPubKey << key.GetPubKey() << OP_CHECKSIG;
        txFrom.vout[0].nValue = 1000;
        txTo.vin.resize(1);
        txTo.vin[0].prevout.hash = txFrom.GetHash();
        txTo.vin[0].prevout.n = 0;
        txTo.vout.resize(1);
        txTo.vout[0].nValue = 900;
    }

    // scriptSig for a signature with the given (r, s) re-encoded: the S half-flip of a valid signature is also valid
    valtype Sign() const
    {
        valtype sig;
        BOOST_REQUIRE(const_cast<CKey&>(key).Sign(SignatureHash(txFrom.vout[0].scriptPubKey, txTo, 0, SIGHASH_ALL), sig));
        sig.push_back(static_cast<unsigned char>(SIGHASH_ALL));
        return sig;
    }

    bool Check(const valtype& sigWithType, unsigned int flags)
    {
        txTo.vin[0].scriptSig = CScript() << sigWithType;
        return VerifySignature(txFrom, txTo, 0, true, 0, flags);
    }
};

// The same signature with S replaced by n - S (still valid, but the other half of the range)
valtype FlipS(const valtype& sigWithType)
{
    BOOST_REQUIRE(IsValidSignatureEncoding(sigWithType));
    const unsigned int lenR = sigWithType[3];
    const unsigned int lenS = sigWithType[5 + lenR];
    valtype r(sigWithType.begin() + 4, sigWithType.begin() + 4 + lenR);
    valtype s(sigWithType.begin() + 6 + lenR, sigWithType.begin() + 6 + lenR + lenS);

    static const char* pszOrder = "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141";
    CBigNum bnOrder;
    bnOrder.SetHex(pszOrder);
    CBigNum bnS;
    bnS.SetHex(HexStr(s.begin(), s.end()));
    CBigNum bnNew = bnOrder - bnS;
    string strNew = bnNew.GetHex();
    while (strNew.size() < 64)
        strNew = "0" + strNew;
    valtype sNew = Hex(strNew.c_str());
    if (sNew[0] & 0x80)
        sNew.insert(sNew.begin(), 0x00);

    valtype out = {0x30, 0, 0x02, static_cast<unsigned char>(r.size())};
    out.insert(out.end(), r.begin(), r.end());
    out.push_back(0x02);
    out.push_back(static_cast<unsigned char>(sNew.size()));
    out.insert(out.end(), sNew.begin(), sNew.end());
    out[1] = static_cast<unsigned char>(out.size() - 2);
    out.push_back(sigWithType.back());
    return out;
}

}   // namespace

BOOST_AUTO_TEST_CASE(strict_der_accepts_well_formed_signatures)
{
    BOOST_CHECK(IsValidSignatureEncoding(SigWithS(Hex("01"))));
    BOOST_CHECK(IsValidSignatureEncoding(SigWithS(Hex("7f"))));
    BOOST_CHECK(IsValidSignatureEncoding(SigWithS(Hex("00ff"))));                  // zero pads a high first byte
    BOOST_CHECK(IsValidSignatureEncoding(Hex("3006020101020101" "01")));            // the smallest signature (9 bytes)
}

BOOST_AUTO_TEST_CASE(strict_der_rejects_malformed_signatures)
{
    BOOST_CHECK(!IsValidSignatureEncoding(valtype()));
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("30050201010201")));                 // too short
    BOOST_CHECK(!IsValidSignatureEncoding(valtype(74, 0x30)));                     // too long
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3106020101020101" "01")));          // wrong compound marker
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3007020101020101" "01")));          // length does not cover the body
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3005020101020101" "01")));
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3006030101020101" "01")));          // R is not an integer
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3006020101030101" "01")));          // S is not an integer
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3006020001020101" "01")));          // R has length zero
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3006020101020001")));               // S has length zero
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3006028001020101" "01")));          // R negative
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3006020101028001" "01")));          // S negative
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("300702020001020101" "01")));        // R padded with an unneeded zero
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3007020101020200" "0101")));        // S padded with an unneeded zero
    BOOST_CHECK(!IsValidSignatureEncoding(Hex("3006020101020201" "01")));          // R/S lengths run past the data
}

BOOST_AUTO_TEST_CASE(low_s_boundary)
{
    // half the order; one more is high
    BOOST_CHECK(IsLowDERSignature(SigWithS(Hex("7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0"))));
    BOOST_CHECK(!IsLowDERSignature(SigWithS(Hex("7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A1"))));
    BOOST_CHECK(IsLowDERSignature(SigWithS(Hex("01"))));
    BOOST_CHECK(!IsLowDERSignature(SigWithS(Hex("00FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"))));
    BOOST_CHECK(!IsLowDERSignature(Hex("3006020101020101")));                           // malformed is never "low"
}

BOOST_AUTO_TEST_CASE(low_s_is_numeric_not_lexical)
{
    // 255 and 256 are both far below half the order, whatever their first byte
    BOOST_CHECK(IsLowDERSignature(SigWithS(Hex("00FF"))));
    BOOST_CHECK(IsLowDERSignature(SigWithS(Hex("0100"))));
}

BOOST_AUTO_TEST_CASE(own_signatures_are_always_low_s)
{
    // OpenSSL picks S at random; CKey::Sign must always return the low one
    SpendFixture f;
    for (int i = 0; i < 64; i++)
    {
        f.txTo.nLockTime = i;   // different hash each round
        valtype sig = f.Sign();
        BOOST_CHECK(IsValidSignatureEncoding(sig));
        BOOST_CHECK(IsLowDERSignature(sig));
        BOOST_CHECK(f.Check(sig, SCRIPT_VERIFY_DERSIG | SCRIPT_VERIFY_LOW_S));
    }
}

BOOST_AUTO_TEST_CASE(high_s_twin_is_valid_by_consensus_but_not_by_policy)
{
    SpendFixture f;
    valtype low = f.Sign();
    valtype high = FlipS(low);
    BOOST_REQUIRE(IsValidSignatureEncoding(high));
    BOOST_CHECK(!IsLowDERSignature(high));

    BOOST_CHECK(f.Check(low, SCRIPT_VERIFY_NONE));
    BOOST_CHECK(f.Check(high, SCRIPT_VERIFY_NONE));                                  // consensus accepts both
    BOOST_CHECK(VerifyScript(CScript() << high, f.txFrom.vout[0].scriptPubKey, f.txTo, 0, true, 0));   // legacy entry point too

    BOOST_CHECK(f.Check(low, SCRIPT_VERIFY_LOW_S));
    BOOST_CHECK(!f.Check(high, SCRIPT_VERIFY_LOW_S));                                // policy refuses the twin
    BOOST_CHECK(f.Check(high, SCRIPT_VERIFY_DERSIG));                                // it is still valid DER
}

BOOST_AUTO_TEST_CASE(padded_der_is_refused_by_the_policy_flags)
{
    // Re-encode R with an unneeded leading zero: not strict DER
    SpendFixture f;
    valtype sig = f.Sign();
    const unsigned int lenR = sig[3];
    valtype padded(sig.begin(), sig.begin() + 4);
    padded.push_back(0x00);                                                           // the unneeded zero
    padded.insert(padded.end(), sig.begin() + 4, sig.end());
    padded[1] += 1;
    padded[3] = static_cast<unsigned char>(lenR + 1);
    BOOST_CHECK(!IsValidSignatureEncoding(padded));
    BOOST_CHECK(!f.Check(padded, SCRIPT_VERIFY_DERSIG));
    BOOST_CHECK(!f.Check(padded, SCRIPT_VERIFY_LOW_S));
}

BOOST_AUTO_TEST_CASE(an_empty_signature_is_not_a_policy_violation)
{
    // it just fails the check, so OP_CHECKSIG yields false instead of aborting the script
    SpendFixture f;
    f.txTo.vin[0].scriptSig = CScript() << valtype();
    BOOST_CHECK(!VerifySignature(f.txFrom, f.txTo, 0, true, 0, SCRIPT_VERIFY_NONE));
    BOOST_CHECK(!VerifySignature(f.txFrom, f.txTo, 0, true, 0, SCRIPT_VERIFY_DERSIG | SCRIPT_VERIFY_LOW_S));
}

BOOST_AUTO_TEST_CASE(multisig_signatures_are_checked_too)
{
    CKey k1, k2;
    k1.MakeNewKey(true);
    k2.MakeNewKey(true);
    CTransaction txFrom, txTo;
    txFrom.vout.resize(1);
    txFrom.vout[0].scriptPubKey << OP_1 << k1.GetPubKey() << k2.GetPubKey() << OP_2 << OP_CHECKMULTISIG;
    txFrom.vout[0].nValue = 1000;
    txTo.vin.resize(1);
    txTo.vin[0].prevout.hash = txFrom.GetHash();
    txTo.vin[0].prevout.n = 0;
    txTo.vout.resize(1);
    txTo.vout[0].nValue = 900;

    valtype sig;
    BOOST_REQUIRE(k1.Sign(SignatureHash(txFrom.vout[0].scriptPubKey, txTo, 0, SIGHASH_ALL), sig));
    sig.push_back(static_cast<unsigned char>(SIGHASH_ALL));
    const valtype high = FlipS(sig);

    txTo.vin[0].scriptSig = CScript() << OP_0 << sig;
    BOOST_CHECK(VerifySignature(txFrom, txTo, 0, true, 0, SCRIPT_VERIFY_DERSIG | SCRIPT_VERIFY_LOW_S));
    txTo.vin[0].scriptSig = CScript() << OP_0 << high;
    BOOST_CHECK(VerifySignature(txFrom, txTo, 0, true, 0, SCRIPT_VERIFY_NONE));
    BOOST_CHECK(!VerifySignature(txFrom, txTo, 0, true, 0, SCRIPT_VERIFY_LOW_S));
}

BOOST_AUTO_TEST_SUITE_END()
