# CMake Build Instructions for CorgiCoin

## Prerequisites

### Compiler
- **C++17 compatible**: GCC 9+, Clang 10+, or MSVC 2019+

### Required Dependencies

- **CMake** 3.10+
- **OpenSSL** 3.x
- **Boost** 1.55+ (program_options, thread)
- **Berkeley DB** 5.3+ (C++ bindings required)

### Optional Dependencies

- **Qt** 5.15+ or 6.x (for GUI wallet)
- **miniupnpc** (for UPnP port forwarding)
- **qrencode** (for QR code support)

## Quick Start

### Linux (Ubuntu/Debian)

```bash
# Install dependencies
sudo apt-get install build-essential cmake libboost-all-dev libssl-dev \
  libdb++-dev libminiupnpc-dev

# Build daemon + tests
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=OFF -DBUILD_TESTS=ON
make -j$(nproc)

# Run tests
./test_corgicoin
```

### macOS

```bash
# Install dependencies
brew install boost openssl@3 berkeley-db miniupnpc cmake

# Build daemon
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=OFF \
  -DOPENSSL_ROOT_DIR=$(brew --prefix openssl@3) \
  -DBerkeleyDB_ROOT=$(brew --prefix berkeley-db)
make -j$(sysctl -n hw.logicalcpu)
```

### macOS with Qt 6 GUI

```bash
brew install qt

mkdir build-qt && cd build-qt
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=ON \
  -DOPENSSL_ROOT_DIR=$(brew --prefix openssl@3) \
  -DBerkeleyDB_ROOT=$(brew --prefix berkeley-db) \
  -DCMAKE_PREFIX_PATH=$(brew --prefix qt)
make -j$(sysctl -n hw.logicalcpu)
```

### Windows (Visual Studio)

```cmd
mkdir build && cd build
cmake .. -G "Visual Studio 16 2019" -A x64
cmake --build . --config Release
```

## Build Options

| Option | Default | Description |
|--------|---------|-------------|
| `BUILD_QT_GUI` | ON | Build Qt GUI wallet (corgicoin-qt) |
| `BUILD_TESTS` | OFF | Build test suite |
| `USE_UPNP` | ON | Enable UPnP support |
| `USE_QRCODE` | OFF | Enable QR code support |
| `USE_DBUS` | OFF | Enable D-Bus notifications (Linux) |
| `ENABLE_HARDENING` | ON | Enable security hardening flags |
| `CMAKE_BUILD_TYPE` | - | Release, Debug, RelWithDebInfo |

### Examples

```bash
# Daemon only, no GUI
cmake .. -DBUILD_QT_GUI=OFF -DCMAKE_BUILD_TYPE=Release

# Daemon + tests
cmake .. -DBUILD_QT_GUI=OFF -DBUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Release

# Full GUI with all features
cmake .. -DBUILD_QT_GUI=ON -DUSE_UPNP=ON -DUSE_QRCODE=ON

# Custom dependency paths
cmake .. \
  -DOPENSSL_ROOT_DIR=/path/to/openssl \
  -DBerkeleyDB_ROOT=/path/to/berkeleydb \
  -DCMAKE_PREFIX_PATH=/path/to/qt
```

## Build Targets

```bash
make corgicoind          # Daemon only
make corgicoin-qt        # Qt GUI only
make test_corgicoin      # Test binary only
make all                 # Everything
```

## IDE Integration

**CLion / VS Code / Qt Creator**: Open the project directory — CMake is auto-detected.

## Troubleshooting

### "Could NOT find BerkeleyDB"
Install Berkeley DB with C++ bindings, or specify the path:
```bash
cmake .. -DBerkeleyDB_ROOT=/path/to/berkeleydb
```

On Ubuntu, `libdb++-dev` provides this. On macOS, `brew install berkeley-db`.

### "Could NOT find OpenSSL"
```bash
cmake .. -DOPENSSL_ROOT_DIR=$(brew --prefix openssl@3)  # macOS
sudo apt install libssl-dev                              # Ubuntu
```

### Qt not found
```bash
cmake .. -DCMAKE_PREFIX_PATH=$(brew --prefix qt)         # macOS Qt6
cmake .. -DCMAKE_PREFIX_PATH=$(brew --prefix qt@5)       # macOS Qt5
```

## License

Released under the MIT license. See [COPYING](COPYING) for details.
