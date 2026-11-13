#!/usr/bin/env python3
"""Run CorgiCoin functional tests (regtest).

    python3 test/functional/test_runner.py [--corgicoind PATH] [-j N] [test ...]

With no test names, runs every script in TESTS. Each test runs in its own
process with its own nodes, ports and temp dir, so they parallelize safely.
"""
import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))

TESTS = [
    "feature_regtest_basics.py",
    "feature_zmq.py",
    "wallet_send.py",
    "wallet_lockunspent.py",
    "wallet_abandon.py",
    "wallet_dump.py",
    "wallet_import_range.py",
    "wallet_encryption.py",
    "wallet_upgrade_fixtures.py",
    "feature_block_sync.py",
    "p2p_network_rpcs.py",
    "p2p_ping_timeout.py",
    "rpc_createauxblock.py",
    "feature_auxpow.py",
    "rpc_mempool_verify.py",
    "rpc_gettxout.py",
    "rpc_submitblock.py",
    "rpc_testmempoolaccept.py",
    "rpc_prioritisetransaction.py",
    "rpc_standard_signatures.py",
    "rpc_invalidateblock.py",
    "wallet_hd_encryption.py",
    "wallet_hd_phrase.py",
    "rpc_http_auth.py",
    "feature_cross_binary.py",   # skips itself unless a second build is given (--alt-corgicoind / $CORGICOIND_ALT)
]


def run(name, binary):
    start = time.time()
    proc = subprocess.run([sys.executable, os.path.join(HERE, name), "--corgicoind", binary],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return name, proc.returncode, time.time() - start, proc.stdout


def main():
    sys.path.insert(0, HERE)
    from test_framework import SKIP_EXIT_CODE, default_binary
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tests", nargs="*", help="test scripts to run (default: all)")
    p.add_argument("--corgicoind", default=os.environ.get("CORGICOIND", default_binary()))
    p.add_argument("-j", "--jobs", type=int, default=4)
    args = p.parse_args()
    binary = os.path.abspath(args.corgicoind)
    tests = args.tests or TESTS
    for t in tests:
        if not os.path.isfile(os.path.join(HERE, t)):
            sys.exit("unknown test: %s" % t)

    print("Running %d functional tests against %s" % (len(tests), binary), flush=True)
    failed = []
    skipped = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for name, rc, secs, out in pool.map(lambda t: run(t, binary), tests):
            if rc == SKIP_EXIT_CODE:
                status = "SKIP"
                skipped.append(name)
            else:
                status = "PASS" if rc == 0 else "FAIL"
            print("  %-28s %s  %5.1fs" % (name, status, secs), flush=True)
            if rc not in (0, SKIP_EXIT_CODE):
                failed.append(name)
                print("\n".join("      " + line for line in out.rstrip().splitlines()), flush=True)
    print("%d/%d passed%s" % (len(tests) - len(failed) - len(skipped), len(tests),
                           (", %d skipped" % len(skipped)) if skipped else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
