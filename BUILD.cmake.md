# CMake Build Instructions for CorgiCoin

CorgiCoin now supports CMake as a modern alternative build system alongside the traditional qmake/make builds.

## Why CMake?

- **Modern Standard**: CMake is the de facto standard for C++ projects
- **Cross-Platform**: Better support for Windows, macOS, and Linux
- **Dependency Management**: Automatic dependency detection and configuration
- **IDE Integration**: Works seamlessly with Visual Studio, CLion, Qt Creator, and more
- **Out-of-Source Builds**: Keeps build artifacts separate from source code

## Prerequisites

### All Platforms

- **CMake 3.10 or higher**
- **C++11 compatible compiler** (GCC 7+, Clang 5+, MSVC 2017+)

### Required Dependencies

- **OpenSSL** 3.x (CRITICAL: Do not use 1.0.x - see MODERNIZATION.md)
  - Ubuntu/Debian: `sudo apt install libssl-dev`
  - macOS: `brew install openssl@3`
  - Windows: Use vcpkg or build from source

- **Boost** 1.55.0+ (1.70+ recommended)
  - Ubuntu/Debian: `sudo apt install libboost-all-dev`
  - macOS: `brew install boost`
  - Windows: Use vcpkg or download from boost.org

- **Berkeley DB** 5.3+ (C++ bindings required)
  - Ubuntu/Debian: Install from source (C++ bindings not in standard packages)
  - macOS: `brew install berkeley-db`
  - Windows: Build from source or use vcpkg

  **Note**: Many Linux distributions only package the C bindings for Berkeley DB.
  You may need to build Berkeley DB from source with C++ support enabled.

### Optional Dependencies

- **Qt** 4.8+ or 5.x (for GUI)
  - Ubuntu/Debian: `sudo apt install qtbase5-dev qttools5-dev-tools`
  - macOS: `brew install qt@5`
  - Windows: Download from qt.io

- **miniupnpc** (for UPnP support)
  - Ubuntu/Debian: `sudo apt install libminiupnpc-dev`
  - macOS: `brew install miniupnpc`

- **qrencode** (for QR code support)
  - Ubuntu/Debian: `sudo apt install libqrencode-dev`
  - macOS: `brew install qrencode`

## Building Berkeley DB with C++ Support

If your distribution doesn't provide Berkeley DB C++ bindings, build from source:

```bash
# Download Berkeley DB 5.3.28 (or newer)
wget https://download.oracle.com/berkeley-db/db-5.3.28.tar.gz
tar xvf db-5.3.28.tar.gz
cd db-5.3.28/build_unix

# Configure with C++ support
../dist/configure --enable-cxx --prefix=/usr/local

# Build and install
make -j$(nproc)
sudo make install
```

## Quick Start

### Linux / macOS - Command Line Build

```bash
# Create build directory
mkdir build && cd build

# Configure (daemon only)
cmake .. -DCMAKE_BUILD_TYPE=Release

# Or configure with Qt GUI
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=ON

# Build
make -j$(nproc)  # Linux
make -j$(sysctl -n hw.ncpu)  # macOS

# Install (optional)
sudo make install
```

### Windows - Visual Studio

```cmd
# Create build directory
mkdir build
cd build

# Generate Visual Studio solution
cmake .. -G "Visual Studio 16 2019" -A x64

# Open CorgiCoin.sln in Visual Studio and build
# Or build from command line:
cmake --build . --config Release
```

### macOS - Xcode

```bash
mkdir build && cd build

# Generate Xcode project
cmake .. -G Xcode

# Open CorgiCoin.xcodeproj in Xcode and build
# Or build from command line:
cmake --build . --config Release
```

## Build Options

Configure the build with CMake options using `-D<OPTION>=<VALUE>`:

| Option | Default | Description |
|--------|---------|-------------|
| `BUILD_QT_GUI` | ON | Build Qt GUI wallet (corgicoin-qt) |
| `USE_UPNP` | ON | Enable UPnP support |
| `USE_QRCODE` | OFF | Enable QR code support (requires qrencode) |
| `USE_DBUS` | OFF | Enable D-Bus desktop notifications (Linux only) |
| `BUILD_TESTS` | OFF | Build test suite (not yet implemented) |
| `ENABLE_HARDENING` | ON | Enable security hardening compiler flags |
| `CMAKE_BUILD_TYPE` | - | Release, Debug, RelWithDebInfo, MinSizeRel |

### Examples

```bash
# Daemon only, no GUI
cmake .. -DBUILD_QT_GUI=OFF -DCMAKE_BUILD_TYPE=Release

# Full GUI with all features
cmake .. -DBUILD_QT_GUI=ON -DUSE_UPNP=ON -DUSE_QRCODE=ON -DUSE_DBUS=ON

# Debug build with hardening disabled
cmake .. -DCMAKE_BUILD_TYPE=Debug -DENABLE_HARDENING=OFF

# Specify custom dependency paths
cmake .. \
  -DOPENSSL_ROOT_DIR=/usr/local/opt/openssl@3 \
  -DBOOST_ROOT=/usr/local/opt/boost \
  -DBERKELEYDB_ROOT=/usr/local
```

## Advanced Configuration

### Custom Dependency Locations

If CMake can't find your dependencies automatically:

```bash
cmake .. \
  -DCMAKE_PREFIX_PATH="/usr/local;/opt/local" \
  -DOPENSSL_ROOT_DIR=/path/to/openssl \
  -DBoost_ROOT=/path/to/boost \
  -DBERKELEYDB_ROOT=/path/to/berkeleydb \
  -DQt5_DIR=/path/to/qt5/lib/cmake/Qt5
```

### macOS with Homebrew Dependencies

```bash
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DOPENSSL_ROOT_DIR=/usr/local/opt/openssl@3 \
  -DBoost_ROOT=/usr/local/opt/boost \
  -DBERKELEYDB_ROOT=/usr/local/opt/berkeley-db \
  -DQt5_DIR=/usr/local/opt/qt@5/lib/cmake/Qt5
```

### Cross-Compilation

CMake supports cross-compilation through toolchain files. Example for ARM:

```bash
cmake .. -DCMAKE_TOOLCHAIN_FILE=/path/to/arm-toolchain.cmake
```

## Build Targets

After configuration, you can build specific targets:

```bash
make corgicoind          # Build daemon only
make corgicoin-qt        # Build Qt GUI only
make all                 # Build everything
make install             # Install to system
make clean               # Clean build artifacts
```

Or with CMake's universal build command:

```bash
cmake --build . --target corgicoind
cmake --build . --target corgicoin-qt
cmake --build . --config Release  # Windows/MSVC
```

## IDE Integration

### CLion

1. Open the CorgiCoin directory in CLion
2. CLion will automatically detect CMakeLists.txt
3. Configure build options in Settings → Build → CMake
4. Build and run from the IDE

### Qt Creator

1. Open CMakeLists.txt as a project
2. Configure build options in Projects → Build Settings
3. Build and run from the IDE

### Visual Studio Code

1. Install the CMake Tools extension
2. Open the CorgiCoin directory
3. Select a kit (compiler)
4. Configure and build using the CMake sidebar

## Troubleshooting

### "Could NOT find BerkeleyDB"

The C++ bindings for Berkeley DB may not be installed. Either:
1. Install Berkeley DB with C++ support (see above)
2. Use the traditional qmake build instead: `qmake && make`

### "Could NOT find Boost"

Specify Boost location manually:
```bash
cmake .. -DBoost_ROOT=/path/to/boost
```

Or install Boost development packages:
```bash
# Ubuntu/Debian
sudo apt install libboost-all-dev

# macOS
brew install boost
```

### "Could NOT find OpenSSL"

**IMPORTANT**: Make sure you're using OpenSSL 3.x, not 1.0.x!

```bash
# Ubuntu/Debian
sudo apt install libssl-dev

# macOS
brew install openssl@3
cmake .. -DOPENSSL_ROOT_DIR=/usr/local/opt/openssl@3
```

### Qt not found or wrong version

Specify Qt location:
```bash
# For Qt5
cmake .. -DQt5_DIR=/path/to/qt5/lib/cmake/Qt5

# For Qt4
cmake .. -DQT_QMAKE_EXECUTABLE=/path/to/qmake
```

### Build fails with linking errors

Make sure all dependencies are found by checking CMake output:
```bash
cmake .. 2>&1 | grep -i "found\|not found"
```

## Comparison with qmake

| Feature | CMake | qmake |
|---------|-------|-------|
| Dependency detection | Automatic | Manual paths |
| IDE support | Excellent | Qt Creator only |
| Cross-platform | Excellent | Good |
| Configuration | Command line flags | .pro file editing |
| Build speed | Fast (parallel by default) | Fast |
| Industry standard | Yes | Qt-specific |

**When to use CMake:**
- Building on modern Linux distributions
- Using IDEs other than Qt Creator
- Cross-compiling
- Automated CI/CD builds
- Prefer modern build systems

**When to use qmake:**
- Quick local builds
- Familiar with Qt tooling
- Dependencies already configured
- Prefer traditional approach

## Security Notes

⚠️ **CRITICAL**: This is a 2014-era codebase with outdated dependencies.

Before building:
1. Read [MODERNIZATION.md](MODERNIZATION.md) for security assessment
2. Use modern dependency versions (OpenSSL 3.x, Boost 1.70+, etc.)
3. **DO NOT** use OpenSSL 1.0.x - it contains critical vulnerabilities
4. Test in an isolated environment
5. **DO NOT** use in production without updating dependencies

## Additional Resources

- [CMake Documentation](https://cmake.org/documentation/)
- [CorgiCoin Modernization Guide](MODERNIZATION.md)
- [Build Instructions (Unix)](doc/build-unix.txt)
- [Original README](README.md)

## License

This build system is released under the same MIT license as CorgiCoin.
See [COPYING](COPYING) for details.

---

**Version**: 1.4.1.29
**Last Updated**: 2025-11-18
**Status**: Production-ready (with modern dependencies)
