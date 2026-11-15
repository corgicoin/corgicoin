#!/bin/sh
# Build libsecp256k1 (static) into a prefix, from the pinned release, so every platform verifies signatures with the same code.
#   contrib/build-secp256k1.sh <prefix> [extra cmake arguments, e.g. a cross-compile toolchain]
# Then build CorgiCoin with -DSECP256K1_INCLUDE_DIR=<prefix>/include -DSECP256K1_LIBRARY=<prefix>/lib/libsecp256k1.a
set -eu
VERSION=0.6.0
SHA256=785bb98e7d6705c51c8dfa8ac3af6aa2ccfa3774714d51c0b9e28fac1146e9f1
URL="https://github.com/bitcoin-core/secp256k1/archive/refs/tags/v${VERSION}.tar.gz"

PREFIX=${1:?usage: build-secp256k1.sh <prefix> [cmake args]}
shift
mkdir -p "$PREFIX"
PREFIX=$(cd "$PREFIX" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

if command -v curl >/dev/null 2>&1; then curl -fsSL -o src.tar.gz "$URL"; else wget -q -O src.tar.gz "$URL"; fi
if command -v sha256sum >/dev/null 2>&1; then GOT=$(sha256sum src.tar.gz | cut -d' ' -f1); else GOT=$(shasum -a 256 src.tar.gz | cut -d' ' -f1); fi
[ "$GOT" = "$SHA256" ] || { echo "libsecp256k1 ${VERSION}: checksum mismatch ($GOT)" >&2; exit 1; }
tar xzf src.tar.gz
cd "secp256k1-${VERSION}"

# Only ECDSA verification and key parsing are used; the optional modules are left out.
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX" \
    -DBUILD_SHARED_LIBS=OFF -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    -DSECP256K1_ENABLE_MODULE_ECDH=OFF -DSECP256K1_ENABLE_MODULE_EXTRAKEYS=OFF -DSECP256K1_ENABLE_MODULE_SCHNORRSIG=OFF \
    -DSECP256K1_ENABLE_MODULE_MUSIG=OFF -DSECP256K1_ENABLE_MODULE_ELLSWIFT=OFF -DSECP256K1_ENABLE_MODULE_RECOVERY=OFF \
    -DSECP256K1_BUILD_TESTS=OFF -DSECP256K1_BUILD_EXHAUSTIVE_TESTS=OFF -DSECP256K1_BUILD_BENCHMARK=OFF -DSECP256K1_BUILD_CTIME_TESTS=OFF \
    -DSECP256K1_BUILD_EXAMPLES=OFF "$@"
cmake --build build -j "$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)"
cmake --install build
ls -la "$PREFIX/lib/libsecp256k1.a" "$PREFIX/include/secp256k1.h"
