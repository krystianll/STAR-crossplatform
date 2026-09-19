# STAR — patched, cross-platform build (work in progress)

A minimal patched copy of [**STAR**](https://github.com/alexdobin/STAR)
(v2.7.11b base) that builds and runs natively on **Linux, macOS (Intel + Apple
Silicon), and Windows (x64 + ARM64)**, with a **bundled modern htslib**.

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
| Linux x64 | your terminal | `gcc` / `g++` | `-mavx2` | libstdc++ |
| Linux ARM64 | your terminal | `gcc` / `g++` | *(empty → NEON)* | libstdc++ |
| macOS Intel | Terminal | Homebrew GCC (auto-detected `$CC`/`$CXX`) | `-mavx2` | libstdc++ |
| macOS Apple Silicon | Terminal | Homebrew GCC (auto-detected `$CC`/`$CXX`) | *(empty → NEON)* | libstdc++ |
| Windows x64 | **MSYS2 UCRT64** | `gcc` / `g++` | `-mavx2` | libstdc++ |
| Windows ARM64 | **MSYS2 CLANGARM64** | `clang` / `clang++` | *(empty → SIMDe/NEON)* | libc++ |

Homebrew **GCC** is recommended on macOS (bundles OpenMP; uses libstdc++, avoiding
the Apple-clang `-fopenmp` hassle). Apple clang works too — the libc++ fix below
covers it — but you must supply OpenMP via `libomp`.

Each platform section below is **self-contained**: install deps, build the
bundled htslib, then build STAR — all run from **this directory** (the one with
`Makefile` and `htslib/`). libdeflate is used everywhere (faster BGZF). Confirm
the result with the shared *Verify* step at the end.

### Linux — x86-64

```bash
sudo apt install build-essential make zlib1g-dev libdeflate-dev     # Debian/Ubuntu

cd htslib
./configure --with-libdeflate --disable-bz2 --disable-lzma --disable-libcurl --disable-plugins
make lib-static
cd ..

make STAR CXXFLAGS_SIMD=-mavx2 CXXFLAGSextra="-DSTAR_GZ_INPUT" \
  LDFLAGS_shared="-pthread htslib/libhts.a -lz -ldeflate"
```

### Linux — ARM64 (aarch64)

Same as x86-64, only the SIMD flag differs (opal's bundled SIMDe maps AVX2 → NEON):

```bash
sudo apt install build-essential make zlib1g-dev libdeflate-dev

cd htslib
./configure --with-libdeflate --disable-bz2 --disable-lzma --disable-libcurl --disable-plugins
make lib-static
cd ..

make STAR CXXFLAGS_SIMD= CXXFLAGSextra="-DSTAR_GZ_INPUT" \
  LDFLAGS_shared="-pthread htslib/libhts.a -lz -ldeflate"
```

### macOS — Apple Silicon (arm64)

Uses Homebrew GCC (bundles OpenMP, uses libstdc++). `$CC`/`$CXX` are detected so no
GCC version is hardcoded; libdeflate is linked statically by path so the binary is
self-contained. The `CPPFLAGS`/`LDFLAGS` point `configure` at Homebrew
(`configure` doesn't search `/opt/homebrew` on its own).

```bash
brew install gcc libdeflate
export CC=$(ls "$(brew --prefix gcc)"/bin/gcc-[0-9]* | sort -V | tail -1)
export CXX=$(ls "$(brew --prefix gcc)"/bin/g++-[0-9]* | sort -V | tail -1)

cd htslib
CC="$CC" CPPFLAGS="-I$(brew --prefix)/include" LDFLAGS="-L$(brew --prefix)/lib" \
  ./configure --with-libdeflate --disable-bz2 --disable-lzma --disable-libcurl --disable-plugins
make lib-static CC="$CC"
cd ..

make STARforMacStatic CC="$CC" CXX="$CXX" CXXFLAGS_SIMD= \
  CXXFLAGSextra="-DSTAR_GZ_INPUT" LDFLAGSextra="$(brew --prefix)/lib/libdeflate.a"
```

### macOS — Intel (x86-64)

Same as Apple Silicon, only the SIMD flag differs:

```bash
brew install gcc libdeflate
export CC=$(ls "$(brew --prefix gcc)"/bin/gcc-[0-9]* | sort -V | tail -1)
export CXX=$(ls "$(brew --prefix gcc)"/bin/g++-[0-9]* | sort -V | tail -1)

cd htslib
CC="$CC" CPPFLAGS="-I$(brew --prefix)/include" LDFLAGS="-L$(brew --prefix)/lib" \
  ./configure --with-libdeflate --disable-bz2 --disable-lzma --disable-libcurl --disable-plugins
make lib-static CC="$CC"
cd ..

make STARforMacStatic CC="$CC" CXX="$CXX" CXXFLAGS_SIMD=-mavx2 \
  CXXFLAGSextra="-DSTAR_GZ_INPUT" LDFLAGSextra="$(brew --prefix)/lib/libdeflate.a"
```

### Windows — x64  (MSYS2 **UCRT64** shell)

Install MSYS2 (<https://www.msys2.org>) and open the **"MSYS2 UCRT64"** shell
(*not* "MSYS2 MSYS"). The build tool is `mingw32-make`.

```bash
pacman -S --needed \
  mingw-w64-ucrt-x86_64-gcc  mingw-w64-ucrt-x86_64-make \
  mingw-w64-ucrt-x86_64-zlib mingw-w64-ucrt-x86_64-libdeflate \
  mingw-w64-ucrt-x86_64-libsystre mingw-w64-ucrt-x86_64-gettext mingw-w64-ucrt-x86_64-libiconv

cd htslib
CC=gcc ./configure --with-libdeflate --disable-bz2 --disable-lzma --disable-libcurl --disable-plugins
make lib-static
cd ..

mingw32-make STAR CXXFLAGS_SIMD=-mavx2 CC=gcc CXX=g++ CXXFLAGSextra="-DSTAR_GZ_INPUT" \
  LDFLAGS_shared="-static -static-libgcc -static-libstdc++ -pthread htslib/libhts.a -lz -ldeflate -lregex -ltre -lintl -liconv -lws2_32 -lpthread"
```
For pre-AVX2 hardware, build with `CXXFLAGS_SIMD=-msse4.1` instead.

### Windows — ARM64  (MSYS2 **CLANGARM64** shell)

Open the **"MSYS2 CLANGARM64"** shell.

```bash
pacman -S --needed \
  mingw-w64-clang-aarch64-clang mingw-w64-clang-aarch64-make \
  mingw-w64-clang-aarch64-zlib  mingw-w64-clang-aarch64-libdeflate \
  mingw-w64-clang-aarch64-libsystre mingw-w64-clang-aarch64-gettext mingw-w64-clang-aarch64-libiconv

cd htslib
CC=clang ./configure --with-libdeflate --disable-bz2 --disable-lzma --disable-libcurl --disable-plugins
make lib-static
cd ..

mingw32-make STAR CXXFLAGS_SIMD= CC=clang CXX=clang++ CXXFLAGSextra="-DSTAR_GZ_INPUT" \
  LDFLAGS_shared="-static -pthread htslib/libhts.a -lz -ldeflate -lregex -ltre -lintl -liconv -lws2_32 -lpthread"
```

On Windows, `libsystre`/`gettext`/`libiconv` supply the POSIX regex chain htslib's
`hts_expr.c` needs, and `-lws2_32` is Winsock (used by htslib's file layer).
`parametersDefault.xxd` is committed, so no `xxd` is required.

### Verify (any platform)

```bash
mkdir idx
./STAR --runMode genomeGenerate --genomeDir idx --genomeFastaFiles ref.fa \
       --genomeSAindexNbases 11 --outFileNamePrefix gg_
./STAR --genomeDir idx --readFilesIn reads.fq.gz --outSAMtype BAM Unsorted \
       --outFileNamePrefix aln_          # gzipped input, no --readFilesCommand
grep "input reads\|Uniquely mapped" aln_Log.final.out    # expect >0 mapped
```
(`--genomeSAindexNbases` = min(14, log2(genomeLength)/2 − 1): ~11 for a small test
genome, 14 for full human. The binary is self-contained — check with `ldd`
(Linux/Windows) or `otool -L` (macOS); only system libraries should appear.)

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
| `htslib/` | Replaced STAR's legacy bundled htslib with **htslib 1.24** | The old bundle (unconditional `<sys/socket.h>`, `knetfile.c`) does not build on Windows; modern htslib is Windows-aware. |
| `IncludeDefine.h` | Guard `<sys/ipc.h>` / `<sys/shm.h>` / `<sys/mman.h>` under `#if !defined(_WIN32)` | Those SysV/mmap headers do not exist in the Windows/MinGW toolchain. |
| `IncludeDefine.h` | Add `#include <pthread.h>` | STAR uses `pthread_mutex_t`; MinGW needs the explicit include (arrives transitively only on Linux). |
| `IncludeDefine.h` | `#if defined(_WIN32)` shim block: 2-arg `mkdir` overload; `mkfifo`/`symlink`/`statvfs` via `_mkdir`/`CopyFileA`/`GetDiskFreeSpaceExA` (Win32 prototypes declared directly, avoiding `<windows.h>`) | MinGW's `mkdir` is 1-arg; `mkfifo`/`symlink`/`statvfs` are POSIX-only; `<windows.h>` `min`/`max` macros collide with STAR/libc++. |
| `SharedMemory.h` | `typedef int key_t;` on `_WIN32` | MinGW has no SysV `key_t`. |
| `SharedMemory.cpp` | Guard SysV includes; `#if defined(_WIN32)` stub (ctor/dtor/`Allocate`/`Clean`), original SysV impl under `#else` | No SysV shared memory on Windows. Stub compiles and throws only if a shared `--genomeLoad` mode is used; default `NoSharedMemory` never touches it. |
| `streamFuns.cpp` | Guard `#include <sys/statvfs.h>` under `#if !defined(_WIN32)` | No `<sys/statvfs.h>` on Windows (shim is in `IncludeDefine.h`). |
| `Parameters_openReadsFiles.cpp` | `#if defined(_WIN32)` replaces the `vfork`/`execlp` block with a clean error | Native Windows has no `fork`/`exec`; gzip is handled internally instead. |
| `Parameters_closeReadsFiles.cpp` | Guard `kill(pid, SIGKILL)` under `#if !defined(_WIN32)` | No POSIX `kill`/`SIGKILL` on Windows. |
| `STAR.cpp` | On `_WIN32`, set `_fmode = _O_BINARY` at the start of `main()` (+ `<stdio.h>`/`<fcntl.h>`/`<io.h>`), and `_setmode` `stdout`/`stdin` to `_O_BINARY` | Windows text mode truncates binary genome/suffix-array files at the first `0x1A` byte (genomeGenerate failure) and writes CRLF into SAM/logs. `_fmode` only covers files opened afterwards, so the pre-opened std streams need `_setmode`, else `--outStd SAM` injects CRLF and `--outStd BAM_*` corrupts the piped BAM (`0x0A`→`0x0D0A`). |
| `Genome_genomeGenerate.cpp` | On `_WIN32`, `flush()`/`close()` the `Log.out` stream before moving it into the genome dir, then reopen it (append) | Windows cannot `rename()` a file that is still open (POSIX can), so genomeGenerate otherwise prints a spurious "Could not move Log.out" warning and leaves the log in the run dir. |
| `BAMoutput.h` / `BAMoutput.cpp` / `bamSortByCoordinate.cpp` | On `_WIN32`, add `BAMoutput::closeBins()` and call it after sorting to close the coord bin write-streams | The bin temp streams are only flushed, never closed; Windows cannot delete a still-open file, so `sysRemoveDir()` otherwise leaves the `_STARtmp/BAMsort` files/dirs behind after `--outSAMtype BAM SortedByCoordinate`. |
| `Transcriptome.cpp` | On `_WIN32`, if the chosen transcript-info dir lacks `geneInfo.tab`, fall back to the genome dir | On Windows the on-the-fly `_STARgenome` (`sjdbInsert.outDir`) is sometimes not produced, so `--quantMode GeneCounts` fails to open `geneInfo.tab`; the genome dir always has it when the index was built with `--sjdbGTFfile`. |
| `ReadAlignChunk_mapChunk.cpp` | Under `#if defined(_LIBCPP_VERSION)`: (a) load the read chunk with `.str(…)` instead of the `pubsetbuf` set in `ReadAlignChunk()`; (b) write the SAM chunk from `chunkOutBAMstream->str()` instead of the `pubsetbuf`-backed `chunkOutBAM` at all three write sites | **libc++'s `std::stringbuf::pubsetbuf` is a no-op** (libstdc++ honors it). On input this reports **0 reads**; on `--outSAMtype SAM` output the buffer stays zeroed so the file is **NUL-filled** (BAM output uses a separate path and is fine). Affects upstream STAR too. |
| `GzIfstream.h` *(new)* | A `std::istream` backed by zlib's `gzFile` that transparently reads plain **or** gzipped FASTQ, streaming; binds its streambuf at construction so an unopened stream is `good()`. `openMulti` opens a **list** of files, decompressing each and concatenating them in `underflow()` | **Adds native streaming gzip input**: `.gz` reads work directly, with no `--readFilesCommand`, no external process, and no temp file, on all platforms — including STAR's comma-separated multi-file `--readFilesIn`. |
| `InOutStreams.h` | Under `#ifdef STAR_GZ_INPUT`, `typedef GzIfstream ReadInFstream` and declare `ReadInFstream readIn[]` (else `std::ifstream`) | Routes read-file input through `GzIfstream` when built with `-DSTAR_GZ_INPUT`. |
| `ReadAlignChunk_processChunks.cpp` | Widen `fastqReadOneLine(ifstream&, …)` to `istream&` | `readIn` is now a base-`istream` (`GzIfstream`); every other read-file call site was unchanged. |
| `Parameters_readFilesInit.cpp` | Under `#ifdef STAR_GZ_INPUT`, keep `readFilesCommandString` empty in the default (`--readFilesCommand -`) case even for multiple files | Multiple comma-separated files are concatenated and decompressed by `GzIfstream` itself, so no external `cat`/fifo is used (works on Windows too, which has no `fork`/fifo). |
| `Parameters_openReadsFiles.cpp` | Under `#ifdef STAR_GZ_INPUT`, the empty-command branch `stat()`s each split file then opens the whole per-mate list via `readIn[imate].openMulti(readFilesNames[imate])` | Streams/decompresses every comma-separated file through one `GzIfstream`, which re-emits upstream's `FILE <n>` boundary markers so `readFilesIndex` still advances across the list — per-file `--outSAMattrRGline` read groups and STARsolo per-file barcode indexing work as upstream. |

---

## Redistribution & licensing

The recipes above produce a **static** binary intended for personal use.

- **Own use:** the static binary is fine as-is.
- **Redistributing the binary:** bundle the license texts + copyright notices of
  everything compiled in — STAR (MIT), the bundled htslib/htscodecs (MIT/BSD),
  zlib, libdeflate. On Windows the POSIX-regex chain statically links
  **gettext/libiconv (LGPL)**; the LGPL relink clause is most easily satisfied by
  building **without `-static`** so those become replaceable DLLs, then bundling
  every DLL's license.
