#!/usr/bin/env python3
"""getheaders across a merged-mined block must not crash the node.

CBlockIndex::GetBlockHeader() carries the AuxPoW version bit (copied from the
block) but not the AuxPoW proof itself -- CBlockIndex only keeps the on-disk
file position, never the CAuxPow object. Serializing a header built that way
used to dereference a null pointer the moment the AuxPoW bit was set, so any
peer could crash a node with a single getheaders whose range covered a
merged-mined block. Fixed by (a) making the serializer throw instead of
dereferencing a null proof, and (b) teaching the getheaders handler (and the
CBlockIndex-based ReadFromDisk shortcut it now reuses) to read the real
block, proof included, from disk for AuxPoW-versioned headers.
"""
import struct

from mininode import P2PConnection, sha256d
from test_framework import CorgiTestFramework, assert_equal, wait_until
from auxpow_builder import build_auxpow

AUXPOW_FORK_REGTEST = 200
CHAIN_ID = 0xC6


def getheaders_payload(hash_stop_hex):
    # CBlockLocator: nVersion(4) + CompactSize(vHave.size()) + vHave[32 each].
    # An empty vHave makes the handler look hashStop up directly (IsNull()),
    # the simplest way to ask for exactly one header. uint256 fields are
    # serialized in internal (reversed) byte order, not the display hex.
    locator = struct.pack("<i", 70001) + b"\x00"
    hash_stop = bytes.fromhex(hash_stop_hex)[::-1]
    return locator + hash_stop


class GetHeadersAuxPowTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        addr = node.getnewaddress()

        self.log("mine past the AuxPoW fork and merge-mine one block")
        node.generate(AUXPOW_FORK_REGTEST)
        work = node.createauxblock(addr)
        proof = build_auxpow(work["hash"], int(work["bits"], 16), CHAIN_ID)
        assert_equal(node.submitauxblock(work["hash"], proof), True)
        aux_hash = node.getbestblockhash()
        assert_equal(aux_hash, work["hash"])
        VERSION_AUXPOW_BIT = 1 << 8
        assert_equal(node.getblockheader(aux_hash)["version"] & VERSION_AUXPOW_BIT != 0, True, "fork block is not AuxPoW-versioned")

        self.log("a plain block on top, so the locator-free single-block path is unambiguous")
        node.generate(1)

        self.log("getheaders for just the merged-mined block used to crash the node")
        peer = P2PConnection(node.p2p_port)
        wait_until(lambda: peer.got_verack, what="handshake")
        peer.send("getheaders", getheaders_payload(aux_hash))

        def got_headers_or_closed():
            return "headers" in peer.messages or peer.closed
        wait_until(got_headers_or_closed, timeout=20, what="a headers reply or a clean disconnect")

        self.log("the node is still up and answers RPCs")
        assert_equal(node.getbestblockhash(), node.getbestblockhash())    # would throw if the daemon died
        assert not peer.closed, "the connection dropped instead of getting a reply"

        self.log("the reply is exactly one header, with the real AuxPoW proof attached (not dropped)")
        assert "headers" in peer.messages, "no headers message arrived"
        payload = peer.messages["headers"][-1]
        count = payload[0]
        assert_equal(count, 1)
        # One serialized CBlock follows: 80-byte header, the AuxPoW proof (since the
        # version bit is set), then the block's own vtx count. In a "headers" reply
        # vtx is always empty, so that trailing count is exactly one byte (0x00) --
        # a protocol fact, not something to infer from this block's AuxPoW bytes.
        # (There is no RPC in this codebase that returns the full raw block --
        # getblock only ever returns JSON -- so the AuxPoW bytes are checked for
        # presence and shape here rather than against an independent raw encoding.)
        block_and_count = payload[1:]
        header_and_auxpow = block_and_count[:-1]
        assert len(header_and_auxpow) > 80, "no AuxPoW proof followed the 80-byte header"
        assert_equal(block_and_count[-1], 0, "a headers reply must carry zero transactions")
        assert_equal(sha256d(header_and_auxpow[:80])[::-1].hex(), aux_hash,
                     "the 80-byte header portion must hash to the block we asked for")

        peer.close()


if __name__ == "__main__":
    GetHeadersAuxPowTest().main()
