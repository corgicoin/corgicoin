#!/bin/bash
# Make SHA256SUMS for the files of a release, and (optionally) sign it.
#
#   contrib/release/make-manifest.sh <release-dir> [<gpg-key-id>]
#
# <release-dir> holds the files to publish (binaries, archives). SHA256SUMS lists them by bare name, in sorted order, so
# the same files always give the same manifest. With a gpg key id the manifest is signed (SHA256SUMS.asc, detached, ASCII).
# Sign on a machine that is not the build machine, and publish the key's fingerprint somewhere other than the release page.
set -eu
DIR=${1:?usage: make-manifest.sh <release-dir> [<gpg-key-id>]}
KEY=${2:-}
cd "$DIR"
rm -f SHA256SUMS SHA256SUMS.asc
FILES=$(ls -1 | LC_ALL=C sort)
[ -n "$FILES" ] || { echo "no files in $DIR" >&2; exit 1; }
# shellcheck disable=SC2086
LC_ALL=C sha256sum $FILES > SHA256SUMS
echo "wrote $(wc -l < SHA256SUMS) entries to $DIR/SHA256SUMS"
if [ -n "$KEY" ]; then
    gpg --batch --yes --local-user "$KEY" --armor --detach-sign --output SHA256SUMS.asc SHA256SUMS
    echo "signed: $DIR/SHA256SUMS.asc"
fi
