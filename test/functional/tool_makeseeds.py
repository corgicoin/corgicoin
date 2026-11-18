#!/usr/bin/env python3
"""contrib/seeds/makeseeds.py: probes nodes, drops the unusable, and prints pnSeed entries in the byte order net.cpp uses."""
import os
import socket
import struct
import subprocess
import sys

from test_framework import CorgiTestFramework, assert_equal

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "contrib", "seeds", "makeseeds.py")


class MakeSeedsTest(CorgiTestFramework):
    num_nodes = 1

    def seeds(self, candidates, magic="fac0b6da"):
        path = os.path.join(self.nodes[0].datadir, "candidates.txt")
        with open(path, "w") as f:
            f.write(candidates)
        return subprocess.run([sys.executable, SCRIPT, path, "--port", str(self.nodes[0].p2p_port), "--magic", magic,
                               "--timeout", "4"], capture_output=True, text=True)

    def run_test(self):
        self.log("a live node is kept, and written the way net.cpp holds it (104.131.90.19 is 0x135a8368)")
        r = self.seeds("# a comment\n127.0.0.1\n")
        assert_equal(r.returncode, 0)
        assert "0x0100007f,  // 127.0.0.1" in r.stdout, r.stdout
        assert "\n127.0.0.1\n" in r.stdout, r.stdout
        assert_equal(struct.unpack("<I", socket.inet_aton("104.131.90.19"))[0], 0x135a8368)

        self.log("a node that is not there is skipped, with a reason")
        r = self.seeds("127.0.0.2\n")        # nothing listens on this address and port
        assert_equal(r.returncode, 1)
        assert "127.0.0.2: skipped" in r.stderr, r.stderr

        self.log("a node on a different network (other magic bytes) is skipped")
        r = self.seeds("127.0.0.1\n", magic="c0c0c0c0")
        assert_equal(r.returncode, 1)


if __name__ == "__main__":
    MakeSeedsTest().main()
