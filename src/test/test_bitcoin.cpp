#define BOOST_TEST_MODULE Bitcoin Test Suite
#include <boost/test/unit_test.hpp>

#include "main.h"
#include "wallet.h"
#include <memory>

std::unique_ptr<CWallet> pwalletMain;
CClientUIInterface uiInterface;

extern bool fPrintToConsole;
extern void noui_connect();

struct TestingSetup {
    TestingSetup() {
        fPrintToConsole = true; // don't want to write to debug.log file
        noui_connect();
        pwalletMain = std::make_unique<CWallet>();
        RegisterWallet(pwalletMain.get());
    }
    ~TestingSetup()
    {
        pwalletMain.reset();  // Automatic cleanup
    }
};

BOOST_GLOBAL_FIXTURE(TestingSetup);

void Shutdown(void* parg)
{
  exit(0);
}

void StartShutdown()
{
  exit(0);
}

