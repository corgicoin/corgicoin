#!/bin/sh
# Build Berkeley DB 5.3.28 as a static library into a prefix, the one BDB version every CorgiCoin release links so that a
# wallet.dat made on one platform opens on every other (a database environment made by a newer version cannot be opened by an older one).
# Usage: contrib/build-bdb53.sh <prefix>
# Then: cmake .. -DBERKELEYDB_INCLUDE_DIR=<prefix>/include -DBERKELEYDB_LIBRARY=<prefix>/lib/libdb_cxx.a
set -e
PREFIX=${1:?usage: build-bdb53.sh <prefix>}
SHA256=e0a992d740709892e81f9d93f06daf305cf73fb81b545afe72478043172c3628
URL=https://download.oracle.com/berkeley-db/db-5.3.28.tar.gz
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
if command -v curl >/dev/null 2>&1; then curl -fsSL -o db.tar.gz "$URL"; else wget -q -O db.tar.gz "$URL"; fi
if command -v sha256sum >/dev/null 2>&1; then SUM=$(sha256sum db.tar.gz | cut -d' ' -f1); else SUM=$(shasum -a 256 db.tar.gz | cut -d' ' -f1); fi
[ "$SUM" = "$SHA256" ] || { echo "db-5.3.28.tar.gz has the wrong checksum: $SUM"; exit 1; }
tar xzf db.tar.gz
cd db-5.3.28
# the names clash with compiler builtins in gcc 5+ and clang
for f in $(grep -rlE '__atomic_compare_exchange|atomic_init' src); do
    sed -i.old -E 's/__atomic_compare_exchange/__atomic_compare_exchange_db/g; s/(^|[^_[:alnum:]])atomic_init([^_[:alnum:]]|$)/\1atomic_init_db\2/g' "$f"
done
cd build_unix
EXTRA=
case "$(uname -s)-$(uname -m)" in
    # the 2009 config.guess does not know Apple silicon: say what it is
    Darwin-arm64) EXTRA="--build=arm-apple-darwin" ;;
esac
case "$(uname -s)" in
    MINGW*|MSYS*)       # a native build on Windows (MSYS2); the include is WinIoCtl.h in the source and winioctl.h on disk
        EXTRA="$EXTRA --enable-mingw"
        sed -i 's/WinIoCtl.h/winioctl.h/g' ../src/dbinc/win_db.h ;;
esac
# the source and configure's probes are 1990s C (implicit int and declarations, mismatched function pointer types), which recent clang
# and gcc 14 refuse as errors unless told they are warnings
export CFLAGS="${CFLAGS:-} -Wno-implicit-int -Wno-implicit-function-declaration -Wno-int-conversion -Wno-incompatible-pointer-types"
export CXXFLAGS="${CXXFLAGS:-} -Wno-implicit-int -Wno-implicit-function-declaration -Wno-int-conversion -Wno-incompatible-pointer-types"
../dist/configure --enable-cxx --disable-shared --disable-replication --with-pic --prefix="$PREFIX" $EXTRA
make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)" libdb-5.3.a libdb_cxx-5.3.a
mkdir -p "$PREFIX/include" "$PREFIX/lib"
cp db.h db_cxx.h db_config.h "$PREFIX/include/"
cp libdb-5.3.a libdb_cxx-5.3.a "$PREFIX/lib/"
ln -sf libdb_cxx-5.3.a "$PREFIX/lib/libdb_cxx.a"
ln -sf libdb-5.3.a "$PREFIX/lib/libdb.a"
echo "Berkeley DB 5.3.28 installed in $PREFIX"
