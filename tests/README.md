# STAR portability test suite

A fast, self-contained suite that exercises the paths most likely to break on
Windows and asserts the invariants that catch them. It uses a small synthetic
genome + reads (`gen_testdata.py`), so it runs in seconds and needs no downloads.

## Run

```bash
STAR=/path/to/STAR SAMTOOLS=/path/to/samtools THREADS=4 bash run_tests.sh
```

- `STAR` (required): the binary under test (`STAR.exe` on Windows).
- `SAMTOOLS` (optional): enables BAM decode checks and the per-file read-group
  assertion. Without it those steps are skipped (not failed).
- `THREADS` (default 4). First positional arg overrides the work dir.

Exit code is 0 iff every check passes; a summary line reports `N passed, M failed`.

## What it covers

- **Indexing** with and without `--sjdbGTFfile`; asserts `Log.out` is moved into
  the genome dir and no `*_STARtmp` dir leaks.
- **Input**: SE / PE × plain / gzip; comma-separated multi-file per mate.
- **Per-file read groups** (`--outSAMattrRGline A , B`): asserts file-A reads get
  `grpA` and file-B reads get `grpB` (needs samtools).
- **Output formats**: `SAM` (file + `--outStd`), `BAM Unsorted` (file + `--outStd`),
  `BAM SortedByCoordinate`. Text outputs are scanned for **CR (`\r`)** and
  **NUL (`\0`)** — the two Windows corruption signatures (CRLF injection and the
  libc++ pubsetbuf NUL buffer). BAM-to-stdout is decoded to prove it isn't
  text-mode-mangled.
- **Extra outputs**: `--outSAMunmapped Within`, `--quantMode GeneCounts`.
- **Error handling**: `--readFilesCommand` on Windows must fail cleanly, not crash.

## Golden comparison (optional, TODO)

`REF=<dir>` is reserved for diffing `Log.final.out` mapping numbers and
`samtools view` output against a reference platform's run. Cross-platform bit
identity of the mapping metrics has been verified manually (yeast + drosophila);
wiring an automated diff here is a straightforward extension.

## Extending

Add a case by calling `run <name> <STAR args...>` (writes to `./<name>/`) and then
the relevant assertions (`mapped_gt0`, `bam_ok`, `no_cr`, `no_nul`, `sam_records`,
`no_startmp`). Candidates not yet covered: STARsolo (`--soloType`), 2-pass
(`--twopassMode Basic`), `--outWigType bedGraph`, chimeric (`--chimSegmentMin`),
`--quantMode TranscriptomeSAM`.
