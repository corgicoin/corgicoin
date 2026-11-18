# Integrating CorgiCoin: exchanges, custodians and payment processors

What to know to accept deposits and make withdrawals safely. Facts here were taken from the source; where a feature is new in the
current development series it says so. See also `doc/mining.md` (chain facts), `doc/bech32-address-spec.md` (addresses) and
`contrib/corgicoin.conf.example`.

## The chain

| | |
|---|---|
| Algorithm | Scrypt, merged mining with other Scrypt chains is supported (chain ID `0xC6`) |
| Block time | 1 minute target, difficulty retargets every block |
| Coinbase maturity | consensus: 30 blocks. `getbalance` and the wallet count a mined reward as mature after 50 (`COINBASE_MATURITY + 20`) |
| Ports | P2P 62556, RPC 62555 (testnet 64556) |
| Smallest fee | 1 coin per started kB is the minimum relay fee (`getmempoolinfo` `minrelaytxfee`) |

## Addresses: read this first

An address has two text forms. Both name the same destination.

- **base58**: P2PKH version byte 28 (starts with `C` on mainnet), P2SH version byte 22.
- **bech32m**: human-readable part `corg` (`tcorg` on testnet and regtest). P2PKH is type 0, P2SH is type **31**.

**Do not use a segwit address library for the bech32m form.** CorgiCoin has no segwit. A generic library reads the first data value
as a witness version, and would read some P2SH addresses as valid witness addresses and pay an output **anyone can spend**.
P2SH addresses use type 31 for this reason; a segwit library refuses them. Decode as the spec says (`doc/bech32-address-spec.md`),
or simply accept base58 only and let `validateaddress` give the canonical form (`address`).

Store and compare addresses in one canonical form. `getnewaddress` may return either form; `validateaddress` returns both
(`address` is base58, `bech32` is the other).

## Receiving deposits

1. Give each customer their own address (`getnewaddress`). Never reuse one for a different customer.
2. Find deposits with `listsinceblock <blockhash>` and keep the `lastblock` it returns, or be told by the node:
   `-walletnotify="<command> %s"` runs the command with the transaction id when a wallet transaction is new or changes (it
   fires again when the transaction confirms), and `-blocknotify` does the same for each new best block. Both are one-off
   notifications: always confirm with the RPC, and poll as a backstop.
3. For each transaction read `confirmations` with `gettransaction <txid>`. Also read **`conflicted`** and `walletconflicts`
   (new in this series): a transaction another transaction in the chain double-spends can never confirm and must never be credited.
4. Credit at your chosen number of confirmations, and store the **block hash** it was confirmed in as well as the transaction id.

### How many confirmations?

There is no safe number that fits every chain, and none is promised here. Two facts should drive the choice:

- Blocks come every minute, but this chain's hash rate is small compared with the biggest Scrypt chains. Anyone who can rent more
  work than the honest network holds can reorganise the chain, so a reorganisation of many blocks is not out of the question on
  a chain of this size. Merged mining raises the cost of an attack, but only as far as miners really merge-mine.
- A coinbase (mined) reward is only spendable after the maturity above. If you are a pool, or you receive mining payouts, treat
  them as pending until the wallet calls them mature (50).

A sensible starting point is **an hour of blocks or more** for deposits of any size, with more for large ones and a hold on a
withdrawal of a deposit that is shallow. Raise it if you see competing branches in `getchaintips`.

### Reorganisations

On a reorganisation a transaction can lose its confirmations, move to another block, or become `conflicted`. Your ledger must be
able to undo a credit. Re-read `confirmations` and the block hash for credited deposits that are not yet very deep, on every new
block, and reverse any credit whose block is no longer in the best chain (`getblockhash <height>` against the stored hash).

## Withdrawals

- Use `sendmany` to pay several customers in one transaction. A transaction over 100 kB is not relayed (standardness).
- The wallet refuses a fee above `-maxtxfee` (default 10000 coins, new in this series), which guards against a fee typed a decimal
  place wrong. Set it to something sensible for your own withdrawals.
- A send that the memory pool would refuse no longer leaves the wallet's coins marked as spent (fixed in this series); in older
  releases, restart the wallet or `abandontransaction` if a send failed after it was recorded.
- Keep the wallet encrypted. Unlock only for as long as a withdrawal batch needs (`walletpassphrase <pass> <seconds>`), and do not
  leave a long unlock.
- Back up the wallet and, for an HD wallet, the recovery phrase (`gethdseed true` shows it while the wallet is unlocked).
  `backupwallet` reports failure if the copy could not be written.

### Cold storage

Keep the cold keys on an offline machine. Build the transaction with `createrawtransaction` on the online node, sign it offline
with `signrawtransaction` (passing the inputs it spends), and send it with `sendrawtransaction`. `testmempoolaccept` says why a
transaction would be refused before you send it.

## Talking to the node safely

- Keep RPC on localhost. If it must be reached from another machine, put a TLS proxy in front: `-rpcssl` is deprecated.
- Do not put `rpcpassword` on the command line. Use `-rpcauth=<user>:<salt>$<hash>` (make a line with `contrib/rpcauth.py`), so
  the config holds no password; or leave credentials unset and use the cookie file (`.cookie` in the data directory).
- After 20 failed logins in a minute from one address the node refuses it for a minute (`-rpcmaxauthfailures`).
- `getmetrics` returns Prometheus text, `getrpcinfo` lists calls in progress, and `logging` switches debug categories on and off
  without a restart (all new in this series).

## Checklist before going live

- [ ] Addresses decoded by `validateaddress`, not a segwit library.
- [ ] Deposits credited by confirmations *and* `conflicted == false`, with the block hash stored.
- [ ] A reorganisation test: credit, fork, check the credit is reversed.
- [ ] Wallet encrypted, backed up, recovery phrase stored offline; backup restored on a spare machine at least once.
- [ ] RPC on localhost, no password on the command line.
- [ ] Alerts on `getmetrics`: blocks stopped rising, peers at zero, `corgicoin_initial_block_download` stuck at 1.
