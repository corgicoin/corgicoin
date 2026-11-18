#include <boost/test/unit_test.hpp>

#include <string>

#include "json/json_compat.h"

using namespace std;
using namespace json_spirit;

BOOST_AUTO_TEST_SUITE(json_compat_tests)

static Value Parse(const string& s)
{
    Value v;
    BOOST_REQUIRE_MESSAGE(read_string(s, v), "does not parse: " + s);
    return v;
}

BOOST_AUTO_TEST_CASE(integers_are_integers)
{
    BOOST_CHECK_EQUAL(Parse("5").get_int(), 5);
    BOOST_CHECK_EQUAL(Parse("-5").get_int(), -5);
    BOOST_CHECK_EQUAL(Parse("2147483647").get_int(), 2147483647);
    BOOST_CHECK_EQUAL(Parse("-2147483648").get_int(), -2147483647 - 1);
    BOOST_CHECK_EQUAL(Parse("9223372036854775807").get_int64(), 9223372036854775807LL);
    BOOST_CHECK_EQUAL(Parse("18446744073709551615").get_uint64(), 18446744073709551615ULL);

    // not integers
    BOOST_CHECK_THROW(Parse("true").get_int(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("false").get_int64(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("1.9").get_int(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("1.0").get_int64(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("1e300").get_int(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("1e300").get_int64(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("1e300").get_uint64(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("\"5\"").get_int(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("null").get_int(), std::runtime_error);

    // integers outside the type
    BOOST_CHECK_THROW(Parse("2147483648").get_int(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("-2147483649").get_int(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("9223372036854775808").get_int64(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("-1").get_uint64(), std::runtime_error);
}

BOOST_AUTO_TEST_CASE(bools_and_reals)
{
    BOOST_CHECK_EQUAL(Parse("true").get_bool(), true);
    BOOST_CHECK_THROW(Parse("1").get_bool(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("\"true\"").get_bool(), std::runtime_error);
    BOOST_CHECK_EQUAL(Parse("1.5").get_real(), 1.5);
    BOOST_CHECK_EQUAL(Parse("3").get_real(), 3.0);
    BOOST_CHECK_THROW(Parse("true").get_real(), std::runtime_error);
    BOOST_CHECK_THROW(Parse("\"1\"").get_real(), std::runtime_error);
}

BOOST_AUTO_TEST_CASE(duplicate_keys_are_refused)
{
    Value v;
    BOOST_CHECK(!read_string("{\"a\":1,\"a\":100}", v));
    BOOST_CHECK(!read_string("{\"x\":{\"a\":1,\"b\":2,\"a\":3}}", v));
    BOOST_CHECK(!read_string("[{\"a\":1},{\"b\":1,\"b\":2}]", v));
    // the same key in different objects is fine
    BOOST_CHECK(read_string("{\"a\":{\"a\":1},\"b\":{\"a\":2},\"c\":[{\"a\":3},{\"a\":4}]}", v));
}

BOOST_AUTO_TEST_CASE(nesting_is_limited)
{
    Value v;
    BOOST_CHECK(read_string(string(50, '[') + string(50, ']'), v));
    BOOST_CHECK(!read_string(string(200, '[') + string(200, ']'), v));
    // far deeper than the stack would take if anything recursed over it: refused, without touching the stack
    BOOST_CHECK(!read_string(string(2000000, '[') + string(2000000, ']'), v));
    string deepObjects;
    for (int i = 0; i < 200; i++)
        deepObjects += "{\"a\":";
    deepObjects += "1" + string(200, '}');
    BOOST_CHECK(!read_string(deepObjects, v));
}

BOOST_AUTO_TEST_CASE(object_order_is_kept)
{
    Value v = Parse("{\"b\":1,\"a\":2,\"c\":3}");
    BOOST_CHECK_EQUAL(write_string(v, false), "{\"b\":1,\"a\":2,\"c\":3}");
    Object o = v.get_obj();
    BOOST_REQUIRE_EQUAL(o.size(), 3u);
    BOOST_CHECK_EQUAL(o[0].name_, "b");
    BOOST_CHECK_EQUAL(o[1].name_, "a");
    BOOST_CHECK_EQUAL(o[2].name_, "c");

    Object built;
    built.emplace_back("z", 1);
    built.emplace_back("a", 2);
    BOOST_CHECK_EQUAL(write_string(Value(built), false), "{\"z\":1,\"a\":2}");
}

BOOST_AUTO_TEST_SUITE_END()
