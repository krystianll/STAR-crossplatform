#!/usr/bin/env python3
"""Second audit: resource limits, manifests, extra Solo modes, and path forms.

Optional --probe-crlf-metadata exposes remaining upstream parser defects; it is
not part of the passing Windows parity suite. --unc-root requires an existing
Windows share directory explicitly supplied by the caller.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
from test_portability import Suite, require, digest


class ExtendedSuite(Suite):
    def execute(self):
        self.idx = self.index('index-lf')
        out = self.run('sam-base', ['--outSAMtype', 'SAM'])
        self.base = self.records(out/'Aligned.out.sam', 2000)
        self.fingerprint('single', self.base)
        if self.args.samtools:
            for name, threads, bins in [('sorted_12_threads', 12, 50), ('sorted_300_bins', 2, 300)]:
                def many(name=name, threads=threads, bins=bins):
                    previous_threads = self.args.threads
                    self.args.threads = threads
                    try:
                        out = self.run(name, ['--outBAMsortingBinsN', bins,
                            '--limitIObufferSize', '12000000', '12000000', '--limitBAMsortRAM', '100000000',
                            '--outSAMtype', 'BAM', 'SortedByCoordinate'])
                    finally:
                        self.args.threads = previous_threads
                    records = self.records(out/'Aligned.sortedByCoord.out.bam', 2000)
                    require(sorted(records) == sorted(self.base), 'high-stream-count BAM differs')
                    self.clean(out)
                    self.fingerprint(name, records)
                self.check(name, many)

        if self.args.samtools:
            def consumed_bins():
                out = self.run('consumed-bins', ['--outSAMtype', 'BAM', 'SortedByCoordinate', '--outTmpKeep', 'All'])
                require(sorted(self.records(out/'Aligned.sortedByCoord.out.bam', 2000)) == sorted(self.base), 'kept-temp BAM differs')
                bins = out/'_STARtmp/BAMsort'
                remaining = [p for d in bins.iterdir() if d.is_dir() for p in d.iterdir() if p.is_file() and p.stat().st_size]
                require(not remaining, 'consumed nonempty BAM input bins remain after sorting')
            self.check('sorted_consumed_bins_removed_with_outTmpKeep_All', consumed_bins)

        def prefix_file():
            prefix = (self.root/'prefix parent'/'nested'/'sample_').as_posix()
            self.run('filename-prefix', ['--outSAMtype', 'SAM'], prefix=prefix)
            require(sorted(self.records(Path(prefix+'Aligned.out.sam'), 2000)) == sorted(self.base), 'filename prefix changed reads')
            require(not Path(prefix+'_STARtmp').exists(), 'filename-prefix temporary directory remains')
        self.check('filename_output_prefix_nested', prefix_file)

        def custom_temp():
            temp = self.root/'separate temp with spaces'
            out = self.run('custom-temp', ['--outSAMtype', 'SAM', '--outTmpDir', temp])
            require(not temp.exists(), 'explicit temp directory remains')
            require(sorted(self.records(out/'Aligned.out.sam', 2000)) == sorted(self.base), 'custom temp changed reads')
        self.check('explicit_temporary_directory_cleanup', custom_temp)

        def keep_temp():
            out = self.run('keep-temp', ['--outSAMtype', 'SAM', '--outReadsUnmapped', 'Fastx', '--outTmpKeep', 'All'],
                           index=self.idx, reads=[self.data/'mixed.fq'])
            files = list((out/'_STARtmp').rglob('*'))
            require(any(p.is_file() and p.stat().st_size for p in files), 'outTmpKeep All discarded temporary files')
            self.records(out/'Aligned.out.sam', 580)
        self.check('outTmpKeep_All_preserves_files', keep_temp)

        def rerun():
            for _ in range(2):
                out = self.run('rerun', ['--outSAMtype', 'SAM'])
                require(sorted(self.records(out/'Aligned.out.sam', 2000)) == sorted(self.base), 'rerun appends or changes SAM')
                self.clean(out)
        self.check('reuse_alignment_output_prefix', rerun)

        def prefixed_reads():
            out = self.run('read-prefix', ['--readFilesPrefix', self.data.as_posix()+'/', '--outSAMtype', 'SAM',
                           '--outSAMattrRGline', 'ID:A', ',', 'ID:B'], reads=['a.fq.gz,b.fq.gz'])
            rows = self.records(out/'Aligned.out.sam', 1600)
            require(sum(b'\tRG:Z:A' in r for r in rows) == 800, 'wrong first read group')
            require(sum(b'\tRG:Z:B' in r for r in rows) == 800, 'wrong second read group')
            self.fingerprint('read_prefix', rows)
            self.clean(out)
        self.check('readFilesPrefix_mixed_lists', prefixed_reads)

        def manifest(paired, crlf=False):
            name = ('paired' if paired else 'single') + ('-crlf' if crlf else '-lf')
            if paired:
                rows = [(self.data/'pe1a.fq', self.data/'pe2a.fq', 'A'),
                        (self.data/'pe1b.fq.gz', self.data/'pe2b.fq.gz', 'B')]
                expected, group_a = 3000, 1400
            else:
                rows = [(self.fixture/'data/a.fq', '-', 'A'), (self.data/'b.fq.gz', '-', 'B')]
                expected, group_a = 1600, 800
            text = ''.join(f'{a}\t{b}\tID:{rg}\n' for a, b, rg in rows).encode()
            path = self.data/(name+'.manifest')
            path.write_bytes(text.replace(b'\n', b'\r\n') if crlf else text)
            out = self.run('manifest-'+name, ['--readFilesManifest', path, '--outSAMtype', 'SAM', '--outSAMattributes', 'NH', 'HI', 'AS', 'nM', 'RG'], reads=False)
            records = self.records(out/'Aligned.out.sam', expected)
            require(sum(b'\tRG:Z:A' in r for r in records) == group_a, 'manifest read-group association wrong')
            require(sum(b'\tRG:Z:B' in r for r in records) == expected-group_a, 'manifest second read group wrong')
            self.fingerprint('manifest_'+name, records)
            self.clean(out)
        self.check('manifest_single_read_groups', lambda: manifest(False))
        self.check('manifest_paired_read_groups', lambda: manifest(True))

        def smartseq():
            data = (self.fixture/'data/genic.fq').read_bytes().splitlines(keepends=True)
            self.write('cellA.fq', b''.join(data[:1000]))
            self.write('cellB.fq.gz', gzip.compress(b''.join(data[1000:]), mtime=0))
            out = self.run('smartseq', ['--outSAMtype', 'SAM', '--soloType', 'SmartSeq', '--soloUMIdedup', 'NoDedup',
                '--soloFeatures', 'Gene', '--soloCellFilter', 'None', '--outSAMattrRGline', 'ID:cellA', ',', 'ID:cellB'],
                index=self.idx, reads=[str(self.data/'cellA.fq')+','+str(self.data/'cellB.fq.gz')])
            raw = out/'Solo.out/Gene/raw'
            require(self.text(raw/'barcodes.tsv').splitlines() == [b'cellA', b'cellB'], 'SmartSeq cell names differ')
            matrix = self.text(raw/'matrix.mtx', True)
            rows = [r.split() for r in matrix.splitlines() if not r.startswith(b'%')]
            require(rows[0] == [b'4', b'2', b'2'] and sorted(int(r[2]) for r in rows[1:]) == [250, 250], 'SmartSeq counts differ')
            self.fingerprints['smartseq_matrix'] = digest(matrix)
            require(b'Finished redistribution' in (out/'Log.out').read_bytes(), 'redistribution path not exercised')
            self.clean(out)
        self.check('solo_SmartSeq_redistribution_cleanup', smartseq)

        if self.args.samtools:
            for tag_only in [False, True]:
                def solo_tags(tag_only=tag_only):
                    name = 'solo-tag-only' if tag_only else 'solo-sorted-tags'
                    attrs = ['NH', 'HI', 'AS', 'nM', 'CR', 'CY', 'UR', 'UY'] + ([] if tag_only else ['CB', 'UB'])
                    extra = ['--outSAMtype', 'BAM', 'Unsorted' if tag_only else 'SortedByCoordinate',
                             '--soloType', 'CB_samTagOut' if tag_only else 'CB_UMI_Simple',
                             '--soloCBwhitelist', self.data/'whitelist.txt', '--soloCellFilter', 'None',
                             '--soloUMIdedup', 'Exact', '--soloCBmatchWLtype', 'Exact', '--outSAMattributes'] + attrs
                    out = self.run(name, extra, index=self.idx, reads=[self.data/'solo-rna.fq', self.data/'solo-cb.fq'])
                    bam = out/('Aligned.out.bam' if tag_only else 'Aligned.sortedByCoord.out.bam')
                    records = self.records(bam, 40)
                    for row in records:
                        require(b'\tCR:Z:ACGTACGTACGTACGT' in row and b'\tUR:Z:' in row, 'raw barcode/UMI tag missing')
                        if not tag_only: require(b'\tCB:Z:' in row and b'\tUB:Z:' in row, 'corrected barcode/UMI tag missing')
                    self.fingerprint(name, records)
                    self.clean(out)
                self.check('solo_tag_only_cleanup' if tag_only else 'solo_sorted_corrected_tags_cleanup', solo_tags)

            def input_bam():
                source = self.run('wiggle-source', ['--outSAMtype', 'BAM', 'SortedByCoordinate'], reads=[self.fixture/'data/genic.fq'])
                out = self.run('input-bam', ['--runMode', 'inputAlignmentsFromBAM', '--inputBAMfile', source/'Aligned.sortedByCoord.out.bam',
                               '--outWigType', 'bedGraph', '--outWigStrand', 'Unstranded', '--outWigNorm', 'None'], index=False, reads=False)
                data = self.text(out/'Signal.Unique.str1.out.bg', True)
                area = sum((int(r[2])-int(r[1]))*float(r[3]) for r in (line.split() for line in data.splitlines()))
                require(area == 50000, 'BAM-input coverage differs')
                self.fingerprints['input_bam_coverage'] = digest(data)
                self.clean(out)
            self.check('inputAlignmentsFromBAM_coverage', input_bam)

        def cell_filter(crlf=False):
            raw = self.data/('raw-crlf' if crlf else 'raw-lf'); raw.mkdir()
            for name, data in [('features.tsv', b'g1\tgene1\tGene Expression\n'),
                               ('barcodes.tsv', b'ACGT\nTGCA\n'),
                               ('matrix.mtx', b'%%MatrixMarket matrix coordinate integer general\n1 2 2\n1 1 10\n1 2 5\n')]:
                (raw/name).write_bytes(data.replace(b'\n', b'\r\n') if crlf else data)
            prefix = self.root/('filtered-crlf' if crlf else 'filtered-lf')
            out = self.run('filter-crlf' if crlf else 'filter-lf', ['--runMode', 'soloCellFiltering', raw, prefix.as_posix()+'/',
                '--soloCellFilter', 'TopCells', '1'], index=False, reads=False)
            require(self.text(prefix/'barcodes.tsv', True) == b'ACGT\n', 'filtered barcode content differs')
            matrix = self.text(prefix/'matrix.mtx', True)
            require(matrix.splitlines()[-1].split() == [b'1', b'1', b'10'], 'filtered matrix differs')
            self.fingerprints['cell_filter_'+('crlf' if crlf else 'lf')] = digest(matrix)
        self.check('soloCellFiltering_external_matrix', cell_filter)

        if self.args.unc_root:
            require(os.name == 'nt', '--unc-root is Windows-only')
            for native in [False, True]:
                def unc(native=native):
                    prefix = self.args.unc_root/('backslash' if native else 'forward')/'new parent'/'nested'
                    arg = str(prefix)+'\\' if native else prefix.as_posix()+'/'
                    self.run('unc-backslash' if native else 'unc-forward', ['--outSAMtype', 'SAM'], prefix=arg)
                    require(sorted(self.records(prefix/'Aligned.out.sam', 2000)) == sorted(self.base), 'UNC output differs')
                    self.clean(prefix)
                self.check('UNC_backslash_nested_output' if native else 'UNC_forward_nested_output', unc)

        if self.args.probe_crlf_metadata:
            self.check('upstream_probe_manifest_crlf', lambda: manifest(False, True))
            self.check('upstream_probe_cell_filter_crlf', lambda: cell_filter(True))
            def sam_crlf():
                self.write('input-crlf.sam', (self.data/'input0.sam').read_bytes().replace(b'\n', b'\r\n'))
                out = self.run('sam-crlf', ['--readFilesType', 'SAM', 'SE', '--outSAMtype', 'SAM'], reads=[self.data/'input-crlf.sam'])
                self.records(out/'Aligned.out.sam', 10)
            self.check('upstream_probe_sam_crlf', sam_crlf)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--star', required=True)
    p.add_argument('--samtools')
    p.add_argument('--fixture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--only')
    p.add_argument('--reference', type=Path)
    p.add_argument('--unc-root', type=Path)
    p.add_argument('--probe-crlf-metadata', action='store_true')
    p.set_defaults(foreign_index=None)
    args = p.parse_args()
    suite = ExtendedSuite(args)
    try:
        suite.execute()
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as exc:
        suite.results.append(dict(name='suite_setup', status='FAIL', error=str(exc)))
        print('FAIL: suite setup: '+str(exc), flush=True)
    return suite.finish()


if __name__ == '__main__':
    raise SystemExit(main())
