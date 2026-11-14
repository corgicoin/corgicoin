#!/bin/bash
# Check a downloaded release: the signature on SHA256SUMS, and every file against it.
#
#   contrib/release/verify-release.sh <release-dir> <signer-fingerprint> [<public-key-file>]
#
# The fingerprint is the part that matters and it must come from somewhere other than the release itself (the project page, a
# message from the maintainer you trust). A signature that checks against a key you never pinned proves only that somebody
# signed it. The public key file, if given, is imported into a throwaway keyring for the check and not into yours.
set -eu
DIR=${1:?usage: verify-release.sh <release-dir> <signer-fingerprint> [<public-key-file>]}
FPR=$(echo "${2:?the fingerprint of the signer is required}" | tr -d ' ' | tr 'a-f' 'A-F')
PUBKEY=${3:-}
[ -f "$DIR/SHA256SUMS" ] && [ -f "$DIR/SHA256SUMS.asc" ] || { echo "FAIL: SHA256SUMS or SHA256SUMS.asc is missing" >&2; exit 1; }

GNUPGHOME=$(mktemp -d)
export GNUPGHOME
trap 'rm -rf "$GNUPGHOME"' EXIT
chmod 700 "$GNUPGHOME"
if [ -n "$PUBKEY" ]; then
    gpg --batch --quiet --import "$PUBKEY" 2>/dev/null
fi

STATUS=$(gpg --batch --status-fd 1 --verify "$DIR/SHA256SUMS.asc" "$DIR/SHA256SUMS" 2>/dev/null || true)
if ! echo "$STATUS" | grep -q '^\[GNUPG:\] VALIDSIG '; then
    echo "FAIL: no valid signature on SHA256SUMS (wrong key, changed manifest, or the public key was not given)" >&2
    exit 1
fi
SIGNED_BY=$(echo "$STATUS" | awk '/^\[GNUPG:\] VALIDSIG /{print $12}' | head -1)     # the primary key's fingerprint
SUBKEY=$(echo "$STATUS" | awk '/^\[GNUPG:\] VALIDSIG /{print $3}' | head -1)
if [ "$SIGNED_BY" != "$FPR" ] && [ "$SUBKEY" != "$FPR" ]; then
    echo "FAIL: signed by $SIGNED_BY, not by the fingerprint you gave ($FPR)" >&2
    exit 1
fi

cd "$DIR"
if ! sha256sum --check --strict --quiet SHA256SUMS; then
    echo "FAIL: a file does not match SHA256SUMS" >&2
    exit 1
fi
# no file that the manifest does not mention
awk '{print $2}' SHA256SUMS | sed 's/^\*//' | LC_ALL=C sort > "$GNUPGHOME/listed"
ls -1 | grep -vxF -e SHA256SUMS -e SHA256SUMS.asc | LC_ALL=C sort > "$GNUPGHOME/present"
EXTRA=$(comm -13 "$GNUPGHOME/listed" "$GNUPGHOME/present" | tr '\n' ' ')
if [ -n "$EXTRA" ]; then
    echo "FAIL: files that SHA256SUMS does not list: $EXTRA" >&2
    exit 1
fi
echo "OK: SHA256SUMS is signed by $FPR and every file matches"
