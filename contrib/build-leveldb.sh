#!/bin/sh
# Build LevelDB (static) into a prefix, from the pinned release: the store of the unspent-output set and its undo data (8.1).
#   contrib/build-leveldb.sh <prefix> [extra cmake arguments, e.g. a cross-compile toolchain]
# Then build CorgiCoin with -DLEVELDB_INCLUDE_DIR=<prefix>/include -DLEVELDB_LIBRARY=<prefix>/lib/libleveldb.a
set -eu
VERSION=1.23
SHA256=9a37f8a6174f09bd622bc723b55881dc541cd50747cbd08831c2a82d620f6d76
URL="https://github.com/google/leveldb/archive/refs/tags/${VERSION}.tar.gz"

PREFIX=${1:?usage: build-leveldb.sh <prefix> [cmake args]}
shift
mkdir -p "$PREFIX"
PREFIX=$(cd "$PREFIX" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

if command -v curl >/dev/null 2>&1; then curl -fsSL -o src.tar.gz "$URL"; else wget -q -O src.tar.gz "$URL"; fi
if command -v sha256sum >/dev/null 2>&1; then GOT=$(sha256sum src.tar.gz | cut -d' ' -f1); else GOT=$(shasum -a 256 src.tar.gz | cut -d' ' -f1); fi
[ "$GOT" = "$SHA256" ] || { echo "leveldb ${VERSION}: checksum mismatch ($GOT)" >&2; exit 1; }
tar xzf src.tar.gz
cd "leveldb-${VERSION}"

# No snappy (the chainstate is small and compresses little), no tests or benchmarks (they need the submodules the tarball lacks).
# C++17: leveldb 1.23 asks for C++11 and breaks on the standard headers of the newest compilers if left to its own setting.
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DBUILD_SHARED_LIBS=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DCMAKE_CXX_STANDARD=17 \
    -DLEVELDB_BUILD_TESTS=OFF -DLEVELDB_BUILD_BENCHMARKS=OFF -DLEVELDB_INSTALL=ON \
    -DHAVE_SNAPPY=OFF -DHAVE_CRC32C=OFF -DHAVE_TCMALLOC=OFF "$@"
cmake --build build -j "$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)"
cmake --install build
ls -la "$PREFIX/lib/libleveldb.a" "$PREFIX/include/leveldb/db.h"
