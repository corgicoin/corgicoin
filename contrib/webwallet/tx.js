// CorgiCoin legacy (pre-SegWit) P2PKH transaction building and signing.
// Runs entirely in the browser; private keys never leave the page.
// Mirrors the daemon's CTransaction: nVersion(4 LE) | vin | vout | nLockTime(4 LE).

import * as secp from "./vendor/noble-secp256k1.js";
import { NETWORKS, base58checkDecode, concat, sha256d, hash160, toHex, fromHex } from "./wallet.js";

export const COIN = 100000000n;                 // satoshis per CORG
const MIN_TX_FEE = COIN;                         // 1 CORG per kB (matches the daemon)
const DUST = COIN;                               // outputs < 1 CORG draw an extra fee; treat as dust for change
const SIGHASH_ALL = 1;

// ---- byte helpers ----------------------------------------------------------
function le32(n) { return new Uint8Array([n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255]); }
function le64(v) {                               // BigInt satoshis -> 8-byte little-endian
  const out = new Uint8Array(8);
  let x = BigInt(v);
  for (let i = 0; i < 8; i++) { out[i] = Number(x & 0xffn); x >>= 8n; }
  return out;
}
function varint(n) {
  n = Number(n);
  if (n < 0xfd) return new Uint8Array([n]);
  if (n <= 0xffff) return new Uint8Array([0xfd, n & 255, (n >>> 8) & 255]);
  return concat(new Uint8Array([0xfe]), le32(n));
}
function pushData(data) {                         // scriptSig pushes (sig ~72B, pubkey 33B — both < 76)
  if (data.length >= 76) throw new Error("pushData: unexpected large push");
  return concat(new Uint8Array([data.length]), data);
}
const reverse = (u8) => u8.slice().reverse();

// ---- scripts ---------------------------------------------------------------
// Standard P2PKH: OP_DUP OP_HASH160 <20> OP_EQUALVERIFY OP_CHECKSIG
function p2pkhScript(hash160Bytes) {
  return concat(new Uint8Array([0x76, 0xa9, 0x14]), hash160Bytes, new Uint8Array([0x88, 0xac]));
}
// Resolve a recipient address to its P2PKH scriptPubKey, validating the
// version byte against this network (reject cross-network / script addresses).
export async function scriptForAddress(addr, net) {
  const { version, hash } = await base58checkDecode(addr);
  const p = NETWORKS[net];
  if (version !== p.pubkey) {
    if (version === p.script) throw new Error("P2SH addresses aren't supported for sending yet");
    throw new Error("address is not a valid " + net + " CorgiCoin address");
  }
  if (hash.length !== 20) throw new Error("bad address hash length");
  return p2pkhScript(hash);
}

// ---- serialization ---------------------------------------------------------
// tx = { version, vin:[{txid, vout, script(Uint8Array)}], vout:[{value(BigInt), script}], locktime }
function serialize(tx) {
  const parts = [le32(tx.version)];
  parts.push(varint(tx.vin.length));
  for (const i of tx.vin) {
    parts.push(reverse(fromHex(i.txid)));        // prevout hash, internal byte order
    parts.push(le32(i.vout));
    const s = i.script || new Uint8Array(0);
    parts.push(varint(s.length), s);
    parts.push(le32(0xffffffff));                // sequence
  }
  parts.push(varint(tx.vout.length));
  for (const o of tx.vout) {
    parts.push(le64(o.value), varint(o.script.length), o.script);
  }
  parts.push(le32(tx.locktime));
  return concat(...parts);
}

async function txid(serialized) { return toHex(reverse(await sha256d(serialized))); }

// ---- reading a transaction ------------------------------------------------------------------------------
// Needed to check what the explorer says about an unspent output. A legacy signature does not commit to the value of
// the output it spends, so a wallet that signs with a value the server made up (lower than the real one) pays the
// difference to the miners as fee. The wallet fetches the transaction that created each coin, checks that it hashes to
// the id the server gave, and takes the value from it.
function readVarint(b, pos) {
  const f = b[pos];
  if (f < 0xfd) return [f, pos + 1];
  const size = f === 0xfd ? 2 : f === 0xfe ? 4 : 8;
  if (size === 8) throw new Error("transaction: length too large");
  if (pos + 1 + size > b.length) throw new Error("transaction: truncated");
  let n = 0;
  for (let i = size - 1; i >= 0; i--) n = n * 256 + b[pos + 1 + i];
  return [n, pos + 1 + size];
}

// Outputs of a serialized legacy transaction (hex) and its txid. Throws unless the bytes are exactly one transaction.
export async function parseTransaction(hex) {
  if (!/^([0-9a-fA-F]{2})+$/.test(hex)) throw new Error("transaction: not hex");
  const b = fromHex(hex);
  let pos = 4;                                           // version
  let n;
  [n, pos] = readVarint(b, pos);
  for (let i = 0; i < n; i++) {
    pos += 36;                                           // prevout hash and index
    let len; [len, pos] = readVarint(b, pos);
    pos += len + 4;                                      // scriptSig, sequence
  }
  let nOut; [nOut, pos] = readVarint(b, pos);
  const outputs = [];
  for (let i = 0; i < nOut; i++) {
    if (pos + 8 > b.length) throw new Error("transaction: truncated");
    let value = 0n;
    for (let j = 7; j >= 0; j--) value = (value << 8n) | BigInt(b[pos + j]);
    pos += 8;
    let len; [len, pos] = readVarint(b, pos);
    if (pos + len > b.length) throw new Error("transaction: truncated");
    outputs.push({ value, script: b.slice(pos, pos + len) });
    pos += len;
  }
  pos += 4;                                              // lock time
  if (pos !== b.length) throw new Error("transaction: not exactly one transaction");
  return { txid: await txid(b), outputs };
}

// The real value of an unspent output as the server described it: { txid, vout, value }. rawHex is the transaction the
// server says created it; scriptExpected the P2PKH script of the address it was found for. Returns the value (BigInt)
// read from the transaction, or throws if the transaction is not the one named, has no such output, or pays another script.
export async function verifiedValue(rawHex, utxo, scriptExpected) {
  const tx = await parseTransaction(rawHex);
  if (tx.txid !== utxo.txid) throw new Error("the transaction the server sent is not " + utxo.txid);
  const out = tx.outputs[utxo.vout];
  if (!out) throw new Error("the transaction has no output " + utxo.vout);
  if (toHex(out.script) !== toHex(scriptExpected)) throw new Error("the output does not pay this address");
  return out.value;
}

export { serialize, p2pkhScript, txid };

// ---- coin selection ---------------------------------------------------------
// Largest-first: fewest inputs, simplest; fine for a browser wallet.
function selectCoins(utxos, target) {
  const sorted = [...utxos].sort((a, b) => (a.value < b.value ? 1 : a.value > b.value ? -1 : 0));
  const picked = [];
  let sum = 0n;
  for (const u of sorted) { picked.push(u); sum += u.value; if (sum >= target) break; }
  return { picked, sum };
}

// Fee required by the daemon: 1 CORG per started kB, + 1 CORG per sub-1-CORG output.
function requiredFee(nBytes, vout) {
  let fee = (1n + BigInt(Math.floor(nBytes / 1000))) * MIN_TX_FEE;
  for (const o of vout) if (o.value < DUST) fee += MIN_TX_FEE;
  return fee;
}

// ---- build + sign -----------------------------------------------------------
// accounts: [{ address, privKey, pubKey, utxos:[{txid, vout, value(sats)}] }]
// Returns { hex, txid, fee, change, inputs } ready for /api/broadcast.
export async function buildAndSign({ accounts, toAddr, amountSats, net, changeAddr }) {
  const amount = BigInt(amountSats);
  if (amount <= 0n) throw new Error("amount must be positive");
  const outScript = await scriptForAddress(toAddr, net);

  // Flatten spendable UTXOs, each tagged with the key that can sign it.
  const spendable = [];
  for (const a of accounts) {
    for (const u of (a.utxos || [])) {
      spendable.push({ txid: u.txid, vout: u.vout, value: BigInt(u.value), owner: a });
    }
  }
  if (!spendable.length) throw new Error("no spendable coins found");

  // Pick inputs, then recompute the fee from the real signed size and, if the
  // larger size pulled in another fee tier, select again (at most a few passes).
  let picked, sum, fee = MIN_TX_FEE;
  for (let pass = 0; pass < 4; pass++) {
    ({ picked, sum } = selectCoins(spendable, amount + fee));
    if (sum < amount + fee) throw new Error("insufficient funds (need " + fmt(amount + fee) + " CORG)");
    const change = sum - amount - fee;
    const vout = [{ value: amount, script: outScript }];
    if (change >= DUST) vout.push({ value: change, script: p2pkhScript((await base58checkDecode(changeAddr)).hash) });
    // ~148 bytes per P2PKH input (incl. ~107-byte scriptSig) + outputs + overhead.
    const estBytes = 10 + picked.length * 148 + vout.length * 34;
    const need = requiredFee(estBytes, vout);
    if (need <= fee) break;
    fee = need;                                  // retry with the higher fee tier
  }

  const change = sum - amount - fee;
  if (change < 0n) throw new Error("fee exceeds inputs");
  const vout = [{ value: amount, script: outScript }];
  const changeHash = (await base58checkDecode(changeAddr)).hash;
  if (change >= DUST) vout.push({ value: change, script: p2pkhScript(changeHash) });
  // (sub-DUST change is dropped into the fee, matching the daemon's behaviour)

  const vin = picked.map((p) => ({ txid: p.txid, vout: p.vout, script: new Uint8Array(0), _owner: p.owner }));
  const tx = { version: 1, vin, vout, locktime: 0 };

  // Legacy SIGHASH_ALL: for each input, serialize the tx with only that input's
  // script set to the prevout's P2PKH script, append the 4-byte hashtype, hash.
  for (let i = 0; i < vin.length; i++) {
    const owner = vin[i]._owner;
    const prevScript = p2pkhScript(await hash160(owner.pubKey));
    const copy = {
      version: tx.version, locktime: tx.locktime, vout: tx.vout,
      vin: tx.vin.map((v, j) => ({ txid: v.txid, vout: v.vout, script: j === i ? prevScript : new Uint8Array(0) })),
    };
    const preimage = concat(serialize(copy), le32(SIGHASH_ALL));
    const sighash = await sha256d(preimage);
    const der = await secp.sign(sighash, owner.privKey);   // low-s canonical DER
    const sig = concat(der, new Uint8Array([SIGHASH_ALL]));
    vin[i].script = concat(pushData(sig), pushData(owner.pubKey));
  }

  const raw = serialize({ version: tx.version, vin, vout, locktime: tx.locktime });
  return {
    hex: toHex(raw),
    txid: await txid(raw),
    fee, change,
    inputs: picked.length,
    amount,
  };
}

// CORG formatting for messages (8 dp, BigInt sats).
export function fmt(sats) {
  const neg = sats < 0n; let s = (neg ? -sats : sats).toString().padStart(9, "0");
  const whole = s.slice(0, -8), frac = s.slice(-8).replace(/0+$/, "");
  return (neg ? "-" : "") + whole + (frac ? "." + frac : "");
}
