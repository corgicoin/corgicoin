#!/usr/bin/env python3
"""Regenerate the old-release wallet fixtures used by wallet_upgrade_fixtures.py.

Run it with the binary of the release the fixtures should come from (they were made with v4.7.0.0, built against
Berkeley DB 5.3):

    python3 test/functional/data/wallets/make_fixtures.py --corgicoind /path/to/v4.7.0.0/corgicoind

Each fixture is a regtest wallet.dat plus info.json (what the test needs to know: the addresses it handed out, its
passphrase, its recovery phrase). They hold regtest keys only, worth nothing.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
from test_framework import TestNode   # noqa: E402

PASSPHRASE = "corgi fixture passphrase"


def make(binary, name, made_by, steps):
    tmp = tempfile.mkdtemp(prefix="corgi_fixture_")
    node = TestNode(0, binary, tmp)
    node.start()
    info = {"made_by": made_by, "addresses": [], "passphrase": None, "mnemonic": None}
    steps(node, info)
    if info["passphrase"]:
        node.encryptwallet(info["passphrase"])   # the daemon stops itself
        node.process.wait(timeout=60)
    else:
        node.stop()
    out = os.path.join(HERE, name)
    os.makedirs(out, exist_ok=True)
    shutil.copy(os.path.join(tmp, "regtest", "wallet.dat"), os.path.join(out, "wallet.dat"))
    with open(os.path.join(out, "info.json"), "w") as f:
        json.dump(info, f, indent=2)
        f.write("\n")
    shutil.rmtree(tmp)
    print("wrote", out)


def hd(node, info):
    info["mnemonic"] = node.sethdseed()["mnemonic"]
    info["addresses"] = [node.getnewaddress() for _ in range(2)]


def hd_encrypted(node, info):
    hd(node, info)
    info["passphrase"] = PASSPHRASE


def plain_encrypted(node, info):
    info["addresses"] = [node.getnewaddress() for _ in range(2)]
    info["passphrase"] = PASSPHRASE


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--corgicoind", required=True)
    p.add_argument("--made-by", default="v4.7.0.0")
    a = p.parse_args()
    tag = a.made_by.replace(".", "")[:3]   # v4.7.0.0 -> v47
    make(a.corgicoind, tag + "-hd", a.made_by, hd)
    make(a.corgicoind, tag + "-hd-encrypted", a.made_by, hd_encrypted)
    make(a.corgicoind, tag + "-encrypted", a.made_by, plain_encrypted)


if __name__ == "__main__":
    main()
