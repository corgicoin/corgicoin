#include <map>
#include <string>
#include <vector>

#include "zmqnotify.h"
#include "main.h"
#include "util.h"
#include "logging.h"

#ifdef ENABLE_ZMQ
#include <zmq.h>

namespace {

struct ZMQTopic
{
    const char* pszName;
    const char* pszOption;
    std::vector<void*> vSockets;        // the publishers this topic is sent on
    uint32_t nSequence = 0;
};

CCriticalSection cs_zmq;                // libzmq sockets are not thread safe, and callers come from several threads
void* pContext = nullptr;
std::map<std::string, void*> mapSockets;   // one publisher per bound address
ZMQTopic topics[] = {
    {"hashblock", "-zmqpubhashblock", {}, 0},
    {"rawblock",  "-zmqpubrawblock",  {}, 0},
    {"hashtx",    "-zmqpubhashtx",    {}, 0},
    {"rawtx",     "-zmqpubrawtx",     {}, 0},
};
ZMQTopic& HashBlock() { return topics[0]; }
ZMQTopic& RawBlock()  { return topics[1]; }
ZMQTopic& HashTx()    { return topics[2]; }
ZMQTopic& RawTx()     { return topics[3]; }

bool SendFrame(void* pSocket, const void* pData, size_t nSize, int nFlags)
{
    zmq_msg_t msg;
    if (zmq_msg_init_size(&msg, nSize) != 0)
        return false;
    if (nSize > 0)
        memcpy(zmq_msg_data(&msg), pData, nSize);
    if (zmq_msg_send(&msg, pSocket, nFlags) == -1)
    {
        zmq_msg_close(&msg);
        return false;
    }
    return true;
}

// topic, body, sequence: all frames or none, never blocking the caller
void Publish(ZMQTopic& topic, const unsigned char* pBody, size_t nBody)
{
    LOCK(cs_zmq);
    if (topic.vSockets.empty())
        return;
    unsigned char seq[4] = {
        (unsigned char)(topic.nSequence), (unsigned char)(topic.nSequence >> 8),
        (unsigned char)(topic.nSequence >> 16), (unsigned char)(topic.nSequence >> 24)};
    topic.nSequence++;
    for (void* pSocket : topic.vSockets)
    {
        if (!SendFrame(pSocket, topic.pszName, strlen(topic.pszName), ZMQ_SNDMORE | ZMQ_DONTWAIT) ||
            !SendFrame(pSocket, pBody, nBody, ZMQ_SNDMORE | ZMQ_DONTWAIT) ||
            !SendFrame(pSocket, seq, sizeof(seq), ZMQ_DONTWAIT))
            LogPrintf("ZMQ: not sent on %s (%s)\n", topic.pszName, zmq_strerror(zmq_errno()));
    }
}

// the hash the way it is printed, not the way it is stored
void PublishHash(ZMQTopic& topic, const uint256& hashIn)
{
    uint256 hash = hashIn;      // begin() is not const
    unsigned char out[32];
    for (int i = 0; i < 32; i++)
        out[31 - i] = hash.begin()[i];
    Publish(topic, out, sizeof(out));
}

} // namespace

bool ZMQEnabled()
{
    LOCK(cs_zmq);
    return pContext != nullptr;
}

bool ZMQWantsRawBlock()
{
    LOCK(cs_zmq);
    return !RawBlock().vSockets.empty();
}

bool ZMQWantsHashBlock()
{
    LOCK(cs_zmq);
    return !HashBlock().vSockets.empty();
}

bool ZMQInit(std::string& strError)
{
    bool fAny = false;
    for (const ZMQTopic& topic : topics)
        fAny |= !GetArg(topic.pszOption, "").empty();
    if (!fAny)
        return true;

    LOCK(cs_zmq);
    pContext = zmq_ctx_new();
    if (pContext == nullptr)
    {
        strError = "ZMQ: could not create a context";
        return false;
    }
    for (ZMQTopic& topic : topics)
    {
        const std::string strAddress = GetArg(topic.pszOption, "");
        if (strAddress.empty())
            continue;
        auto it = mapSockets.find(strAddress);
        if (it == mapSockets.end())
        {
            void* pSocket = zmq_socket(pContext, ZMQ_PUB);
            int nLinger = 0;
            int nHwm = 1000;
            if (pSocket == nullptr)
            {
                strError = std::string("ZMQ: could not create a publisher socket: ") + zmq_strerror(zmq_errno());
                return false;
            }
            zmq_setsockopt(pSocket, ZMQ_LINGER, &nLinger, sizeof(nLinger));
            zmq_setsockopt(pSocket, ZMQ_SNDHWM, &nHwm, sizeof(nHwm));
            if (zmq_bind(pSocket, strAddress.c_str()) != 0)
            {
                strError = strprintf("ZMQ: could not bind %s for %s: %s", strAddress.c_str(), topic.pszOption, zmq_strerror(zmq_errno()));
                zmq_close(pSocket);
                return false;
            }
            it = mapSockets.insert({strAddress, pSocket}).first;
            LogPrintf("ZMQ: publishing on %s\n", strAddress.c_str());
        }
        topic.vSockets.push_back(it->second);
    }
    return true;
}

void ZMQShutdown()
{
    LOCK(cs_zmq);
    for (ZMQTopic& topic : topics)
        topic.vSockets.clear();
    for (auto& item : mapSockets)
        zmq_close(item.second);
    mapSockets.clear();
    if (pContext)
    {
        zmq_ctx_term(pContext);
        pContext = nullptr;
    }
}

void ZMQNotifyBlock(const CBlock& block, const uint256& hash)
{
    if (ZMQWantsHashBlock())
        PublishHash(HashBlock(), hash);
    if (ZMQWantsRawBlock())
    {
        CDataStream ss(SER_NETWORK, PROTOCOL_VERSION);
        ss << block;
        std::vector<unsigned char> vch(ss.begin(), ss.end());
        Publish(RawBlock(), vch.data(), vch.size());
    }
}

void ZMQNotifyTransaction(const CTransaction& tx)
{
    {
        LOCK(cs_zmq);
        if (HashTx().vSockets.empty() && RawTx().vSockets.empty())
            return;
    }
    PublishHash(HashTx(), tx.GetHash());
    {
        LOCK(cs_zmq);
        if (RawTx().vSockets.empty())
            return;
    }
    CDataStream ss(SER_NETWORK, PROTOCOL_VERSION);
    ss << tx;
    std::vector<unsigned char> vch(ss.begin(), ss.end());
    Publish(RawTx(), vch.data(), vch.size());
}

#else   // built without libzmq

bool ZMQInit(std::string& strError)
{
    for (const char* pszOption : {"-zmqpubhashblock", "-zmqpubrawblock", "-zmqpubhashtx", "-zmqpubrawtx"})
        if (!GetArg(pszOption, "").empty())
        {
            strError = strprintf("%s was given but this build has no ZeroMQ support (libzmq was not found when it was built)", pszOption);
            return false;
        }
    return true;
}

void ZMQShutdown() {}
bool ZMQEnabled() { return false; }
bool ZMQWantsRawBlock() { return false; }
bool ZMQWantsHashBlock() { return false; }
void ZMQNotifyBlock(const CBlock&, const uint256&) {}
void ZMQNotifyTransaction(const CTransaction&) {}

#endif
