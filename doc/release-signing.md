# Signing and verifying a release

`contrib/release/` has three scripts. They need `bash`, `sha256sum` and `gpg`.

| Script | Who runs it | What it does |
|---|---|---|
| `make-manifest.sh <dir> [<key-id>]` | the maintainer, on a machine that did not build the files | writes `SHA256SUMS` for the files in `<dir>` (bare names, sorted: the same files always give the same manifest) and, with a key id, a detached signature `SHA256SUMS.asc` |
| `verify-release.sh <dir> <fingerprint> [<public-key-file>]` | anyone who downloaded a release | checks the signature, that the signer is **the fingerprint you give**, that every file matches, and that no file is present that the manifest does not list |
| `test-release-scripts.sh` | whoever changes the scripts | makes throwaway keys and checks both scripts, including that each kind of damage (a changed file, a changed manifest, a missing signature, the wrong key, a stray file) is refused **for its own reason** |

## What the signature is worth

A signature that checks out against a key you never pinned proves only that somebody signed it. Get the fingerprint from somewhere
other than the release page (the project's site, a message from a maintainer you know), and give it to `verify-release.sh`. The
script refuses to run without one.

Keep the signing key off the build machine and off the machines that run CI. A release built by a compromised build machine and
signed by a good key on that machine is still a bad release.

## What this does not give you yet

- **Reproducible builds.** Nothing here shows that the published binaries are what the source produces. For that, two people build
  the same tag in the same pinned environment (a container with fixed compiler, library and tool versions, fixed timestamps) and
  compare the hashes. That environment does not exist yet, and until two independent builds have matched, a signature says who
  published the binary, not what is in it. `doc/release-process.txt` describes the old Gitian method, which is not in use.
- **The release workflow does not run these scripts.** The workflow builds and publishes; signing is a separate step done by hand
  with a key that is not in CI. Adding the manifest to the workflow (unsigned) is easy; the signature has to stay offline.
- **Windows and macOS code signing** (Authenticode, Apple notarisation) is separate from this and not done.
