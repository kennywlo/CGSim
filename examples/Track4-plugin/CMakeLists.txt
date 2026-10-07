# Set up the project.
cmake_minimum_required(VERSION 3.12)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
project( "Track4Plugin" )
option(remote "Enable Remote Build" OFF)

# Disable annoying warnings
add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")

if(NOT remote)
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/CMakeModules/")
endif()

# Find and set the source file.
include_directories(include/)
file(GLOB SOURCES src/*.cpp)

# Set up the library.
add_library(Track4Plugin SHARED ${SOURCES})

# Find SimGrid, CGSim, Boost, and SQLite3
find_package(Boost     REQUIRED)
find_package(SQLite3   REQUIRED)

if(NOT remote)
find_package(SimGrid REQUIRED)
find_package(CGSim REQUIRED)
target_include_directories( Track4Plugin PUBLIC ${SimGrid_INCLUDE_DIR} ${CGSim_INCLUDE_DIR} ${Boost_INCLUDE_DIR})
else()
include_directories(json/include/)
include_directories(../../simgrid/include/ ../../simgrid/build/include/)
include_directories(../../include/ ../../include/util/ ../../include/cgsim/ ../../include/global_managers/ ../../include/core/)
target_include_directories( Track4Plugin PUBLIC ${Boost_INCLUDE_DIR})
endif()

#Link libraries and Include Directories
if(NOT remote)
target_link_libraries ( Track4Plugin PUBLIC ${SimGrid_LIBRARY} ${Boost_LIBRARIES} CGSim::CGSim SQLite::SQLite3)
else()
target_link_libraries ( Track4Plugin PUBLIC ${Boost_LIBRARIES} SQLite::SQLite3 "${CMAKE_SOURCE_DIR}/../../simgrid/build/lib/libsimgrid.so" "${CMAKE_SOURCE_DIR}/../../build/libCGSim.so")
endif()

