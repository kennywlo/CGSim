# Set up the project.
cmake_minimum_required(VERSION 3.12)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
project( "SimpleDispatcherPlugin" )

# Disable annoying warnings
add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/CMakeModules/")

# Find and set the source file.
include_directories(include/)
file(GLOB SOURCES src/*.cpp)

# Set up the library.
add_library(SimpleDispatcherPlugin SHARED ${SOURCES})

# Find SimGrid, SimATLAS, Boost, and FSMod
find_package(SimGrid REQUIRED)
find_package(Boost REQUIRED)
find_package(CGSim REQUIRED)
find_package(spdlog REQUIRED)
find_package(SQLite3   REQUIRED)


#Link libraries and Include Directories
target_link_libraries ( SimpleDispatcherPlugin PUBLIC ${SimGrid_LIBRARY} ${Boost_LIBRARIES} spdlog::spdlog CGSim::CGSim SQLite::SQLite3)
target_include_directories( SimpleDispatcherPlugin PUBLIC ${SimGrid_INCLUDE_DIR} ${CGSim_INCLUDE_DIR} ${Boost_INCLUDE_DIR} ${CMAKE_CURRENT_SOURCE_DIR}/../../json/single_include)


