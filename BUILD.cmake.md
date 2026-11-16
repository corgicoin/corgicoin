# CMake Build Instructions for CorgiCoin

## Prerequisites

### Compiler
- **C++17 compatible**: GCC 9+, Clang 10+, or MSVC 2019+

### Required Dependencies

- **CMake** 3.10+
- **OpenSSL** 3.x
- **Boost** 1.55+ (program_options, thread)
- **Berkeley DB** 5.3.28 (C++ bindings; built by `contrib/build-bdb53.sh`, see doc/berkeley-db.md)

### Optional Dependencies

- **Qt** 5.15+ or 6.x (for GUI wallet)
- **miniupnpc** (for UPnP port forwarding)
- **qrencode** (for QR code support)

## Quick Start

### Linux (Ubuntu/Debian)

```bash
# Install dependencies
sudo apt-get install build-essential cmake curl libboost-all-dev libssl-dev \
  libminiupnpc-dev

# Berkeley DB 5.3.28 (pinned, checked by checksum), into $HOME/bdb53
contrib/build-bdb53.sh $HOME/bdb53

# Build daemon + tests
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=OFF -DBUILD_TESTS=ON \
  -DBERKELEYDB_INCLUDE_DIR=$HOME/bdb53/include -DBERKELEYDB_LIBRARY=$HOME/bdb53/lib/libdb_cxx.a
make -j$(nproc)

# Run tests
./test_corgicoin
```

### macOS

```bash
# Install dependencies
brew install boost openssl@3 miniupnpc cmake
contrib/build-bdb53.sh $HOME/bdb53

# Build daemon
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=OFF \
  -DOPENSSL_ROOT_DIR=$(brew --prefix openssl@3) \
  -DBERKELEYDB_INCLUDE_DIR=$HOME/bdb53/include -DBERKELEYDB_LIBRARY=$HOME/bdb53/lib/libdb_cxx.a
make -j$(sysctl -n hw.logicalcpu)
```

### macOS with Qt 6 GUI

```bash
brew install qt

mkdir build-qt && cd build-qt
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=ON \
  -DOPENSSL_ROOT_DIR=$(brew --prefix openssl@3) \
  -DBERKELEYDB_INCLUDE_DIR=$HOME/bdb53/include -DBERKELEYDB_LIBRARY=$HOME/bdb53/lib/libdb_cxx.a \
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
  -DBERKELEYDB_INCLUDE_DIR=/path/to/bdb/include -DBERKELEYDB_LIBRARY=/path/to/bdb/lib/libdb_cxx.a \
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
Build the pinned Berkeley DB (5.3.28) and say where it is:
```bash
contrib/build-bdb53.sh $HOME/bdb53
cmake .. -DBERKELEYDB_INCLUDE_DIR=$HOME/bdb53/include -DBERKELEYDB_LIBRARY=$HOME/bdb53/lib/libdb_cxx.a
```

All platforms use this one version so that a `wallet.dat` opens on every one of them (see doc/berkeley-db.md).

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
