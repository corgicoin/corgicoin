# Berkeley DB version

Every CorgiCoin build links **Berkeley DB 5.3.28**, built from source by `contrib/build-bdb53.sh` (static, checksum pinned), on Linux, macOS
and Windows (the daemon cross-built with MinGW, the Qt wallet built with MSYS2). Before this, Linux and macOS used the distribution's or Homebrew's
5.3 (or 18.x), the cross-built Windows daemon used 4.8, and the Windows Qt wallet used the MSYS2 package; so a `wallet.dat` could meet a different
version on another platform.

Why one version: a database environment or index file made by a newer BDB cannot be opened by an older one, while the newer ones open the older
ones' files. Once opened by 5.3 a data directory cannot go back to 4.8.

## Who has to do anything

* **Linux or macOS on 5.3 already (the usual case):** nothing.
* **Windows, from a release built with 4.8:** nothing to do to start. 5.3 reads 4.8's files and upgrades them. Keep a copy of `wallet.dat` first,
  because the upgraded files cannot be read by the old release again.
* **From a build that used BDB 18.x (some Homebrew installs):** 18.x files cannot be opened by 5.3. With the old version stopped: copy `wallet.dat`
  somewhere safe, delete `database/`, `db.log` and `blkindex.dat` from the data directory (keep `wallet.dat` and the `blk*.dat` files), and start
  the new version with `-reindex`. The block index is rebuilt from the block files. (`wallet.dat` itself opens once the old environment is gone;
  this was checked from a 5.3 build to a 4.8 build, the same kind of step.)

A new data directory (a fresh install) needs none of this.
