# Berkeley DB versions

The wallet (`wallet.dat`) and the block index (`blkindex.dat`) are Berkeley DB files. **A data directory that a newer Berkeley DB has written
cannot be opened by an older one**, and this includes `wallet.dat`: the maintainers found that a wallet written by 18.1 cannot be read by 5.3
(`DB_RUNRECOVERY`; recreating the environment files does not help), and `dumpwallet` does not export the HD recovery phrase. So there is no
safe way back to an older Berkeley DB, and a build must never be switched to one.

## What each release links

The requirements say "Berkeley DB 5.3+", so each build takes the newest one its platform's package provides, and nothing pins one. As found
by the maintainers in the v4.8 and v4.9 release binaries:

| Release | Berkeley DB |
|---|---|
| Linux daemon | 5.3 (the distribution's `libdb++-dev`) |
| macOS daemon and macOS Qt app | 18.1 (Homebrew `berkeley-db`) |
| Windows Qt wallet | 6.2.32 (MSYS2 `mingw-w64-x86_64-db`) |
| Windows daemon | 4.8 (cross-built from source) |

(6.x and later are licensed under the AGPLv3.)

The README's macOS instructions install `berkeley-db@5` (5.x), while the release builds use Homebrew's unversioned `berkeley-db` (18.1). A
Mac built from the README therefore does not match the shipped app, and a data directory the app has written cannot be opened by that build.

## What follows

* **Do not point a build at a different Berkeley DB than the one it had**, and do not open a data directory with a build that has an older one
  than the build that last wrote it. Moving a wallet between platforms moves it between these versions: copy `wallet.dat` only from a platform
  with an older (or equal) version to one with a newer one, never the other way, and keep a copy first.
* Unifying the versions has to move users only to **newer** versions, or has to read each old wallet with the Berkeley DB that wrote it and move
  it to a format that does not depend on one (for example SQLite, as Bitcoin Core did), leaving Berkeley DB for the block index, which
  `-reindex` can always rebuild.
