# STAR portability test suite

Self-contained regressions for Windows/POSIX parity, using a deterministic
synthetic genome and reads. No input downloads or third-party Python packages
are needed. See [the audit report](PORTABILITY_AUDIT_2026-09-19.md) for findings,
before/after evidence, validation platforms, and known limitations.

## Run

From this directory, with Bash, Python 3, and the native target binaries:

```bash
STAR=/absolute/path/to/STAR SAMTOOLS=/absolute/path/to/samtools THREADS=4 \
  bash run_tests.sh /path/to/disposable-results
python3 run_unit_tests.py --cxx /path/to/native/c++ --output /path/to/new-unit-results
```

On Windows use the matching MSYS2 UCRT64 or CLANGARM64 environment, native
Windows Python, and `.exe` binaries with their runtime DLL directories on PATH.
The C++ runner compiles directly; it does not require htslib or a test framework.

- `STAR` is required; use an absolute path. Build with `-DSTAR_GZ_INPUT`.
- `SAMTOOLS` enables exact BAM decoding and transcript-ID checks. Set it for a
  complete audit; otherwise BAM-dependent checks are skipped.
- `THREADS` defaults to 4. The extended chunk-ordering checks always use at least
  2 threads, even when the outer suite is requested at 1 thread.
- `QUANT_REPEATS` defaults to 3 per scenario/thread count. Set it to 10 for a
  longer intermittent-bug check.
- The shell suite **replaces its result directory** (default `star_testrun`).
  Python runners require new output directories and preserve all results.
- Exit 0 means no failures. Windows Unicode input paths currently produce a
  separately reported `KNOWN_LIMITATION`; this does not conceal other failures.

## Coverage

- Index generation with/without GTF, existing log replacement, same-path logs,
  CRLF FASTA/GTF, and binary index contents.
- Single/paired reads, plain/gzip/mixed lists, concatenated gzip members, empty
  members, per-file read groups, CRLF FASTQ/read FASTA, and SAM header/attribute
  preservation. Truncated gzip, bad CRC, and missing later files must fail.
- Exact SAM/BAM records, ordered multichunk SAM with repeated buffer flushes,
  SAM and all three BAM stdout modes, and CR/NUL checks on text outputs.
- Unmapped Fastx, chimeric junctions, annotated/novel splices, BySJout, two-pass
  reopening, bedGraph coverage, empty/all-unmapped sorted BAM, and combined
  workflows. Successful runs assert temporary-file cleanup where applicable.
- Nonempty STARsolo Gene/SJ matrices with relative/absolute prefixes and CRLF
  whitelists; exact SJ feature-file copying.
- Spaces, nested directories, native Windows backslashes, Unicode limitations,
  and clean Windows rejection of shared-memory/read-command options.
- Sparse files larger than 2 GiB: STAR's input stat check plus native stat,
  seek/tell, recursive removal, and target-path free-space queries. The Windows
  helper explicitly marks the file sparse, avoiding a multi-gigabyte allocation.
- Repeated combined GeneCounts/TranscriptomeSAM across baked-in GTF, mapping-time
  GTF, and replacement annotations, at 1 and `THREADS` threads. Exact gene counts,
  transcript IDs, models, and cleanup are checked. Results: `quant_regression/`.
- Top-level `run_tests.sh` integrity checks: a truncated `.gz` input must exit
  nonzero, SAM-input `@RG`/`@CO` header lines must reach the output header, and
  single-thread GeneCounts must count all 500 genic reads.
- Deterministic C++ checks: 16 transformed-output flag combinations, 7 platform
  I/O/counter assertions (including real accumulation beyond 2³²), and a
  failed-write cleanup case. Repetition alone cannot reliably detect the
  upstream uninitialized `outQuant` flag.
- `test_portability_extended.py`: 15 additional cases for high stream counts
  (12 threads / 300 sorting bins), removal of consumed BAM input bins,
  explicit/retained temporary directories, filename prefixes, repeated output,
  read-file prefixes, single/paired manifests with read groups, SmartSeq
  redistribution, corrected Solo BAM tags, tag-only Solo, BAM-input coverage,
  and external cell filtering. Results: `portability_extended/results.json`.

The second suite is included automatically by `run_tests.sh`. On Windows,
`STAR_TEST_UNC_ROOT=//server/share/disposable-audit-directory` adds two UNC
directory-creation/output checks (forward and backslashes). The share must
already exist and be accessible; the suite creates only its test directories.
Use a fresh UNC test root per run. This tests normal share I/O, not network
interruptions or every remote filesystem.

Known upstream CRLF metadata issues have separate opt-in diagnostic probes:

```bash
python3 test_portability_extended.py --star /absolute/path/to/STAR \
  --fixture /path/to/completed-suite --output /path/to/new-diagnostics \
  --probe-crlf-metadata --only upstream_probe
```

Those three probes currently **fail on both POSIX and Windows** because CR bytes
survive in manifest read groups, external cell-filtering barcodes, and SAM input
headers. They are not converted to passes or silently swallowed; keep this
diagnostic run separate from the ordinary suite. Use LF inputs in these cases.
See [the second audit](PORTABILITY_AUDIT_2026-09-19_ROUND2.md).

The outer shell summary counts aggregate checks. Detailed integration results,
commands, logs, and 23 canonical output fingerprints are in
`portability/results.json`; nested checks are not additional outer checks.
The second suite retains 11 fingerprints: the single-read control plus 10
additional output categories. `REF` compares both suites;
reference runs must therefore include `portability_extended/results.json` too.

## Cross-platform comparisons

To compare against a complete suite run from another platform:

```bash
REF=/path/to/reference-suite STAR=/absolute/path/to/STAR \
  SAMTOOLS=/absolute/path/to/samtools bash run_tests.sh /path/to/new-results
```

Both runs must enable the same optional checks. This compares normalized
biological outputs: record order and optional-tag order are normalized where
semantically irrelevant; header command paths and timestamps are excluded.
It does not require byte-identical compressed BAM files.

To also test an index copied from another platform, copy the reference run's
`portability/index-lf/index` directory and run:

```bash
python3 test_portability.py --star /absolute/path/to/STAR \
  --samtools /absolute/path/to/samtools --fixture /path/to/completed-suite \
  --output /path/to/new-portability-results \
  --reference /path/to/reference-suite/portability/results.json \
  --foreign-index /path/to/copied/index
```

For a focused regression, add `--only 'case_name_regex'` and omit `--reference`
(which expects a complete fingerprint set). `--foreign-index` can be combined
with `--only foreign_platform_index_roundtrip` for a fast index-exchange check.
