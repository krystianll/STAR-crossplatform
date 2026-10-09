# STAR Windows/POSIX parity audit — 2026-09-19

Follow-up: [the second audit](PORTABILITY_AUDIT_2026-09-19_ROUND2.md) adds resource
limit, failed-write cleanup, consumed-bin, UNC, and extra workflow regressions.
The results and limits below describe this initial run; the follow-up verifies
normal loopback UNC I/O and records remaining CRLF metadata defects explicitly.

Scope: native MinGW Windows ARM64 (Clang/libc++) and Windows x64
(GCC/libstdc++, emulated on the ARM64 VM), compared with macOS ARM64/GCC.
This continues the earlier `outQuant` investigation; its changes and tests were
preserved. Production changes remain small, with Windows compatibility changes
guarded by `_WIN32`. This audit does not claim native x64 hardware or Linux
runtime validation.

## Confirmed Windows defects and contained fixes

| Finding | Evidence before the fix | Fix and regression |
|---|---|---|
| GeneCounts uses a 32-bit `unsigned long` on Windows | Adding 2 to 4,294,967,295 wraps on Windows; macOS returns 4,294,967,297 | Windows-only `uintQ` definition in `Quantifications.h`; exercise every accumulator in `addQuants`, without billions of reads |
| Directory walking still uses 32-bit file sizes | A sparse file larger than 2 GiB passes `stat`/`tellg`/`seekg`, but `sysRemoveDir` leaves its directory behind | Define `_FILE_OFFSET_BITS=64` before headers in `sysRemoveDir.cpp`, selecting both MinGW's `nftw64` function and its matching callback ABI |
| Existing index log is not replaced | A second `genomeGenerate` run leaves its log outside the index and retains the old index log | Existing Windows close/reopen block now uses `MoveFileExA` with `MOVEFILE_REPLACE_EXISTING`; test replacement and identical source/destination paths |
| Backslash paths do not create parent directories | Native `C:\...\new parent\nested\output\` prefix fails while forward slashes work | Normalize separators locally in `createDirectory`, only on Windows; test nested paths containing spaces |
| STARsolo treats drive-qualified paths as relative | Absolute prefix produces a duplicated working-directory/drive path and the `CopyFileA` shim fails | Windows-only absolute-path check at the STARsolo call site; verify both relative and absolute Gene/SJ matrices and exact SJ feature-file contents |
| Open temporary streams prevent cleanup | Successful Fastx, chimeric, BySJout, and STARsolo runs leave per-thread files behind | Close the actual stream owners before Windows cleanup, including first-pass filter streams and Solo redistribution streams; test combined two-pass/BySJout/sorted-BAM/Fastx as well as individual modes |
| Free-space shim ignores its path and reports success on errors | Original shim always queries the current drive, even for a nonexistent requested path | Resolve a file's parent directory, query that volume, and propagate failure in `IncludeDefine.h`; test file/directory volume consistency and a nonexistent path |

The data-model and rename differences are specified by Microsoft:
[LLP64](https://learn.microsoft.com/en-us/windows/win32/winprog64/abstract-data-models),
[CRT rename](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/rename-wrename),
and [GetDiskFreeSpaceEx](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getdiskfreespaceexa).
The installed MinGW `ftw.h` was inspected to verify the `nftw64` ABI selection.

## Native input/build integration defects

These affect the added `STAR_GZ_INPUT` path on all platforms; they are not
changes to the alignment algorithm.

- **SAM headers disappeared.** The synthetic `FILE n` marker prevented the
  header reader from seeing `@RG`, `@PG`, and `@CO` lines. The native header path
  now inspects each plain/gzip member separately; direct single-file stream
  opens do not inject a marker. Multi-file mapping still emits the required
  markers, preserving per-file read groups. Tests check single, gzip, and mixed
  multi-file SAM headers and retained alignment attributes.
- **Gzip errors were treated as EOF.** Before the fix, a CRC error could produce
  successful output with zero reads, and missing trailers could be silently
  accepted. Check `gzerror` immediately after *every* `gzread`, including positive
  partial reads, and fail clearly before treating an error as EOF. Also fail if
  a later input file cannot be opened. This remains contained in `GzIfstream.h`.
- **Conditional-header dependencies were missing.** `Makefile` generated
  dependencies without `CXXFLAGSextra`/`CPPFLAGS`, omitting `GzIfstream.h` when
  `STAR_GZ_INPUT` was enabled. Incremental rebuilds could therefore keep old
  behavior despite updated source. Pass those flags to dependency generation
  and regenerate dependencies when the Makefile changes. Final Windows checks
  use clean STAR-object rebuilds; a dry run checks that changing the gzip header
  schedules recompilation.

## Small upstream defects found incidentally

These reproduce on macOS and Windows. They are intentionally unguarded and
clearly separate from Windows compatibility changes:

1. **CRLF FASTQ with no second header field:** the parser mistakes `\r` for the
   start of a second field, then consumes sequence data. One condition now
   recognizes both CR and LF as the end of the header.
2. **`--outStd BAM_Quant`:** upstream assigns `"-"` to `outFileNamePrefix`
   instead of `outQuantBAMfileName`, then opens an empty BAM filename and crashes.
   Correct that single assignment. The regression decodes all 500 transcriptome
   records from stdout and verifies the transcript IDs.
3. The prior **uninitialized `transform.outQuant`** fix remains unchanged; see
   [WINDOWS_ISSUES.md](WINDOWS_ISSUES.md) for its deterministic regression and
   before/after repeated-run evidence.

The first two defects were checked against canonical 2.7.11b
[read parsing](https://github.com/alexdobin/STAR/blob/2.7.11b/source/ReadAlignChunk_processChunks.cpp)
and [parameter initialization](https://github.com/alexdobin/STAR/blob/2.7.11b/source/Parameters.cpp).

## Previous audit claims corrected

- Standard CRLF **genome FASTA, read FASTA, GTF, and CB_UMI_Simple whitelist**
  fixtures pass. The existing FASTA code removes control characters; standard
  GTF attributes have delimiters; whitelist extraction skips whitespace. There
  is no justification for adding broad CR-stripping changes to those parsers.
- Temp cleanup was not universally clean: prior tests did not assert it for
  nonempty Fastx, chimeric, BySJout, and Solo output.
- Fixing `stat()` did not fix MinGW's separately compiled `nftw` implementation.
- The old test helpers could report a missing SAM file as containing records,
  and their claimed CR/NUL sweep checked only CR and split paths on spaces.
  Helpers now fail on missing files, stdout exit codes are checked, and a
  Python sweep checks both bytes without splitting filenames or scanning
  deliberately CRLF input fixtures.

## Coverage and remaining limits

The source review traced the platform shims, data-width aliases, stream opening
and buffering, file-size checks, directory walking, every active rename/remove
call site, read-list/header handling, and the guarded fork/FIFO/shared-memory
paths. The existing `uint`/`uint64` aliases already use `unsigned long long`;
`uintQ` was the remaining native-long counter found in STAR's own code. The
active large-file reads/writes use C++ streams and bounded chunks; no broad
replacement of I/O functions was needed. Bundled htslib was exercised through
BAM decoding, not subjected to a separate full source audit.

New integration checks include exact decoded SAM/BAM records; ordered SAM over
multiple input chunks and output-buffer flushes; paired mixed plain/gzip input
with per-file read groups; concatenated gzip members and empty intermediate
files; missing later files; CRLF fixtures; all three BAM stdout modes; annotated
and novel splice alignments; chimeric junctions; real unmapped Fastx records;
empty and all-unmapped sorted BAM; bedGraph coverage integral; nonempty
STARsolo Gene/SJ matrices; path forms; and clean rejection of all four shared
memory modes and `readFilesCommand` on Windows. The stat precheck is also
exercised by mapping one read from a sparse FASTQ larger than 2 GiB.

The existing libc++ buffer changes pass the ordered/multiple-flush case,
including exact record counts/order and no CR/NUL bytes. The existing global
Windows binary-mode settings pass index generation, alignment-file output and
SAM/BAM stdout decoding. The sorted-BAM close patch passes normal, empty,
all-unmapped, and combined workflows.

Remaining limits:

- Non-ANSI input names such as Greek/emoji paths fail cleanly on Windows; the
  narrow-character argv/filesystem interfaces are not a complete Unicode port.
  The test records this specific exit-102 result as `KNOWN_LIMITATION`; crashes
  or timeouts still fail. Supporting all Unicode paths needs a coordinated
  wide-character/UTF-8 interface change and is not folded into this small patch.
- Windows file permissions follow ACLs; POSIX `runDirPerm` mode bits are ignored
  by `_mkdir`. Shared-memory loading and arbitrary `readFilesCommand` remain
  explicitly unsupported. The latter currently reaches the FIFO rejection
  (exit 112) before the later fork/exec diagnostic.
- Long paths, UNC shares, network-filesystem locking, full disks, and interrupted
  processes have not been certified by this VM run. The free-space test does
  not simulate disk exhaustion or compare two physical Windows volumes.
- This is not a wholesale upstream parser/algorithm audit. For example,
  externally supplied Solo cell-filtering barcode files use a separate raw
  `getline` path, and nonstandard GTF/GFF attribute endings need separate CRLF
  fixtures. No blanket claim is made about every text-input variant.

## Validation and artifacts

| Check | macOS ARM64 / GCC | Windows ARM64 / Clang | Windows x64 / GCC (emulated) |
|---|---:|---:|---:|
| Complete shell suite, with samtools | 38 passed | 38 passed | 38 passed |
| Nested repeated quantification matrix | 18 passed | 18 passed | 18 passed |
| Nested extended parity checks | 35 passed | 40 passed + 1 known limitation | 40 passed + 1 known limitation |
| Deterministic C++ assertions | 23 passed | 23 passed | 23 passed |
| Complete extended run with reference comparison and foreign index | Reference | 42 passed + 1 known limitation | 42 passed + 1 known limitation |

There were **zero failures in the final runs**. The known limitation is the
Greek/emoji input pathname, not a skipped biological comparison. All **23
canonical output fingerprints** match across the three platforms. Both Windows
builds load the macOS-generated synthetic index with identical alignments;
macOS also loads each Windows-generated index with identical alignments.
The outer and nested counts describe the same runs and should not be added.

An additional macOS `THREADS=1` shell run passes all 38 outer checks, its 9-case
quantification matrix, and all 35 extended checks (the chunk-ordering tests use
2 threads). This verifies the wrapper's minimum-thread handling. The optional
foreign-index argument is resolved before the test changes STAR's working
directory; a test-only relative-path mistake was corrected and both complete
Windows cross-platform runs repeated successfully.

Both Windows executables were rebuilt after deleting STAR/opal objects and
`Depend.list`, using the existing architecture-specific htslib libraries. The
build logs, dependency probe, and source manifests are retained. After the two
test-runner corrections, **269 code/test files** were hash-verified against the
local tree in both Windows source trees; production code was unchanged from the
clean builds. Documentation was finalized afterwards. These audit executables
use the VM's dependency DLLs and do not certify the static redistribution recipe.

The work used an isolated, disposable VM workspace; installed binaries were not
replaced. Evidence (kept outside this repository):

- `evidence-final.tar.gz` contains 709 evidence files, including before/after
  logs, clean-build logs, replay scripts, final results, and source/binary hashes.
- A local copy of that archive, extracted as `windows-evidence-final/`; macOS
  results are in `mac-suite-final/`,
  `mac-units-final/`, `mac-arm-index/`, `mac-x64-index/`, and
  `mac-suite-single-thread/` alongside their logs.
- Windows ARM64 executable SHA-256:
  `cf4299178f53a22968e8edf18f66dd217eeaac5cac7fe6fac0a3753b5b9ac824`.
- Windows x64 executable SHA-256:
  `78d19283cf0040f36c635c7a2468351a777266a0955ef8a99d21554e71a1e210`.
- macOS executable SHA-256:
  `d0b9b5d4d50320505fc6a3b583d2e53651e60fd6e179881a73d2cc02b11387e4`.

### Cleanup layout follow-up

The Windows cleanup bodies now live in `static` helpers after the includes at
the tops of `STAR.cpp` and `twoPassRunPass1.cpp`. Their original lifecycle
locations retain only one `_WIN32`-guarded call each. This is a relocation of the
same operations; it adds no dependencies or changes to non-Windows behavior.
The main README's **Patch layout and maintenance** section maps the headers,
helpers, integration points, and three direct upstream fixes.

After this relocation, both Windows architectures and macOS were rebuilt.
All **10 affected integration cases passed on each platform**, covering Fastx,
BySJout, two-pass gzip, combined two-pass/BySJout/sorted BAM/Fastx, chimeric output,
empty/unmapped sorted BAM, and all three Solo cases. Their **12 output
fingerprints** match the earlier audited baseline on every platform. The full
audit counts and binary hashes above identify the preceding full-suite builds;
the layout follow-up has separate artifacts and hashes.

Evidence is retained outside this repository as `layout-evidence.tar.gz` (VM
copy) and `windows-layout-evidence.tar.gz` (local copy, extracted as
`windows-layout-evidence/`). It includes both changed source files,
their verified hashes, replay scripts, build/test logs, results, and new Windows
binary hashes. Local macOS results are in `mac-layout-tests/` with
`mac-layout-build.log` and `mac-layout-tests.log` alongside it.
