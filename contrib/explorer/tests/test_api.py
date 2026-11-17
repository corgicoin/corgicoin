"""Tests for the explorer's public API: what a request may cost the node, and what a wallet may be told."""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import explorer  # noqa: E402

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58check(version: int, payload: bytes) -> str:
    raw = bytes([version]) + payload
    raw += hashlib.sha256(hashlib.sha256(raw).digest()).digest()[:4]
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return out


HASH = bytes(range(20))
ADDR = b58check(28, HASH)
TXID = "ab" * 32


class FakeRPC:
    def __init__(self):
        self.calls = []

    def call(self, method, *params):
        self.calls.append(method)
        if method == "getblockcount":
            return 120
        if method == "getrawtransaction":
            if params[0] == TXID:
                return "0100000000"
            raise RuntimeError("No information available about transaction")
        if method == "sendrawtransaction":
            return "cd" * 32
        raise AssertionError(method)


@pytest.fixture
def client(tmp_path):
    db = explorer.open_db(tmp_path / "e.db")
    db.execute("INSERT INTO blocks VALUES (100, 'h100', 1700000000, '1d00ffff', 1.0, 300, 1)")
    db.execute("INSERT INTO txs VALUES (?, 100, 0, 1700000000, 0)", (TXID,))
    db.execute("INSERT INTO outputs VALUES (?, 0, ?, 500000000, NULL)", (TXID, ADDR))
    db.commit()
    rpc = FakeRPC()
    app = explorer.create_app(rpc, tmp_path / "e.db")
    app.config["TESTING"] = True
    c = app.test_client()
    c.rpc = rpc
    c.db = db
    c.tmp = tmp_path
    return c


def test_script_for_address():
    assert explorer.script_for_address(ADDR) == "76a914" + HASH.hex() + "88ac"
    assert explorer.script_for_address(b58check(22, HASH)) == "a914" + HASH.hex() + "87"
    assert explorer.script_for_address(b58check(113, HASH)) == "76a914" + HASH.hex() + "88ac"
    assert explorer.script_for_address(b58check(99, HASH)) is None          # not a CorgiCoin prefix
    assert explorer.script_for_address(ADDR[:-1] + ("2" if ADDR[-1] != "2" else "3")) is None   # bad checksum
    assert explorer.script_for_address("not an address") is None
    assert explorer.script_for_address("") is None


def test_utxos_do_not_ask_the_node_for_each_coin(client):
    r = client.get(f"/api/address/{ADDR}/utxos")
    assert r.status_code == 200
    j = r.get_json()
    assert j["count"] == 1
    assert j["utxos"][0]["scriptPubKey"] == "76a914" + HASH.hex() + "88ac"
    assert j["utxos"][0]["confirmations"] == 21
    assert "getrawtransaction" not in client.rpc.calls      # it used to make one node call per coin (up to 500)


def test_address_totals_cover_every_output_but_the_list_is_capped(client):
    for i in range(1, 700):
        client.db.execute("INSERT INTO outputs VALUES (?, ?, ?, 1000, ?)", (TXID, i, ADDR, "ee" * 32 if i % 2 else None))
    client.db.commit()
    j = client.get(f"/api/address/{ADDR}").get_json()
    assert len(j["outputs"]) == explorer.MAX_ADDRESS_ROWS
    assert j["truncated"] is True
    assert j["received"] == 500000000 + 699 * 1000
    unspent_small = len([i for i in range(1, 700) if i % 2 == 0])
    assert j["balance"] == 500000000 + unspent_small * 1000


def test_rawtx(client):
    assert client.get(f"/api/rawtx/{TXID}").get_json()["hex"] == "0100000000"
    assert client.get("/api/rawtx/nothex").status_code == 400
    assert client.get("/api/rawtx/" + "00" * 32).status_code == 404


def test_broadcast_takes_only_a_transaction_sized_hex(client):
    post = lambda body: client.post("/api/broadcast", json={"hex": body})
    assert post("zz").status_code == 400
    assert post("abc").status_code == 400                       # odd length
    assert post("00" * 100_001).status_code == 400              # over 100 kB as a transaction
    assert client.post("/api/broadcast", data="0" * 600_000, content_type="text/plain").status_code == 413
    assert post("0100000000").status_code == 200


def test_broadcast_is_rate_limited(client):
    codes = [client.post("/api/broadcast", json={"hex": "0100000000"}).status_code for _ in range(15)]
    assert codes[:10] == [200] * 10
    assert 429 in codes[10:]


def test_wallet_page_has_a_content_security_policy(client):
    r = client.get("/wallet/")
    assert r.status_code == 200
    csp = r.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
    assert r.headers["Cache-Control"] == "no-store"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_network_page_numbers_the_peers_instead_of_naming_them(tmp_path):
    class PeerRPC(FakeRPC):
        def call(self, method, *params):
            if method == "getnetworkinfo":
                return {"version": 1, "connections": 2}
            if method == "getpeerinfo":
                return [{"addr": "203.0.113.7:62556", "subver": "/CorgiCoin:4.8.0/", "startingheight": 100, "pingtime": 0.05},
                        {"addr": "198.51.100.9:62556", "subver": "/CorgiCoin:4.8.0/", "startingheight": 101, "pingtime": 0.07}]
            if method == "getrawmempool":
                return []
            return super().call(method, *params)

    explorer.open_db(tmp_path / "e.db").close()
    hidden = explorer.create_app(PeerRPC(), tmp_path / "e.db")
    body = hidden.test_client().get("/network").get_data(as_text=True)
    assert "203.0.113.7" not in body and "198.51.100.9" not in body
    assert "peer 1" in body and "peer 2" in body and "/CorgiCoin:4.8.0/" in body

    shown = explorer.create_app(PeerRPC(), tmp_path / "e.db", show_peer_addresses=True)
    body = shown.test_client().get("/network").get_data(as_text=True)
    assert "203.0.113.7:62556" in body
