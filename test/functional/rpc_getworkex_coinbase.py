#!/usr/bin/env python3
"""getworkex(data, coinbase): a coinbase that is not one must be refused, and must not change the template other callers get.

A template from getworkex() is kept until the tip moves. The coinbase a caller sent used to be written into it without a check: with no
inputs, the next getworkex() wrote through the empty input list and the node aborted (std::length_error). Now the coinbase must decode, be a
coinbase (one null input) and have an output, and the submission is tried on a copy.
"""
from test_framework import CorgiTestFramework, JSONRPCException, assert_equal

NO_INPUTS = "01000000" + "00" + "00" + "00000000"               # version 1, no inputs, no outputs, lock time 0
NO_INPUTS_ONE_OUTPUT = "01000000" + "00" + "01" + "0000000000000000" + "00" + "00000000"
NOT_A_COINBASE = "01000000" + "01" + "11" * 32 + "00000000" + "00" + "ffffffff" + "01" + "0000000000000000" + "00" + "00000000"
NO_OUTPUT = "01000000" + "01" + "00" * 32 + "ffffffff" + "01" + "51" + "ffffffff" + "00" + "00000000"
BAD = ["01", NO_INPUTS, NO_INPUTS_ONE_OUTPUT, NOT_A_COINBASE, NO_OUTPUT, "ff" * 200]


class GetworkexCoinbaseTest(CorgiTestFramework):
    num_nodes = 1

    def run_test(self):
        node = self.nodes[0]
        node.generate(3)
        template = node.getworkex()
        assert_equal(len(template["coinbase"]) // 2 > 20, True)
        height = node.getblockcount()

        self.log("a coinbase that is not one is refused, or fails the work check, and the node goes on")
        for bad in BAD:
            try:
                result = node.getworkex(template["data"], bad)
                assert_equal(result, False)
            except JSONRPCException as e:
                assert e.error["code"] in (-22, -8), e.error
            assert node.process.poll() is None, "the node exited after getworkex with coinbase %r" % bad
            again = node.getworkex()                  # the old code wrote through the stored template here
            assert_equal(len(again["coinbase"]), len(template["coinbase"]))      # still a coinbase of the same shape: one input, the node's outputs
            assert_equal(node.getblockcount(), height)

        self.log("the template is not changed by what was refused: the same coinbase script, and the work can still be submitted")
        assert_equal(node.getworkex()["merkle"], template["merkle"])
        # the regtest target takes about half of all hashes, and every template has its own extra nonce, so a few tries are enough
        for _ in range(40):
            work = node.getworkex()
            if node.getworkex(work["data"], work["coinbase"]) is True:
                break
        else:
            raise AssertionError("no submission of a good coinbase was accepted in 40 tries")
        assert_equal(node.getblockcount(), height + 1)


if __name__ == "__main__":
    GetworkexCoinbaseTest().main()
