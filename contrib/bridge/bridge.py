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
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from solana.rpc.api import Client as SolanaClient
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

DEFAULT_CONFIRMATIONS = 10   # devnet PoC depth; revisit before mainnet
DEFAULT_POLL_SECONDS  = 30
DEFAULT_SOLANA_RPC    = "https://api.devnet.solana.com"


# ---------------------------------------------------------------------------
# CorgiCoin JSON-RPC client
# ---------------------------------------------------------------------------

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
        resp.raise_for_status()
        body = resp.json()
        if body.get("error"):
            raise RuntimeError(f"corgicoind RPC error on {method}: {body['error']}")
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

    @classmethod
    def from_config(cls, tag: str, cfg: dict, keys_dir: Path) -> "Partner":
        keypair_path = keys_dir / cfg["treasury_keypair"]
        with keypair_path.open() as f:
            secret = json.load(f)
        return cls(
            tag=tag,
            token_mint=Pubkey.from_string(cfg["token_mint"]),
            decimals=int(cfg["decimals"]),
            reward_ratio=Decimal(str(cfg["reward_ratio"])),
            treasury=Keypair.from_bytes(bytes(secret)),
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
        self.processed: dict[str, dict] = dict(data.get("processed", {}))

    def already_processed(self, txid: str) -> bool:
        return txid in self.processed

    def record(self, txid: str, entry: dict) -> None:
        self.processed[txid] = entry

    def save(self) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp.open("w") as f:
            json.dump({"last_height": self.last_height, "processed": self.processed}, f, indent=2)
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


def extract_burns(rpc: CorgiRPC, txid: str, height: int) -> list[Burn]:
    """Pull the tx, scan every output, delegate parsing to decodeburn RPC."""
    tx = rpc.call("getrawtransaction", txid, 1)
    burns: list[Burn] = []
    for vout in tx.get("vout", []):
        script_hex = vout["scriptPubKey"]["hex"]
        try:
            decoded = rpc.call("decodeburn", script_hex)
        except RuntimeError:
            continue  # not a bridge burn
        burns.append(Burn(
            txid=txid,
            height=height,
            partner=decoded["partner"],
            sol_dest=Pubkey.from_string(decoded["sol_dest_base58"]),
            amount_corg=Decimal(str(vout["value"])),
        ))
    return burns


# ---------------------------------------------------------------------------
# Solana dispatch
# ---------------------------------------------------------------------------

class SolanaDispatcher:
    def __init__(self, client: SolanaClient):
        self._client = client

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
        return str(resp.value)

    def _account_exists(self, pubkey: Pubkey) -> bool:
        info = self._client.get_account_info(pubkey).value
        return info is not None


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def tick(rpc: CorgiRPC, partners: dict[str, Partner], dispatcher: SolanaDispatcher,
         state: State, confirmations: int) -> None:
    tip = int(rpc.call("getblockcount"))
    safe_tip = tip - confirmations
    if safe_tip <= state.last_height:
        return

    for height in range(state.last_height + 1, safe_tip + 1):
        block_hash = rpc.call("getblockhash", height)
        block = rpc.call("getblock", block_hash)
        for txid in block.get("tx", []):
            if state.already_processed(txid):
                continue
            for burn in extract_burns(rpc, txid, height):
                process_burn(burn, partners, dispatcher, state)
        state.last_height = height
        state.save()


def process_burn(burn: Burn, partners: dict[str, Partner],
                 dispatcher: SolanaDispatcher, state: State) -> None:
    partner = partners.get(burn.partner)
    if partner is None:
        log.warning("ignoring burn %s: unknown partner %r", burn.txid, burn.partner)
        state.record(burn.txid, {
            "status": "skipped_unknown_partner",
            "partner": burn.partner, "height": burn.height,
            "amount_corg": str(burn.amount_corg),
        })
        state.save()
        return

    reward = burn.amount_corg * partner.reward_ratio
    try:
        sol_sig = dispatcher.send_reward(partner, burn.sol_dest, reward)
    except Exception as e:
        log.error("dispatch failed for %s -> %s: %s", burn.txid, burn.partner, e)
        # Intentionally do NOT record - next tick will retry.
        return

    log.info("dispatched %s %s -> %s (corg tx %s, sol sig %s)",
             reward, partner.tag, burn.sol_dest, burn.txid, sol_sig)
    state.record(burn.txid, {
        "status": "dispatched",
        "partner": partner.tag,
        "height": burn.height,
        "amount_corg": str(burn.amount_corg),
        "reward": str(reward),
        "sol_dest": str(burn.sol_dest),
        "sol_sig": sol_sig,
    })
    state.save()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--confirmations", type=int, default=DEFAULT_CONFIRMATIONS)
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--once", action="store_true", help="run a single tick and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

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

    stopping = False
    def _stop(*_): nonlocal stopping; stopping = True
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not stopping:
        try:
            tick(rpc, partners, dispatcher, state, args.confirmations)
        except Exception as e:
            log.exception("tick failed: %s", e)
        if args.once:
            return 0
        for _ in range(args.poll_seconds):
            if stopping: break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
