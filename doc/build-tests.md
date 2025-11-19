# Building and Running Tests

## Overview

CorgiCoin includes a comprehensive test suite using Boost.Test. The tests have been modernized to work with Boost 1.70+ and use C++11 features.

## Prerequisites

### Required Dependencies

To build and run the test suite, you need:

1. **Boost.Test library** (1.55.0+, 1.70+ recommended)
2. **All daemon build dependencies** (OpenSSL, Berkeley DB, etc.)

### Installing Dependencies

#### Ubuntu/Debian

```bash
# Install Boost.Test library
sudo apt-get install libboost-test-dev

# Install other required Boost components
sudo apt-get install libboost-system-dev libboost-filesystem-dev \
                     libboost-program-options-dev libboost-thread-dev

# Install other dependencies (if not already installed)
sudo apt-get install build-essential libssl-dev libdb++-dev
```

#### macOS (Homebrew)

```bash
# Install Boost (includes all components including test)
brew install boost

# Install other dependencies
brew install openssl@3 berkeley-db
```

#### Windows

Use vcpkg or build Boost from source with the test component enabled.

## Building Tests

### Using Make (Traditional)

```bash
cd src/
make -f makefile.unix test_corgicoin
```

This will:
1. Compile all source files
2. Compile all test files
3. Link with Boost.Test library
4. Create `test_corgicoin` executable

### Using CMake (Modern)

CMake support for tests coming soon. Currently use the makefile.unix approach.

## Running Tests

After building:

```bash
# Run all tests
./test_corgicoin

# Run with verbose output
./test_corgicoin --log_level=all

# Run specific test suite
./test_corgicoin --run_test=Checkpoints_tests

# List all available tests
./test_corgicoin --list_content
```

## Test Suites

The following test suites are available:

- **Checkpoints_tests** - Blockchain checkpoint validation
- **DoS_tests** - Denial of service prevention
- **base32_tests** - Base32 encoding/decoding
- **base58_tests** - Base58 encoding/decoding
- **base64_tests** - Base64 encoding/decoding
- **bignum_tests** - Big number arithmetic
- **getarg_tests** - Command line argument parsing
- **key_tests** - Cryptographic key operations
- **miner_tests** - Mining difficulty tests
- **mruset_tests** - Limited size set tests
- **multisig_tests** - Multi-signature transactions
- **netbase_tests** - Network address handling
- **rpc_tests** - RPC command tests
- **script_P2SH_tests** - Pay-to-script-hash tests
- **script_tests** - Script validation tests
- **sigopcount_tests** - Signature operation counting
- **transaction_tests** - Transaction validation
- **uint160_tests** - 160-bit integer tests
- **uint256_tests** - 256-bit integer tests
- **util_tests** - Utility function tests
- **wallet_tests** - Wallet operations

## Modernization Status

✅ **Completed (v1.4.1.35)**:
- Removed deprecated `boost/assign/list_of.hpp` usage
- Replaced `map_list_of()` with C++11 initializer lists
- Removed deprecated `boost/foreach.hpp` (using C++11 range-for)
- Compatible with Boost 1.70+ and modern compilers

## Troubleshooting

### "boost/test/unit_test.hpp: No such file or directory"

**Solution**: Install libboost-test-dev package (see dependencies above)

### Link errors with boost_unit_test_framework

**Solution**: Make sure you have the full Boost development package installed, not just headers.

On Ubuntu/Debian:
```bash
sudo apt-get install libboost-test-dev
```

### Tests fail with "undefined reference to boost::unit_test"

**Solution**: You may need to install the dynamic library version:
```bash
sudo apt-get install libboost-test1.XX  # Replace XX with your version
```

### Makefile can't find boost libraries

**Solution**: Set BOOST_LIB_PATH and BOOST_INCLUDE_PATH:
```bash
export BOOST_INCLUDE_PATH=/usr/include
export BOOST_LIB_PATH=/usr/lib/x86_64-linux-gnu
make -f makefile.unix test_corgicoin
```

## Continuous Integration

For CI/CD pipelines, install dependencies in your build script:

```yaml
# Example GitHub Actions
- name: Install dependencies
  run: |
    sudo apt-get update
    sudo apt-get install -y libboost-test-dev libboost-all-dev \
                           libssl-dev libdb++-dev

- name: Build and run tests
  run: |
    cd src
    make -f makefile.unix test_corgicoin
    ./test_corgicoin
```

## Test Development

When adding new tests:

1. Create test file in `src/test/` directory
2. Include `<boost/test/unit_test.hpp>`
3. Use `BOOST_AUTO_TEST_SUITE` and `BOOST_AUTO_TEST_CASE`
4. Use C++11 features (range-for, initializer lists, etc.)
5. Avoid deprecated Boost libraries (assign, foreach)

Example:
```cpp
#include <boost/test/unit_test.hpp>
#include "../your_module.h"

BOOST_AUTO_TEST_SUITE(YourModule_tests)

BOOST_AUTO_TEST_CASE(test_something)
{
    // Use C++11 initializer lists
    std::vector<int> data = {1, 2, 3, 4, 5};

    // Use range-based for loops
    for (const auto& value : data) {
        BOOST_CHECK(value > 0);
    }
}

BOOST_AUTO_TEST_SUITE_END()
```

## See Also

- [Build Instructions](build-unix.txt) - General build guide
- [CMake Build Instructions](../BUILD.cmake.md) - Modern CMake build
- [Modernization Guide](../MODERNIZATION.md) - C++11 modernization status
