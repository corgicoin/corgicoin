# Seed Node Upgrade Runbook

How to upgrade a CorgiCoin seed/full node to a new release with minimal
downtime. Written for the project seed nodes (`seed1.corgicoin.co`,
`seed2.corgicoin.co`) but applies to any Linux node operator.

Upgrades are drop-in: v4.x releases share the same wallet, database, and
protocol formats, so no reindex or wallet migration is needed. The chain
keeps running while one seed is down — peers just use the other.

## 1. Get the new binary

Preferred: the release binary from GitHub.

```bash
VER=v4.2.0.0
cd /tmp
curl -LO https://github.com/corgicoin/corgicoin/releases/download/$VER/corgicoin-$VER-linux-x64.tar.gz
curl -LO https://github.com/corgicoin/corgicoin/releases/download/$VER/SHA256SUMS
sha256sum -c --ignore-missing SHA256SUMS   # must say OK
tar xzf corgicoin-$VER-linux-x64.tar.gz
```

**Check it runs on this box** (release binaries are built on Ubuntu 24.04
and dynamically linked):

```bash
cd corgicoin-$VER-linux-x64
ldd ./corgicoind | grep "not found" || ./corgicoind --help >/dev/null && echo BINARY_OK
```

If you see `not found` libraries or a GLIBC version error (likely on
Ubuntu ≤22.04 droplets), build from source on the box instead:

```bash
sudo apt-get install -y build-essential cmake libboost-all-dev libssl-dev libdb++-dev libminiupnpc-dev
git clone --depth 1 --branch $VER https://github.com/corgicoin/corgicoin.git /tmp/corgicoin-src
cd /tmp/corgicoin-src && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DBUILD_QT_GUI=OFF -DBUILD_TESTS=ON
make -j$(nproc) && ./test_corgicoin
```

## 2. Record pre-upgrade state

```bash
corgicoind getinfo > /tmp/pre-upgrade-info.json
cat /tmp/pre-upgrade-info.json   # note: version, blocks, connections
```

Back up the wallet (cheap insurance even for a seed node):

```bash
cp ~/.corgicoin/wallet.dat ~/wallet.dat.bak-$(date +%Y%m%d)
```

## 3. Swap the binary

```bash
corgicoind stop
sleep 5   # give it time to flush the database cleanly
which corgicoind   # confirm install location, commonly /usr/local/bin
sudo install -m 755 ./corgicoind /usr/local/bin/corgicoind
```

If the node runs under systemd, `systemctl stop corgicoind` /
`systemctl start corgicoind` instead of the direct commands.

## 4. Restart and verify

```bash
corgicoind
sleep 10
corgicoind getinfo
```

Check, comparing against the pre-upgrade snapshot:

- `version` reports the new release
- `blocks` is at or above the pre-upgrade height and advancing with the network
- `connections` > 0 (the other seed should connect within a few minutes)
- `errors` is empty

From any other machine, confirm the seed is reachable:

```bash
nc -zv seed1.corgicoin.co 62556
```

## 5. Rollback

If the new binary misbehaves, reinstall the previous one and restart —
same steps as 3–4. Data and wallet formats are unchanged between v4.x
releases, so rolling back is safe. This is why step 3 uses `install`
rather than overwriting: keep the old binary around
(`cp /usr/local/bin/corgicoind ~/corgicoind-old`) before the swap if you
want a fast path back.

## Current project seeds

| Host | Provider | Notes |
|------|----------|-------|
| seed1.corgicoin.co (104.131.90.19) | DigitalOcean | on v4.1.0 as of 2026-05, needs this upgrade |
| seed2.corgicoin.co (159.65.161.47) | DigitalOcean | upgraded to v4.2.0 2026-05 |

Upgrade one seed at a time and verify it is healthy before touching the
other, so the network always has at least one live seed.
