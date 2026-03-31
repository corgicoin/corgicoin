cmake_minimum_required(VERSION 3.10)

# Use modern find_package behavior
if(POLICY CMP0074)
    cmake_policy(SET CMP0074 NEW)
endif()
if(POLICY CMP0167)
    cmake_policy(SET CMP0167 OLD)
endif()

project(CorgiCoin VERSION 4.0.0.0 LANGUAGES CXX C)

# Add custom CMake modules path
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake/Modules")

# C++ Standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build options
option(BUILD_QT_GUI "Build Qt GUI wallet" ON)
option(USE_UPNP "Enable UPnP support" ON)
option(USE_QRCODE "Enable QR code support" OFF)
option(USE_DBUS "Enable D-Bus support for desktop notifications" OFF)
option(BUILD_TESTS "Build test suite" OFF)
option(ENABLE_HARDENING "Enable security hardening flags" ON)

# Platform detection
if(WIN32)
    set(WINDOWS TRUE)
    add_definitions(-DWIN32)
elseif(APPLE)
    set(MACOSX TRUE)
    add_definitions(-DMAC_OSX -DMSG_NOSIGNAL=0)
else()
    set(LINUX TRUE)
    add_definitions(-DLINUX)
endif()

# Find required dependencies
find_package(Threads REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(BerkeleyDB REQUIRED)

# Boost components
set(Boost_USE_STATIC_LIBS OFF)
set(Boost_USE_MULTITHREADED ON)
set(BOOST_COMPONENTS program_options thread)
if(BUILD_TESTS)
    list(APPEND BOOST_COMPONENTS unit_test_framework)
endif()
find_package(Boost 1.55.0 REQUIRED COMPONENTS ${BOOST_COMPONENTS})

# Optional dependencies
if(USE_UPNP)
    find_library(MINIUPNPC_LIBRARY miniupnpc)
    if(MINIUPNPC_LIBRARY)
        add_definitions(-DUSE_UPNP=1 -DSTATICLIB)
        message(STATUS "Building with UPnP support")
    else()
        message(WARNING "miniupnpc not found, UPnP support disabled")
        set(USE_UPNP OFF)
    endif()
endif()

if(USE_QRCODE)
    find_library(QRENCODE_LIBRARY qrencode)
    if(QRENCODE_LIBRARY)
        add_definitions(-DUSE_QRCODE)
        message(STATUS "Building with QR code support")
    else()
        message(WARNING "qrencode not found, QR code support disabled")
        set(USE_QRCODE OFF)
    endif()
endif()

# Common definitions
add_definitions(
    -DBOOST_SPIRIT_THREADSAFE
    -DBOOST_THREAD_USE_LIB
    -D__NO_SYSTEM_INCLUDES
)

# IPv6 support
add_definitions(-DUSE_IPV6)

# Suppress Boost bind placeholder deprecation warning
add_definitions(-DBOOST_BIND_GLOBAL_PLACEHOLDERS)

# Common compiler flags
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(
        -Wall
        -Wextra
        -Wformat
        -Wformat-security
        -Wno-unused-parameter
        -Wno-deprecated
        -Wno-deprecated-declarations
    )

    # GCC-specific warning suppressions (C++ only — avoid passing to C compiler)
    if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
        add_compile_options($<$<COMPILE_LANGUAGE:CXX>:-Wno-stringop-truncation> $<$<COMPILE_LANGUAGE:CXX>:-Wno-deprecated-copy>)
    endif()

    # Security hardening flags
    if(ENABLE_HARDENING)
        add_compile_options(
            -fstack-protector-all
            -Wstack-protector
            -D_FORTIFY_SOURCE=2
        )

        if(NOT WINDOWS AND NOT MACOSX)
            add_compile_options(-fPIE)
            add_link_options(-pie)

            # GCC 8+ / Clang 7+ additional hardening
            if((CMAKE_CXX_COMPILER_ID STREQUAL "GNU" AND CMAKE_CXX_COMPILER_VERSION VERSION_GREATER_EQUAL 8.0) OR
               (CMAKE_CXX_COMPILER_ID STREQUAL "Clang" AND CMAKE_CXX_COMPILER_VERSION VERSION_GREATER_EQUAL 7.0))
                add_compile_options(-fstack-clash-protection)
            endif()

            add_link_options(
                -Wl,-z,relro
                -Wl,-z,now
            )
        endif()
    endif()
endif()

# Platform-specific settings
if(MACOSX)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "10.13" CACHE STRING "Minimum macOS deployment version")
    set(CMAKE_MACOSX_RPATH ON)
endif()

if(WINDOWS)
    # Windows-specific libraries
    link_libraries(
        ws2_32
        shlwapi
        mswsock
        iphlpapi
        ole32
        oleaut32
        uuid
        gdi32
    )
endif()

# Include directories
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR}/src/json
    ${OPENSSL_INCLUDE_DIR}
    ${Boost_INCLUDE_DIRS}
    ${BERKELEYDB_INCLUDE_DIR}
)

# Source files for daemon
set(DAEMON_SOURCES
    src/version.cpp
    src/checkpoints.cpp
    src/netbase.cpp
    src/addrman.cpp
    src/crypter.cpp
    src/key.cpp
    src/db.cpp
    src/init.cpp
    src/keystore.cpp
    src/main.cpp
    src/net.cpp
    src/protocol.cpp
    src/corgicoinrpc.cpp
    src/rpcdump.cpp
    src/rpcnet.cpp
    src/rpcrawtransaction.cpp
    src/script.cpp
    src/scrypt.c
    src/sync.cpp
    src/util.cpp
    src/wallet.cpp
    src/walletdb.cpp
    src/noui.cpp
)

# Suppress stack protector warning for scrypt.c (uses VLA for scratchpad)
set_source_files_properties(src/scrypt.c PROPERTIES COMPILE_OPTIONS "-Wno-stack-protector")

# JSON library (nlohmann/json with json_spirit compatibility layer)
set(JSON_SOURCES
    src/json/json_compat.cpp
)

# Build info generation — always regenerate to capture git state
add_custom_target(generate_build_info ALL
    COMMAND /bin/sh ${CMAKE_CURRENT_SOURCE_DIR}/share/genbuild.sh ${CMAKE_CURRENT_BINARY_DIR}/build.h
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    COMMENT "Generating build info"
    BYPRODUCTS ${CMAKE_CURRENT_BINARY_DIR}/build.h
)

add_definitions(-DHAVE_BUILD_INFO)
include_directories(${CMAKE_CURRENT_BINARY_DIR})

# Daemon executable
add_executable(corgicoind ${DAEMON_SOURCES} ${JSON_SOURCES})
add_dependencies(corgicoind generate_build_info)

target_link_libraries(corgicoind
    ${OPENSSL_LIBRARIES}
    ${BERKELEYDB_LIBRARY}
    ${Boost_LIBRARIES}
    Threads::Threads
    ${CMAKE_DL_LIBS}
)

if(LINUX)
    target_link_libraries(corgicoind rt)
endif()

if(USE_UPNP)
    target_link_libraries(corgicoind ${MINIUPNPC_LIBRARY})
endif()

# Qt GUI
if(BUILD_QT_GUI)
    # Find Qt (try Qt6 first, fallback to Qt5)
    find_package(Qt6 COMPONENTS Core Gui Widgets Network QUIET)
    if(Qt6_FOUND)
        message(STATUS "Building with Qt6")
        set(QT_VERSION 6)
    else()
        find_package(Qt5 COMPONENTS Core Gui Widgets Network REQUIRED)
        message(STATUS "Building with Qt5")
        set(QT_VERSION 5)
    endif()

    if(USE_DBUS)
        if(QT_VERSION EQUAL 6)
            find_package(Qt6 COMPONENTS DBus QUIET)
            if(Qt6DBus_FOUND)
                add_definitions(-DUSE_DBUS)
                message(STATUS "Building with D-Bus support")
            endif()
        else()
            find_package(Qt5 COMPONENTS DBus QUIET)
            if(Qt5DBus_FOUND)
                add_definitions(-DUSE_DBUS)
                message(STATUS "Building with D-Bus support")
            endif()
        endif()
    endif()

    # QT_GUI and QT_NO_FOREACH are added per-target below (not globally)

    # Qt source files
    set(QT_SOURCES
        src/qt/bitcoin.cpp
        src/qt/bitcoingui.cpp
        src/qt/transactiontablemodel.cpp
        src/qt/addresstablemodel.cpp
        src/qt/optionsdialog.cpp
        src/qt/sendcoinsdialog.cpp
        src/qt/addressbookpage.cpp
        src/qt/signverifymessagedialog.cpp
        src/qt/aboutdialog.cpp
        src/qt/editaddressdialog.cpp
        src/qt/bitcoinaddressvalidator.cpp
        src/qt/clientmodel.cpp
        src/qt/guiutil.cpp
        src/qt/transactionrecord.cpp
        src/qt/optionsmodel.cpp
        src/qt/monitoreddatamapper.cpp
        src/qt/transactiondesc.cpp
        src/qt/transactiondescdialog.cpp
        src/qt/bitcoinstrings.cpp
        src/qt/bitcoinamountfield.cpp
        src/qt/transactionfilterproxy.cpp
        src/qt/transactionview.cpp
        src/qt/walletmodel.cpp
        src/qt/overviewpage.cpp
        src/qt/csvmodelwriter.cpp
        src/qt/sendcoinsentry.cpp
        src/qt/qvalidatedlineedit.cpp
        src/qt/bitcoinunits.cpp
        src/qt/qvaluecombobox.cpp
        src/qt/askpassphrasedialog.cpp
        src/qt/notificator.cpp
        src/qt/qtipcserver.cpp
        src/qt/rpcconsole.cpp
        src/qt/miningpage.cpp
    )

    # Qt headers that need MOC
    set(QT_HEADERS
        src/qt/bitcoingui.h
        src/qt/transactiontablemodel.h
        src/qt/addresstablemodel.h
        src/qt/optionsdialog.h
        src/qt/sendcoinsdialog.h
        src/qt/addressbookpage.h
        src/qt/signverifymessagedialog.h
        src/qt/aboutdialog.h
        src/qt/editaddressdialog.h
        src/qt/bitcoinaddressvalidator.h
        src/qt/clientmodel.h
        src/qt/guiutil.h
        src/qt/transactionrecord.h
        src/qt/optionsmodel.h
        src/qt/monitoreddatamapper.h
        src/qt/transactiondesc.h
        src/qt/transactiondescdialog.h
        src/qt/bitcoinamountfield.h
        src/qt/transactionfilterproxy.h
        src/qt/transactionview.h
        src/qt/walletmodel.h
        src/qt/overviewpage.h
        src/qt/csvmodelwriter.h
        src/qt/sendcoinsentry.h
        src/qt/qvalidatedlineedit.h
        src/qt/bitcoinunits.h
        src/qt/qvaluecombobox.h
        src/qt/askpassphrasedialog.h
        src/qt/notificator.h
        src/qt/qtipcserver.h
        src/qt/miningpage.h
        src/qt/rpcconsole.h
    )

    # Qt UI forms
    set(QT_FORMS
        src/qt/forms/sendcoinsdialog.ui
        src/qt/forms/addressbookpage.ui
        src/qt/forms/signverifymessagedialog.ui
        src/qt/forms/aboutdialog.ui
        src/qt/forms/editaddressdialog.ui
        src/qt/forms/transactiondescdialog.ui
        src/qt/forms/overviewpage.ui
        src/qt/forms/sendcoinsentry.ui
        src/qt/forms/askpassphrasedialog.ui
        src/qt/forms/rpcconsole.ui
        src/qt/forms/miningpage.ui
        src/qt/forms/optionsdialog.ui
    )

    # Qt resources
    set(QT_RESOURCES
        src/qt/bitcoin.qrc
    )

    # Optional QR code dialog
    if(USE_QRCODE)
        list(APPEND QT_SOURCES src/qt/qrcodedialog.cpp)
        list(APPEND QT_HEADERS src/qt/qrcodedialog.h)
        list(APPEND QT_FORMS src/qt/forms/qrcodedialog.ui)
    endif()

    # macOS-specific
    if(MACOSX)
        list(APPEND QT_SOURCES src/qt/macdockiconhandler.mm)
        list(APPEND QT_HEADERS src/qt/macdockiconhandler.h)
        set_source_files_properties(src/qt/macdockiconhandler.mm PROPERTIES
            COMPILE_FLAGS "-x objective-c++"
        )
    endif()

    # AUTOMOC will be set per-target on corgicoin-qt only (not daemon/tests)

    # Process Qt files (qt5_ prefix works for both Qt5 and Qt6 via compatibility)
    if(QT_VERSION EQUAL 6)
        qt_wrap_ui(QT_UI ${QT_FORMS})
        qt_add_resources(QT_QRC ${QT_RESOURCES})
    else()
        qt5_wrap_ui(QT_UI ${QT_FORMS})
        qt5_add_resources(QT_QRC ${QT_RESOURCES})
    endif()

    include_directories(
        ${CMAKE_CURRENT_SOURCE_DIR}/src/qt
        ${CMAKE_CURRENT_BINARY_DIR}
    )

    # Exclude noui.cpp for GUI build
    set(GUI_DAEMON_SOURCES ${DAEMON_SOURCES})
    list(REMOVE_ITEM GUI_DAEMON_SOURCES src/noui.cpp)

    # GUI executable
    if(MACOSX)
        add_executable(corgicoin-qt MACOSX_BUNDLE
            ${GUI_DAEMON_SOURCES}
            ${JSON_SOURCES}
            ${QT_SOURCES}
            ${QT_UI}
            ${QT_QRC}
        )
        set_target_properties(corgicoin-qt PROPERTIES
            MACOSX_BUNDLE_INFO_PLIST ${CMAKE_CURRENT_SOURCE_DIR}/contrib/macdeploy/Info.plist
            MACOSX_BUNDLE_ICON_FILE corgicoin.icns
        )
        # Copy icon to bundle
        set(ICON_FILE ${CMAKE_CURRENT_SOURCE_DIR}/src/qt/res/icons/corgicoin.icns)
        set_source_files_properties(${ICON_FILE} PROPERTIES
            MACOSX_PACKAGE_LOCATION Resources
        )
        target_sources(corgicoin-qt PRIVATE ${ICON_FILE})
    else()
        add_executable(corgicoin-qt
            ${GUI_DAEMON_SOURCES}
            ${JSON_SOURCES}
            ${QT_SOURCES}
            ${QT_UI}
            ${QT_QRC}
        )
    endif()

    set_target_properties(corgicoin-qt PROPERTIES AUTOMOC ON)
    target_compile_definitions(corgicoin-qt PRIVATE QT_GUI QT_NO_FOREACH)
    add_dependencies(corgicoin-qt generate_build_info)

    # Link Qt libraries (Qt::Core etc. works for both Qt5.15+ and Qt6)
    target_link_libraries(corgicoin-qt
        Qt::Core
        Qt::Gui
        Qt::Widgets
        Qt::Network
    )
    if(USE_DBUS)
        if(QT_VERSION EQUAL 6 AND Qt6DBus_FOUND)
            target_link_libraries(corgicoin-qt Qt::DBus)
        elseif(QT_VERSION EQUAL 5 AND Qt5DBus_FOUND)
            target_link_libraries(corgicoin-qt Qt::DBus)
        endif()
    endif()

    # Link other libraries
    target_link_libraries(corgicoin-qt
        ${OPENSSL_LIBRARIES}
        ${BERKELEYDB_LIBRARY}
        ${Boost_LIBRARIES}
        Threads::Threads
        ${CMAKE_DL_LIBS}
    )

    if(LINUX)
        target_link_libraries(corgicoin-qt rt)
    endif()

    if(MACOSX)
        target_link_libraries(corgicoin-qt
            "-framework Foundation"
            "-framework ApplicationServices"
            "-framework AppKit"
        )
    endif()

    if(USE_UPNP)
        target_link_libraries(corgicoin-qt ${MINIUPNPC_LIBRARY})
    endif()

    if(USE_QRCODE)
        target_link_libraries(corgicoin-qt ${QRENCODE_LIBRARY})
    endif()
endif()

# Test suite
if(BUILD_TESTS)
    enable_testing()

    set(TEST_SOURCES
        src/test/test_bitcoin.cpp
        src/test/Checkpoints_tests.cpp
        src/test/DoS_tests.cpp
        src/test/base32_tests.cpp
        src/test/base58_tests.cpp
        src/test/base64_tests.cpp
        src/test/bignum_tests.cpp
        src/test/getarg_tests.cpp
        src/test/key_tests.cpp
        src/test/miner_tests.cpp
        src/test/mruset_tests.cpp
        src/test/multisig_tests.cpp
        src/test/netbase_tests.cpp
        src/test/rpc_tests.cpp
        src/test/script_P2SH_tests.cpp
        src/test/script_tests.cpp
        src/test/sigopcount_tests.cpp
        src/test/transaction_tests.cpp
        src/test/uint160_tests.cpp
        src/test/uint256_tests.cpp
        src/test/util_tests.cpp
        src/test/wallet_tests.cpp
        src/test/scrypt_tests.cpp
        src/test/address_tests.cpp
        src/test/blockreward_tests.cpp
        src/test/serialize_tests.cpp
    )

    # Tests use the daemon sources minus init.cpp (test_bitcoin.cpp provides its own main/setup)
    set(TEST_DAEMON_SOURCES ${DAEMON_SOURCES})
    list(REMOVE_ITEM TEST_DAEMON_SOURCES src/init.cpp)

    add_executable(test_corgicoin ${TEST_SOURCES} ${TEST_DAEMON_SOURCES} ${JSON_SOURCES})
    add_dependencies(test_corgicoin generate_build_info)
    target_compile_definitions(test_corgicoin PRIVATE
        TEST_DATA_DIR=${CMAKE_CURRENT_SOURCE_DIR}/src/test/data
    )

    target_link_libraries(test_corgicoin
        ${OPENSSL_LIBRARIES}
        ${BERKELEYDB_LIBRARY}
        ${Boost_LIBRARIES}
        Threads::Threads
        ${CMAKE_DL_LIBS}
    )

    if(LINUX)
        target_link_libraries(test_corgicoin rt)
    endif()

    if(USE_UPNP)
        target_link_libraries(test_corgicoin ${MINIUPNPC_LIBRARY})
    endif()

    add_test(NAME corgicoin_tests COMMAND test_corgicoin)
endif()

# Installation
install(TARGETS corgicoind DESTINATION bin)

if(BUILD_QT_GUI)
    if(MACOSX)
        install(TARGETS corgicoin-qt BUNDLE DESTINATION .)
    else()
        install(TARGETS corgicoin-qt DESTINATION bin)
    endif()
endif()

# Print configuration summary
message(STATUS "")
message(STATUS "CorgiCoin Configuration Summary:")
message(STATUS "  Version:              ${PROJECT_VERSION}")
message(STATUS "  C++ Standard:         C++${CMAKE_CXX_STANDARD}")
message(STATUS "  Build type:           ${CMAKE_BUILD_TYPE}")
message(STATUS "  Platform:             ${CMAKE_SYSTEM_NAME}")
message(STATUS "")
message(STATUS "Build Options:")
message(STATUS "  Qt GUI:               ${BUILD_QT_GUI}")
message(STATUS "  UPnP support:         ${USE_UPNP}")
message(STATUS "  QR code support:      ${USE_QRCODE}")
message(STATUS "  D-Bus support:        ${USE_DBUS}")
message(STATUS "  Security hardening:   ${ENABLE_HARDENING}")
message(STATUS "  Tests:                ${BUILD_TESTS}")
message(STATUS "")
message(STATUS "Dependencies:")
message(STATUS "  OpenSSL:              ${OPENSSL_VERSION}")
message(STATUS "  Boost:                ${Boost_VERSION}")
message(STATUS "  Berkeley DB:          ${BERKELEYDB_VERSION}")
if(BUILD_QT_GUI)
    if(QT_VERSION EQUAL 6)
        message(STATUS "  Qt:                   ${Qt6_VERSION}")
    else()
        message(STATUS "  Qt:                   ${Qt5_VERSION}")
    endif()
endif()
message(STATUS "")
message(STATUS "Note: CorgiCoin v4.0.0.0 — modernized codebase (C++17, OpenSSL 3.x, Qt 5/6)")
message(STATUS "  Genesis block not yet mined — network is not live.")
message(STATUS "")
