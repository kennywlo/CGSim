## Local Build Instructions

Before you begin, ensure you have the following packages installed:

- [**Boost**](https://www.boost.org/)
- [**SimGrid v3.36**](https://framagit.org/simgrid/simgrid/)

Then follow these steps to build the project locally:
   ```bash
   git clone https://github.com/REDWOOD24/CGSim.git
   cd CGSim
   mkdir build
   cd build
   cmake ..
   make -j
   sudo make install
   ```

## Remote Build Instructions
Follow these steps to build the project remotely on a server (with no ```sudo``` privlidges):
   ```bash
   git clone https://github.com/REDWOOD24/CGSim.git
   cd CGSim
   git clone --branch v3.36 https://framagit.org/simgrid/simgrid.git
   cd simgrid
   mkdir build
   cd build
   cmake ..
   make -j
   cd ../../
   mkdir build
   cd build
   cmake -Dremote=ON ..
   make -j
   ```

!!! warning
    It is assumed that the ```boost``` libraries are already installed in this case. If this is not the case, they have to be built remotely as well and paths can be specifed by running ```ccmake ..``` in the build directory.

## Run Instructions

CGSim runs with a configuration file [[see example]](configuration.md) specified with the ```-c``` flag.

   ```bash
   cg-sim -c config.json
   ```
# Installing CGSim on a Server (without sudo)

This guide describes how to build CGSim and its dependencies inside a user home directory on a remote server where `sudo` is unavailable. The procedure was tested on a Debian/Ubuntu-based server with Anaconda's GCC 11.2 toolchain on the `PATH`.

## Overview

| Component | Version | Location after installation |
|---|---|---|
| Boost (all headers, plus the `context` and `stacktrace` libraries) | 1.86.0 | `$HOME/local/boost` |
| SimGrid | v3.36 | `$HOME/CGSim/simgrid/build` |
| CGSim | `main` | `$HOME/CGSim/build` |
| Track4 example plugin (optional) | `main` | `$HOME/CGSim/examples/Track4-plugin/build` |

All commands assume CGSim is cloned into `$HOME`. Adjust the paths if you use a different location.

## Prerequisites

- A C++17 compiler (GCC 7 or newer), CMake 3.12 or newer, `git`, `wget`, and `make`
- SQLite3 development files, which are required only for the Track4 example plugin

To see whether the server already provides Boost, run the following.

```bash
dpkg -l | grep libboost
module avail boost
```

This guide builds a private copy of Boost regardless, so the result does not depend on what the server provides.

## Step 1. Clone CGSim and SimGrid

SimGrid must be cloned inside the CGSim directory, because the remote build expects it at `CGSim/simgrid`.

```bash
cd $HOME
git clone https://github.com/REDWOOD24/CGSim.git
cd CGSim
git clone --branch v3.36 https://framagit.org/simgrid/simgrid.git
```

## Step 2. Build Boost

```bash
cd $HOME
wget https://archives.boost.io/release/1.86.0/source/boost_1_86_0.tar.gz
tar xzf boost_1_86_0.tar.gz
cd boost_1_86_0
./bootstrap.sh --prefix=$HOME/local/boost --with-libraries=context,stacktrace
./b2 -j$(nproc) install
```

All Boost headers are installed regardless of `--with-libraries`. CGSim itself only needs the headers, while SimGrid additionally detects and links the compiled `context` and `stacktrace` libraries.

Confirm that the libraries were installed.

```bash
ls $HOME/local/boost/lib | grep -E "libboost_(context|stacktrace)"
```

After installation, the source directory and tarball are no longer needed and can be removed with `rm -rf $HOME/boost_1_86_0 $HOME/boost_1_86_0.tar.gz`.

## Step 3. Build SimGrid

```bash
cd $HOME/CGSim/simgrid
mkdir -p build && cd build
cmake -DBOOST_ROOT=$HOME/local/boost ..
make -j$(nproc)
```

In the `cmake` output, the section titled "Looking for optional Boost components" should report `context: found`. SimGrid is not installed with `make install`. The CGSim remote build links directly against `simgrid/build/lib/libsimgrid.so`, so this build directory must be kept.

## Step 4. Patch CGSim to link libdl

CGSim loads plugins through `dlopen` and `dlsym`, but its `CMakeLists.txt` does not link `libdl`. On systems with glibc 2.34 or newer these functions are part of `libc`, so the omission goes unnoticed. The Anaconda toolchain uses an older glibc sysroot in which they live in a separate library, and the link fails without this patch.

Run the following command once.

```bash
cd $HOME/CGSim
sed -i 's/^\tBoost::boost$/\tBoost::boost\n\t${CMAKE_DL_LIBS}/' CMakeLists.txt
grep -n -A1 "Boost::boost" CMakeLists.txt
```

Both `Boost::boost` lines should now be followed by a `${CMAKE_DL_LIBS}` line. Running the `sed` command a second time adds duplicate lines, which is harmless but unnecessary.

## Step 5. Build CGSim

```bash
export BOOST_LIBDIR=$HOME/local/boost/lib
export LDFLAGS="$LDFLAGS -Wl,-rpath,$BOOST_LIBDIR -Wl,-rpath-link,$BOOST_LIBDIR"

cd $HOME/CGSim
rm -rf build && mkdir build && cd build
cmake -Dremote=ON -DBOOST_ROOT=$HOME/local/boost ..
make -j$(nproc)
```

`libsimgrid.so` depends on `libboost_context.so.1.86.0`. The `-rpath-link` flag lets the Anaconda linker locate that library while linking `cg-sim`, and the `-rpath` flag records the Boost path inside the binaries so it is also found at runtime without setting `LD_LIBRARY_PATH`.

CMake reads `LDFLAGS` only when a build directory is configured for the first time, which is why the build directory is removed and recreated here. The flags are then stored in `CMakeCache.txt`, so running `make` later in a new shell does not require exporting them again.

A successful build produces `build/cg-sim` and `build/libCGSim.so`.

## Step 6. Build the Track4 example plugin (optional)

Run these commands in the same shell as Step 5 so that `LDFLAGS` is still set.

```bash
cd $HOME/CGSim/examples/Track4-plugin
mkdir -p build && cd build
cmake -Dremote=ON -DBOOST_ROOT=$HOME/local/boost ..
make -j$(nproc)
```

The remote build of the plugin refers to SimGrid and CGSim through the relative paths `../../simgrid` and `../../build`. The plugin must therefore remain inside the CGSim source tree, and CGSim must be built before the plugin. A successful build produces `libTrack4Plugin.so`.

## Step 7. Run a simulation

CGSim is launched with a JSON configuration file passed through the `-c` flag. When using a plugin, set the `Plugin` entry in the configuration to the absolute path of the plugin library.

```json
{
  "Plugin": "/home/<username>/CGSim/examples/Track4-plugin/build/libTrack4Plugin.so"
}
```

Run `cg-sim` from the directory that contains the configuration file, so that any relative paths inside the configuration resolve correctly.

```bash
cd /path/to/config
$HOME/CGSim/build/cg-sim -c track4-config.json
```

## Verifying the installation

```bash
ldd $HOME/CGSim/build/cg-sim | grep -E "not found|simgrid|CGSim|boost"
readelf -d $HOME/CGSim/build/cg-sim | grep -E "RPATH|RUNPATH"
```

The `ldd` output should show resolved paths for `libCGSim.so`, `libsimgrid.so`, and `libboost_context.so.1.86.0`, with no `not found` entries. The `readelf` output should include `$HOME/local/boost/lib` in its expanded form.

## Troubleshooting

| Error message | Cause | Fix |
|---|---|---|
| `undefined reference to symbol 'dlsym@@GLIBC_2.2.5'` followed by `DSO missing from command line` | `libdl` is not linked, and the Anaconda sysroot provides an older glibc | Apply the patch in Step 4, then rerun `make` |
| `warning: libboost_context.so.1.86.0, needed by .../libsimgrid.so, not found` | The linker cannot locate the private Boost libraries | Export `LDFLAGS` as in Step 5, then configure a fresh build directory |
| `undefined reference to 'jump_fcontext'` or `'make_fcontext'` | Same cause as the previous row, since these symbols belong to Boost.Context | Same fix as the previous row |
| `error while loading shared libraries: libboost_context.so.1.86.0` at runtime | The build directory was configured before `LDFLAGS` was exported, so no runtime path was recorded | Rebuild following Step 5, or as a temporary workaround run `export LD_LIBRARY_PATH=$HOME/local/boost/lib:$LD_LIBRARY_PATH` |
| `Could NOT find SQLite3` when configuring the Track4 plugin | SQLite3 development files are not available | Install them, or ask the system administrators to provide a module |

## Maintenance notes

- **Updating CGSim.** The Step 4 patch is a local modification of `CMakeLists.txt`, so `git pull` may report a conflict. Run `git checkout CMakeLists.txt` before pulling, then reapply Step 4 and rebuild.
- **New build directories.** Export `LDFLAGS` as shown in Step 5 before configuring any new CGSim or plugin build directory. Rerunning `make` in an existing build directory does not require it.
- **Directories to keep.** Both `$HOME/local/boost` and `$HOME/CGSim/simgrid/build` are needed at runtime. Removing either one breaks `cg-sim`.

