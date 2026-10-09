# STAR Windows/POSIX parity audit — second pass, 2026-09-19

This audit extends the [first audit](PORTABILITY_AUDIT_2026-09-19.md), preserving
its changes. The focus remains native Windows compatibility and small, contained
patches. Only three production files change in this pass: `STAR.cpp`,
`streamFuns.cpp`, and `bamSortByCoordinate.cpp`. New behavior is Windows-guarded;
helpers live after the includes, with minimal calls at the required lifecycle
points. No RAII redesign, new dependency, or upstream parser fix was introduced.

## Confirmed Windows defects

| Finding | Before-fix evidence | Contained fix and regression |
|---|---|---|
| CRT stream limit is too low for ordinary sorting configurations | Both Windows builds exit 109 opening BAM bins with 12 threads × 50 bins or 2 threads × 300 bins; macOS succeeds | Set `_setmaxstdio(8192)` in the existing Windows startup block and check its return value; compare every decoded alignment in both configurations |
| Recursive output-directory creation mishandles UNC roots | Forward- and backslash UNC prefixes fail with exit 102 while attempting to create `/`, although the existing share is accessible | Top-of-file path helper skips the server/share and drive roots; test fresh nested directories, exact SAM records, and cleanup through both UNC spellings |
| Failed binary-write cleanup removes an open file | A deterministic real `fstreamWriteBig` error leaves a partial file on Windows ARM64; macOS removes it | Top-of-file helper closes the failed writer on Windows before the existing removal; native C++ regression checks both the fatal-write error and absence of the partial file |
| Sorted BAM writers close too late | Under `--outTmpKeep All`, Windows ARM64 retains consumed nonempty per-thread input bins; macOS removes them | Move the existing Windows `closeBins()` block to the start of sorting, after mapping has flushed the bins; check consumed-bin removal and unchanged BAM records |

The Windows CRT defaults to 512 stdio streams and permits at most 8,192 through
[`_setmaxstdio`](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/setmaxstdio?view=msvc-170).
The new limit is finite: sufficiently large thread/bin combinations can still
exhaust it. Closing the bins before sorting also releases their stream slots
when they are no longer needed; it cannot reduce the simultaneous mapping-time
requirement. This is separate from the operating system's file-handle limit.

The failed-write regression creates and flushes a small partial output, sets
the stream's error state, and calls the actual `fstreamWriteBig` implementation.
Its test-only fatal-error stub throws so that cleanup can be inspected. This
tests the production error branch without filling a disk; it does not certify
every write, delayed flush, close error, or storage failure in STAR/htslib.

## Additional coverage

`test_portability_extended.py` adds 15 default cases with samtools enabled:
the two resource-limit configurations; consumed-bin cleanup; filename output
prefixes; explicit temporary directories; retained temporary files; repeated
output prefixes; read-file prefixes; single/paired manifests and their read
groups; SmartSeq redistribution; corrected Solo BAM tags; tag-only Solo;
coverage from an existing BAM; and external matrix cell filtering.

These extend checks of earlier README patches, particularly Solo redistribution
stream cleanup, the tag-only branch, native multi-file read groups, binary BAM
I/O, and directory handling. Two optional Windows UNC tests bring that suite to
17 cases. Normalization compares biological contents rather than compressed
BAM bytes, command paths, or timestamps. Exact record counts, tags, matrix
counts, coverage integral, and relevant cleanup are asserted separately.

The new failed-write executable joins the deterministic C++ tests: 16 flag
initialization cases, seven platform/counter checks, and one write-error case.
See [tests/README.md](README.md) for self-contained commands and prerequisites.

## Remaining upstream issues, deliberately separate

Opt-in `--probe-crlf-metadata` diagnostics reproduce three failures on both
macOS and Windows ARM64:

1. CRLF read manifests retain CR in read-group metadata and resulting SAM.
2. External `soloCellFiltering` barcode tables retain CR in output barcodes.
3. CRLF SAM input headers retain CR in emitted SAM headers.

These are separate parsing paths from the previously fixed CRLF FASTQ header
case. LF variants pass. Use LF for these metadata inputs. The diagnostic probes
report failures and return nonzero; they are excluded from the default passing
suite, rather than being converted into successful assertions.

The relevant raw-line parsing is also present in upstream 2.7.11b:
[manifest parsing](https://github.com/alexdobin/STAR/blob/2.7.11b/source/Parameters_readFilesInit.cpp),
[SAM headers](https://github.com/alexdobin/STAR/blob/2.7.11b/source/Parameters_readSAMheader.cpp),
and [external matrix loading](https://github.com/alexdobin/STAR/blob/2.7.11b/source/SoloFeature_loadRawMatrix.cpp).
No production parser changes were added in this pass.

## Final validation

| Check | macOS ARM64 / GCC | Windows ARM64 / Clang | Windows x64 / GCC |
|---|---:|---:|---:|
| Full shell suite, with samtools | 39 passed | 39 passed | 39 passed |
| Nested quantification matrix | 18 passed | 18 passed | 18 passed |
| Original nested portability suite | 35 passed | 40 passed + 1 known limitation | 40 passed + 1 known limitation |
| New nested workflow/resource suite | 15 passed | 17 passed | 17 passed |
| Deterministic C++ assertions | 24 passed | 24 passed | 24 passed |

There are zero failures in these final default runs. Outer checks aggregate
nested suites, so the rows must not be added. The known limitation remains the
non-ANSI Unicode input pathname. Separately, the three opt-in upstream metadata
diagnostics fail as described above; they are not covered by the zero-failure
claim.

All 23 original output fingerprints and all 11 fingerprints in the new suite
match exactly across the three platforms. The new suite includes the existing
single-read control, so it contributes ten additional output categories.
The x64 executable ran under emulation on the ARM64 Windows VM, not on native
x64 hardware. This pass does not add Linux runtime validation or repeat the
first audit's bidirectional index-exchange certification.

Before Windows builds, 271 code/test files were hash-verified against the local
tree in both isolated source directories. The three changed translation units
were rebuilt against the previously clean-built trees and existing htslib.
The failed-write test was subsequently strengthened to reject an invalid setup
and require `ENOENT`; all native unit tests were rerun on the final test source.
These executables use the VM's runtime DLLs; static distribution was not tested.
Installed binaries and VM sharing settings were not changed. UNC tests use the
existing accessible `//localhost/C$` share; they do not certify arbitrary remote
SMB servers, disconnect recovery, extended-length paths, or Unicode paths.

## Evidence

Artifacts are kept outside this repository, in a local scratch directory and an
isolated VM workspace. The first audit's isolated source trees were reused for
compilation.

- `mac-suite/`, `arm-suite/`, and `x64-suite/` retain commands, outputs, and JSON
  results; accompanying `*-suite.log` files retain the full summaries.
- `mac-units-verified/`, `arm-units-verified/`, and `x64-units-verified/` retain
  final native C++ results.
- `windows-evidence.tar.gz` is also downloaded locally and extracted in
  `windows-evidence/`; it includes build/test logs, result manifests, source
  hashes, the source overlay, and replay scripts.
- `source-sha256.json` identifies the 271 verified code/test files;
  `source-sha256-final.json` includes the strengthened test, whose final replay
  is retained in `unit-final-evidence.tar.gz`. `cross-platform-comparison.json`
  records the fingerprint comparisons.
- `mac-before-corrected.log` and `arm-before-corrected.log` retain the corrected
  baseline fixtures and three metadata diagnostics. `*-consumed-before.log`
  records the later consumed-bin regression. Earlier exploratory logs contain
  fixture mistakes and are not counted as product defects.

Tested executable SHA-256 values:

```text
macOS ARM64  1449a1db048e359155ffe9d41a1a99fa233a6b1baa79a28d619815d3b3f57d9a
Windows ARM  565a38280e942b95a280d973606ba993f07a675b453401a0f66154643d548d64
Windows x64  e788a40063cd3f8af1cda4865483f2a915ed8bd3ebb507abe2babda5fbb2490c
```

RAII can improve stream ownership and exception/return cleanup, but cannot by
itself select binary mode, raise CRT limits, implement UNC path handling, or
check delayed I/O errors. `exit()` does not unwind local objects, and stream
destruction is not a reliable place to report finalization failures. Those
concerns need explicit lifecycle and error-handling decisions even in a RAII
design.
