# STAR — patched, cross-platform build

A minimal patched copy of [**STAR**](https://github.com/alexdobin/STAR)
(v2.7.11b base) that builds and runs natively on **Linux, macOS (Intel + Apple
Silicon), and Windows (x64 + ARM64)**, with a **bundled modern htslib**.
Added support for streaming gzipped files using zlib.

For STAR's documentation, options, and canonical source, see the upstream
repository: <https://github.com/alexdobin/STAR>. Upstream appears unmaintained,
so the portability patches are kept here. **This README covers only how to build
this tree and what was changed** — everything else is unchanged from upstream.

---

## Building from source

**Model:** build the bundled htslib first, then build STAR (which links it). Run
every command **from this directory** (the one containing `Makefile` and
`htslib/`). On Windows the build is **native MinGW** — *not* MSVC, and *not* the
Cygwin-style “MSYS2 MSYS” shell.

### Toolchain / shell per platform

| Platform | Shell / prompt | CC / CXX | `CXXFLAGS_SIMD` | C++ runtime |
|---|---|---|---|---|
| Linux x64 | your terminal | `gcc` / `g++` | `-mavx2` (or `-msse4.1`) | libstdc++ |
| Linux ARM64 | your terminal | `gcc` / `g++` | *(empty → NEON)* | libstdc++ |
| macOS Intel | Terminal | `gcc-14` / `g++-14` (Homebrew) | `-mavx2` (or `-msse4.1`) | libstdc++ |
| macOS Apple Silicon | Terminal | `gcc-14` / `g++-14` (Homebrew) | *(empty → NEON)* | libstdc++ |
| Windows x64 | **MSYS2 UCRT64** | `gcc` / `g++` | `-mavx2` (or `-msse4.1`) | libstdc++ |
| Windows ARM64 | **MSYS2 CLANGARM64** | `clang` / `clang++` | *(empty → SIMDe/NEON)* | libc++ |

Homebrew **GCC** is recommended on macOS (bundles OpenMP; uses libstdc++, avoiding
the Apple-clang `-fopenmp` hassle). Apple clang works too — the libc++ fix below
covers it — but you must supply OpenMP via `libomp`.

### Prerequisites

**Linux (Debian/Ubuntu)**
```bash
sudo apt install build-essential make zlib1g-dev libdeflate-dev
```

**macOS**
```bash
brew install gcc libdeflate      # provides g++-14 (check: ls $(brew --prefix)/bin/g++-*)
```

**Windows — MSYS2** — install from <https://www.msys2.org>, then open the matching
**colored** shell from the Start menu (**“MSYS2 CLANGARM64”** for ARM64,
**“MSYS2 UCRT64”** for x64; not “MSYS2 MSYS”). Install deps (ARM64 names; for x64
swap the prefix `mingw-w64-clang-aarch64-` → `mingw-w64-ucrt-x86_64-`):
```bash
pacman -S --needed \
  mingw-w64-clang-aarch64-clang \
  mingw-w64-clang-aarch64-make \
  mingw-w64-clang-aarch64-zlib \
  mingw-w64-clang-aarch64-libdeflate \
  mingw-w64-clang-aarch64-libsystre \
  mingw-w64-clang-aarch64-gettext \
  mingw-w64-clang-aarch64-libiconv
```
`libsystre` supplies `<regex.h>` (+ `libregex`/`libtre`) for htslib's `hts_expr.c`;
`gettext`/`libiconv` complete the static regex link chain. `parametersDefault.xxd`
is committed, so no `xxd` is needed.

### 1. Build the bundled htslib (all platforms)

```bash
cd htslib
./configure --disable-bz2 --disable-lzma --disable-libcurl --disable-plugins --with-libdeflate
make lib-static          # -> htslib/libhts.a
cd ..
```
On Windows pass the compiler explicitly: `CC=clang ./configure …` (CLANGARM64) or
`CC=gcc ./configure …` (UCRT64).

### 2. Build STAR

**Linux**
```bash
make STAR CXXFLAGS_SIMD=-mavx2 CXXFLAGSextra="-DSTAR_GZ_INPUT" \
  LDFLAGS_shared="-pthread htslib/libhts.a -lz -ldeflate"
# ARM64: CXXFLAGS_SIMD=   (empty)
```

**macOS** (Homebrew GCC; output binary is `STAR`)
```bash
make STARforMacStatic CC=gcc-14 CXX=g++-14 CXXFLAGS_SIMD=-mavx2 \
  CXXFLAGSextra="-DSTAR_GZ_INPUT" LDFLAGSextra="-ldeflate"
# Apple Silicon: CXXFLAGS_SIMD=   (empty)
```

**Windows x64** — in the **MSYS2 UCRT64** shell
```bash
mingw32-make STAR CXXFLAGS_SIMD=-msse4.1 CC=gcc CXX=g++ CXXFLAGSextra="-DSTAR_GZ_INPUT" \
  LDFLAGS_shared="-static -static-libgcc -static-libstdc++ -pthread htslib/libhts.a -lz -ldeflate -lregex -ltre -lintl -liconv -lws2_32 -lpthread"
```

**Windows ARM64** — in the **MSYS2 CLANGARM64** shell
```bash
mingw32-make STAR CXXFLAGS_SIMD= CC=clang CXX=clang++ CXXFLAGSextra="-DSTAR_GZ_INPUT" \
  LDFLAGS_shared="-static -pthread htslib/libhts.a -lz -ldeflate -lregex -ltre -lintl -liconv -lws2_32 -lpthread"
```

Notes:
- `CXXFLAGS_SIMD=` empty on ARM (opal's bundled SIMDe maps AVX2→NEON); `-msse4.1`
  is the widest-compatible x86 target (also runs under Windows-on-ARM x64
  emulation), `-mavx2` is faster on AVX2-capable hosts.
- `-DSTAR_GZ_INPUT` enables reading gzipped **and** plain FASTQ directly (no
  `--readFilesCommand`).
- The Windows `LDFLAGS_shared=` override replaces the Makefile's GNU-ld
  `-Bstatic/-Bdynamic` (which clang misreads) and links `htslib/libhts.a` plus its
  transitive deps directly. The regex chain + `-lws2_32` are Windows-only.
- `-static…` yields a self-contained binary (verify with `ldd` / `otool -L`); drop
  `-static` for a dynamically-linked build.

### 3. Verify

```bash
mkdir idx
./STAR --runMode genomeGenerate --genomeDir idx --genomeFastaFiles ref.fa \
       --genomeSAindexNbases 11 --outFileNamePrefix gg_
./STAR --genomeDir idx --readFilesIn reads.fq.gz --outSAMtype BAM Unsorted \
       --outFileNamePrefix aln_          # gzipped input, no --readFilesCommand
grep "input reads\|Uniquely mapped" aln_Log.final.out    # expect >0 mapped
```
(`--genomeSAindexNbases` = min(14, log2(genomeLength)/2 − 1): ~11 for a small test
genome, 14 for full human.)

### Known limitations on Windows
- `--readFilesCommand <arbitrary cmd>` is unsupported (no `fork`/named pipes on
  native Windows). Gzip is handled internally instead; for other preprocessing,
  transform reads in a separate step.
- Shared-memory genome loading (`--genomeLoad LoadAndKeep`/`Remove`) is
  unsupported; use the default `--genomeLoad NoSharedMemory`.

---

## Patches (vs upstream 2.7.11b)

All changes are `#if`-gated by platform / C++ runtime, so Linux and macOS behave
as upstream except for the libc++ fix (a genuine cross-platform correctness bug).

| File | Change | Reason |
|------|--------|--------|
| `htslib/` | Replaced STAR's ancient bundled htslib with modern **htslib 1.24** (pristine release source) | The old bundle (unconditional `<sys/socket.h>`, `knetfile.c`) does not build on Windows; modern htslib is Windows-aware. |
| `IncludeDefine.h` | Guard `<sys/ipc.h>` / `<sys/shm.h>` / `<sys/mman.h>` under `#if !defined(_WIN32)` | Those SysV/mmap headers do not exist in the Windows/MinGW toolchain. |
| `IncludeDefine.h` | Add `#include <pthread.h>` | STAR uses `pthread_mutex_t`; MinGW needs the explicit include (arrives transitively only on Linux). |
| `IncludeDefine.h` | `#if defined(_WIN32)` shim block: 2-arg `mkdir` overload; `mkfifo`/`symlink`/`statvfs` via `_mkdir`/`CopyFileA`/`GetDiskFreeSpaceExA` (Win32 prototypes declared directly, avoiding `<windows.h>`) | MinGW's `mkdir` is 1-arg; `mkfifo`/`symlink`/`statvfs` are POSIX-only; `<windows.h>` `min`/`max` macros collide with STAR/libc++. |
| `SharedMemory.h` | `typedef int key_t;` on `_WIN32` | MinGW has no SysV `key_t`. |
| `SharedMemory.cpp` | Guard SysV includes; `#if defined(_WIN32)` stub (ctor/dtor/`Allocate`/`Clean`), original SysV impl under `#else` | No SysV shared memory on Windows. Stub compiles and throws only if a shared `--genomeLoad` mode is used; default `NoSharedMemory` never touches it. |
| `streamFuns.cpp` | Guard `#include <sys/statvfs.h>` under `#if !defined(_WIN32)` | No `<sys/statvfs.h>` on Windows (shim is in `IncludeDefine.h`). |
| `Parameters_openReadsFiles.cpp` | `#if defined(_WIN32)` replaces the `vfork`/`execlp` block with a clean error | Native Windows has no `fork`/`exec`; gzip is handled internally instead. |
| `Parameters_closeReadsFiles.cpp` | Guard `kill(pid, SIGKILL)` under `#if !defined(_WIN32)` | No POSIX `kill`/`SIGKILL` on Windows. |
| `STAR.cpp` | On `_WIN32`, set `_fmode = _O_BINARY` at the start of `main()` (+ `<stdio.h>`/`<fcntl.h>`) | Windows text mode truncates binary genome/suffix-array files at the first `0x1A` byte (genomeGenerate failure) and writes CRLF into SAM/logs. |
| `ReadAlignChunk_mapChunk.cpp` | Under `#if defined(_LIBCPP_VERSION)`, load the read chunk with `.str(…)` instead of the `pubsetbuf` set in `ReadAlignChunk()` | **libc++'s `std::stringbuf::pubsetbuf` is a no-op** (libstdc++ honors it), so any clang/libc++ build (macOS default, Windows CLANGARM64) otherwise reports **0 input reads**. Affects upstream STAR too. |
| `GzIfstream.h` *(new)* | A `std::istream` backed by zlib's `gzFile`; binds its streambuf at construction so an unopened stream is `good()` | Reads gzipped **and** plain FASTQ transparently, streaming, no `--readFilesCommand`, no temp file, all platforms. |
| `InOutStreams.h` | Under `#ifdef STAR_GZ_INPUT`, `typedef GzIfstream ReadInFstream` and declare `ReadInFstream readIn[]` (else `std::ifstream`) | Routes read-file input through `GzIfstream` when built with `-DSTAR_GZ_INPUT`. |
| `ReadAlignChunk_processChunks.cpp` | Widen `fastqReadOneLine(ifstream&, …)` to `istream&` | `readIn` is now a base-`istream` (`GzIfstream`); every other read-file call site was unchanged. |
