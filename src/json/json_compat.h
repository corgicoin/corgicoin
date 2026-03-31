// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.
//
// Compatibility layer: maps the old json_spirit API to nlohmann/json.

#ifndef JSON_COMPAT_H
#define JSON_COMPAT_H

#include "nlohmann_json.hpp"
#include <string>
#include <vector>
#include <iostream>

namespace json_spirit
{

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
    nlohmann::json data;
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
    Value(const nlohmann::json& j) : data(j) {}
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
    int get_int() const { return data.get<int>(); }
    int64_t get_int64() const { return data.get<int64_t>(); }
    uint64_t get_uint64() const { return data.get<uint64_t>(); }
    double get_real() const { return data.get<double>(); }
    bool get_bool() const { return data.get<bool>(); }
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
    data = nlohmann::json::object();
    for (const auto& p : obj)
        data[p.name_] = p.value_.data;
}

inline Value::Value(const std::vector<Value>& arr) {
    data = nlohmann::json::array();
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

inline bool read_string(const std::string& s, Value& value) {
    try {
        value.data = nlohmann::json::parse(s);
        return true;
    } catch (...) {
        return false;
    }
}

inline std::string write_string(const Value& value, bool pretty) {
    if (pretty) return value.data.dump(4);
    return value.data.dump();
}

inline bool read_stream(std::istream& is, Value& value) {
    try {
        value.data = nlohmann::json::parse(is);
        return true;
    } catch (...) {
        return false;
    }
}

} // namespace json_spirit

#endif // JSON_COMPAT_H
