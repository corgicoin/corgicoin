# Running a pool: operations notes

`doc/mining.md` says how to connect pool software to the node (stratum is the pool's job; the node serves `getblocktemplate`,
`createauxblock`/`submitauxblock`, `getauxblock` and `submitblock`). This note covers what to do around it. **No pool-software
configuration is shipped here, because none could be tested** (that includes Miningcore): take the RPC names above and the
fields in `doc/auxpow-spec.md` and test your own set-up on regtest first (`-regtest` needs no peers, and `getblocktemplate` works
there with no peers).

## Paying out

- A mined reward is spendable by consensus after 30 blocks, but the wallet only counts it as mature after **50**. Pay miners from
  matured funds only, and pay out later than the maturity, not at it: a reward that is orphaned after you have paid it comes out of
  the pool's pocket. A deeper margin is cheap insurance on a chain with a small hash rate.
- Pay from a wallet that is separate from the one that receives the block rewards. The receiving address can be fixed with
  `-mineraddress=<address>` (the node's own miner) or by the address you pass to `createauxblock`.
- Before paying, read `gettransaction` for each reward: `confirmations`, and `conflicted`. Use `sendmany` and keep each transaction
  under 100 kB. The wallet refuses fees above `-maxtxfee` (default 10000 coins).

## Knowing when there is a new block

Poll `getblocktemplate` (about once a second; it does not long-poll), or be told:
`-blocknotify="<command> %s"` runs a command with the new best block's hash, and a ZeroMQ build can publish `hashblock`
(`doc/mining.md`). `-walletnotify="<command> %s"` runs a command when a wallet transaction is new or changes, for payout
tracking. A block that the node cannot connect is marked failed until the node restarts; one marked with `invalidateblock` stays marked
across restarts, and `reconsiderblock` lifts either.

## Watching the node

- `getmetrics` returns Prometheus text: height, difficulty, peers (in and out), mempool size, traffic, uptime, calls in flight.
  Scrape it from localhost.
- `getrpcinfo` shows which RPC calls are running or waiting; one long call holds the node lock and blocks the others.
- `logging ["net"]` turns a debug category on without a restart, `logging [] ["net"]` turns it off.
- Alert on: height not rising for several minutes, no peers, `corgicoin_initial_block_download` stuck at 1.

## Keeping the node healthy

- Credentials: use `-rpcauth` (`contrib/rpcauth.py`) or the cookie file, never a password on the command line.
- Several nodes behind the pool are better than one: if the node a pool trusts is on a stale chain, every share it accepts is wasted.
  Compare `getblockcount` and `getbestblockhash` across them.
- Restart gently: give the node several minutes to close its databases (`doc/packaging.md`; the systemd unit allows ten).
- Run the current release. Merged-mined blocks need v4.7.0.0 or later, and fixes in this series close ways for a remote peer to
  crash or stall a node.
