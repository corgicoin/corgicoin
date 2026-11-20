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
    "rpc_logging.py",
    "feature_zmq.py",
    "wallet_send.py",
    "wallet_listtransactions.py",
    "wallet_sendmany_total.py",
    "wallet_change_position.py",
    "rpc_sighash_single.py",
    "wallet_lockunspent.py",
    "wallet_abandon.py",
    "wallet_conflicts.py",
    "wallet_dump.py",
    "wallet_backup.py",
    "wallet_import_range.py",
    "wallet_encryption.py",
    "wallet_accounting.py",
    "wallet_rewrite_safety.py",
    "wallet_relock_during_topup.py",
    "wallet_unlock_timeout.py",
    "wallet_upgrade_fixtures.py",
    "feature_block_sync.py",
    "p2p_network_rpcs.py",
    "p2p_ping_timeout.py",
    "p2p_getheaders_auxpow.py",
    "p2p_auxpow_refetch.py",
    "p2p_bad_subver.py",
    "p2p_maxconnections.py",
    "p2p_resource_limits.py",
    "p2p_log_injection.py",
    "p2p_upload_target.py",
    "feature_chainstate_catchup.py",
    "feature_chainstate_random.py",
    "feature_chainstate_recover.py",
    "feature_coinsvalidate_blocks.py",
    "feature_signature_variants.py",
    "feature_chainstate_stale.py",
    "rpc_createauxblock.py",
    "rpc_createauxblock_cache.py",
    "feature_auxpow.py",
    "rpc_mempool_verify.py",
    "rpc_gettxout.py",
    "rpc_getblock_verbose.py",
    "rpc_rawtransaction.py",
    "rpc_small_fixes.py",
    "rpc_mining_info.py",
    "rpc_submitblock.py",
    "rpc_getblocktemplate.py",
    "mining_feerate_blocks.py",
    "rpc_gettxoutsetinfo.py",
    "mining_getwork.py",
    "rpc_http_protocol.py",
    "wallet_listtransactions_paging.py",
    "rpc_estimatefee.py",
    "rpc_testmempoolaccept.py",
    "rpc_prioritisetransaction.py",
    "rpc_mempool_policy.py",
    "rpc_standard_signatures.py",
    "rpc_invalidateblock.py",
    "rpc_invalidateblock_deep.py",
    "wallet_hd_encryption.py",
    "rpc_multisig_limits.py",
    "rpc_hostile_inputs.py",
    "wallet_hd_phrase.py",
    "wallet_hd_version_gate.py",
    "wallet_scrypt_kdf.py",
    "wallet_hd_restore.py",
    "wallet_hd_lock_secrets.py",
    "wallet_hdseed_index.py",
    "wallet_hdseed_atomic.py",
    "rpc_http_auth.py",
    "rpc_http_limits.py",
    "rpc_shutdown_keepalive.py",
    "feature_shutdown_exit.py",
    "rpc_cookie_auth.py",
    "rpc_config_hardening.py",
    "rpc_failed_block.py",
    "rpc_mempool_cap.py",
    "rpc_mempool_conflict_block.py",
    "rpc_sendrawtransaction_reason.py",
    "p2p_free_relay_limit.py",
    "p2p_locator_limit.py",
    "wallet_maxtxfee.py",
    "wallet_notify.py",
    "tool_makeseeds.py",
    "feature_init_error.py",
    "p2p_inbound_group.py",
    "p2p_foreign_peer.py",
    "p2p_alerts_retired.py",
    "feature_bootstrap_export.py",
    "rpc_minimum_chain_work.py",
    "rpc_reorg_postponed.py",
    "rpc_big_block_locks.py",
    "wallet_rbf.py",
    "wallet_commit_dryrun.py",
    "rpc_observability.py",

    "rpc_metrics.py",
    "wallet_watchonly.py",
    "wallet_verify.py",
    "wallet_backup_encrypted.py",
    "wallet_key_metadata.py",
    "wallet_fundraw.py",
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
