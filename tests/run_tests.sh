#!/usr/bin/env bash
# STAR cross-platform / Windows-hazard test suite.
#
# Usage:  STAR=/path/to/STAR[.exe] [SAMTOOLS=/path/to/samtools] [THREADS=4] \
#             bash run_tests.sh [workdir]
#
# Exercises the paths most likely to break on Windows (binary/text mode, the
# libc++ output buffer, temp-dir handling, per-file read groups, stdout piping)
# and asserts the invariants that catch them: no CR (\r) or NUL (\0) in text
# outputs, no leftover *_STARtmp dirs, Log.out moved into the genome dir, and
# non-zero mapping. BAM is validated by decoding with samtools when available.
#
# Exit code 0 = all checks pass. REF=<suite-dir> compares canonical biological
# outputs from the extended parity suite with a reference platform.
set -u
STAR="${STAR:?set STAR=/path/to/STAR}"
SAMTOOLS="${SAMTOOLS:-}"
THREADS="${THREADS:-4}"
case "$STAR" in *.exe) IS_WIN=1;; *) IS_WIN=0;; esac    # Windows target (for platform-conditional checks)
SAIDX=8                                  # min(14, log2(500kb)/2-1) ~ 8
W="${1:-$PWD/star_testrun}"
HERE="$(cd "$(dirname "$0")" && pwd)"
rm -rf "$W"; mkdir -p "$W"; cd "$W"

PASS=0; FAIL=0
ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
# -- invariant helpers --
no_cr()  { [ -f "$1" ] || { bad "missing $1"; return; }; if LC_ALL=C grep -qU $'\r' "$1" 2>/dev/null; then bad "CR (\\r) found in $1"; else ok "no CR in $(basename "$1")"; fi; }
no_nul() { [ -f "$1" ] || { bad "missing $1"; return; }; if [ "$(tr -cd '\000' < "$1" | wc -c | tr -d ' ')" != 0 ]; then bad "NUL byte in $1"; else ok "no NUL in $(basename "$1")"; fi; }
nonempty(){ if [ -s "$1" ]; then ok "$(basename "$1") non-empty"; else bad "$1 missing/empty"; fi; }
no_startmp(){ if ls -d "$1"/*_STARtmp >/dev/null 2>&1; then bad "leftover _STARtmp in $1"; else ok "no _STARtmp leaked"; fi; }
mapped_gt0(){ n=$(awk -F'|' '/Uniquely mapped reads number/{gsub(/ /,"",$2);print $2}' "$1"); if [ "${n:-0}" -gt 0 ] 2>/dev/null; then ok "mapped=$n (>0)"; else bad "0 mapped in $1"; fi; }
sam_records(){ local n; n=$(awk '!/^@/ && NF {n++} END {print n+0}' "$1" 2>/dev/null)
    if [ "${n:-0}" -gt 0 ]; then ok "SAM has records"; else bad "no SAM records in $1"; fi; }
bam_ok(){ [ -z "$SAMTOOLS" ] && { echo "  SKIP: samtools not set, BAM decode skipped ($1)"; return; }
          if "$SAMTOOLS" view "$1" >/dev/null 2>&1 && [ "$("$SAMTOOLS" view -c "$1" 2>/dev/null)" -gt 0 ]; then ok "BAM decodes ($(basename "$1"))"; else bad "BAM invalid/corrupt: $1"; fi; }

echo "########## generate test data ##########"
python3 "$HERE/gen_testdata.py" data >/dev/null || python "$HERE/gen_testdata.py" data

echo "########## indexing ##########"
"$STAR" --runMode genomeGenerate --genomeDir idx --genomeFastaFiles data/genome.fa \
        --genomeSAindexNbases $SAIDX --runThreadN $THREADS --outFileNamePrefix idx_ >idx.log 2>&1
[ $? -eq 0 ] && ok "genomeGenerate (no GTF)" || { bad "genomeGenerate failed"; cat idx.log; }
[ -f idx/Log.out ] && ok "Log.out moved into genome dir" || bad "Log.out not in genome dir"
no_startmp .
"$STAR" --runMode genomeGenerate --genomeDir idxg --genomeFastaFiles data/genome.fa \
        --sjdbGTFfile data/genes.gtf --sjdbOverhang 99 \
        --genomeSAindexNbases $SAIDX --runThreadN $THREADS --outFileNamePrefix idxg_ >idxg.log 2>&1
[ $? -eq 0 ] && ok "genomeGenerate (+GTF)" || { bad "genomeGenerate +GTF failed"; cat idxg.log; }

# helper: run one alignment case in its own dir
run() { local name="$1"; shift; mkdir -p "$name"; ( "$STAR" --genomeDir idx --runThreadN $THREADS \
        --outFileNamePrefix "$name/" "$@" ) >"$name/run.log" 2>&1; return $?; }

echo "########## input variants ##########"
run se_plain  --readFilesIn data/single.fq                              --outSAMtype BAM Unsorted && ok "SE plain" || bad "SE plain"
mapped_gt0 se_plain/Log.final.out; bam_ok se_plain/Aligned.out.bam
run se_gz     --readFilesIn data/single.fq.gz                           --outSAMtype BAM Unsorted && ok "SE gz" || bad "SE gz"
mapped_gt0 se_gz/Log.final.out
run pe_plain  --readFilesIn data/pe_1.fq data/pe_2.fq                    --outSAMtype BAM Unsorted && ok "PE plain" || bad "PE plain"
mapped_gt0 pe_plain/Log.final.out
run pe_gz     --readFilesIn data/pe_1.fq.gz data/pe_2.fq.gz             --outSAMtype BAM Unsorted && ok "PE gz" || bad "PE gz"
mapped_gt0 pe_gz/Log.final.out

echo "########## per-file read groups (multi-file) ##########"
run rg --readFilesIn data/a.fq,data/b.fq --outSAMattrRGline ID:grpA , ID:grpB --outSAMtype BAM Unsorted && ok "multi-file+RG ran" || bad "multi-file+RG"
if [ -n "$SAMTOOLS" ]; then
  a_rg=$("$SAMTOOLS" view rg/Aligned.out.bam | awk '/^A_/{for(i=12;i<=NF;i++)if($i~/^RG:Z:/)print $i}' | sort -u | tr '\n' ' ')
  b_rg=$("$SAMTOOLS" view rg/Aligned.out.bam | awk '/^B_/{for(i=12;i<=NF;i++)if($i~/^RG:Z:/)print $i}' | sort -u | tr '\n' ' ')
  [ "$a_rg" = "RG:Z:grpA " ] && [ "$b_rg" = "RG:Z:grpB " ] && ok "per-file RG split (A=grpA B=grpB)" || bad "per-file RG wrong: A=[$a_rg] B=[$b_rg]"
else echo "  SKIP: RG split needs samtools"; fi

echo "########## output formats (SAM text NUL/CR + stdout piping) ##########"
run sam_file  --readFilesIn data/single.fq --outSAMtype SAM               && ok "SAM file ran" || bad "SAM file"
nonempty sam_file/Aligned.out.sam; no_nul sam_file/Aligned.out.sam; no_cr sam_file/Aligned.out.sam; sam_records sam_file/Aligned.out.sam
run bam_uns   --readFilesIn data/single.fq --outSAMtype BAM Unsorted        && ok "BAM Unsorted ran" || bad "BAM Unsorted"; bam_ok bam_uns/Aligned.out.bam
run bam_sort  --readFilesIn data/single.fq --outSAMtype BAM SortedByCoordinate && ok "BAM Sorted ran" || bad "BAM Sorted"
bam_ok bam_sort/Aligned.sortedByCoord.out.bam
if ls -d bam_sort/*_STARtmp >/dev/null 2>&1; then bad "leftover _STARtmp in bam_sort"; else ok "no _STARtmp leaked (bam_sort)"; fi
# stdout piping (the binary-mode test)
mkdir -p std
"$STAR" --genomeDir idx --runThreadN 1 --readFilesIn data/single.fq --outSAMtype SAM --outStd SAM --outFileNamePrefix std/s_ >std/out.sam 2>std/s.log
[ $? -eq 0 ] && ok "SAM stdout exit" || bad "SAM stdout exit"
no_nul std/out.sam; no_cr std/out.sam; sam_records std/out.sam
"$STAR" --genomeDir idx --runThreadN 1 --readFilesIn data/single.fq --outSAMtype BAM Unsorted --outStd BAM_Unsorted --outFileNamePrefix std/b_ >std/out.bam 2>std/b.log
[ $? -eq 0 ] && ok "BAM stdout exit" || bad "BAM stdout exit"
bam_ok std/out.bam

echo "########## extra outputs ##########"
run unmapped --readFilesIn data/single.fq --outSAMtype BAM Unsorted --outSAMunmapped Within && ok "outSAMunmapped Within" || bad "unmapped Within"
mkdir -p quant
"$STAR" --genomeDir idxg --runThreadN $THREADS --readFilesIn data/genic.fq --quantMode GeneCounts \
        --outSAMtype BAM Unsorted --outFileNamePrefix quant/ >quant/run.log 2>&1
if [ $? -eq 0 ] && [ -f quant/ReadsPerGene.out.tab ]; then ok "quantMode GeneCounts"; no_cr quant/ReadsPerGene.out.tab
else bad "GeneCounts ReadsPerGene missing"; fi

echo "########## repeated quantification / annotation precedence ##########"
quant_args=(--star "$STAR" --fixture . --output quant_regression
            --threads "$THREADS" --repeats "${QUANT_REPEATS:-3}")
[ -z "$SAMTOOLS" ] || quant_args+=(--samtools "$SAMTOOLS")
if command -v python3 >/dev/null 2>&1; then PYTHON=python3; else PYTHON=python; fi
"$PYTHON" "$HERE/test_quantification.py" "${quant_args[@]}" && ok "quantification regressions" || bad "quantification regressions"

echo "########## extended POSIX/Windows parity ##########"
parity_threads="$THREADS"
[ "$parity_threads" -ge 2 ] || parity_threads=2
parity_args=(--star "$STAR" --fixture . --output portability --threads "$parity_threads")
[ -z "$SAMTOOLS" ] || parity_args+=(--samtools "$SAMTOOLS")
[ -z "${REF:-}" ] || parity_args+=(--reference "$REF/portability/results.json")
"$PYTHON" "$HERE/test_portability.py" "${parity_args[@]}" && ok "extended portability" || bad "extended portability"

echo "########## resource and workflow parity ##########"
extended_args=(--star "$STAR" --fixture . --output portability_extended --threads "$parity_threads")
[ -z "$SAMTOOLS" ] || extended_args+=(--samtools "$SAMTOOLS")
[ -z "${REF:-}" ] || extended_args+=(--reference "$REF/portability_extended/results.json")
[ -z "${STAR_TEST_UNC_ROOT:-}" ] || extended_args+=(--unc-root "$STAR_TEST_UNC_ROOT")
"$PYTHON" "$HERE/test_portability_extended.py" "${extended_args[@]}" && ok "resource and workflow parity" || bad "resource and workflow parity"

echo "########## global text-output CR/NUL sweep ##########"
if "$PYTHON" - <<'PYSCAN'
from pathlib import Path
bad=[]
for f in Path('.').rglob('*'):
    if 'data' in f.parts or not f.is_file():
        continue
    if f.suffix not in {'.tab','.sam'} and f.name != 'Log.final.out':
        continue
    data=f.read_bytes()
    if b'\r' in data or b'\0' in data:
        bad.append(str(f))
for f in bad: print('CR/NUL in '+f)
raise SystemExit(bool(bad))
PYSCAN
then ok "CR/NUL sweep"; else bad "CR/NUL sweep"; fi

echo "########## error handling (unsupported paths -> clean error, not crash) ##########"
mkdir -p err
"$STAR" --genomeDir idx --readFilesIn data/single.fq.gz --readFilesCommand "zcat" --outFileNamePrefix err/rc_ >err/rc.log 2>&1; rc=$?
if [ "$IS_WIN" = 1 ]; then
  # native Windows has no fork/exec -> must fail cleanly, not crash
  { [ $rc -ne 0 ] && grep -qiE 'readFilesCommand|EXITING|fork' err/rc.log; } && ok "readFilesCommand -> clean error on Windows (rc=$rc)" || bad "readFilesCommand did not error cleanly (rc=$rc)"
else
  [ $rc -eq 0 ] && ok "readFilesCommand works on POSIX (rc=0)" || bad "readFilesCommand unexpectedly failed on POSIX (rc=$rc)"
fi

echo "########## input integrity (native gzip errors, SAM-input headers, GeneCounts) ##########"
mkdir -p integrity
"$PYTHON" - <<'PYGEN'
import gzip
reads = open('data/single.fq', 'rb').read()
open('integrity/truncated.fq.gz', 'wb').write(gzip.compress(reads, mtime=0)[:-8])
lines = reads.decode().splitlines()
sam = '@HD\tVN:1.6\n@RG\tID:suiteRG\tSM:suiteSample\n@CO\tsuite-comment\n'
for i in range(0, 40, 4):
    sam += f'{lines[i][1:]}\t4\t*\t0\t0\t*\t*\t0\t0\t{lines[i+1]}\t{lines[i+3]}\tRG:Z:suiteRG\n'
open('integrity/input.sam', 'w', newline='\n').write(sam)
PYGEN
run trunc_gz --readFilesIn integrity/truncated.fq.gz --outSAMtype SAM; rc=$?
[ $rc -ne 0 ] && [ $rc -lt 128 ] && ok "truncated .gz -> nonzero exit (rc=$rc)" || bad "truncated .gz not rejected (rc=$rc)"
run sam_in --readFilesIn integrity/input.sam --readFilesType SAM SE --outSAMtype SAM && ok "SAM input ran" || bad "SAM input"
LC_ALL=C grep -q $'^@RG\tID:suiteRG\tSM:suiteSample' sam_in/Aligned.out.sam 2>/dev/null && LC_ALL=C grep -q $'^@CO\tsuite-comment' sam_in/Aligned.out.sam \
  && ok "SAM-input @RG/@CO header lines kept" || bad "SAM-input header lines lost"
mkdir -p gc1
"$STAR" --genomeDir idxg --runThreadN 1 --readFilesIn data/genic.fq --quantMode GeneCounts \
        --outSAMtype None --outFileNamePrefix gc1/ >gc1/run.log 2>&1
[ $? -eq 0 ] && awk -F'\t' '$1=="g1" && $2==500 {f=1} END {exit !f}' gc1/ReadsPerGene.out.tab 2>/dev/null \
  && ok "GeneCounts single-thread: g1=500" || bad "GeneCounts single-thread wrong/missing"

echo
echo "########## RESULT: $PASS passed, $FAIL failed ##########"
[ $FAIL -eq 0 ] || exit 1
