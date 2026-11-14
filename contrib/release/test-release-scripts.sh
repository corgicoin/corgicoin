#!/bin/bash
# Test make-manifest.sh and verify-release.sh against a throwaway key: contrib/release/test-release-scripts.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
export GNUPGHOME=$WORK/gnupg
mkdir -m 700 "$GNUPGHOME"
fail=0
check() { # name, expected exit (0 or non-0), a pattern the output must show, command...
    local name=$1 want=$2 pattern=$3; shift 3
    "$@" >"$WORK/out" 2>&1; local rc=$?
    local fine=1
    { [ "$want" = 0 ] && [ $rc -eq 0 ]; } || { [ "$want" != 0 ] && [ $rc -ne 0 ]; } || fine=0
    # it must fail (or pass) for the reason the test is about, not for any reason at all
    grep -q -- "$pattern" "$WORK/out" || fine=0
    if [ $fine = 1 ]; then echo "ok   $name"; else echo "FAIL $name (exit $rc, wanted a message matching '$pattern')"; sed 's/^/     /' "$WORK/out"; fail=1; fi
}

gpg --batch --quiet --passphrase '' --quick-generate-key "release test <test@example.invalid>" ed25519 sign never 2>/dev/null
FPR=$(gpg --batch --with-colons --list-keys | awk -F: '/^fpr:/{print $10; exit}')
gpg --batch --armor --export "$FPR" > "$WORK/pub.asc"
gpg --batch --quiet --passphrase '' --quick-generate-key "other <other@example.invalid>" ed25519 sign never 2>/dev/null
OTHER=$(gpg --batch --with-colons --list-keys | awk -F: '/^fpr:/{n++; if (n==2) {print $10; exit}}')

REL=$WORK/rel; mkdir "$REL"
echo "daemon" > "$REL/corgicoind-linux"; echo "windows" > "$REL/corgicoind.exe"; echo "notes" > "$REL/RELEASE-NOTES.txt"

check "a release is signed"                      0 "signed:" bash "$HERE/make-manifest.sh" "$REL" "$FPR"
check "the manifest is the same when made again" 0 "same manifest" bash -c "cp $REL/SHA256SUMS $WORK/first && bash $HERE/make-manifest.sh $REL >/dev/null && cmp $WORK/first $REL/SHA256SUMS && echo same manifest"
bash "$HERE/make-manifest.sh" "$REL" "$FPR" >/dev/null
check "it verifies with the right fingerprint"  0 "^OK: " bash "$HERE/verify-release.sh" "$REL" "$FPR" "$WORK/pub.asc"
check "a spaced, lower case fingerprint works"  0 "^OK: " bash "$HERE/verify-release.sh" "$REL" "$(echo "$FPR" | tr 'A-F' 'a-f' | sed 's/..../& /g')" "$WORK/pub.asc"
check "another key's fingerprint is refused"    1 "signed by .* not by the fingerprint" bash "$HERE/verify-release.sh" "$REL" "$OTHER" "$WORK/pub.asc"
check "no public key to check against fails"    1 "no valid signature" bash "$HERE/verify-release.sh" "$REL" "$FPR"

cp -r "$REL" "$WORK/tampered-file";   echo "evil" >> "$WORK/tampered-file/corgicoind-linux"
check "a changed file is refused"               1 "a file does not match" bash "$HERE/verify-release.sh" "$WORK/tampered-file" "$FPR" "$WORK/pub.asc"
cp -r "$REL" "$WORK/tampered-sums";   sed -i 's/^./0/' "$WORK/tampered-sums/SHA256SUMS"
check "a changed manifest is refused"           1 "no valid signature" bash "$HERE/verify-release.sh" "$WORK/tampered-sums" "$FPR" "$WORK/pub.asc"
cp -r "$REL" "$WORK/extra-file";      echo "extra" > "$WORK/extra-file/surprise.sh"
check "a file the manifest does not list fails" 1 "does not list: surprise.sh" bash "$HERE/verify-release.sh" "$WORK/extra-file" "$FPR" "$WORK/pub.asc"
cp -r "$REL" "$WORK/no-sig";          rm "$WORK/no-sig/SHA256SUMS.asc"
check "a missing signature is refused"          1 "is missing" bash "$HERE/verify-release.sh" "$WORK/no-sig" "$FPR" "$WORK/pub.asc"

[ $fail -eq 0 ] && echo "all release script checks passed"
exit $fail
