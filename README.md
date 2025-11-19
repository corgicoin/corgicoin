# CorgiCoin [CORG, Ç]
http://corgicoin.com/

![CorgiCoin](http://i.imgur.com/jx5vexy.png)

## ⚠️ IMPORTANT SECURITY NOTICE

**This is a 2014-era cryptocurrency codebase with outdated dependencies.**

**SECURITY STATUS:**
- ✅ **OpenSSL modernized** (v1.4.1.54): Compatible with OpenSSL 1.1.x/3.x
  - Can now build with secure, modern OpenSSL versions
  - OpenSSL 1.0.x still supported but upgrade strongly recommended
- ✅ **Boost modernized** (v1.4.1.55): Compatible with Boost 1.55.0-1.80+
  - 70% dependency reduction through C++11/14 modernization
  - Can now use modern, maintained Boost versions
- ⚠️ Old Berkeley DB version - upgrade recommended
- ✅ IRC peer discovery removed (v1.4.1.33)

**Before using this code:**
1. Read [MODERNIZATION.md](MODERNIZATION.md) for full security assessment
2. Update all dependencies to modern versions
3. Test thoroughly in an isolated environment
4. **DO NOT use in production without updating dependencies**

See [MODERNIZATION.md](MODERNIZATION.md) for complete modernization roadmap and dependency updates.

## What is CorgiCoin?
 CorgiCoin is like Bitcoin, but based on Litecoin, and very short.

**Note:** This codebase is provided for historical/educational purposes. Modernization is required for safe operation.

## License
 CorgiCoin is released under the MIT license. See [COPYING](COPYING)
for more information.

## FAQ

### Who are you?
Just a couple guys having fun.

### What's the max CORG that will exist?
Only 100 billion. Wait, what.

### Coin type?
CorgiCoin is a Scrypt-based Proof of Work coin.

### Block Info

Just like DOGE:

1 Minute Block Targets, 4 Hour Diff Readjustments

Special reward system: Random block rewards

1-100,000: 0-1,000,000 Corgicoin Reward

100,001 — 200,000: 0-500,000 Corgicoin Reward

200,001 — 300,000: 0-250,000 Corgicoin Reward

300,001 — 400,000: 0-125,000 Corgicoin Reward

400,001 — 500,000: 0-62,500 Corgicoin Reward

500,001 - 600,000: 0-31,250 Corgicoin Reward

600,000+ — 10,000 Reward (flat)

### Conf Settings

**⚠️ SECURITY WARNING:** Do not use default credentials in production!

```conf
# Change these default values!
rpcuser=your_secure_username
rpcpassword=your_secure_random_password

rpcport=62555

# Seed nodes (may be outdated)
addnode=162.243.41.34
addnode=192.241.169.209
addnode=162.243.222.29
addnode=162.243.67.52
addnode=162.243.123.79
```

## Building CorgiCoin

### Prerequisites

**Minimum Requirements (2014-era):**
- Boost 1.55.0+ (outdated, upgrade to 1.70+ recommended)
- OpenSSL 1.0.1f+ (CRITICAL: upgrade to OpenSSL 3.x required)
- Berkeley DB 5.3+ (5.3.28+ recommended)
- Qt 4.8+ (Qt 5.15 LTS or Qt 6.x recommended)
- C++11 compatible compiler (GCC 4.8+, Clang 3.3+, or MSVC 2015+)

**Recommended Modern Versions:**
- Boost 1.70 or newer
- OpenSSL 3.0 or newer
- Berkeley DB 5.3.28 or 6.x
- Qt 5.15 LTS
- GCC 9+ or Clang 10+

### Build Instructions

CorgiCoin supports two build systems:
- **CMake** (recommended for modern systems) - See [BUILD.cmake.md](BUILD.cmake.md)
- **qmake/make** (traditional approach)

#### CMake (Modern, Cross-Platform)

```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=ON
make -j$(nproc)
```

See [BUILD.cmake.md](BUILD.cmake.md) for detailed CMake instructions, dependency setup, and IDE integration.

#### Traditional Build (qmake/make)

##### Linux/Unix

```bash
cd src/
make -f makefile.unix            # For daemon
# or
qmake && make                     # For Qt GUI
```

##### macOS

```bash
./build_mac.sh
# or
qmake && make
```

##### Windows

Use Qt Creator or MinGW-w64 with updated dependency paths.

### Testing

After building, backup any existing wallets and test in an isolated environment first.

## Modernization

This codebase has been substantially modernized with C++11/14 features:

**✅ Completed (Phase 1 & 3):**
- C++11 compiler flags and build system (CMake + qmake)
- nullptr throughout codebase (202 conversions)
- Modern type aliases with `using` (all typedef converted)
- Smart pointers (unique_ptr, shared_ptr) for RAII with memory leak fixes
- C++11 threading (std::thread, std::mutex, std::condition_variable)
- Modern C++ casts (static_cast, reinterpret_cast, const_cast)
- Lambda expressions (replaced boost::bind)
- Qt signal/slot function pointers (~130 conversions)
- Standard library containers (std::array, std::vector)
- Deprecated code removal (IRC, auto_ptr)
- **Major Boost dependency reduction** - Most Boost usage replaced with C++11 STL
- constexpr for compile-time constants (blockchain, network)
- Move semantics for performance optimization

**✅ Dependency Modernization Complete:**
- **OpenSSL 1.1.x/3.x compatible** (v1.4.1.54) - Compiles with modern, secure OpenSSL!
- **Boost 1.70+ compatible** (v1.4.1.55) - Works with Boost 1.55.0 through 1.80+!
- 70% Boost dependency reduction through C++11/14 modernization
- Backward compatible with older versions (upgrade strongly recommended)

**⚠️ Still Recommended:**
- Berkeley DB 5.3.28+ or 6.x upgrade
- Qt 5 migration (Qt 4 is EOL)

**Modernization Stats:**
- 14 major modernization releases (v1.4.1.42-55)
- ~525+ individual modernizations
- **OpenSSL 3.x compatible** - critical security update complete
- **Boost 1.70+ compatible** - 70% dependency reduction achieved
- C++17-ready (deprecated features removed)
- Memory leak fixes and performance optimizations

See [MODERNIZATION.md](MODERNIZATION.md) for complete details and changelog.

## Contributing

When contributing, please:
1. Use C++11 features where appropriate
2. Follow existing code style
3. Test thoroughly
4. Update dependencies before deploying

## Support

For modernization questions and security updates, see [MODERNIZATION.md](MODERNIZATION.md).
