# Windows — open issues & test-coverage gaps

Initial findings from the 2026-09-19 Windows ARM64 audit, with the
quantification diagnosis corrected by the follow-up below. CRLF input handling
and the remaining coverage gaps are still open.

## Fixed upstream bug: intermittent quantification failure

The original diagnosis (an intermittently empty `sjdbInsert.outDir`, missing
writes, and a reliable GTF-baked-index workaround) was **incorrect**.

`ParametersGenome::initialize()` resets `transform.outYes`, `outSAM`, and
`outSJ`, but upstream 2.7.11b omits `outQuant`. Unless `Quant` is explicitly
requested, that bool remains uninitialized. `Transcriptome` branches on it:
when it selects transformed output, it reads the unset `P.pGeOut.gDir` and
attempts `/geneInfo.tab`. Both baked and mapping-time annotations can be
misdirected by this flag. This is undefined behavior, not a Windows filesystem
or threading defect.

The same omission is present in the canonical
[upstream 2.7.11b source](https://github.com/alexdobin/STAR/blob/2.7.11b/source/ParametersGenome.cpp).
Windows ARM64 exposed it readily; lack of observed failures on another platform
does not make that platform's initialization correct.

### Minimal source change

- Add `transform.outQuant` to the **existing reset assignment** in
  `ParametersGenome.cpp`. This upstream correctness fix is intentionally
  unguarded; Windows compatibility patches remain platform-guarded.
- Remove the previous nine-line Windows `Transcriptome.cpp` fallback. It does
  not repair the invalid flag, and choosing an older index annotation when an
  explicitly supplied mapping-time annotation is unavailable is incorrect.
- No parser changes, broad zero-initialization, new source abstraction, or CRLF
  fix is included in this follow-up.

### Reproduction and regression coverage

The original Windows ARM64 executable failed **13/20** repeated on-the-fly
`GeneCounts TranscriptomeSAM` runs (exit 109). An instrumented pre-fix build
failed **11/20**. In **every** run, including failures, the generated
`_STARgenome/geneInfo.tab` existed. Instrumentation showed an intact
`sjdbInsert.outDir`, empty `pGeOut.gDir`, and varying invalid bool bytes (for
example 241 and 245 in failing runs). Diagnostic instrumentation is retained
only in the isolated audit workspace, not in the source patch.

`test_transform_flags.cpp` seeds valid prior false/true flags and exercises all
eight combinations of SAM/SJ/Quant selection. It fails deterministically before
the fix and passes all **16 cases** afterwards on macOS and Windows ARM64.

`test_quantification.py`, called by `run_tests.sh`, repeatedly checks baked,
on-the-fly, and replacement annotations at one and four threads. It asserts
exact gene counts, transcriptome BAM records/IDs, generated models, and temp
cleanup. The replacement GTF has different gene/transcript IDs, so silently
falling back to baked annotations cannot pass.

### Validation completed 2026-09-19

| Check | macOS ARM64 | Windows ARM64 |
|---|---:|---:|
| Deterministic initialization cases, fixed | 16/16 | 16/16 |
| Portability suite checks | 35 passed, 0 failed | 35 passed, 0 failed |
| Quantification cases within that suite | 18/18 | 60/60 |
| Additional repeated on-the-fly runs, fixed | — | 100/100 |

Both portability suites used samtools, including transcriptome BAM decoding.
The additional 100-run probe checked exit status and gene-model existence;
exact counts and transcript IDs were checked in the separate 60-case matrix.
No fixed-build failures occurred. This follow-up did not test Linux or Windows
x64, and it does not certify a redistributable binary package.

Windows work was isolated in a disposable VM workspace. The existing installed/build
binaries were not replaced. The fixed build recompiled all STAR objects from
268 hash-verified source/test files, using CLANGARM64 and the existing bundled
htslib build/dependencies. Final documentation edits occurred afterwards; the
source and regression-test code are the validated versions.

Retained evidence:
- An evidence archive (kept outside this repository) contains before/after
  results, full build/suite logs, diagnostic source, replay scripts, and
  source/binary hashes; a copy with the macOS suite/build logs was kept locally.
- Fixed Windows executable SHA-256:
  `bcfd1ac27f3583b45e408e21fb82652416a1c38b4fde52a90389de7cc2664114`.

## Follow-up portability audit

The earlier CRLF and cleanup conclusions were superseded by the
[in-depth parity audit](PORTABILITY_AUDIT_2026-09-19.md). Standard CRLF FASTA,
GTF, and CB_UMI_Simple whitelists pass; the specific CRLF FASTQ header bug is
fixed. Real cleanup failures, large-file walking, counter width, Windows path
handling, and index-log replacement now have targeted regressions and fixes.

STARsolo, two-pass, BySJout, bedGraph, chimeric output, and unmapped Fastx are
covered by `test_portability.py`. General Unicode paths and other explicitly
listed limits remain open; see the new report for the exact scope and results.
