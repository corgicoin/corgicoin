// Run with:  node --experimental-global-webcrypto --test contrib/webwallet/tests/
// (Node 18 needs the flag for crypto.subtle; Node 19 and later have it.)
import test from "node:test";
import assert from "node:assert/strict";
import { validateMnemonicChecksum, hash160, toHex } from "../wallet.js";
import { parseTransaction, verifiedValue, serialize, p2pkhScript, txid } from "../tx.js";

const ABANDON12 = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about";
const ABANDON24 = Array(23).fill("abandon").concat(["art"]).join(" ");

test("a valid phrase passes the checksum", async () => {
  assert.equal(await validateMnemonicChecksum(ABANDON12), true);
  assert.equal(await validateMnemonicChecksum(ABANDON24), true);
});

test("a phrase of valid words with a wrong one fails the checksum", async () => {
  assert.equal(await validateMnemonicChecksum(Array(12).fill("abandon").join(" ")), false);
  assert.equal(await validateMnemonicChecksum(ABANDON12.replace("about", "ability")), false);
  assert.equal(await validateMnemonicChecksum(ABANDON12.replace("abandon", "zoo")), false);
});

test("wrong lengths and unknown words fail", async () => {
  assert.equal(await validateMnemonicChecksum("abandon abandon"), false);
  assert.equal(await validateMnemonicChecksum(ABANDON12.replace("about", "notaword")), false);
  assert.equal(await validateMnemonicChecksum(""), false);
});

async function sampleTx(values) {
  const script = p2pkhScript(await hash160(new Uint8Array(33).fill(2)));
  const tx = {
    version: 1,
    vin: [{ txid: "11".repeat(32), vout: 0, script: new Uint8Array([1, 2, 3]) }],
    vout: values.map((v) => ({ value: v, script })),
    locktime: 0,
  };
  const raw = serialize(tx);
  return { hex: toHex(raw), id: await txid(raw), script };
}

test("the value comes from the transaction, and the transaction must be the one named", async () => {
  const { hex, id, script } = await sampleTx([150000000000n, 5n]);
  assert.equal(await verifiedValue(hex, { txid: id, vout: 0 }, script), 150000000000n);
  assert.equal(await verifiedValue(hex, { txid: id, vout: 1 }, script), 5n);
  // a server that sends some other transaction under this id
  const other = await sampleTx([1n]);
  await assert.rejects(verifiedValue(other.hex, { txid: id, vout: 0 }, script), /not /);
  // an output that is not there
  await assert.rejects(verifiedValue(hex, { txid: id, vout: 2 }, script), /no output/);
  // an output that pays another address
  await assert.rejects(verifiedValue(hex, { txid: id, vout: 0 }, p2pkhScript(new Uint8Array(20).fill(7))), /does not pay/);
});

test("bytes that are not exactly one transaction are refused", async () => {
  const { hex } = await sampleTx([10n]);
  await assert.rejects(parseTransaction(hex + "00"), /exactly one/);
  await assert.rejects(parseTransaction(hex.slice(0, -10)), /./);
  await assert.rejects(parseTransaction("zz"), /not hex/);
  await assert.rejects(parseTransaction(""), /not hex/);
  const parsed = await parseTransaction(hex);
  assert.equal(parsed.outputs.length, 1);
  assert.equal(parsed.outputs[0].value, 10n);
});
