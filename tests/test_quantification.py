#!/usr/bin/env python3
"""Repeat quantification against run_tests.sh's synthetic indexes.

Checks exact counts and annotation precedence, not just output-file presence.
All subprocess logs and a JSON result summary are retained in --output.
"""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--star", required=True)
    parser.add_argument("--samtools")
    parser.add_argument("--fixture", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("quant_regression"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    if args.repeats < 1 or args.threads < 1:
        parser.error("repeats and threads must be positive")
    fixture = args.fixture.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    override = output / "override.gtf"
    annotation = (fixture / "data/genes.gtf").read_text()
    for i in range(1, 4):
        annotation = annotation.replace(f'"g{i}"', f'"override_g{i}"')
        annotation = annotation.replace(f'"t{i}"', f'"override_t{i}"')
    override.write_bytes(annotation.encode())

    results = []
    for case, index, gtf, prefix in [
        ("baked", "idxg", None, ""),
        ("on_the_fly", "idx", fixture / "data/genes.gtf", ""),
        ("override_baked", "idxg", override, "override_"),
    ]:
        expected = {f"{prefix}g1": [500, 500, 0],
                    f"{prefix}g2": [0, 0, 0], f"{prefix}g3": [0, 0, 0]}
        for threads in sorted({1, args.threads}):
            for repeat in range(args.repeats):
                name = f"{case}_t{threads}_{repeat}"
                run_dir = output / name
                run_dir.mkdir()
                cmd = [args.star, "--genomeDir", str(fixture / index),
                       "--readFilesIn", str(fixture / "data/genic.fq"),
                       "--runThreadN", str(threads), "--quantMode",
                       "GeneCounts", "TranscriptomeSAM", "--outSAMtype", "BAM",
                       "Unsorted", "--outFileNamePrefix", str(run_dir) + "/"]
                if gtf:
                    cmd += ["--sjdbGTFfile", str(gtf), "--sjdbOverhang", "99"]
                result = {"case": name, "command": cmd}
                try:
                    with (run_dir / "run.log").open("wb") as log:
                        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                                              timeout=120)
                    result["returncode"] = proc.returncode
                    if proc.returncode:
                        raise ValueError(f"STAR exited {proc.returncode}")
                    table = (run_dir / "ReadsPerGene.out.tab").read_bytes()
                    if b"\r" in table or b"\0" in table:
                        raise ValueError("CR/NUL in gene counts")
                    rows = [line.split("\t") for line in table.decode().splitlines()]
                    counts = {r[0]: list(map(int, r[1:])) for r in rows}
                    wanted = dict(expected, N_unmapped=[0, 0, 0],
                                  N_multimapping=[0, 0, 0], N_ambiguous=[0, 0, 0],
                                  N_noFeature=[0, 0, 500])
                    if len(rows) != len(wanted) or counts != wanted:
                        raise ValueError(f"unexpected gene counts: {counts}")
                    if gtf:
                        model = run_dir / "_STARgenome/geneInfo.tab"
                        if not model.is_file() or not model.stat().st_size:
                            raise ValueError("on-the-fly gene model missing")
                    bam = run_dir / "Aligned.toTranscriptome.out.bam"
                    if not bam.is_file() or not bam.stat().st_size:
                        raise ValueError("transcriptome BAM missing/empty")
                    if args.samtools:
                        decoded = subprocess.run([args.samtools, "view", str(bam)],
                                                 check=True, capture_output=True,
                                                 text=True, timeout=30)
                        records = [line.split("\t") for line in decoded.stdout.splitlines()]
                        if len(records) != 500 or any(r[2] != prefix + "t1" for r in records):
                            raise ValueError("transcriptome BAM count/annotation mismatch")
                    if list(run_dir.glob("*_STARtmp")):
                        raise ValueError("temporary directory leaked")
                    result["passed"] = True
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    result.update(passed=False, error=str(exc))
                results.append(result)
                print(f'{"PASS" if result["passed"] else "FAIL"}: {name}'
                      + (f': {result["error"]}' if "error" in result else ""), flush=True)
    (output / "results.json").write_text(json.dumps(results, indent=2))
    failures = sum(not result["passed"] for result in results)
    print(f"Quantification: {len(results) - failures} passed, {failures} failed")
    if not args.samtools:
        print("SKIP: transcriptome BAM decoding (samtools not supplied)")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
