cmake_minimum_required(VERSION 3.12)

message(STATUS "Cmake version ${CMAKE_MAJOR_VERSION}.${CMAKE_MINOR_VERSION}.${CMAKE_PATCH_VERSION}")
project(CGSim VERSION 2.0)

##Remote Build
option(remote "Enable Remote Build" OFF)

# Disable annoying warnings
add_definitions("-DBOOST_ALLOW_DEPRECATED_HEADERS")
set(CMAKE_CXX_STANDARD 17)

if(NOT remote)
set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} "${CMAKE_SOURCE_DIR}/cmake/CMakeModules/")
# Find required packages
find_package(SimGrid REQUIRED)
endif()

find_package(Boost REQUIRED)


# Add json subdir
add_subdirectory(json)
list(APPEND BUILT_PACKAGES "json")

if(NOT remote)
# Include directories
include_directories(${SimGrid_INCLUDE_DIR} ${Boost_INCLUDE_DIR} ${CMAKE_SOURCE_DIR}/json/single_include)
else()
include_directories(${Boost_INCLUDE_DIR} ${CMAKE_SOURCE_DIR}/json/single_include)
include_directories(simgrid/include/ simgrid/build/include/)
endif()

include_directories(include/)
include_directories(include/core/)
include_directories(include/global_managers/)
include_directories(include/util/)
include_directories(include/cgsim/)

# Source files
file(GLOB_RECURSE SOURCE_FILES "src/cgsim/*.cpp" "src/util/*.cpp" "src/core/*.cpp" "src/global_managers/*.cpp")

# Build the library
add_library(CGSim SHARED ${SOURCE_FILES})

# Generating the executable
add_executable(cg-sim src/main.cpp)

if(NOT remote)
target_link_libraries(
	CGSim
	${SimGrid_LIBRARY}
	Boost::boost
)
else()
target_link_libraries(
	CGSim
	"${CMAKE_SOURCE_DIR}/simgrid/build/lib/libsimgrid.so"
	Boost::boost
)
endif()

target_link_libraries(cg-sim CGSim)

# ==============================
# Installation Configuration
# ==============================

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)


# Install Library
install(TARGETS CGSim
    EXPORT CGSimTargets
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
)

# Install header files
install(FILES include/CGSim.h include/global_managers/file_manager.h include/util/logger.h include/cgsim/job.h include/cgsim/plugin.h include/cgsim/site.h include/cgsim/cpu.h include/cgsim/disk.h "include/cgsim/file.h" include/global_managers/resource_manager.h include/global_managers/policy_manager.h include/util/units_parser.h include/util/statistics.h
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/CGSim)

# Install the executable
install(TARGETS cg-sim
        DESTINATION ${CMAKE_INSTALL_BINDIR})

# Export targets to a file
install(EXPORT CGSimTargets
	NAMESPACE CGSim::
    	FILE CGSimTargets.cmake
    	DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/cmake/CGSim
)

# Create a package configuration file
configure_package_config_file(
        "${CMAKE_SOURCE_DIR}/cmake/CGSimConfig.cmake.in"
        "${CMAKE_BINARY_DIR}/CGSimConfig.cmake"
        INSTALL_DESTINATION "${CMAKE_INSTALL_DATAROOTDIR}/cmake/CGSim"
)

install(FILES "${CMAKE_BINARY_DIR}/CGSimConfig.cmake"
        DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/cmake/CGSim)

# Generate a version file
write_basic_package_version_file(
        "${CMAKE_BINARY_DIR}/CGSimConfigVersion.cmake"
        VERSION ${PROJECT_VERSION}
        COMPATIBILITY SameMajorVersion
)

install(FILES "${CMAKE_BINARY_DIR}/CGSimConfigVersion.cmake"
        DESTINATION ${CMAKE_INSTALL_DATAROOTDIR}/cmake/CGSim)
