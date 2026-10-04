#!/usr/bin/env python3
"""
CorgiCoin block explorer.

Single-file explorer in the spirit of contrib/bridge/bridge.py: an indexer
thread walks the chain over RPC into SQLite (this codebase has no address
index RPC, so the explorer builds its own), and a small Flask UI serves
block / transaction / address pages plus a burns page that decodes bridge
burn payloads via the decodeburn RPC — making every cross-chain burn
publicly auditable.

Usage:
    pip install -r requirements.txt
    ./explorer.py [--conf ~/.corgicoin/corgicoin.conf] [--port 8080]

The corgicoin.conf is read for rpcuser / rpcpassword / rpcport.
"""

from __future__ import annotations

import argparse
import logging
import sqlite3
import threading
import time
from pathlib import Path

import requests
from flask import Flask, abort, jsonify, redirect, render_template_string, request, url_for

log = logging.getLogger("explorer")

COIN = 100_000_000
POLL_SECONDS = 10


# ----------------------------------------------------------------------------
# RPC


class CorgiRPC:
    """Minimal JSON-RPC client. corgicoind returns HTTP 500 for application
    errors (Bitcoin-RPC convention), so parse the body before raising."""

    def __init__(self, url: str, user: str, password: str):
        self.url = url
        self._id = 0
        # Keep-alive session: the indexer makes ~100k calls on first sync,
        # and one TCP connection per call exhausts ephemeral ports
        self.session = requests.Session()
        self.session.auth = (user, password)

    def call(self, method: str, *params):
        self._id += 1
        payload = {"id": self._id, "method": method, "params": list(params)}
        resp = self.session.post(self.url, json=payload, timeout=30)
        body = resp.json()
        if body.get("error"):
            raise RuntimeError(f"RPC {method}: {body['error']}")
        return body["result"]


def load_rpc_config(conf_path: Path) -> dict:
    cfg = {"rpcport": "62555", "rpcconnect": "127.0.0.1"}
    for line in conf_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    if "rpcuser" not in cfg or "rpcpassword" not in cfg:
        raise SystemExit(f"rpcuser/rpcpassword not found in {conf_path}")
    return cfg


# ----------------------------------------------------------------------------
# Database

SCHEMA = """
CREATE TABLE IF NOT EXISTS blocks (
    height INTEGER PRIMARY KEY,
    hash TEXT NOT NULL UNIQUE,
    time INTEGER NOT NULL,
    bits TEXT NOT NULL,
    difficulty REAL NOT NULL,
    size INTEGER NOT NULL,
    txcount INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS txs (
    txid TEXT PRIMARY KEY,
    height INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    time INTEGER NOT NULL,
    is_coinbase INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS txs_height ON txs(height);
CREATE TABLE IF NOT EXISTS outputs (
    txid TEXT NOT NULL,
    n INTEGER NOT NULL,
    address TEXT,
    value INTEGER NOT NULL,
    spent_txid TEXT,
    PRIMARY KEY (txid, n)
);
CREATE INDEX IF NOT EXISTS outputs_address ON outputs(address);
CREATE TABLE IF NOT EXISTS burns (
    txid TEXT NOT NULL,
    n INTEGER NOT NULL,
    height INTEGER NOT NULL,
    value INTEGER NOT NULL,
    script_hex TEXT NOT NULL,
    partner TEXT,
    sol_address TEXT,
    PRIMARY KEY (txid, n)
);
CREATE INDEX IF NOT EXISTS burns_height ON burns(height);
"""


def open_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db


# ----------------------------------------------------------------------------
# Indexer


class Indexer(threading.Thread):
    def __init__(self, rpc: CorgiRPC, db_path: Path):
        super().__init__(daemon=True, name="indexer")
        self.rpc = rpc
        self.db_path = db_path

    def run(self):
        db = open_db(self.db_path)
        while True:
            try:
                self.sync(db)
            except Exception:
                log.exception("sync pass failed; retrying in %ss", POLL_SECONDS)
            time.sleep(POLL_SECONDS)

    def sync(self, db: sqlite3.Connection):
        tip = self.rpc.call("getblockcount")
        row = db.execute("SELECT height, hash FROM blocks ORDER BY height DESC LIMIT 1").fetchone()
        next_height = 0 if row is None else row["height"] + 1

        # Reorg check: rewind while our stored tip is no longer on the chain
        while row is not None and self.rpc.call("getblockhash", row["height"]) != row["hash"]:
            log.warning("reorg: unwinding block %d", row["height"])
            self.rewind_block(db, row["height"])
            row = db.execute("SELECT height, hash FROM blocks ORDER BY height DESC LIMIT 1").fetchone()
            next_height = 0 if row is None else row["height"] + 1

        for h in range(next_height, tip + 1):
            self.index_block(db, h)
            if h % 500 == 0 or h == tip:
                log.info("indexed height %d / %d", h, tip)

    def rewind_block(self, db: sqlite3.Connection, height: int):
        txids = [r["txid"] for r in db.execute("SELECT txid FROM txs WHERE height=?", (height,))]
        for txid in txids:
            db.execute("UPDATE outputs SET spent_txid=NULL WHERE spent_txid=?", (txid,))
            db.execute("DELETE FROM outputs WHERE txid=?", (txid,))
            db.execute("DELETE FROM burns WHERE txid=?", (txid,))
        db.execute("DELETE FROM txs WHERE height=?", (height,))
        db.execute("DELETE FROM blocks WHERE height=?", (height,))
        db.commit()

    def index_block(self, db: sqlite3.Connection, height: int):
        bhash = self.rpc.call("getblockhash", height)
        blk = self.rpc.call("getblock", bhash)
        db.execute(
            "INSERT OR REPLACE INTO blocks VALUES (?,?,?,?,?,?,?)",
            (height, blk["hash"], blk["time"], blk["bits"], blk["difficulty"],
             blk["size"], len(blk["tx"])),
        )
        for idx, txid in enumerate(blk["tx"]):
            try:
                tx = self.rpc.call("getrawtransaction", txid, 1)
            except RuntimeError:
                # The genesis coinbase is not in the daemon's tx index;
                # record the tx with no outputs (it is unspendable anyway)
                log.warning("tx %s at height %d not in tx index; indexing without outputs", txid, height)
                db.execute("INSERT OR REPLACE INTO txs VALUES (?,?,?,?,?)",
                           (txid, height, idx, blk["time"], 1))
                continue
            is_coinbase = 1 if tx["vin"] and "coinbase" in tx["vin"][0] else 0
            db.execute(
                "INSERT OR REPLACE INTO txs VALUES (?,?,?,?,?)",
                (txid, height, idx, tx.get("time", blk["time"]), is_coinbase),
            )
            if not is_coinbase:
                for vin in tx["vin"]:
                    db.execute(
                        "UPDATE outputs SET spent_txid=? WHERE txid=? AND n=?",
                        (txid, vin["txid"], vin["vout"]),
                    )
            for vout in tx["vout"]:
                spk = vout["scriptPubKey"]
                addresses = spk.get("addresses") or [None]
                value = int(round(vout["value"] * COIN))
                db.execute(
                    "INSERT OR REPLACE INTO outputs (txid, n, address, value) VALUES (?,?,?,?)",
                    (txid, vout["n"], addresses[0], value),
                )
                script_hex = spk.get("hex", "")
                if script_hex.startswith("6a"):  # OP_RETURN: a burn output
                    partner = sol_address = None
                    try:
                        decoded = self.rpc.call("decodeburn", script_hex)
                        partner = decoded.get("partner")
                        sol_address = decoded.get("sol_dest_base58")
                    except Exception:
                        pass  # raw/opaque burn (burncoin), or pre-spec payload
                    db.execute(
                        "INSERT OR REPLACE INTO burns VALUES (?,?,?,?,?,?,?)",
                        (txid, vout["n"], height, value, script_hex, partner, sol_address),
                    )
        db.commit()


# ----------------------------------------------------------------------------
# Web UI

BASE = """
<!doctype html>
<title>CorgiCoin Explorer</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/png" href="/corgi.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bungee&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  /* Themed to match corgicoin.co — forest green + Bungee/Inter */
  :root {
    --bg: #1a3d1a; --panel: #214a21; --panel-2: #183618;
    --text: #e8f5e9; --muted: #a9c7ab; --border: #2f5e2f;
    --accent: #4caf50; --lime: #8bc34a; --gold: #e6c34a;
  }
  * { box-sizing: border-box; }
  body {
    font-family: Inter, system-ui, sans-serif; color: var(--text);
    background: var(--bg); max-width: 1000px; margin: 0 auto; padding: 1.5rem 1rem 3rem;
    background-image: radial-gradient(1200px 500px at 70% -10%, #27552733, transparent);
  }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  header { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; margin-bottom: 1.5rem;
           border-bottom: 2px solid var(--border); padding-bottom: 1rem; }
  header h1 { margin: 0; font-size: 1.15rem; }
  header h1 a { font-family: 'Bungee', system-ui, sans-serif; color: var(--text); letter-spacing: .5px;
                display: inline-flex; align-items: center; gap: .5rem; }
  header h1 a img.logo { height: 1.8em; width: auto; }
  nav a { margin-right: .9rem; font-weight: 600; }
  h2 { font-family: 'Bungee', system-ui, sans-serif; font-size: 1.1rem; letter-spacing: .5px;
       color: #fff; margin: 1.4rem 0 .8rem; }
  h3 { font-weight: 700; color: var(--lime); margin: 1.2rem 0 .5rem; font-size: 1rem; }
  table { border-collapse: collapse; width: 100%; overflow-x: auto; display: block; }
  th, td { text-align: left; padding: .45rem .6rem; border-bottom: 1px solid var(--border); font-size: .92rem; }
  th { font-family: 'Bungee', system-ui, sans-serif; font-size: .7rem; letter-spacing: 1px;
       text-transform: uppercase; color: var(--muted); font-weight: 400; }
  tr:hover td { background: #ffffff08; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  code, .mono { font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: .85rem; word-break: break-all; }
  form.search { flex: 1; min-width: 240px; display: flex; gap: .5rem; }
  form.search input[type=text] { flex: 1; padding: .45rem .6rem; border-radius: 6px;
      border: 1px solid var(--border); background: var(--panel-2); color: var(--text); }
  form.search input[type=text]::placeholder { color: var(--muted); }
  form.search input[type=submit] { padding: .45rem 1rem; border: 0; border-radius: 6px;
      background: var(--accent); color: #fff; font-weight: 600; cursor: pointer; }
  form.search input[type=submit]:hover { background: #5cbf60; }
  .cards { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .card { border: 1px solid var(--border); border-radius: 10px; padding: .7rem 1.1rem;
          background: var(--panel); min-width: 140px; }
  .card .v { font-size: 1.2rem; font-weight: 700; color: #fff; margin-top: .15rem; }
  .muted { color: var(--muted); font-size: .85rem; }
</style>
<header>
  <h1><a href="{{ url_for('home') }}"><img class="logo" src="/corgi.png" alt="CorgiCoin">CorgiCoin Explorer</a></h1>
  <nav><a href="{{ url_for('home') }}">Blocks</a><a href="{{ url_for('charts') }}">Charts</a><a href="{{ url_for('burns') }}">Burns</a></nav>
  <form class="search" action="{{ url_for('search') }}">
    <input type="text" name="q" placeholder="height / block hash / txid / address">
    <input type="submit" value="Search">
  </form>
</header>
{% block body %}{% endblock %}
"""

PAGE_HOME = """{% extends "base" %}{% block body %}
<div class="cards">
  <div class="card"><div class="muted">Height</div><div class="v">{{ tip }}</div></div>
  <div class="card"><div class="muted">Difficulty</div><div class="v">{{ "%.8f"|format(diff) }}</div></div>
  <div class="card"><div class="muted">Transactions indexed</div><div class="v">{{ txcount }}</div></div>
  <div class="card"><div class="muted">CORG burned</div><div class="v">{{ fmt(burned) }}</div></div>
</div>
{% if forks %}
<div class="cards">
{% for f in forks %}
  <div class="card"><div class="muted">{{ f.name|upper }} fork</div>
  <div class="v">{% if f.active %}active{% else %}at {{ f.height }}{% endif %}</div></div>
{% endfor %}
</div>
{% endif %}
<table>
<tr><th>Height</th><th>Time (UTC)</th><th class="num">Txs</th><th class="num">Size</th><th>Difficulty</th><th>Hash</th></tr>
{% for b in blocks %}
<tr><td><a href="{{ url_for('block', ref=b['height']) }}">{{ b['height'] }}</a></td>
<td>{{ ts(b['time']) }}</td><td class="num">{{ b['txcount'] }}</td><td class="num">{{ b['size'] }}</td>
<td>{{ "%.8f"|format(b['difficulty']) }}</td>
<td class="mono">{{ b['hash'][:24] }}&hellip;</td></tr>
{% endfor %}
</table>
{% endblock %}"""

PAGE_BLOCK = """{% extends "base" %}{% block body %}
<h2>Block {{ b['height'] }}</h2>
<table>
<tr><th>Hash</th><td class="mono">{{ b['hash'] }}</td></tr>
<tr><th>Time (UTC)</th><td>{{ ts(b['time']) }}</td></tr>
<tr><th>Difficulty</th><td>{{ "%.8f"|format(b['difficulty']) }} (bits {{ b['bits'] }})</td></tr>
<tr><th>Size</th><td>{{ b['size'] }} bytes</td></tr>
</table>
<h3>{{ txs|length }} transaction(s)</h3>
<table>
<tr><th>Txid</th><th class="num">Out value</th><th></th></tr>
{% for t in txs %}
<tr><td class="mono"><a href="{{ url_for('tx', txid=t['txid']) }}">{{ t['txid'] }}</a></td>
<td class="num">{{ fmt(t['total']) }}</td>
<td>{% if t['is_coinbase'] %}<span class="muted">coinbase</span>{% endif %}</td></tr>
{% endfor %}
</table>
{% endblock %}"""

PAGE_TX = """{% extends "base" %}{% block body %}
<h2>Transaction</h2>
<p class="mono">{{ t['txid'] }}</p>
<p>In block <a href="{{ url_for('block', ref=t['height']) }}">{{ t['height'] }}</a>
&middot; {{ ts(t['time']) }} {% if t['is_coinbase'] %}&middot; coinbase{% endif %}</p>
<h3>Outputs</h3>
<table>
<tr><th class="num">#</th><th>Address</th><th class="num">Value</th><th>Status</th></tr>
{% for o in outs %}
<tr><td class="num">{{ o['n'] }}</td>
<td>{% if o['address'] %}<a class="mono" href="{{ url_for('address', addr=o['address']) }}">{{ o['address'] }}</a>
{% else %}<span class="muted">OP_RETURN (burn)</span>{% endif %}</td>
<td class="num">{{ fmt(o['value']) }}</td>
<td>{% if o['spent_txid'] %}spent in <a class="mono" href="{{ url_for('tx', txid=o['spent_txid']) }}">{{ o['spent_txid'][:16] }}&hellip;</a>
{% elif o['address'] %}unspent{% endif %}</td></tr>
{% endfor %}
</table>
{% if burns %}
<h3>Burn payload</h3>
<table>
{% for u in burns %}
<tr><th>Amount</th><td>{{ fmt(u['value']) }} CORG</td></tr>
{% if u['partner'] %}<tr><th>Partner</th><td>{{ u['partner'] }}</td></tr>
<tr><th>Solana address</th><td class="mono">{{ u['sol_address'] }}</td></tr>
{% else %}<tr><th>Payload</th><td class="mono">{{ u['script_hex'] }}</td></tr>{% endif %}
{% endfor %}
</table>
{% endif %}
{% endblock %}"""

PAGE_ADDRESS = """{% extends "base" %}{% block body %}
<h2>Address</h2>
<p class="mono">{{ addr }}</p>
{% if bech32 %}<p class="muted">bech32: <span class="mono">{{ bech32 }}</span></p>{% endif %}
<div class="cards">
  <div class="card"><div class="muted">Balance</div><div class="v">{{ fmt(balance) }}</div></div>
  <div class="card"><div class="muted">Received</div><div class="v">{{ fmt(received) }}</div></div>
  <div class="card"><div class="muted">Outputs</div><div class="v">{{ outs|length }}</div></div>
</div>
<table>
<tr><th>Txid</th><th class="num">Value</th><th>Height</th><th>Status</th></tr>
{% for o in outs %}
<tr><td class="mono"><a href="{{ url_for('tx', txid=o['txid']) }}">{{ o['txid'][:32] }}&hellip;</a></td>
<td class="num">{{ fmt(o['value']) }}</td>
<td><a href="{{ url_for('block', ref=o['height']) }}">{{ o['height'] }}</a></td>
<td>{% if o['spent_txid'] %}spent{% else %}unspent{% endif %}</td></tr>
{% endfor %}
</table>
{% endblock %}"""

PAGE_CHARTS = """{% extends "base" %}{% block body %}
<h2>Network Charts</h2>
<p class="muted">Last {{ n }} blocks (heights {{ first_h }}&ndash;{{ last_h }}).</p>
<h3>Difficulty</h3>
{{ diff_svg|safe }}
<h3>Block time (seconds between blocks)</h3>
{{ time_svg|safe }}
{% endblock %}"""

PAGE_BURNS = """{% extends "base" %}{% block body %}
<h2>Burns</h2>
<div class="cards">
  <div class="card"><div class="muted">Total burned</div><div class="v">{{ fmt(total) }} CORG</div></div>
  <div class="card"><div class="muted">Burn count</div><div class="v">{{ rows|length }}</div></div>
</div>
<table>
<tr><th>Height</th><th>Txid</th><th class="num">Amount</th><th>Partner</th><th>Solana address</th></tr>
{% for u in rows %}
<tr><td><a href="{{ url_for('block', ref=u['height']) }}">{{ u['height'] }}</a></td>
<td class="mono"><a href="{{ url_for('tx', txid=u['txid']) }}">{{ u['txid'][:24] }}&hellip;</a></td>
<td class="num">{{ fmt(u['value']) }}</td>
<td>{{ u['partner'] or '—' }}</td>
<td class="mono">{{ u['sol_address'] or '—' }}</td></tr>
{% endfor %}
</table>
{% endblock %}"""


def svg_line_chart(values, color="#4caf50", w=920, h=220, pad=34, fmt="{:.4g}"):
    """Themed inline-SVG line chart with min/max labels. No dependencies."""
    import html as _html
    if not values:
        return '<p class="muted">no data</p>'
    ymin, ymax = min(values), max(values)
    if ymax == ymin:
        ymax = ymin + 1
    n = len(values)
    def X(i):
        return pad + (w - 2 * pad) * (i / (n - 1) if n > 1 else 0)
    def Y(v):
        return h - pad - (h - 2 * pad) * ((v - ymin) / (ymax - ymin))
    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(values))
    area = f"{pad:.1f},{h - pad:.1f} " + line + f" {X(n - 1):.1f},{h - pad:.1f}"
    gid = f"g{abs(hash((n, ymin, ymax, color))) % 100000}"
    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px" '
        f'xmlns="http://www.w3.org/2000/svg" role="img">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{color}" stop-opacity="0.35"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="#183618" rx="10"/>'
        f'<line x1="{pad}" y1="{h-pad}" x2="{w-pad}" y2="{h-pad}" stroke="#2f5e2f"/>'
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h-pad}" stroke="#2f5e2f"/>'
        f'<polygon points="{area}" fill="url(#{gid})"/>'
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2"/>'
        f'<text x="{pad+4}" y="{pad}" fill="#a9c7ab" font-size="11">{_html.escape(fmt.format(ymax))}</text>'
        f'<text x="{pad+4}" y="{h-pad-4}" fill="#a9c7ab" font-size="11">{_html.escape(fmt.format(ymin))}</text>'
        f'</svg>'
    )


def create_app(rpc: CorgiRPC, db_path: Path) -> Flask:
    app = Flask(__name__)
    app.jinja_loader = None  # templates are inline

    from jinja2 import DictLoader

    app.jinja_loader = DictLoader({
        "base": BASE, "home": PAGE_HOME, "block": PAGE_BLOCK,
        "tx": PAGE_TX, "address": PAGE_ADDRESS, "burns": PAGE_BURNS,
        "charts": PAGE_CHARTS,
    })

    def db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def helpers():
        return {
            "fmt": lambda v: f"{v / COIN:,.8f}".rstrip("0").rstrip("."),
            "ts": lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t)),
        }

    @app.route("/corgi.png")
    def logo():
        from flask import send_file
        resp = send_file(Path(__file__).resolve().parent / "corgicoin.png",
                         mimetype="image/png")
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    @app.route("/")
    def home():
        d = db()
        blocks = d.execute("SELECT * FROM blocks ORDER BY height DESC LIMIT 25").fetchall()
        tip = blocks[0]["height"] if blocks else 0
        diff = blocks[0]["difficulty"] if blocks else 0.0
        txcount = d.execute("SELECT COUNT(*) c FROM txs").fetchone()["c"]
        burned = d.execute("SELECT COALESCE(SUM(value),0) s FROM burns").fetchone()["s"]
        # Live chain + fork-activation status (getblockchaininfo, v4.4+).
        # Degrades gracefully against older nodes that lack the RPC.
        forks = []
        try:
            info = rpc.call("getblockchaininfo")
            for name, sf in sorted((info.get("softforks") or {}).items()):
                forks.append({
                    "name": name,
                    "height": sf.get("height"),
                    "active": sf.get("active"),
                })
        except Exception:
            pass
        return render_template_string(
            PAGE_HOME, blocks=blocks, tip=tip, diff=diff, txcount=txcount,
            burned=burned, forks=forks, **helpers())

    @app.route("/block/<ref>")
    def block(ref):
        d = db()
        if ref.isdigit():
            b = d.execute("SELECT * FROM blocks WHERE height=?", (int(ref),)).fetchone()
        else:
            b = d.execute("SELECT * FROM blocks WHERE hash=?", (ref,)).fetchone()
        if b is None:
            abort(404)
        txs = d.execute(
            "SELECT t.*, (SELECT SUM(value) FROM outputs o WHERE o.txid=t.txid) total "
            "FROM txs t WHERE height=? ORDER BY idx", (b["height"],)).fetchall()
        return render_template_string(PAGE_BLOCK, b=b, txs=txs, **helpers())

    @app.route("/tx/<txid>")
    def tx(txid):
        d = db()
        t = d.execute("SELECT * FROM txs WHERE txid=?", (txid,)).fetchone()
        if t is None:
            abort(404)
        outs = d.execute("SELECT * FROM outputs WHERE txid=? ORDER BY n", (txid,)).fetchall()
        burns_ = d.execute("SELECT * FROM burns WHERE txid=?", (txid,)).fetchall()
        return render_template_string(PAGE_TX, t=t, outs=outs, burns=burns_, **helpers())

    @app.route("/address/<addr>")
    def address(addr):
        d = db()
        outs = d.execute(
            "SELECT o.*, t.height FROM outputs o JOIN txs t ON t.txid=o.txid "
            "WHERE o.address=? ORDER BY t.height DESC", (addr,)).fetchall()
        if not outs:
            abort(404)
        received = sum(o["value"] for o in outs)
        balance = sum(o["value"] for o in outs if not o["spent_txid"])
        bech = None
        try:
            info = rpc.call("validateaddress", addr)
            bech = info.get("bech32")
        except Exception:
            pass
        return render_template_string(
            PAGE_ADDRESS, addr=addr, outs=outs, received=received,
            balance=balance, bech32=bech, **helpers())

    @app.route("/burns")
    def burns():
        d = db()
        rows = d.execute("SELECT * FROM burns ORDER BY height DESC LIMIT 500").fetchall()
        total = d.execute("SELECT COALESCE(SUM(value),0) s FROM burns").fetchone()["s"]
        return render_template_string(PAGE_BURNS, rows=rows, total=total, **helpers())

    @app.route("/charts")
    def charts():
        d = db()
        rows = d.execute(
            "SELECT height, time, difficulty FROM blocks ORDER BY height DESC LIMIT 500"
        ).fetchall()
        rows = list(reversed(rows))  # oldest -> newest
        if not rows:
            return render_template_string(
                PAGE_CHARTS, diff_svg="", time_svg="", n=0, first_h=0, last_h=0, **helpers())
        diffs = [r["difficulty"] for r in rows]
        # block times = gaps between consecutive block timestamps (clamped >= 0)
        times = [max(0, rows[i]["time"] - rows[i - 1]["time"]) for i in range(1, len(rows))]
        return render_template_string(
            PAGE_CHARTS,
            diff_svg=svg_line_chart(diffs, color="#8bc34a", fmt="{:.6f}"),
            time_svg=svg_line_chart(times, color="#e6c34a", fmt="{:.0f}s"),
            n=len(rows), first_h=rows[0]["height"], last_h=rows[-1]["height"],
            **helpers())

    @app.route("/search")
    def search():
        q = (request.args.get("q") or "").strip()
        d = db()
        if q.isdigit() and d.execute("SELECT 1 FROM blocks WHERE height=?", (int(q),)).fetchone():
            return redirect(url_for("block", ref=q))
        if len(q) == 64:
            if d.execute("SELECT 1 FROM txs WHERE txid=?", (q,)).fetchone():
                return redirect(url_for("tx", txid=q))
            if d.execute("SELECT 1 FROM blocks WHERE hash=?", (q,)).fetchone():
                return redirect(url_for("block", ref=q))
        if d.execute("SELECT 1 FROM outputs WHERE address=? LIMIT 1", (q,)).fetchone():
            return redirect(url_for("address", addr=q))
        # A bech32 address the index stores under its base58 form
        try:
            info = rpc.call("validateaddress", q)
            if info.get("isvalid"):
                return redirect(url_for("address", addr=info["address"]))
        except Exception:
            pass
        abort(404)

    # ---- JSON API (machine-readable; amounts in satoshis) -------------------

    def rows_to_dicts(rows):
        return [dict(r) for r in rows]

    @app.route("/api/chaininfo")
    def api_chaininfo():
        d = db()
        tip = d.execute("SELECT MAX(height) h FROM blocks").fetchone()["h"]
        row = d.execute("SELECT difficulty FROM blocks WHERE height=?", (tip,)).fetchone() if tip is not None else None
        out = {
            "height": tip,
            "difficulty": row["difficulty"] if row else None,
            "tx_count_indexed": d.execute("SELECT COUNT(*) c FROM txs").fetchone()["c"],
            "total_burned": d.execute("SELECT COALESCE(SUM(value),0) s FROM burns").fetchone()["s"],
        }
        try:
            out["softforks"] = (rpc.call("getblockchaininfo") or {}).get("softforks")
        except Exception:
            out["softforks"] = None
        return jsonify(out)

    @app.route("/api/block/<ref>")
    def api_block(ref):
        d = db()
        if ref.isdigit():
            b = d.execute("SELECT * FROM blocks WHERE height=?", (int(ref),)).fetchone()
        else:
            b = d.execute("SELECT * FROM blocks WHERE hash=?", (ref,)).fetchone()
        if b is None:
            return jsonify({"error": "block not found"}), 404
        txs = d.execute("SELECT txid, idx, is_coinbase FROM txs WHERE height=? ORDER BY idx", (b["height"],)).fetchall()
        res = dict(b)
        res["tx"] = rows_to_dicts(txs)
        return jsonify(res)

    @app.route("/api/tx/<txid>")
    def api_tx(txid):
        d = db()
        t = d.execute("SELECT * FROM txs WHERE txid=?", (txid,)).fetchone()
        if t is None:
            return jsonify({"error": "tx not found"}), 404
        res = dict(t)
        res["outputs"] = rows_to_dicts(d.execute("SELECT * FROM outputs WHERE txid=? ORDER BY n", (txid,)).fetchall())
        res["burns"] = rows_to_dicts(d.execute("SELECT * FROM burns WHERE txid=?", (txid,)).fetchall())
        return jsonify(res)

    @app.route("/api/address/<addr>")
    def api_address(addr):
        d = db()
        outs = d.execute(
            "SELECT o.*, t.height FROM outputs o JOIN txs t ON t.txid=o.txid "
            "WHERE o.address=? ORDER BY t.height DESC", (addr,)).fetchall()
        if not outs:
            return jsonify({"error": "address not found"}), 404
        received = sum(o["value"] for o in outs)
        balance = sum(o["value"] for o in outs if not o["spent_txid"])
        return jsonify({
            "address": addr,
            "balance": balance,
            "received": received,
            "outputs": rows_to_dicts(outs),
        })

    @app.route("/api/burns")
    def api_burns():
        d = db()
        rows = d.execute("SELECT * FROM burns ORDER BY height DESC LIMIT 1000").fetchall()
        total = d.execute("SELECT COALESCE(SUM(value),0) s FROM burns").fetchone()["s"]
        return jsonify({"total_burned": total, "count": len(rows), "burns": rows_to_dicts(rows)})

    return app


# ----------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description="CorgiCoin block explorer")
    ap.add_argument("--conf", default=str(Path.home() / ".corgicoin" / "corgicoin.conf"))
    ap.add_argument("--db", default="explorer.db")
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_rpc_config(Path(args.conf))
    rpc = CorgiRPC(
        f"http://{cfg['rpcconnect']}:{cfg['rpcport']}", cfg["rpcuser"], cfg["rpcpassword"])
    rpc.call("getblockcount")  # fail fast if the node is unreachable

    db_path = Path(args.db)
    open_db(db_path).close()  # create schema before threads race
    Indexer(rpc, db_path).start()
    create_app(rpc, db_path).run(host=args.bind, port=args.port)


if __name__ == "__main__":
    main()
