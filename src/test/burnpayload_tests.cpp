// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include <string>
#include <vector>

#include "burnpayload.h"
#include "script.h"

using namespace std;

BOOST_AUTO_TEST_SUITE(burnpayload_tests)

static vector<unsigned char> SampleSolDest()
{
    vector<unsigned char> v(burnpayload::SOL_DEST_LEN, 0);
    for (size_t i = 0; i < v.size(); ++i) v[i] = static_cast<unsigned char>(i + 1);
    return v;
}

BOOST_AUTO_TEST_CASE(encode_layout_is_magic_partner_soldest)
{
    auto solDest = SampleSolDest();
    auto payload = burnpayload::Encode("CORG", solDest);

    BOOST_CHECK_EQUAL(payload.size(), burnpayload::PAYLOAD_LEN);
    BOOST_CHECK_EQUAL(payload[0], 'S');
    BOOST_CHECK_EQUAL(payload[1], 'O');
    BOOST_CHECK_EQUAL(payload[2], 'L');
    BOOST_CHECK_EQUAL(payload[3], 'C');
    BOOST_CHECK_EQUAL(payload[4], 'O');
    BOOST_CHECK_EQUAL(payload[5], 'R');
    BOOST_CHECK_EQUAL(payload[6], 'G');
    BOOST_CHECK(equal(solDest.begin(), solDest.end(),
                      payload.begin() + burnpayload::MAGIC_LEN + burnpayload::PARTNER_LEN));
}

BOOST_AUTO_TEST_CASE(payload_round_trips_through_decode)
{
    auto solDest = SampleSolDest();
    auto payload = burnpayload::Encode("CORG", solDest);

    string partnerOut;
    vector<unsigned char> solOut;
    BOOST_CHECK(burnpayload::DecodePayload(payload, partnerOut, solOut));
    BOOST_CHECK_EQUAL(partnerOut, "CORG");
    BOOST_CHECK(solOut == solDest);
}

BOOST_AUTO_TEST_CASE(script_round_trips_through_decode)
{
    auto solDest = SampleSolDest();
    auto payload = burnpayload::Encode("SHIB", solDest);

    CScript script;
    script << OP_RETURN << payload;

    string partnerOut;
    vector<unsigned char> solOut;
    BOOST_CHECK(burnpayload::DecodeScript(script, partnerOut, solOut));
    BOOST_CHECK_EQUAL(partnerOut, "SHIB");
    BOOST_CHECK(solOut == solDest);
}

BOOST_AUTO_TEST_CASE(encode_rejects_bad_partner_tag)
{
    auto solDest = SampleSolDest();
    BOOST_CHECK_THROW(burnpayload::Encode("",     solDest), std::invalid_argument);
    BOOST_CHECK_THROW(burnpayload::Encode("CORGI", solDest), std::invalid_argument);
    BOOST_CHECK_THROW(burnpayload::Encode("C G",  solDest), std::invalid_argument); // space
    vector<unsigned char> shortDest(31, 0);
    BOOST_CHECK_THROW(burnpayload::Encode("CORG", shortDest), std::invalid_argument);
}

BOOST_AUTO_TEST_CASE(decode_rejects_wrong_magic)
{
    auto payload = burnpayload::Encode("CORG", SampleSolDest());
    payload[0] = 'X'; // corrupt magic

    string partnerOut;
    vector<unsigned char> solOut;
    BOOST_CHECK(!burnpayload::DecodePayload(payload, partnerOut, solOut));
}

BOOST_AUTO_TEST_CASE(decode_rejects_wrong_length)
{
    vector<unsigned char> shortPayload(burnpayload::PAYLOAD_LEN - 1, 0);
    string partnerOut;
    vector<unsigned char> solOut;
    BOOST_CHECK(!burnpayload::DecodePayload(shortPayload, partnerOut, solOut));
}

BOOST_AUTO_TEST_CASE(decode_script_rejects_non_op_return)
{
    // P2PKH-shaped script: OP_DUP OP_HASH160 <20 bytes> OP_EQUALVERIFY OP_CHECKSIG
    CScript script;
    vector<unsigned char> hash160(20, 0xab);
    script << OP_DUP << OP_HASH160 << hash160 << OP_EQUALVERIFY << OP_CHECKSIG;

    string partnerOut;
    vector<unsigned char> solOut;
    BOOST_CHECK(!burnpayload::DecodeScript(script, partnerOut, solOut));
}

BOOST_AUTO_TEST_CASE(decode_script_rejects_op_return_with_garbage)
{
    CScript script;
    vector<unsigned char> garbage(39, 0xff); // right length, wrong magic
    script << OP_RETURN << garbage;

    string partnerOut;
    vector<unsigned char> solOut;
    BOOST_CHECK(!burnpayload::DecodeScript(script, partnerOut, solOut));
}

BOOST_AUTO_TEST_SUITE_END()
