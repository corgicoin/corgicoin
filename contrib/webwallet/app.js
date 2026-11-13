// CorgiCoin web wallet: the page logic. (It used to be an inline script in index.html; it is a file so the page can
// forbid inline scripts with a Content-Security-Policy, which is what keeps a recovery phrase typed into this page
// from being read by script that was injected into it.)
import { openWallet, generateMnemonic, validateMnemonicWords, validateMnemonicChecksum, selfTest,
         deriveAddress, hash160 } from "./wallet.js";
import { buildAndSign, fmt as fmtSats, COIN as COIN_BIG, verifiedValue, p2pkhScript } from "./tx.js";

const $ = (id) => document.getElementById(id);
const COIN = 100000000;
const fmt = (sat) => (sat / COIN).toLocaleString(undefined, { maximumFractionDigits: 8 });

// How many unused addresses in a row end the scan (BIP44), and the most addresses ever scanned.
const GAP_LIMIT = 20;
const MAX_ADDRESSES = 1000;

// Parse a CORG decimal string into BigInt satoshis (exact, no float rounding).
function parseCorg(str) {
  const s = (str || "").trim();
  if (!/^\d+(\.\d{1,8})?$/.test(s)) throw new Error("Enter an amount like 12.5 (up to 8 decimals).");
  const [whole, frac = ""] = s.split(".");
  return BigInt(whole) * COIN_BIG + BigInt(frac.padEnd(8, "0"));
}

let wallet = null;
let pending = null;   // the built+signed tx awaiting broadcast

// A phrase typed into a page that came over plain HTTP can be read by anyone on the path between you and the server,
// and the page itself can be changed on the way. Local use (the explorer on this machine) is the exception.
if (location.protocol !== "https:" && !["localhost", "127.0.0.1", "[::1]"].includes(location.hostname)) {
  const w = $("httpWarning");
  if (w) w.classList.remove("hidden");
}

// Crypto self-test — proves the derivation matches the daemon before use.
selfTest().then((r) => {
  const el = $("selftest");
  if (r.okSeed && r.okRipemd && r.okAddr) { el.className = "pill ok"; el.textContent = "crypto verified ✓"; }
  else { el.className = "pill err"; el.textContent = "crypto self-test FAILED — do not use"; }
}).catch(() => { $("selftest").className = "pill err"; $("selftest").textContent = "crypto error"; });

$("genBtn").onclick = async () => {
  $("mnemonic").value = await generateMnemonic(128);
  $("openMsg").textContent = "New phrase generated. WRITE IT DOWN — it is the only backup. Then click Open Wallet.";
};

$("openBtn").onclick = async () => {
  const mn = $("mnemonic").value.trim().replace(/\s+/g, " ");
  if (!validateMnemonicWords(mn)) { $("openMsg").textContent = "That doesn't look like a valid recovery phrase."; return; }
  // The checksum catches a mistyped word that is still a word of the list: without this check it opens a different,
  // empty wallet, and shows a receive address for it.
  if (!(await validateMnemonicChecksum(mn))) {
    $("openMsg").textContent = "The words are valid but the phrase is not: one of them is wrong or out of place (the checksum fails). Check it against your backup.";
    return;
  }
  $("openMsg").textContent = "Deriving addresses…";
  const net = $("network").value;
  const count = Math.max(1, Math.min(100, parseInt($("count").value) || 20));
  wallet = await openWallet(mn, net, count);
  $("mnemonic").value = ""; // don't leave the phrase on screen
  $("openCard").classList.add("hidden");
  $("walletView").classList.remove("hidden");
  await refresh();
};

async function fetchAddr(addr) {
  try {
    const r = await fetch("/api/address/" + encodeURIComponent(addr));
    if (!r.ok) return { balance: 0, received: 0 };
    return await r.json();
  } catch { return { balance: 0, received: 0 }; }
}

function addRow(body, a, bal, recv) {
  const tr = document.createElement("tr");
  const cells = [[String(a.index), ""], [a.address, "mono"], [fmt(bal), "num"], [fmt(recv), "num"]];
  for (const [text, cls] of cells) {
    const td = document.createElement("td");
    td.textContent = text;                      // textContent, never innerHTML: nothing here is trusted markup
    if (cls) td.className = cls;
    tr.appendChild(td);
  }
  body.appendChild(tr);
}

async function refresh() {
  if (!wallet) return;
  $("totalBal").textContent = "…";
  const body = $("addrBody");
  body.textContent = "";
  let total = 0;
  // Scan until GAP_LIMIT addresses in a row have never received anything (and at least the number asked for): a phrase
  // used in the desktop wallet beyond the first few addresses has coins further along.
  let scanned = 0, lastUsed = -1;
  while (true) {
    if (scanned >= wallet.accounts.length) {
      if (wallet.accounts.length >= MAX_ADDRESSES || scanned - 1 - lastUsed >= GAP_LIMIT) break;
      for (let i = 0; i < GAP_LIMIT && wallet.accounts.length < MAX_ADDRESSES; i++)
        wallet.accounts.push(await deriveAddress(wallet.seed, wallet.accounts.length, wallet.net));
    }
    const a = wallet.accounts[scanned];
    const info = await fetchAddr(a.address);
    const bal = info.balance || 0, recv = info.received || 0;
    a._received = recv;
    total += bal;
    if (recv > 0) lastUsed = scanned;
    addRow(body, a, bal, recv);
    scanned++;
    if (scanned >= wallet.accounts.length && scanned - 1 - lastUsed >= GAP_LIMIT) break;
  }
  const firstUnused = wallet.accounts.find((a) => a._received === 0);
  $("totalBal").textContent = fmt(total);
  $("balNote").textContent = `across ${wallet.accounts.length} scanned ${wallet.net} addresses`;
  $("recvAddr").textContent = (firstUnused || wallet.accounts[0]).address;
}

$("refreshBtn").onclick = refresh;
$("receiveBtn").onclick = () => $("receiveCard").classList.toggle("hidden");
$("sendBtn").onclick = () => { $("sendCard").classList.toggle("hidden"); $("reviewBox").classList.add("hidden"); };
$("lockBtn").onclick = () => { wallet = null; location.reload(); };

// Fetch the unspent outputs of every scanned address, and take each one's value from the transaction that made it.
// The server's number is not trusted: a legacy signature does not commit to the value being spent, so a wallet told a
// smaller value than the real one would build a transaction that pays the difference to the miners as fee.
async function loadUtxos() {
  let total = 0n;
  const raw = new Map();                         // txid -> hex, fetched once
  let refused = 0;
  for (const a of wallet.accounts) {
    a.utxos = [];
    let list = [];
    try {
      const r = await fetch("/api/address/" + encodeURIComponent(a.address) + "/utxos");
      if (r.ok) { const j = await r.json(); list = j.utxos || []; }
    } catch {}
    const script = p2pkhScript(await hash160(a.pubKey));
    for (const u of list) {
      try {
        if (!raw.has(u.txid)) {
          const r = await fetch("/api/rawtx/" + encodeURIComponent(u.txid));
          if (!r.ok) throw new Error("no transaction from the server");
          raw.set(u.txid, (await r.json()).hex);
        }
        const value = await verifiedValue(raw.get(u.txid), u, script);
        a.utxos.push({ txid: u.txid, vout: u.vout, value: value.toString() });
        total += value;
      } catch (e) { refused++; }
    }
  }
  if (refused) $("sendMsg").textContent = `⚠ ${refused} coin(s) were left out because the server's description of them could not be verified.`;
  return total;
}

function changeAddress() {
  // Reuse the first scanned address with no received history as change, else index 0.
  const unused = wallet.accounts.find((a) => a._received === 0);
  return (unused || wallet.accounts[0]).address;
}

$("maxBtn").onclick = async () => {
  $("sendMsg").textContent = "Finding spendable coins…";
  try {
    const total = await loadUtxos();
    // Leave the typical single-tier fee; buildAndSign re-checks and will error if short.
    const max = total > COIN_BIG ? total - COIN_BIG : 0n;
    $("amount").value = fmtSats(max);
    $("sendMsg").textContent = "Max spendable (after ~1 CORG fee). Review to confirm the exact fee.";
  } catch (e) { $("sendMsg").textContent = e.message; }
};

$("reviewBtn").onclick = async () => {
  $("sendMsg").textContent = "";
  $("reviewBox").classList.add("hidden");
  $("bcMsg").textContent = "";
  pending = null;
  const toAddr = $("toAddr").value.trim();
  let amountSats;
  try { amountSats = parseCorg($("amount").value); } catch (e) { $("sendMsg").textContent = e.message; return; }
  if (!toAddr) { $("sendMsg").textContent = "Enter a recipient address."; return; }
  $("sendMsg").textContent = "Building & signing in your browser…";
  try {
    await loadUtxos();
    pending = await buildAndSign({
      accounts: wallet.accounts, toAddr, amountSats, net: wallet.net, changeAddr: changeAddress(),
    });
    $("rvAmount").textContent = fmtSats(pending.amount) + " CORG";
    $("rvTo").textContent = toAddr;
    $("rvFee").textContent = fmtSats(pending.fee) + " CORG";
    $("rvChange").textContent = fmtSats(pending.change) + " CORG";
    $("rvInputs").textContent = pending.inputs;
    $("reviewBox").classList.remove("hidden");
    $("sendMsg").textContent = "Signed locally. Review, then broadcast.";
  } catch (e) { $("sendMsg").textContent = "⚠ " + e.message; }
};

$("cancelBtn").onclick = () => { pending = null; $("reviewBox").classList.add("hidden"); $("sendMsg").textContent = "Cancelled."; };

$("confirmBtn").onclick = async () => {
  if (!pending) return;
  $("confirmBtn").disabled = true;
  $("bcMsg").textContent = "Broadcasting…";
  try {
    const r = await fetch("/api/broadcast", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hex: pending.hex }),
    });
    const j = await r.json();
    if (j.txid && /^[0-9a-f]{64}$/.test(j.txid)) {
      // built from the checked txid, as text and a link: the server's reply is not markup
      const msg = $("bcMsg");
      msg.textContent = "✓ Sent — txid ";
      const link = document.createElement("a");
      link.href = "/tx/" + j.txid;
      link.textContent = j.txid;
      msg.appendChild(link);
      $("toAddr").value = ""; $("amount").value = ""; pending = null;
      $("reviewBox").classList.add("hidden");
      setTimeout(refresh, 800);
    } else {
      $("bcMsg").textContent = "✗ Rejected: " + (j.error || "unknown error");
    }
  } catch (e) { $("bcMsg").textContent = "✗ Network error: " + e.message; }
  finally { $("confirmBtn").disabled = false; }
};
