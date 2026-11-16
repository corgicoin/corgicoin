#include <boost/test/unit_test.hpp>
#include <climits>
#include <boost/foreach.hpp>

#include "base58.h"
#include "util.h"
#include "corgicoinrpc.h"

using namespace std;
using namespace json_spirit;

BOOST_AUTO_TEST_SUITE(rpc_tests)

static Array
createArgs(int nRequired, const char* address1=nullptr, const char* address2=nullptr)
{
    Array result;
    result.push_back(nRequired);
    Array addresses;
    if (address1) addresses.push_back(address1);
    if (address2) addresses.push_back(address1);
    result.push_back(addresses);
    return result;
}

// This can be removed this when addmultisigaddress is enabled on main net:
struct TestNetFixture
{
    TestNetFixture() { fTestNet = true; }
    ~TestNetFixture() { fTestNet = false; }
};

BOOST_FIXTURE_TEST_CASE(rpc_addmultisig, TestNetFixture)
{
    rpcfn_type addmultisig = tableRPC["addmultisigaddress"]->actor;

    // old, 65-byte-long:
    const char address1Hex[] = "0434e3e09f49ea168c5bbf53f877ff4206923858aab7c7e1df25bc263978107c95e35065a27ef6f1b27222db0ec97e0e895eaca603d3ee0d4c060ce3d8a00286c8";
    // new, compressed:
    const char address2Hex[] = "0388c2037017c62240b6b72ac1a2a5f94da790596ebd06177c8572752922165cb4";

    Value v;
    CBitcoinAddress address;
    BOOST_CHECK_NO_THROW(v = addmultisig(createArgs(1, address1Hex), false));
    address.SetString(v.get_str());
    BOOST_CHECK(address.IsValid() && address.IsScript());

    BOOST_CHECK_NO_THROW(v = addmultisig(createArgs(1, address1Hex, address2Hex), false));
    address.SetString(v.get_str());
    BOOST_CHECK(address.IsValid() && address.IsScript());

    BOOST_CHECK_NO_THROW(v = addmultisig(createArgs(2, address1Hex, address2Hex), false));
    address.SetString(v.get_str());
    BOOST_CHECK(address.IsValid() && address.IsScript());

    BOOST_CHECK_THROW(addmultisig(createArgs(0), false), runtime_error);
    BOOST_CHECK_THROW(addmultisig(createArgs(1), false), runtime_error);
    BOOST_CHECK_THROW(addmultisig(createArgs(2, address1Hex), false), runtime_error);

    BOOST_CHECK_THROW(addmultisig(createArgs(1, ""), false), runtime_error);
    BOOST_CHECK_THROW(addmultisig(createArgs(1, "NotAValidPubkey"), false), runtime_error);

    string short1(address1Hex, address1Hex+sizeof(address1Hex)-2); // last byte missing
    BOOST_CHECK_THROW(addmultisig(createArgs(2, short1.c_str()), false), runtime_error);

    string short2(address1Hex+1, address1Hex+sizeof(address1Hex)); // first byte missing
    BOOST_CHECK_THROW(addmultisig(createArgs(2, short2.c_str()), false), runtime_error);
}

// The JSON layer used to cast with nlohmann's get<int>(), so 2^32+1 read as 1 (a 1-of-N multisig when the caller
// sent nonsense) and a uint64 above INT64_MAX read as negative. Out-of-range values now throw.
BOOST_FIXTURE_TEST_CASE(rpc_json_int_range, TestNetFixture)
{
    BOOST_CHECK_EQUAL(Value(INT_MAX).get_int(), INT_MAX);
    BOOST_CHECK_EQUAL(Value(INT_MIN).get_int(), INT_MIN);
    BOOST_CHECK_EQUAL(Value((int64_t)-5).get_int(), -5);
    BOOST_CHECK_THROW(Value((int64_t)INT_MAX + 1).get_int(), runtime_error);
    BOOST_CHECK_THROW(Value((int64_t)INT_MIN - 1).get_int(), runtime_error);
    BOOST_CHECK_THROW(Value((int64_t)4294967297LL).get_int(), runtime_error);

    BOOST_CHECK_EQUAL(Value(INT64_MAX).get_int64(), INT64_MAX);
    BOOST_CHECK_EQUAL(Value(INT64_MIN).get_int64(), INT64_MIN);
    BOOST_CHECK_EQUAL(Value((uint64_t)INT64_MAX).get_int64(), INT64_MAX);
    BOOST_CHECK_THROW(Value((uint64_t)INT64_MAX + 1).get_int64(), runtime_error);
    BOOST_CHECK_THROW(Value(UINT64_MAX).get_int64(), runtime_error);
    BOOST_CHECK_THROW(Value(UINT64_MAX).get_int(), runtime_error);

    // and the same when parsed from JSON text, as the RPC server receives it
    Value v;
    BOOST_REQUIRE(read_string(std::string("18446744073709551615"), v));
    BOOST_CHECK_THROW(v.get_int64(), runtime_error);
    BOOST_REQUIRE(read_string(std::string("1099511627776"), v));
    BOOST_CHECK_THROW(v.get_int(), runtime_error);
    BOOST_CHECK_EQUAL(v.get_int64(), 1099511627776LL);

    // addmultisigaddress with nrequired = 2^32+1 must not become a 1-of-1
    rpcfn_type addmultisig = tableRPC["addmultisigaddress"]->actor;
    Array keys;
    keys.push_back("0388c2037017c62240b6b72ac1a2a5f94da790596ebd06177c8572752922165cb4");
    Array args;
    args.push_back(1);
    args.push_back(keys);
    BOOST_CHECK_NO_THROW(addmultisig(args, false));
    args[0] = (int64_t)4294967297LL;
    BOOST_CHECK_THROW(addmultisig(args, false), runtime_error);
}

BOOST_AUTO_TEST_SUITE_END()
