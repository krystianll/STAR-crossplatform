#!/usr/bin/env python3
"""Generate a small, deterministic synthetic test dataset for the STAR test suite:
a 2-contig genome, a minimal GTF, and reads (SE / PE / gzipped / multi-file).
All FASTQ/FASTA are written LF-only so line endings are controlled by STAR, not
the OS. Reads are exact genome substrings (mate2 reverse-complemented) so they map
uniquely, making output comparisons stable across platforms."""
import random, gzip, os, sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(OUT, exist_ok=True)
random.seed(1234)
rc = lambda s: s.translate(str.maketrans("ACGT", "TGCA"))[::-1]
rs = lambda n: "".join(random.choice("ACGT") for _ in range(n))

G = {"chr1": rs(300_000), "chr2": rs(200_000)}
def w(path, text, gz=False):
    op = gzip.open(path, "wt", newline="\n") if gz else open(path, "w", newline="\n")
    with op as f: f.write(text)

# genome.fa
fa = "".join(f">{k}\n" + "\n".join(v[i:i+70] for i in range(0, len(v), 70)) + "\n"
             for k, v in G.items())
w(os.path.join(OUT, "genome.fa"), fa)

# minimal GTF: a few single-exon genes on chr1 (enough for --sjdbGTFfile / GeneCounts)
genes = [(10_000, 12_000, "+"), (50_000, 53_000, "-"), (120_000, 121_500, "+")]
gtf = []
for gi, (s, e, st) in enumerate(genes, 1):
    attr = f'gene_id "g{gi}"; transcript_id "t{gi}";'
    gtf.append(f"chr1\ttest\tgene\t{s}\t{e}\t.\t{st}\t.\tgene_id \"g{gi}\";")
    gtf.append(f"chr1\ttest\ttranscript\t{s}\t{e}\t.\t{st}\t.\t{attr}")
    gtf.append(f"chr1\ttest\texon\t{s}\t{e}\t.\t{st}\t.\t{attr}")
w(os.path.join(OUT, "genes.gtf"), "\n".join(gtf) + "\n")

def se_reads(n, L=100, region=None):
    out = []
    for i in range(n):
        if region:
            chrom, lo, hi = region
            p = random.randint(lo, hi - L)
            out.append(("g_%d" % i, G[chrom][p:p+L]))
        else:
            c = random.choice(list(G)); s = G[c]; p = random.randint(0, len(s) - L)
            out.append(("u_%d" % i, s[p:p+L]))
    return out

def fq(reads):
    return "".join(f"@{name}\n{seq}\n+\n{'I'*len(seq)}\n" for name, seq in reads)

# single-end (plain + gz)
se = se_reads(2000)
w(os.path.join(OUT, "single.fq"), fq(se))
w(os.path.join(OUT, "single.fq.gz"), fq(se), gz=True)

# reads inside gene g1 region, for --quantMode GeneCounts
gse = se_reads(500, region=("chr1", 10_000, 12_000))
w(os.path.join(OUT, "genic.fq"), fq(gse))

# paired-end (plain + gz), mate2 reverse-complemented so pairs map FR
pe1, pe2 = [], []
for i in range(1500):
    c = random.choice(list(G)); s = G[c]; p = random.randint(0, len(s) - 300)
    pe1.append(("p_%d" % i, s[p:p+100])); pe2.append(("p_%d" % i, rc(s[p+200:p+300])))
w(os.path.join(OUT, "pe_1.fq"), fq(pe1)); w(os.path.join(OUT, "pe_2.fq"), fq(pe2))
w(os.path.join(OUT, "pe_1.fq.gz"), fq(pe1), gz=True); w(os.path.join(OUT, "pe_2.fq.gz"), fq(pe2), gz=True)

# multi-file per mate, for per-file read-group test (names prefixed A_/B_)
a = [("A_%d" % i, se[i][1]) for i in range(0, 800)]
b = [("B_%d" % i, se[i][1]) for i in range(800, 1600)]
w(os.path.join(OUT, "a.fq"), fq(a)); w(os.path.join(OUT, "b.fq"), fq(b))

print("generated test data in", OUT)
