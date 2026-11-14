#!/usr/bin/env python3
"""
CorgiCoin cross-chain burn bridge (proof-of-concept).

Watches a corgicoind node for burn transactions that match the bridge payload
spec (see doc/burn-payload-spec.md), looks up the named partner in
partners.json, and dispatches an SPL token reward on Solana from that
partner's treasury.

This is a single-file PoC. Devnet only. No HSM, no multisig, no Solana
program - just a treasury keypair and the SPL token program. Do not point
this at mainnet without a lot more paranoia than exists here today.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import shlex
import signal
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from solana.rpc.api import Client as SolanaClient
from solana.rpc.commitment import Finalized
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import (
    TransferCheckedParams,
    create_associated_token_account,
    get_associated_token_address,
    transfer_checked,
)

log = logging.getLogger("bridge")

DEFAULT_CONFIRMATIONS = 50   # blocks to wait; at least the 30-block coinbase maturity and the wallet's 50
DEFAULT_POLL_SECONDS  = 30
NOT_A_BURN_CODE       = -3   # decodeburn's JSON-RPC error for a script that is not a bridge burn payload
DEFAULT_SOLANA_RPC    = "https://api.devnet.solana.com"


# ---------------------------------------------------------------------------
# CorgiCoin JSON-RPC client
# ---------------------------------------------------------------------------

def alert(message: str) -> None:
    """Tell the operator something needs a person (BRIDGE_ALERT_CMD: a command, which gets the message as its last argument).

    The log has the same words, but nobody reads a log at night. A failing command is logged and does not stop the bridge.
    """
    command = os.environ.get("BRIDGE_ALERT_CMD", "").strip()
    if not command:
        return
    try:
        subprocess.run(shlex.split(command) + [message], timeout=30, check=False)
    except Exception as e:     # an alert that cannot be sent must not stop the bridge from doing its work
        log.error("could not run BRIDGE_ALERT_CMD: %s", e)


class RPCError(RuntimeError):
    """corgicoind answered with a JSON-RPC error. .code is its error code (None if it had none)."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class CorgiRPC:
    """Tiny JSON-RPC wrapper for corgicoind."""

    def __init__(self, url: str, user: str, password: str):
        self._url = url
        self._auth = (user, password)
        self._id = 0

    def call(self, method: str, *params: Any) -> Any:
        self._id += 1
        resp = requests.post(
            self._url,
            auth=self._auth,
            json={"jsonrpc": "1.0", "id": self._id, "method": method, "params": list(params)},
            timeout=30,
        )
        try:
            # amounts as Decimal, not float: a float is only exact to about 15 digits
            body = resp.json(parse_float=Decimal)
        except ValueError:
            resp.raise_for_status()
            raise RuntimeError(f"corgicoind RPC non-JSON response on {method}: {resp.text[:200]}")
        if body.get("error"):
            err = body["error"]
            raise RPCError(f"corgicoind RPC error on {method}: {err}", err.get("code") if isinstance(err, dict) else None)
        return body["result"]


# ---------------------------------------------------------------------------
# Partner registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Partner:
    tag: str
    token_mint: Pubkey
    decimals: int
    reward_ratio: Decimal
    treasury: Keypair
    # optional limits, in the partner token (None: no limit). A burn over max_reward_per_burn, or one that would take the
    # day's total over max_reward_per_day, is not paid: it is recorded as "over_limit" for the operator to look at.
    max_reward_per_burn: Decimal | None = None
    max_reward_per_day: Decimal | None = None

    @classmethod
    def from_config(cls, tag: str, cfg: dict, keys_dir: Path) -> "Partner":
        keypair_path = keys_dir / cfg["treasury_keypair"]
        # The treasury key is a hot key. A file that other users of the machine can read is a key they can take.
        if os.name == "posix" and keypair_path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise SystemExit("refusing to start: %s can be read by other users (mode %o). chmod 600 it."
                             % (keypair_path, stat.S_IMODE(keypair_path.stat().st_mode)))
        with keypair_path.open() as f:
            secret = json.load(f)
        return cls(
            tag=tag,
            token_mint=Pubkey.from_string(cfg["token_mint"]),
            decimals=int(cfg["decimals"]),
            reward_ratio=Decimal(str(cfg["reward_ratio"])),
            treasury=Keypair.from_bytes(bytes(secret)),
            max_reward_per_burn=Decimal(str(cfg["max_reward_per_burn"])) if "max_reward_per_burn" in cfg else None,
            max_reward_per_day=Decimal(str(cfg["max_reward_per_day"])) if "max_reward_per_day" in cfg else None,
        )


def load_partners(path: Path, keys_dir: Path) -> dict[str, Partner]:
    with path.open() as f:
        raw = json.load(f)
    return {tag: Partner.from_config(tag, cfg, keys_dir) for tag, cfg in raw.items()}


# ---------------------------------------------------------------------------
# Persistent state (idempotency + resume point)
# ---------------------------------------------------------------------------

class State:
    def __init__(self, path: Path):
        self._path = path
        if path.exists():
            with path.open() as f:
                data = json.load(f)
        else:
            data = {}
        self.last_height: int = int(data.get("last_height", 0))
        self.last_hash: str | None = data.get("last_hash")
        self.processed: dict[str, dict] = dict(data.get("processed", {}))
        # reward paid so far each UTC day, per partner: {"2026-11-13": {"CORG": "123.4"}}
        self.paid_by_day: dict[str, dict[str, str]] = dict(data.get("paid_by_day", {}))

    def already_processed(self, key: str) -> bool:
        return key in self.processed

    def paid_today(self, partner: str, today: str) -> Decimal:
        return Decimal(self.paid_by_day.get(today, {}).get(partner, "0"))

    def add_paid(self, partner: str, today: str, amount: Decimal) -> None:
        day = self.paid_by_day.setdefault(today, {})
        day[partner] = str(Decimal(day.get(partner, "0")) + amount)

    def record(self, txid: str, entry: dict) -> None:
        self.processed[txid] = entry

    def save(self) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp.open("w") as f:
            json.dump({"last_height": self.last_height, "last_hash": self.last_hash,
                       "processed": self.processed, "paid_by_day": self.paid_by_day}, f, indent=2)
            f.flush()
            os.fsync(f.fileno())    # the file must be on disk before it replaces the old one
        tmp.replace(self._path)


# ---------------------------------------------------------------------------
# Burn detection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Burn:
    txid: str
    height: int
    partner: str
    sol_dest: Pubkey
    amount_corg: Decimal
    vout: int = 0           # which output of the transaction (a transaction can hold several burns)

    @property
    def key(self) -> str:
        """The key of this burn in state.json. Per output: keyed by txid alone, a second burn in the same transaction
        replaced the first one's record."""
        return f"{self.txid}:{self.vout}"


def extract_burns(rpc: CorgiRPC, txid: str, height: int) -> list[Burn]:
    """Pull the tx, scan every output, delegate parsing to decodeburn RPC."""
    tx = rpc.call("getrawtransaction", txid, 1)
    burns: list[Burn] = []
    for n, vout in enumerate(tx.get("vout", [])):
        script_hex = vout["scriptPubKey"]["hex"]
        try:
            decoded = rpc.call("decodeburn", script_hex)
        except RPCError as e:
            # Only the daemon saying "this script is not a bridge burn" means the output is not one. Any other error (the
            # node loading or restarting, an internal error) says nothing about the output, and skipping it would lose the
            # burn for good, because the scan moves on. Let it end the tick: the same blocks are scanned again next time.
            if e.code == NOT_A_BURN_CODE:
                continue
            raise
        burns.append(Burn(
            txid=txid,
            height=height,
            partner=decoded["partner"],
            sol_dest=Pubkey.from_string(decoded["sol_dest_base58"]),
            amount_corg=Decimal(str(vout["value"])),
            vout=n,
        ))
    return burns


# ---------------------------------------------------------------------------
# Solana dispatch
# ---------------------------------------------------------------------------

class DispatchUnconfirmed(RuntimeError):
    """The reward transaction was submitted (.sol_sig) but did not reach finality in time. It may still land or it may
    have expired: the operator has to look it up before paying again."""

    def __init__(self, sol_sig: str):
        super().__init__(f"reward transaction {sol_sig} was submitted but not confirmed")
        self.sol_sig = sol_sig


class SolanaDispatcher:
    def __init__(self, client: SolanaClient, confirm_timeout: int = 90):
        self._client = client
        self._confirm_timeout = confirm_timeout

    def send_reward(self, partner: Partner, dest: Pubkey, reward_tokens: Decimal) -> str:
        """Transfer `reward_tokens` of partner's SPL token from treasury to dest.
        Creates the destination's ATA if needed. Returns the Solana tx signature."""
        raw_amount = int(reward_tokens * (Decimal(10) ** partner.decimals))
        if raw_amount <= 0:
            raise ValueError(f"reward amount rounds to zero: {reward_tokens}")

        treasury_pub = partner.treasury.pubkey()
        src_ata = get_associated_token_address(treasury_pub, partner.token_mint)
        dst_ata = get_associated_token_address(dest, partner.token_mint)

        instructions = []
        if not self._account_exists(dst_ata):
            instructions.append(create_associated_token_account(
                payer=treasury_pub, owner=dest, mint=partner.token_mint,
            ))
        instructions.append(transfer_checked(TransferCheckedParams(
            program_id=TOKEN_PROGRAM_ID,
            source=src_ata,
            mint=partner.token_mint,
            dest=dst_ata,
            owner=treasury_pub,
            amount=raw_amount,
            decimals=partner.decimals,
            signers=[],
        )))

        blockhash = self._client.get_latest_blockhash().value.blockhash
        tx = Transaction.new_signed_with_payer(
            instructions, treasury_pub, [partner.treasury], blockhash,
        )
        resp = self._client.send_transaction(tx, opts=TxOpts(skip_preflight=False))
        sol_sig = str(resp.value)
        # "submitted" is not "paid": a transaction whose blockhash expires is dropped with no error. Wait for it to be final.
        try:
            self._client.confirm_transaction(resp.value, commitment=Finalized, sleep_seconds=2)
        except Exception as e:
            raise DispatchUnconfirmed(sol_sig) from e
        return sol_sig

    def treasury_balance(self, partner: Partner) -> Decimal | None:
        """The partner token the treasury holds, in whole tokens; None if it cannot be found out (then the payment is tried)."""
        try:
            ata = get_associated_token_address(partner.treasury.pubkey(), partner.token_mint)
            amount = self._client.get_token_account_balance(ata).value.amount
            return Decimal(amount) / (Decimal(10) ** partner.decimals)
        except Exception as e:
            log.warning("could not read the treasury balance for %s: %s", partner.tag, e)
            return None

    def _account_exists(self, pubkey: Pubkey) -> bool:
        info = self._client.get_account_info(pubkey).value
        return info is not None


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def tick(rpc: CorgiRPC, partners: dict[str, Partner], dispatcher: SolanaDispatcher,
         state: State, confirmations: int) -> None:
    tip = int(rpc.call("getblockcount"))

    # Is the block we stopped at still on the chain? If a reorganisation was deeper than the confirmations we wait, burns we
    # have already paid for may be gone from the chain. We cannot take a reward back: say so loudly, and scan the blocks
    # that replaced them (what was paid is protected by the per-burn records).
    if state.last_height > 0 and state.last_hash:
        if rpc.call("getblockhash", state.last_height) != state.last_hash:
            rewind = max(0, state.last_height - 3 * max(confirmations, 10))
            log.error("REORG deeper than %d blocks: block %d is no longer %s. Rewinding the scan to height %d. Rewards for burns "
                      "in blocks that were replaced may have been paid for burns that no longer exist: review state.json.",
                      confirmations, state.last_height, state.last_hash, rewind)
            alert("CorgiCoin bridge: a reorganisation deeper than %d blocks replaced block %d. Rewards may have been paid for burns "
                  "that no longer exist: review state.json." % (confirmations, state.last_height))
            state.last_height = rewind
            state.last_hash = None
            state.save()

    safe_tip = tip - confirmations
    if safe_tip <= state.last_height:
        return

    for height in range(state.last_height + 1, safe_tip + 1):
        block_hash = rpc.call("getblockhash", height)
        block = rpc.call("getblock", block_hash)
        for txid in block.get("tx", []):
            if state.already_processed(txid):
                continue    # a record made before burns were keyed per output: the whole transaction counts as done
            for burn in extract_burns(rpc, txid, height):
                if state.already_processed(burn.key):
                    continue
                process_burn(burn, partners, dispatcher, state)
        state.last_height = height
        state.last_hash = block_hash
        state.save()


def process_burn(burn: Burn, partners: dict[str, Partner],
                 dispatcher: SolanaDispatcher, state: State) -> None:
    partner = partners.get(burn.partner)
    if partner is None:
        log.warning("ignoring burn %s: unknown partner %r", burn.key, burn.partner)
        state.record(burn.key, {
            "status": "skipped_unknown_partner",
            "partner": burn.partner, "height": burn.height,
            "amount_corg": str(burn.amount_corg),
        })
        state.save()
        return

    reward = burn.amount_corg * partner.reward_ratio
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    base_entry = {
        "partner": partner.tag,
        "height": burn.height,
        "amount_corg": str(burn.amount_corg),
        "reward": str(reward),
        "sol_dest": str(burn.sol_dest),
    }

    # Write 'pending' BEFORE the Solana RPC call. If we crash between
    # send_reward dispatching and recording the result, the next tick will see
    # this entry as already_processed and refuse to re-dispatch. The operator
    # reconciles manually (see README).
    # Payout limits: a treasury is a hot key, and the reward is whatever was burned. A burn over a limit is not paid.
    over = None
    if partner.max_reward_per_burn is not None and reward > partner.max_reward_per_burn:
        over = f"reward {reward} is over max_reward_per_burn {partner.max_reward_per_burn}"
    elif partner.max_reward_per_day is not None and state.paid_today(partner.tag, today) + reward > partner.max_reward_per_day:
        over = f"reward {reward} would take today's total past max_reward_per_day {partner.max_reward_per_day}"
    if over:
        log.error("NOT paying burn %s: %s. Recorded as over_limit; pay it by hand or raise the limit, then mark it dispatched.",
                  burn.key, over)
        state.record(burn.key, {**base_entry, "status": "over_limit", "error": over})
        state.save()
        alert("CorgiCoin bridge: burn %s NOT paid, %s. Pay it by hand or raise the limit." % (burn.key, over))
        return

    # A treasury that does not hold the reward cannot pay it: say so before anything is recorded as pending.
    balance = dispatcher.treasury_balance(partner)
    if isinstance(balance, Decimal) and balance < reward:
        msg = "treasury holds %s %s, the reward is %s" % (balance, partner.tag, reward)
        log.error("NOT paying burn %s: %s. Recorded as treasury_low; fund the treasury, then reset it to be paid.", burn.key, msg)
        state.record(burn.key, {**base_entry, "status": "treasury_low", "error": msg})
        state.save()
        alert("CorgiCoin bridge: burn %s NOT paid, %s. Fund the treasury, then --reset it." % (burn.key, msg))
        return

    state.record(burn.key, {**base_entry, "status": "pending"})
    state.save()

    try:
        sol_sig = dispatcher.send_reward(partner, burn.sol_dest, reward)
    except DispatchUnconfirmed as e:
        log.error("reward for %s was submitted as %s but is not confirmed: marked unconfirmed, look the signature up before "
                  "paying again", burn.key, e.sol_sig)
        state.record(burn.key, {**base_entry, "status": "unconfirmed", "sol_sig": e.sol_sig, "error": str(e)})
        state.add_paid(partner.tag, today, reward)      # count it: it may well have landed
        state.save()
        alert("CorgiCoin bridge: reward for %s was submitted as %s but is not confirmed. Look the signature up before paying again." % (burn.key, e.sol_sig))
        return
    except Exception as e:
        log.error("dispatch failed for %s -> %s: %s — marked dispatch_error, manual review required",
                  burn.key, burn.partner, e)
        state.record(burn.key, {**base_entry, "status": "dispatch_error", "error": str(e)})
        state.save()
        alert("CorgiCoin bridge: payment for %s failed (%s). Manual review needed." % (burn.key, e))
        return

    log.info("dispatched %s %s -> %s (corg tx %s, sol sig %s)",
             reward, partner.tag, burn.sol_dest, burn.key, sol_sig)
    state.record(burn.key, {**base_entry, "status": "dispatched", "sol_sig": sol_sig})
    state.add_paid(partner.tag, today, reward)
    state.save()


# ---------------------------------------------------------------------------
# Reconciliation (operator actions on stuck entries)
# ---------------------------------------------------------------------------

RECONCILABLE_STATUSES = ("pending", "dispatch_error", "unconfirmed", "over_limit", "treasury_low")


def reconcile_list_pending(state: "State") -> int:
    rows = [(t, e) for t, e in state.processed.items()
            if e.get("status") in RECONCILABLE_STATUSES]
    if not rows:
        print("no pending or dispatch_error entries")
        return 0
    for txid, e in rows:
        line = f"{e['status'].upper():15s} {txid}  partner={e.get('partner')}  "\
               f"amount={e.get('amount_corg')}  reward={e.get('reward')}  "\
               f"sol_dest={e.get('sol_dest')}"
        if e.get("status") == "dispatch_error":
            line += f"  error={e.get('error', '?')}"
        print(line)
    return 0


def reconcile_mark_dispatched(state: "State", txid: str, sol_sig: str) -> int:
    entry = state.processed.get(txid)
    if entry is None:
        print(f"error: txid {txid} not found in state.json", file=sys.stderr)
        return 2
    if entry.get("status") == "dispatched":
        print(f"error: txid {txid} is already dispatched (sig={entry.get('sol_sig')})",
              file=sys.stderr)
        return 2
    if entry.get("status") not in RECONCILABLE_STATUSES:
        print(f"error: txid {txid} has status {entry.get('status')!r}, not reconcilable",
              file=sys.stderr)
        return 2
    new_entry = {k: v for k, v in entry.items() if k != "error"}
    new_entry["status"] = "dispatched"
    new_entry["sol_sig"] = sol_sig
    state.record(txid, new_entry)
    state.save()
    print(f"marked {txid} dispatched with sig {sol_sig}")
    return 0


def reconcile_reset(state: "State", txid: str) -> int:
    entry = state.processed.get(txid)
    if entry is None:
        print(f"error: txid {txid} not found in state.json", file=sys.stderr)
        return 2
    if entry.get("status") == "dispatched":
        print(f"error: refusing to reset dispatched entry {txid} "
              f"(would risk double-send on reprocess)", file=sys.stderr)
        return 2
    if entry.get("status") not in RECONCILABLE_STATUSES:
        print(f"error: txid {txid} has status {entry.get('status')!r}, not resettable",
              file=sys.stderr)
        return 2
    burn_height = entry.get("height")
    state.processed.pop(txid)
    # Rewind so the next tick re-scans the block this burn was in. Without
    # this, last_height being past burn_height means the bridge silently
    # skips it forever. Already-processed entries in the rewound range
    # are protected by the already_processed check.
    if isinstance(burn_height, int) and state.last_height >= burn_height:
        state.last_height = max(0, burn_height - 1)
    state.save()
    print(f"reset {txid} (entry removed; last_height={state.last_height} for reprocess)")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--confirmations", type=int, default=DEFAULT_CONFIRMATIONS)
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--once", action="store_true", help="run a single tick and exit")
    rec = parser.add_mutually_exclusive_group()
    rec.add_argument("--list-pending", action="store_true",
                     help="list pending and dispatch_error entries, then exit")
    rec.add_argument("--mark-dispatched", nargs=2, metavar=("TXID", "SOL_SIG"),
                     help="mark a pending/dispatch_error entry as dispatched and exit")
    rec.add_argument("--reset", metavar="TXID",
                     help="delete a pending/dispatch_error entry and rewind for reprocess, then exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    state_path = args.config_dir / "state.json"
    if args.list_pending:
        return reconcile_list_pending(State(state_path))
    if args.mark_dispatched:
        s = State(state_path)
        rc = reconcile_mark_dispatched(s, args.mark_dispatched[0], args.mark_dispatched[1])
        return rc
    if args.reset:
        s = State(state_path)
        return reconcile_reset(s, args.reset)

    rpc = CorgiRPC(
        url=os.environ.get("CORGI_RPC_URL", "http://127.0.0.1:62555"),
        user=os.environ["CORGI_RPC_USER"],
        password=os.environ["CORGI_RPC_PASSWORD"],
    )
    solana = SolanaClient(os.environ.get("SOLANA_RPC_URL", DEFAULT_SOLANA_RPC))
    dispatcher = SolanaDispatcher(solana)

    partners = load_partners(
        args.config_dir / "partners.json",
        args.config_dir / "keys",
    )
    log.info("loaded %d partner(s): %s", len(partners), list(partners.keys()))

    state = State(args.config_dir / "state.json")
    log.info("resuming from height %d (%d burns in log)",
             state.last_height, len(state.processed))

    pending = [t for t, e in state.processed.items() if e.get("status") == "pending"]
    if pending:
        log.warning("%d burn(s) left in 'pending' state from a previous run: %s", len(pending), pending)
        log.warning("these will NOT be auto-retried (would risk double-send). Verify on Solana, "
                    "then edit state.json: set status='dispatched' (with sol_sig) if the reward "
                    "landed, or remove the entry to allow reprocess.")

    stopping = False
    def _stop(*_): nonlocal stopping; stopping = True
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    failures = 0
    while not stopping:
        try:
            tick(rpc, partners, dispatcher, state, args.confirmations)
            failures = 0
        except Exception as e:
            log.exception("tick failed: %s", e)
            failures += 1
            if failures == 5:       # once, not on every try after it
                alert("CorgiCoin bridge: the last %d ticks failed (%s). Is corgicoind or Solana reachable?" % (failures, e))
        if args.once:
            return 0
        for _ in range(args.poll_seconds):
            if stopping: break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
