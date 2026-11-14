// A stand-in for libFuzzer where there is none (gcc, or clang without the fuzzer runtime): replay a corpus, then mutate it.
//
//   FUZZ_TARGET=tx ./fuzz_corgicoin [-runs=N] [-seed=S] [-max_len=L] corpus_dir_or_file ...
//
// Not coverage guided: it does not learn which inputs reach new code. It is enough to run every seed under the sanitizers and to
// throw a few million cheap mutations at a parser, and it needs nothing but the compiler. With clang, build with
// -DBUILD_FUZZ=ON for the real thing.
#ifndef FUZZ_LIBFUZZER

#include "util.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fstream>
#include <iterator>
#include <random>
#include <string>
#include <sys/stat.h>
#include <vector>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size);

extern void noui_connect();

static void Collect(const std::string& path, std::vector<std::vector<uint8_t> >& seeds)
{
    struct stat st;
    if (stat(path.c_str(), &st) != 0)
        return;
    if (S_ISDIR(st.st_mode))
    {
        if (DIR* d = opendir(path.c_str()))
        {
            while (dirent* e = readdir(d))
                if (e->d_name[0] != '.')
                    Collect(path + "/" + e->d_name, seeds);
            closedir(d);
        }
        return;
    }
    std::ifstream f(path, std::ios::binary);
    seeds.emplace_back((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
}

static void Mutate(std::vector<uint8_t>& v, std::mt19937_64& rng, const std::vector<std::vector<uint8_t> >& seeds, size_t nMaxLen)
{
    const int nChanges = 1 + (int)(rng() % 4);
    for (int i = 0; i < nChanges; i++)
    {
        switch (rng() % 7)
        {
        case 0: if (!v.empty()) v[rng() % v.size()] ^= (uint8_t)(1u << (rng() % 8)); break;           // flip a bit
        case 1: if (!v.empty()) v[rng() % v.size()] = (uint8_t)rng(); break;                           // a byte
        case 2: v.insert(v.begin() + (v.empty() ? 0 : rng() % (v.size() + 1)), (uint8_t)rng()); break; // insert
        case 3: if (!v.empty()) v.erase(v.begin() + rng() % v.size()); break;                          // delete
        case 4: if (!v.empty()) v.resize(1 + rng() % v.size()); break;                                 // truncate
        case 5:                                                                                        // a boundary value in a field
            if (v.size() >= 4)
            {
                static const uint32_t kInteresting[] = {0, 1, 0x7f, 0x80, 0xfc, 0xfd, 0xfe, 0xff, 0xffff, 0x10000, 0x7fffffff, 0xffffffff};
                const uint32_t n = kInteresting[rng() % (sizeof(kInteresting) / sizeof(kInteresting[0]))];
                memcpy(&v[rng() % (v.size() - 3)], &n, 4);
            }
            break;
        case 6:                                                                                        // splice in part of another seed
            if (!seeds.empty())
            {
                const std::vector<uint8_t>& other = seeds[rng() % seeds.size()];
                if (!other.empty())
                {
                    const size_t from = rng() % other.size();
                    const size_t len = 1 + rng() % (other.size() - from);
                    v.insert(v.begin() + (v.empty() ? 0 : rng() % (v.size() + 1)), other.begin() + from, other.begin() + from + len);
                }
            }
            break;
        }
    }
    if (v.size() > nMaxLen)
        v.resize(nMaxLen);
}

int main(int argc, char** argv)
{
    // the node logs every error it meets, and the fuzzer is built to meet them: keep the log off the terminal
    fPrintToConsole = true;
    noui_connect();
    if (!freopen("/dev/null", "w", stdout))
        return 2;

    uint64_t nRuns = 100000, nSeed = 1;
    size_t nMaxLen = 4096;
    std::vector<std::string> paths;
    for (int i = 1; i < argc; i++)
    {
        const std::string a = argv[i];
        if (a.rfind("-runs=", 0) == 0) nRuns = strtoull(a.c_str() + 6, nullptr, 10);
        else if (a.rfind("-seed=", 0) == 0) nSeed = strtoull(a.c_str() + 6, nullptr, 10);
        else if (a.rfind("-max_len=", 0) == 0) nMaxLen = (size_t)strtoull(a.c_str() + 9, nullptr, 10);
        else paths.push_back(a);
    }
    std::vector<std::vector<uint8_t> > seeds;
    for (const std::string& p : paths)
        Collect(p, seeds);
    if (seeds.empty())
        seeds.push_back(std::vector<uint8_t>());

    // every seed as it is
    for (const auto& s : seeds)
        LLVMFuzzerTestOneInput(s.data(), s.size());
    fprintf(stderr, "replayed %zu seed(s)\n", seeds.size());

    std::mt19937_64 rng(nSeed);
    for (uint64_t n = 0; n < nRuns; n++)
    {
        std::vector<uint8_t> v = seeds[rng() % seeds.size()];
        Mutate(v, rng, seeds, nMaxLen);
        LLVMFuzzerTestOneInput(v.data(), v.size());
    }
    fprintf(stderr, "done: %llu mutated inputs, no crash\n", (unsigned long long)nRuns);
    return 0;
}

#endif // FUZZ_LIBFUZZER
