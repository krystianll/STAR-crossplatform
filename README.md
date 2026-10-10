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
sudo apt install build-essential make zlib1g-dev libbz2-dev libdeflate-dev     # Debian/Ubuntu

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
sudo apt install build-essential make zlib1g-dev libbz2-dev libdeflate-dev

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
  mingw-w64-ucrt-x86_64-zlib mingw-w64-ucrt-x86_64-bzip2 mingw-w64-ucrt-x86_64-libdeflate \
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
  mingw-w64-clang-aarch64-zlib  mingw-w64-clang-aarch64-bzip2 mingw-w64-clang-aarch64-libdeflate \
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
       --outFileNamePrefix aln_          # gzipped input, no --readFilesCommand (.bz2 works the same way)
grep "input reads\|Uniquely mapped" aln_Log.final.out    # expect >0 mapped
```
(`--genomeSAindexNbases` = min(14, log2(genomeLength)/2 − 1): ~11 for a small test
genome, 14 for full human. The binary is self-contained — check with `ldd`
(Linux/Windows) or `otool -L` (macOS); only system libraries should appear.)

### Known limitations on Windows
- `--readFilesCommand <arbitrary cmd>` is unsupported (no `fork`/named pipes on
  native Windows). Gzip and bzip2 are handled internally instead; for other preprocessing,
  transform reads in a separate step.
- Paths outside the active Windows ANSI code page are not supported by the current narrow-character filesystem interfaces; Unicode path support remains open.
- Shared-memory genome loading (`--genomeLoad LoadAndKeep`/`Remove`) is
  unsupported; use the default `--genomeLoad NoSharedMemory`.

---

## Patches (vs upstream 2.7.11b)

Windows compatibility changes are `#if`-gated by platform / C++ runtime; native
gzip input is enabled with `STAR_GZ_INPUT`. The small upstream fixes for
`outQuant`, `mutexLogMain`, CRLF FASTQ headers, and `BAM_Quant` stdout apply to
all platforms and are deliberately unguarded. See the detailed
[portability audit](tests/PORTABILITY_AUDIT_2026-09-19.md) for evidence, coverage,
and remaining limits, and the [second audit](tests/PORTABILITY_AUDIT_2026-09-19_ROUND2.md)
for resource limits, UNC paths, and additional file-lifetime checks.

| File | Change | Reason |
|------|--------|--------|
| `htslib/` | Replaced STAR's legacy bundled htslib with **htslib 1.24** | The old bundle (unconditional `<sys/socket.h>`, `knetfile.c`) does not build on Windows; modern htslib is Windows-aware. |
| `IncludeDefine.h` | Guard `<sys/ipc.h>` / `<sys/shm.h>` / `<sys/mman.h>` under `#if !defined(_WIN32)` | Those SysV/mmap headers do not exist in the Windows/MinGW toolchain. |
| `IncludeDefine.h` | Add `#include <pthread.h>` | STAR uses `pthread_mutex_t`; MinGW needs the explicit include (arrives transitively only on Linux). |
| `IncludeDefine.h` | `#if defined(_WIN32)` shim block: 2-arg `mkdir` overload; `mkfifo`/`symlink`/`statvfs` via `_mkdir`/`CopyFileA`/`GetDiskFreeSpaceExA` (querying the requested file's volume; Win32 prototypes declared directly, avoiding `<windows.h>`) | MinGW's `mkdir` is 1-arg; `mkfifo`/`symlink`/`statvfs` are POSIX-only; `<windows.h>` `min`/`max` macros collide with STAR/libc++. |
| `SharedMemory.h` | `typedef int key_t;` on `_WIN32` | MinGW has no SysV `key_t`. |
| `SharedMemory.cpp` | Guard SysV includes; `#if defined(_WIN32)` stub (ctor/dtor/`Allocate`/`Clean`), original SysV impl under `#else` | No SysV shared memory on Windows. Stub compiles and throws only if a shared `--genomeLoad` mode is used; default `NoSharedMemory` never touches it. |
| `streamFuns.cpp` | Guard `#include <sys/statvfs.h>` under `#if !defined(_WIN32)` | No `<sys/statvfs.h>` on Windows (shim is in `IncludeDefine.h`). |
| `Parameters_openReadsFiles.cpp` | `#if defined(_WIN32)` replaces the `vfork`/`execlp` block with a clean error | Native Windows has no `fork`/`exec`; gzip is handled internally instead. |
| `Parameters_closeReadsFiles.cpp` | Guard `kill(pid, SIGKILL)` under `#if !defined(_WIN32)` | No POSIX `kill`/`SIGKILL` on Windows. |
| `STAR.cpp` | On `_WIN32`, set `_fmode = _O_BINARY` at the start of `main()` (+ `<stdio.h>`/`<fcntl.h>`/`<io.h>`), and `_setmode` `stdout`/`stdin` to `_O_BINARY` | Windows text mode truncates binary genome/suffix-array files at the first `0x1A` byte (genomeGenerate failure) and writes CRLF into SAM/logs. `_fmode` only covers files opened afterwards, so the pre-opened std streams need `_setmode`, else `--outStd SAM` injects CRLF and `--outStd BAM_*` corrupts the piped BAM (`0x0A`→`0x0D0A`). |
| `Genome_genomeGenerate.cpp` | On `_WIN32`, `flush()`/`close()` the `Log.out` stream before moving it with `MoveFileExA(REPLACE_EXISTING)`, then reopen it (append) | Windows cannot `rename()` a file that is still open (POSIX can), so genomeGenerate otherwise prints a spurious "Could not move Log.out" warning and leaves the log in the run dir. CRT `rename` also refuses an existing destination, so replacement must be explicit. |
| `BAMoutput.h` / `BAMoutput.cpp` / `bamSortByCoordinate.cpp` | On `_WIN32`, add `BAMoutput::closeBins()` and call it before sorting, after mapping has flushed the bins | Windows must close the writers before the sorter can delete consumed input bins. Closing only after sorting fixes final cleanup but retains consumed bins during sorting and with `--outTmpKeep All`. |
| `IncludeDefine.h` / `sysRemoveDir.cpp` | Windows uses `_stat64` and `_FILE_OFFSET_BITS=64` for MinGW's `nftw64` callback ABI | Both ordinary file checks and recursive cleanup must handle files over 2 GiB; changing `stat` alone is insufficient. |
| `Quantifications.h` | Windows-only 64-bit `uintQ` | Windows `unsigned long` is 32-bit; prevents gene-count accumulator wrap at 2³². |
| `streamFuns.cpp` / `SoloFeature_outputResults.cpp` | Windows-only separator normalization for directory creation and drive-qualified absolute-prefix detection | Native backslashes and `C:/...` prefixes must not be parsed as Unix relative paths. |
| `STAR.cpp` | At Windows startup, raise the CRT stdio-stream limit to 8,192; fail clearly if initialization fails | The default limit of 512 is exceeded by 12 threads with 50 sorting bins, or 2 threads with 300 bins. The CRT's 8,192 ceiling still applies. |
| `streamFuns.cpp` | Top-of-file helpers skip existing drive/UNC roots during recursive parent creation and close a failed output's writer before removing it on Windows | UNC output must not try to create `/` or the server/share root; incomplete files otherwise survive the write-error path because their handles are still open. |
| `STAR.cpp` / `twoPassRunPass1.cpp` | Windows-only helpers at the tops of the files close remaining Fastx/chimeric/BySJout/Solo temporary streams; each lifecycle point has one guarded helper call | Unlike POSIX, Windows cannot unlink those still-open files. Includes first-pass and Solo redistribution streams. |
| `ReadAlignChunk_processChunks.cpp` | Treat `\r` like `\n` when testing for a second read-ID field | **Upstream 2.7.11b bug (unguarded):** with CRLF FASTQ whose ID lines have no comment field, the parser reads the sequence line as the "second field" and desynchronises; upstream exits 104 with "wrong read ID line format" at read #2 on macOS/Linux exactly as on Windows. |
| `Parameters.cpp` | `--outStd BAM_Quant` sets `outQuantBAMfileName="-"` | **Upstream 2.7.11b bug (unguarded):** upstream assigns `"-"` to `outFileNamePrefix` instead, then opens an empty BAM filename and crashes. |
| `ThreadControl.cpp` | `pthread_mutex_init(&mutexLogMain)` in the `ThreadControl` constructor | **Upstream 2.7.11b bug (unguarded):** `mutexLogMain` is locked (even with one thread) but never initialised. A zero-filled mutex happens to work on glibc; on macOS `pthread_mutex_lock` returns `EINVAL` and does not lock, and winpthreads likewise rejects it, so `Log.out` writes from mapping threads were unsynchronised. The other `g_threadChunks` mutexes are initialised before their (`runThreadN>1`-guarded) use. |
| `Parameters_readSAMheader.cpp` / `GzIfstream.h` | Preserve headers from each native plain/gzip SAM input; reject gzip read errors instead of treating them as EOF | Correctness of the optional `STAR_GZ_INPUT` path across platforms. |
| `Makefile` | `LDFLAGS_GZ` adds `-lbz2` to every STAR target's link line when `CXXFLAGSextra`/`CXXFLAGS` contain `STAR_GZ_INPUT` | `GzIfstream.h` reads bzip2 through libbz2; builds without `STAR_GZ_INPUT` keep upstream's dependencies. The recipes above that set `LDFLAGS_shared` get it too. |
| `Makefile` | Include user preprocessor flags when generating header dependencies | Otherwise edits to the conditionally included `GzIfstream.h` can leave stale object files. |
| `Makefile` | New `BUILD_GIT_INFO` variable for the embedded git text (upstream's `BUILD_PLACE` is kept) | Upstream embeds `$(HOSTNAME):$(pwd)` and `git status`/`diff` text in every binary and prints them in `Log.out`. For distributed builds pass `BUILD_PLACE=<neutral text> BUILD_GIT_INFO=` (empty blanks the git text); when not given, both behave exactly as upstream. |
| `ParametersGenome.cpp` | Include `transform.outQuant` in the existing assignment that resets the transformed-output flags | **Upstream 2.7.11b bug:** this bool was otherwise uninitialized unless `Quant` was explicitly requested. It can select an empty transformed-genome directory and intermittently fail on `/geneInfo.tab`, despite correctly generated annotations. One assignment fixes all platforms. The earlier Windows-only `Transcriptome.cpp` directory fallback was removed; it did not fix the flag and could substitute the wrong annotation. See `tests/WINDOWS_ISSUES.md`. |
| `ReadAlignChunk_mapChunk.cpp` | Under `#if defined(_LIBCPP_VERSION)`: (a) load the read chunk with `.str(…)` instead of the `pubsetbuf` set in `ReadAlignChunk()`; (b) write the SAM chunk from `chunkOutBAMstream->str()` instead of the `pubsetbuf`-backed `chunkOutBAM` at all three write sites | **libc++'s `std::stringbuf::pubsetbuf` is a no-op** (libstdc++ honors it). On input this reports **0 reads**; on `--outSAMtype SAM` output the buffer stays zeroed so the file is **NUL-filled** (BAM output uses a separate path and is fine). Affects upstream STAR too. |
| `GzIfstream.h` *(new)* | A `std::istream` backed by zlib's `gzFile` that transparently reads plain **or** gzipped FASTQ, streaming; binds its streambuf at construction so an unopened stream is `good()`. `openMulti` opens a **list** of files, decompressing each and concatenating them in `underflow()`. A regular file that starts with a bzip2 header (recognised by its bytes, not its name) is read through libbz2 instead, including concatenated bzip2 streams; bytes after the last stream are ignored as `bzip2 -dc` does, while a truncated or corrupt stream is a fatal error. Pipes are not sniffed, so they still read plain or gzip | **Adds native streaming gzip and bzip2 input**: `.gz` and `.bz2` reads work directly, with no `--readFilesCommand`, no external process, and no temp file, on all platforms — including STAR's comma-separated multi-file `--readFilesIn`, where plain, gzip and bzip2 files can be mixed. Like gzip, bzip2 checks a block's CRC only after handing out its bytes, so damage inside a block may first be reported by STAR's read parser. |
| `InOutStreams.h` | Under `#ifdef STAR_GZ_INPUT`, `typedef GzIfstream ReadInFstream` and declare `ReadInFstream readIn[]` (else `std::ifstream`) | Routes read-file input through `GzIfstream` when built with `-DSTAR_GZ_INPUT`. |
| `ReadAlignChunk_processChunks.cpp` | Widen `fastqReadOneLine(ifstream&, …)` to `istream&` | `readIn` is now a base-`istream` (`GzIfstream`); every other read-file call site was unchanged. |
| `Parameters_readFilesInit.cpp` | Under `#ifdef STAR_GZ_INPUT`, keep `readFilesCommandString` empty in the default (`--readFilesCommand -`) case even for multiple files | Multiple comma-separated files are concatenated and decompressed by `GzIfstream` itself, so no external `cat`/fifo is used (works on Windows too, which has no `fork`/fifo). |
| `Parameters_openReadsFiles.cpp` | Under `#ifdef STAR_GZ_INPUT`, the empty-command branch `stat()`s each split file then opens the whole per-mate list via `readIn[imate].openMulti(readFilesNames[imate])` | Streams/decompresses every comma-separated file through one `GzIfstream`, which re-emits upstream's `FILE <n>` boundary markers so `readFilesIndex` still advances across the list — per-file `--outSAMattrRGline` read groups and STARsolo per-file barcode indexing work as upstream. |

### Patch layout and maintenance

All portability source, build changes, tests, and documentation are contained in
this `STAR/` tree. No external source overlay, PowerShell wrapper, or VM-specific
path is needed to build or run the fixes. The existing compiler, htslib, zlib,
and other dependencies in the build recipes are still required; source
self-containment does not mean every resulting executable is statically linked.

Prefer compatibility headers or small helpers after the includes at the top of
a `.cpp` file, guarded by `_WIN32`. Keep edits inside upstream functions to the
smallest necessary call, condition, or assignment. Current locations:

- **Headers:** `IncludeDefine.h` contains the Windows API shims and stat mapping;
  `Quantifications.h` contains the counter-width correction; `GzIfstream.h`
  contains native gzip/bzip2 streaming and its error handling. `STAR_GZ_INPUT` and
  `_LIBCPP_VERSION` guard functionality/runtime differences that also apply
  outside Windows.
- **Top-of-file compatibility code:** `sysRemoveDir.cpp` selects the 64-bit
  directory-walker ABI before any includes. `STAR.cpp` and
  `twoPassRunPass1.cpp` contain Windows-only temporary-stream cleanup helpers.
  `streamFuns.cpp` contains the parent-path and failed-output cleanup helpers;
  their Windows-specific behavior is guarded by `_WIN32`.
- **Necessary integration points:** binary mode must be set before files open;
  log moves must flush/close/reopen their owning stream; temporary streams must
  close after their final use and before directory removal. Path interpretation,
  SAM headers, and libc++ buffers likewise need small changes where STAR handles
  those values. A header alone cannot choose those execution points.
- **Upstream fixes:** the `outQuant` initialization, `mutexLogMain`
  initialization, CRLF FASTQ condition, and `BAM_Quant` filename assignment
  remain direct, minimal edits in their original functions. They are intentionally not Windows-guarded. The obsolete
  Windows-only transcriptome-directory fallback was removed.

Avoid broad macros that replace stream operations or file-removal calls just
to hide integration edits: they obscure ownership and can change unrelated
call sites. Preserve the explicit, documented hooks instead. Regression tests
and commands are described in [tests/README.md](tests/README.md).

CRLF manifests, external `soloCellFiltering` barcode tables, and SAM input
headers still retain CR bytes in metadata on both Windows and POSIX. These
upstream limitations are documented with opt-in diagnostic probes in the second
audit; use LF files for these inputs. General Unicode/long-path support, remote
share failure recovery, and comprehensive disk-full/flush-error handling remain
outside the validated scope.

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
