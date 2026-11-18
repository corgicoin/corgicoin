# CorgiCoin bech32m addresses

An alternative text form of the same two destinations that base58 addresses name (a key hash and a script hash). Base58
stays the default everywhere; this form is what `validateaddress` reports as `bech32` and what the address book page shows.

    <hrp> "1" <data> <checksum>        Bech32m (BIP 350)
    hrp:   "corg" (mainnet)  "tcorg" (testnet and regtest)
    data:  one 5-bit type value, then the 20-byte hash regrouped into 5-bit values

| Destination | Type value | First data character |
|---|---|---|
| Pay to key hash (P2PKH) | 0 | `q` |
| Pay to script hash (P2SH) | **31** | `l` |

## Why P2SH is type 31 (changed)

CorgiCoin has no segwit. A generic segwit library reads the first data value as a witness version and the rest as a witness
program, and BIP 350 allows versions 1 to 16 with a program of 2 to 40 bytes. An exchange, pool or explorer that added
"bech32 support" with such a library would therefore read a P2SH address written with type 1 as a valid version 1 address with a
20-byte program, and pay it with the output `OP_1 <20 bytes>`: an output **anyone can spend**.

The type of a P2SH address is now 31. No witness version may be above 16, so a segwit library refuses the address. A P2PKH
address (type 0) is refused too: version 0 has to use plain bech32 and this form is bech32m.

P2SH addresses that were written with type 1 are still read, as the same P2SH destination, and are never written again.
Anyone who gave out or received one should take care that it is not passed to software that treats it as a segwit address,
and may ask `validateaddress` for the current form.

Anyone writing software for these addresses must **not** use a segwit address library for them: decode the string as bech32m with
the hrp above, take the first value as the type in the table, and regroup the rest from 5 bits to 8 (no padding allowed).
