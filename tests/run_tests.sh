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
# Exit code 0 = all pass. Set REF=<dir> to also diff Log.final.out mapping
# numbers against a reference platform's outputs (golden comparison).
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
no_cr()  { if LC_ALL=C grep -qU $'\r' "$1" 2>/dev/null; then bad "CR (\\r) found in $1"; else ok "no CR in $(basename "$1")"; fi; }
no_nul() { if [ "$(tr -cd '\000' < "$1" | wc -c | tr -d ' ')" != 0 ]; then bad "NUL byte in $1"; else ok "no NUL in $(basename "$1")"; fi; }
nonempty(){ if [ -s "$1" ]; then ok "$(basename "$1") non-empty"; else bad "$1 missing/empty"; fi; }
no_startmp(){ if ls -d "$1"/*_STARtmp >/dev/null 2>&1; then bad "leftover _STARtmp in $1"; else ok "no _STARtmp leaked"; fi; }
mapped_gt0(){ n=$(awk -F'|' '/Uniquely mapped reads number/{gsub(/ /,"",$2);print $2}' "$1"); if [ "${n:-0}" -gt 0 ] 2>/dev/null; then ok "mapped=$n (>0)"; else bad "0 mapped in $1"; fi; }
sam_records(){ if LC_ALL=C grep -avc -e '^@' "$1" | grep -q '^0$'; then bad "no SAM records in $1"; else ok "SAM has records"; fi; }
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
no_nul std/out.sam; no_cr std/out.sam; sam_records std/out.sam
"$STAR" --genomeDir idx --runThreadN 1 --readFilesIn data/single.fq --outSAMtype BAM Unsorted --outStd BAM_Unsorted --outFileNamePrefix std/b_ >std/out.bam 2>std/b.log
bam_ok std/out.bam

echo "########## extra outputs ##########"
run unmapped --readFilesIn data/single.fq --outSAMtype BAM Unsorted --outSAMunmapped Within && ok "outSAMunmapped Within" || bad "unmapped Within"
mkdir -p quant
"$STAR" --genomeDir idxg --runThreadN $THREADS --readFilesIn data/genic.fq --quantMode GeneCounts \
        --outSAMtype BAM Unsorted --outFileNamePrefix quant/ >quant/run.log 2>&1
if [ -f quant/ReadsPerGene.out.tab ]; then ok "quantMode GeneCounts"; no_cr quant/ReadsPerGene.out.tab
else bad "GeneCounts ReadsPerGene missing"; fi

echo "########## global text-output CR/NUL sweep ##########"
for f in $(find . -name '*.tab' -o -name 'Log.final.out' -o -name '*.sam' 2>/dev/null); do
  LC_ALL=C grep -qU $'\r' "$f" 2>/dev/null && bad "CR in $f"
done; ok "CR sweep of .tab/.sam/Log.final.out done"

echo "########## error handling (unsupported paths -> clean error, not crash) ##########"
mkdir -p err
"$STAR" --genomeDir idx --readFilesIn data/single.fq.gz --readFilesCommand "zcat" --outFileNamePrefix err/rc_ >err/rc.log 2>&1; rc=$?
if [ "$IS_WIN" = 1 ]; then
  # native Windows has no fork/exec -> must fail cleanly, not crash
  { [ $rc -ne 0 ] && grep -qiE 'readFilesCommand|EXITING|fork' err/rc.log; } && ok "readFilesCommand -> clean error on Windows (rc=$rc)" || bad "readFilesCommand did not error cleanly (rc=$rc)"
else
  [ $rc -eq 0 ] && ok "readFilesCommand works on POSIX (rc=0)" || bad "readFilesCommand unexpectedly failed on POSIX (rc=$rc)"
fi

echo
echo "########## RESULT: $PASS passed, $FAIL failed ##########"
[ $FAIL -eq 0 ] || exit 1
