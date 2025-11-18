# FindBerkeleyDB.cmake
# -  Finds Berkeley DB library
#
# This module defines:
#  BERKELEYDB_FOUND - System has Berkeley DB
#  BERKELEYDB_INCLUDE_DIR - The Berkeley DB include directory
#  BERKELEYDB_LIBRARY - The Berkeley DB library
#  BERKELEYDB_VERSION - The Berkeley DB version (if detectable)

# Try to find the header
find_path(BERKELEYDB_INCLUDE_DIR
    NAMES db_cxx.h
    PATHS
        /usr/include
        /usr/local/include
        /usr/local/Cellar/berkeley-db/*/include
        /usr/local/Cellar/berkeley-db@5/*/include
        /usr/local/opt/berkeley-db/include
        /opt/local/include
        /opt/include
        $ENV{BERKELEYDB_ROOT}/include
    PATH_SUFFIXES
        db5
        db53
        db6
        bdb
)

# Try to find the library
find_library(BERKELEYDB_LIBRARY
    NAMES
        db_cxx-5.3
        db_cxx-5
        db_cxx-6
        db_cxx-6.2
        db_cxx-18
        db_cxx
        libdb_cxx
    PATHS
        /usr/lib
        /usr/local/lib
        /usr/local/Cellar/berkeley-db/*/lib
        /usr/local/Cellar/berkeley-db@5/*/lib
        /usr/local/opt/berkeley-db/lib
        /opt/local/lib
        /opt/lib
        $ENV{BERKELEYDB_ROOT}/lib
    PATH_SUFFIXES
        db5
        db53
        db6
)

# Try to determine version
if(BERKELEYDB_INCLUDE_DIR AND EXISTS "${BERKELEYDB_INCLUDE_DIR}/db_cxx.h")
    file(STRINGS "${BERKELEYDB_INCLUDE_DIR}/db_cxx.h" BERKELEYDB_VERSION_LINE
        REGEX "^#define[ \t]+DB_VERSION_STRING[ \t]+\".*\"")

    if(BERKELEYDB_VERSION_LINE)
        string(REGEX REPLACE "^#define[ \t]+DB_VERSION_STRING[ \t]+\"Berkeley DB ([0-9.]+):.*\".*" "\\1"
            BERKELEYDB_VERSION "${BERKELEYDB_VERSION_LINE}")
    endif()
endif()

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(BerkeleyDB
    REQUIRED_VARS BERKELEYDB_LIBRARY BERKELEYDB_INCLUDE_DIR
    VERSION_VAR BERKELEYDB_VERSION
)

mark_as_advanced(BERKELEYDB_INCLUDE_DIR BERKELEYDB_LIBRARY)

# Create imported target
if(BERKELEYDB_FOUND AND NOT TARGET BerkeleyDB::BerkeleyDB)
    add_library(BerkeleyDB::BerkeleyDB UNKNOWN IMPORTED)
    set_target_properties(BerkeleyDB::BerkeleyDB PROPERTIES
        IMPORTED_LOCATION "${BERKELEYDB_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${BERKELEYDB_INCLUDE_DIR}"
    )
endif()
