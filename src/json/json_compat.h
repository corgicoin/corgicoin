// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
//
// Compatibility layer: maps the old json_spirit API to nlohmann/json.

#ifndef JSON_COMPAT_H
#define JSON_COMPAT_H

#include "nlohmann_json.hpp"
#include <climits>
#include <cstdint>
#include <limits>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <iostream>

namespace json_spirit
{

// An ordered JSON object keeps keys in the order they were written or received (request order matters to callers
// such as sendmany and createrawtransaction), where a plain nlohmann::json sorts them.
using Json = nlohmann::ordered_json;

// Deepest nesting a request may have. The parser is iterative, but copying, printing and destroying a value are
// not guaranteed to be, and no RPC takes more than a few levels.
static constexpr int MAX_JSON_DEPTH = 64;

enum Value_type {
    obj_type, array_type, str_type, bool_type, int_type, real_type, null_type
};

[[maybe_unused]] static const char* Value_type_name[] = {
    "object", "array", "string", "boolean", "integer", "real", "null"
};

struct Pair;
using Object = std::vector<Pair>;

class Value {
public:
    Json data;
    static const Value null;

    Value() : data(nullptr) {}
    Value(std::nullptr_t) : data(nullptr) {}
    Value(const char* s) : data(std::string(s)) {}
    Value(const std::string& s) : data(s) {}
    Value(int i) : data(i) {}
    Value(unsigned int i) : data(i) {}
    Value(int64_t i) : data(i) {}
    Value(uint64_t i) : data(i) {}
    Value(double d) : data(d) {}
    Value(bool b) : data(b) {}
    Value(const Json& j) : data(j) {}
    // Object/Array constructors - defined after Pair
    inline Value(const Object& obj);
    inline Value(const std::vector<Value>& arr);

    Value_type type() const {
        if (data.is_object()) return obj_type;
        if (data.is_array()) return array_type;
        if (data.is_string()) return str_type;
        if (data.is_boolean()) return bool_type;
        if (data.is_number_integer()) return int_type;
        if (data.is_number_float()) return real_type;
        return null_type;
    }

    std::string get_str() const { return data.get<std::string>(); }
    // Overwrites, in place, every string this value holds (for a tree that held private keys, before it is freed). get_str, get_obj
    // and get_array return copies, which this does not reach: wipe those copies themselves.
    void wipe_strings() const { WipeStrings(const_cast<Json&>(data)); }
    static void WipeStrings(Json& j)
    {
        if (j.is_string()) {
            std::string& s = j.get_ref<std::string&>();
            volatile char* p = s.empty() ? nullptr : &s[0];
            for (size_t i = 0; i < s.size(); i++)
                p[i] = 0;
        } else if (j.is_array() || j.is_object()) {
            for (auto& e : j)
                WipeStrings(e);
        }
    }
    // The integer getters take JSON integers only, as json_spirit did: not true/false, not 1.9, and nothing outside
    // the range of the C++ type (a bare static_cast wraps, and from a float outside the range it is undefined)
    int get_int() const
    {
        const int64_t n = get_int64();
        if (n < std::numeric_limits<int>::min() || n > std::numeric_limits<int>::max())
            throw std::runtime_error("JSON integer out of range");
        return static_cast<int>(n);
    }
    int64_t get_int64() const
    {
        if (!data.is_number_integer())
            throw std::runtime_error("JSON value is not an integer as expected");
        if (data.is_number_unsigned() && data.get<uint64_t>() > static_cast<uint64_t>(std::numeric_limits<int64_t>::max()))
            throw std::runtime_error("JSON integer out of range");
        return data.get<int64_t>();
    }
    uint64_t get_uint64() const
    {
        if (!data.is_number_integer())
            throw std::runtime_error("JSON value is not an integer as expected");
        if (!data.is_number_unsigned() && data.get<int64_t>() < 0)
            throw std::runtime_error("JSON integer out of range");
        return data.get<uint64_t>();
    }
    double get_real() const
    {
        if (!data.is_number())
            throw std::runtime_error("JSON value is not a number as expected");
        return data.get<double>();
    }
    bool get_bool() const
    {
        if (!data.is_boolean())
            throw std::runtime_error("JSON value is not a boolean as expected");
        return data.get<bool>();
    }
    inline Object get_obj() const;
    inline std::vector<Value> get_array() const;

    template<typename T> T get_value() const { return data.get<T>(); }

    bool operator==(const Value& other) const { return data == other.data; }
    bool operator!=(const Value& other) const { return data != other.data; }
};

using Array = std::vector<Value>;

struct Pair {
    std::string name_;
    Value value_;
    Pair() = default;
    Pair(const std::string& name, const Value& val) : name_(name), value_(val) {}
    template<typename T>
    Pair(const std::string& name, const T& val) : name_(name), value_(Value(val)) {}
};

// --- Deferred inline implementations ---

inline Value::Value(const Object& obj) {
    data = Json::object();
    for (const auto& p : obj)
        data[p.name_] = p.value_.data;
}

inline Value::Value(const std::vector<Value>& arr) {
    data = Json::array();
    for (const auto& v : arr)
        data.push_back(v.data);
}

inline Object Value::get_obj() const {
    Object obj;
    for (auto it = data.begin(); it != data.end(); ++it)
        obj.emplace_back(it.key(), Value(it.value()));
    return obj;
}

inline Array Value::get_array() const {
    Array arr;
    for (const auto& elem : data)
        arr.emplace_back(Value(elem));
    return arr;
}

// Template specializations for get_value
template<> inline Value Value::get_value<Value>() const { return *this; }
template<> inline Array Value::get_value<Array>() const { return get_array(); }
template<> inline Object Value::get_value<Object>() const { return get_obj(); }
template<> inline bool Value::get_value<bool>() const { return get_bool(); }
template<> inline int Value::get_value<int>() const { return get_int(); }
template<> inline int64_t Value::get_value<int64_t>() const { return get_int64(); }
template<> inline uint64_t Value::get_value<uint64_t>() const { return get_uint64(); }
template<> inline double Value::get_value<double>() const { return get_real(); }
template<> inline std::string Value::get_value<std::string>() const { return get_str(); }

// --- Free functions ---

inline const Value& find_value(const Object& obj, const std::string& name) {
    for (const auto& p : obj) {
        if (p.name_ == name)
            return p.value_;
    }
    return Value::null;
}

// Parse with the limits above, and refuse an object that names the same key twice: which of the two values wins is
// not defined by JSON, and "pay A 1 and pay A 100" must not quietly turn into one payment.
template <typename Input>
inline bool parse_limited(Input&& in, Value& value) {
    try {
        std::vector<std::set<std::string> > keys;
        auto cb = [&keys](int depth, Json::parse_event_t event, Json& parsed) {
            if (depth > MAX_JSON_DEPTH)
                throw std::runtime_error("JSON nested too deeply");
            if (event == Json::parse_event_t::object_start)
                keys.emplace_back();
            else if (event == Json::parse_event_t::object_end)
                keys.pop_back();
            else if (event == Json::parse_event_t::key && !keys.back().insert(parsed.template get<std::string>()).second)
                throw std::runtime_error("duplicate key in JSON object");
            return true;
        };
        value.data = Json::parse(in, cb);
        return true;
    } catch (...) {
        return false;
    }
}

inline bool read_string(const std::string& s, Value& value) {
    return parse_limited(s, value);
}

inline std::string write_string(const Value& value, bool pretty) {
    // Invalid UTF-8 in a string (anything that reached a reply from outside) is replaced, not thrown on: one bad
    // byte must not turn a whole RPC reply into an error
    if (pretty) return value.data.dump(4, ' ', false, nlohmann::json::error_handler_t::replace);
    return value.data.dump(-1, ' ', false, nlohmann::json::error_handler_t::replace);
}

inline bool read_stream(std::istream& is, Value& value) {
    return parse_limited(is, value);
}

} // namespace json_spirit

#endif // JSON_COMPAT_H
