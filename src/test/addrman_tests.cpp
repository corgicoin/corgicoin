#include <boost/test/unit_test.hpp>

#include "addrman.h"
#include "serialize.h"
#include "util.h"

using namespace std;

// An address file is a version byte, the key, the counts, then the entries. Build one that stops after the counts and a run
// of zero-size buckets.
static CDataStream MakeFile(int nNew, int nTried, int nUBuckets, int nZeroBuckets)
{
    CDataStream ss(SER_DISK, CLIENT_VERSION);
    unsigned char nVersion = 0;
    ss << nVersion;
    std::vector<unsigned char> vchKey(32, 1);
    ss << vchKey;
    ss << nNew << nTried << nUBuckets;
    for (int i = 0; i < nZeroBuckets; i++)
        ss << (int)0;
    return ss;
}

BOOST_AUTO_TEST_SUITE(addrman_tests)

BOOST_AUTO_TEST_CASE(a_plain_file_loads)
{
    CAddrMan am;
    CDataStream ss = MakeFile(0, 0, ADDRMAN_NEW_BUCKET_COUNT, ADDRMAN_NEW_BUCKET_COUNT);
    BOOST_CHECK_NO_THROW(ss >> am);
}

BOOST_AUTO_TEST_CASE(counts_past_the_tables_are_refused)
{
    // more new-table buckets than there are: used to index past the end of vvNew
    {
        CAddrMan am;
        CDataStream ss = MakeFile(0, 0, ADDRMAN_NEW_BUCKET_COUNT + 44, ADDRMAN_NEW_BUCKET_COUNT + 44);
        BOOST_CHECK_THROW(ss >> am, std::exception);
    }
    // negative and enormous entry counts
    {
        CAddrMan am;
        CDataStream ss = MakeFile(-1, 0, ADDRMAN_NEW_BUCKET_COUNT, ADDRMAN_NEW_BUCKET_COUNT);
        BOOST_CHECK_THROW(ss >> am, std::exception);
    }
    {
        CAddrMan am;
        CDataStream ss = MakeFile(0, 1 << 30, ADDRMAN_NEW_BUCKET_COUNT, ADDRMAN_NEW_BUCKET_COUNT);
        BOOST_CHECK_THROW(ss >> am, std::exception);
    }
}

BOOST_AUTO_TEST_SUITE_END()
