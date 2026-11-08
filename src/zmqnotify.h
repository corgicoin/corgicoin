#ifndef CORGICOIN_ZMQNOTIFY_H
#define CORGICOIN_ZMQNOTIFY_H

#include <string>

#include "uint256.h"

class CBlock;
class CTransaction;

/**
 * ZeroMQ publish notifications, so pool software can learn about new blocks and transactions the moment they happen
 * instead of polling or waiting for -blocknotify to spawn a process.
 *
 *   -zmqpubhashblock=<address>   32-byte block hash (display byte order) of each new best block
 *   -zmqpubrawblock=<address>    the serialized block
 *   -zmqpubhashtx=<address>      32-byte txid of each transaction entering the memory pool or a connected block
 *   -zmqpubrawtx=<address>       the serialized transaction
 *
 * Every message has three frames: the topic ("hashblock", "rawblock", "hashtx", "rawtx"), the body, and a 4-byte
 * little-endian per-topic sequence number so a subscriber can notice a gap. Several topics may share one address.
 * Compiled in only when libzmq is found at build time; without it ZMQInit() refuses to start if a -zmqpub* option is set.
 */

/** Open the sockets for the -zmqpub* options. False (with a message in strError) if one cannot be bound. */
bool ZMQInit(std::string& strError);
void ZMQShutdown();
bool ZMQEnabled();

/** The best chain now ends at this block. */
void ZMQNotifyBlock(const CBlock& block, const uint256& hash);
void ZMQNotifyTransaction(const CTransaction& tx);

/** Whether a rawblock subscriber exists, so callers can skip reading the block from disk when nobody wants it. */
bool ZMQWantsRawBlock();
bool ZMQWantsHashBlock();

#endif
