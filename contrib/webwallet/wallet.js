// CorgiCoin non-custodial web wallet — key derivation and address encoding.
// All crypto runs client-side; private keys never leave the browser.
// BIP32/39/44, mirroring the daemon's HD derivation (m/44'/99'/0'/0/i).

import * as secp from "./vendor/noble-secp256k1.js";
import { ripemd160 } from "./vendor/ripemd160.mjs";
import { WORDLIST } from "./wordlist.js";

// ---- CorgiCoin network parameters -----------------------------------------
export const NETWORKS = {
  main: { pubkey: 28, script: 22, wif: 156, hrp: "corg" },      // CorgiCoin addresses start with C
  test: { pubkey: 113, script: 196, wif: 241, hrp: "tcorg" },
};
const HD_COIN_TYPE = 99;        // must match the daemon's HD_COIN_TYPE
// Use '+' (not '|') to set the hardened bit: bitwise OR yields a *signed*
// int32, making the index negative and silently un-hardening derivation.
const HARDENED = 0x80000000;
const hard = (n) => n + HARDENED;
const SECP_N = BigInt("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141");

// ---- byte helpers ----------------------------------------------------------
const enc = new TextEncoder();
const toHex = (u8) => [...u8].map((b) => b.toString(16).padStart(2, "0")).join("");
const fromHex = (h) => new Uint8Array(h.match(/.{1,2}/g).map((x) => parseInt(x, 16)));
function concat(...arrs) {
  const n = arrs.reduce((s, a) => s + a.length, 0);
  const out = new Uint8Array(n);
  let o = 0;
  for (const a of arrs) { out.set(a, o); o += a.length; }
  return out;
}
function be32(n) { return new Uint8Array([(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255]); }
function bnTo32(bn) {
  let h = bn.toString(16).padStart(64, "0");
  return fromHex(h);
}

// ---- hashes (SubtleCrypto for sha2/hmac/pbkdf2; noble for ripemd160) --------
async function sha256(data) { return new Uint8Array(await crypto.subtle.digest("SHA-256", data)); }
async function sha256d(data) { return sha256(await sha256(data)); }
async function hash160(data) { return ripemd160(await sha256(data)); }
async function hmacSha512(key, data) {
  const k = await crypto.subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-512" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", k, data));
}
async function pbkdf2Sha512(pw, salt, iters, len) {
  const k = await crypto.subtle.importKey("raw", pw, "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-512", salt, iterations: iters }, k, len * 8);
  return new Uint8Array(bits);
}

// ---- base58check -----------------------------------------------------------
const B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
function base58encode(bytes) {
  let x = BigInt("0x" + (toHex(bytes) || "0"));
  let out = "";
  while (x > 0n) { out = B58[Number(x % 58n)] + out; x /= 58n; }
  for (const b of bytes) { if (b === 0) out = "1" + out; else break; }
  return out;
}
async function base58check(version, payload) {
  const data = concat(new Uint8Array([version]), payload);
  const chk = (await sha256d(data)).slice(0, 4);
  return base58encode(concat(data, chk));
}

// ---- BIP39 -----------------------------------------------------------------
export function validateMnemonicWords(mnemonic) {
  const words = mnemonic.trim().split(/\s+/);
  if (![12, 15, 18, 21, 24].includes(words.length)) return false;
  return words.every((w) => WORDLIST.includes(w));
}
export async function generateMnemonic(bits = 128) {
  const ent = crypto.getRandomValues(new Uint8Array(bits / 8));
  const hash = await sha256(ent);
  const csBits = bits / 32;
  const bitsArr = [];
  for (const b of ent) for (let i = 7; i >= 0; i--) bitsArr.push((b >> i) & 1);
  for (let i = 0; i < csBits; i++) bitsArr.push((hash[Math.floor(i / 8)] >> (7 - (i % 8))) & 1);
  const words = [];
  for (let i = 0; i < bitsArr.length; i += 11) {
    let idx = 0;
    for (let j = 0; j < 11; j++) idx = (idx << 1) | bitsArr[i + j];
    words.push(WORDLIST[idx]);
  }
  return words.join(" ");
}
async function mnemonicToSeed(mnemonic, passphrase = "") {
  return pbkdf2Sha512(enc.encode(mnemonic.normalize("NFKD")),
    enc.encode(("mnemonic" + passphrase).normalize("NFKD")), 2048, 64);
}

// ---- BIP32 (private derivation) --------------------------------------------
async function masterFromSeed(seed) {
  const I = await hmacSha512(enc.encode("Bitcoin seed"), seed);
  return { key: I.slice(0, 32), chainCode: I.slice(32) };
}
async function ckdPriv(node, index) {
  const hardened = index >= HARDENED;
  const kpar = BigInt("0x" + toHex(node.key));
  let data;
  if (hardened) data = concat(new Uint8Array([0]), node.key, be32(index));
  else data = concat(secp.getPublicKey(node.key, true), be32(index));
  const I = await hmacSha512(node.chainCode, data);
  const il = BigInt("0x" + toHex(I.slice(0, 32)));
  const childKey = (il + kpar) % SECP_N;
  return { key: bnTo32(childKey), chainCode: I.slice(32) };
}
async function derivePath(seed, path) {
  let node = await masterFromSeed(seed);
  for (const p of path) node = await ckdPriv(node, p);
  return node;
}

// ---- Wallet ----------------------------------------------------------------
// Derive the external-chain address at index i for the given network.
export async function deriveAddress(seed, i, net = "main") {
  const node = await derivePath(seed, [hard(44), hard(HD_COIN_TYPE), hard(0), 0, i]);
  const pub = secp.getPublicKey(node.key, true); // 33-byte compressed
  const addr = await base58check(NETWORKS[net].pubkey, await hash160(pub));
  return { index: i, address: addr, privKey: node.key, pubKey: pub };
}

// Build a watch set of the first `count` external addresses from a mnemonic.
export async function openWallet(mnemonic, net = "main", count = 20, passphrase = "") {
  const seed = await mnemonicToSeed(mnemonic, passphrase);
  const accounts = [];
  for (let i = 0; i < count; i++) accounts.push(await deriveAddress(seed, i, net));
  return { seed, net, accounts };
}

// ---- Self-test against official vectors (run on load) ----------------------
export async function selfTest() {
  const MN = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about";
  // BIP39: abandon...about with "TREZOR" passphrase -> the official seed vector
  const seedTrezor = await mnemonicToSeed(MN, "TREZOR");
  const okSeed = toHex(seedTrezor) ===
    "c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04";
  // ripemd160("") known vector
  const okRipemd = toHex(ripemd160(new Uint8Array(0))) === "9c1185a5c5e9fc54612808977ee8f548b2258d31";
  // CorgiCoin testnet address for that mnemonic (EMPTY passphrase, as the
  // daemon uses), index 0 — must match the daemon's HD derivation.
  const seed = await mnemonicToSeed(MN, "");
  const a0 = await deriveAddress(seed, 0, "test");
  const okAddr = a0.address === "nZBJuTqg4EkMbntazHGaTPuqpiHnzQe7Lz";
  return { okSeed, okRipemd, okAddr, addr0test: a0.address };
}

export { toHex, fromHex };
