# Mining CorgiCoin

CorgiCoin is a Scrypt proof-of-work chain with 1-minute blocks. Network
hashrate is currently low, which means **CPU mining works today** — the
built-in miner in `corgicoind` is enough to find blocks. This guide gets you
from zero to mining.

## Chain facts

| Parameter | Value |
|-----------|-------|
| Algorithm | Scrypt (1024, 1, 1, 256) |
| Block time | 1 minute |
| Difficulty retarget | Every 4 hours |
| Block reward | Random, seeded from previous block hash (see README for the schedule) |
| Coinbase maturity | 30 blocks before rewards are spendable |
| P2P / RPC ports | 62556 / 62555 |

## 1. Get the software

**Download** the latest release for your platform from
[GitHub Releases](https://github.com/corgicoin/corgicoin/releases), or
**build from source** — see the Building section in the top-level
[README](../README.md).

## 2. Configure

Create a `corgicoin.conf` in your data directory:

- Linux: `~/.corgicoin/corgicoin.conf`
- macOS: `~/Library/Application Support/CorgiCoin/corgicoin.conf`
- Windows: `%APPDATA%\CorgiCoin\corgicoin.conf`

Minimal config (see [contrib/corgicoin.conf.example](../contrib/corgicoin.conf.example)
for the full annotated version):

```ini
rpcuser=corgirpc
rpcpassword=pick_a_long_random_password
daemon=1
```

Seed nodes (`seed1.corgicoin.co`, `seed2.corgicoin.co`) are built into the
client — no `addnode` needed, though it doesn't hurt to pin them.

## 3. Start the daemon and sync

```bash
./corgicoind
```

Check sync progress and peer connections:

```bash
./corgicoind getinfo
```

The chain is small; initial sync takes minutes, not hours. You should see
`connections` ≥ 1 (the seed nodes accept inbound connections).

## 4. Mine

### Built-in CPU miner

Start mining with 2 threads:

```bash
./corgicoind setgenerate true 2
```

Watch your progress:

```bash
./corgicoind getmininginfo    # difficulty, network hashrate, your hashrate
./corgicoind gethashespersec  # your raw hashrate
./corgicoind getbalance       # rewards appear here after 30 confirmations
```

Stop mining:

```bash
./corgicoind setgenerate false
```

At current network difficulty a single modern CPU can find blocks in
minutes. Rewards mature after 30 blocks (~30 minutes) before they are
spendable.

### External miners

`corgicoind` serves both `getwork` and `getblocktemplate`, so external
Scrypt miners (e.g. cpuminer / minerd) can point at your local daemon:

```bash
minerd -a scrypt -o http://127.0.0.1:62555 -O corgirpc:yourpassword
```

There is no public stratum pool yet. If you run one, let us know and we'll
list it here.

## 5. What to do with mined CORG

Beyond holding and transacting, CorgiCoin has an on-chain burn mechanism
that bridges to Solana partner tokens:

- `burnforpartner <amount> <partner_tag> <sol_address>` — burn CORG,
  credited to your Solana wallet by the bridge
- See [doc/burn-payload-spec.md](burn-payload-spec.md) and
  [ROADMAP-PUMPFUN.md](../ROADMAP-PUMPFUN.md) for where this is headed.

## Troubleshooting

- **0 connections**: check that outbound TCP 62556 isn't blocked; try
  `addnode=seed1.corgicoin.co` in your config.
- **`setgenerate` returns but hashrate is 0**: the wallet won't mine until
  the chain is fully synced.
- **RPC refuses connections**: `rpcuser`/`rpcpassword` must be set in
  `corgicoin.conf` before the daemon starts.

Questions or want to get involved? Open an issue on GitHub.
