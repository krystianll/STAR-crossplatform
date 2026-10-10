#!/usr/bin/env python3
"""Native bzip2 read input (GzIfstream.h, built with -DSTAR_GZ_INPUT).

Run from a finished run_tests.sh work directory (it reuses its fixtures):

    python3 test_bzip2_input.py --star /path/to/STAR --fixture . --output bzip2

Every bzip2 case must give exactly the alignments of the same reads given as
plain text. Bad bzip2 data must stop STAR with a clean error. --reference
compares the output fingerprints with another platform's results.json.
"""
import argparse
import bz2
import gzip
import os
from pathlib import Path
import subprocess
import threading
from test_portability import Suite, require


class Bzip2Suite(Suite):
    def same(self, name, reads, expected, extra=(), fingerprint=True):
        out = self.run(name, ['--outSAMtype', 'SAM'] + list(extra), reads=reads)
        records = self.records(out/'Aligned.out.sam', len(expected))
        require(sorted(records) == sorted(expected), 'alignments differ from plain input')
        if fingerprint:   # only cases every platform runs are compared across platforms
            self.fingerprint(name, records)
        return out

    def execute(self):
        fixture = self.fixture/'data'
        base = (fixture/'single.fq').read_bytes()
        a = (fixture/'a.fq').read_bytes()
        b = (fixture/'b.fq').read_bytes()
        packed = bz2.compress(base)
        self.write('single.fq.bz2', packed)
        self.write('single-noext.fq', packed)
        self.write('reads_λ_🧬.fq.bz2', packed)
        self.write('streams.fq.bz2', bz2.compress(a) + bz2.compress(b))
        self.write('garbage.fq.bz2', packed + b'not bzip2 data\n')
        self.write('a.fq.bz2', bz2.compress(a))
        self.write('b.fq.gz', gzip.compress(b, mtime=0))
        self.write('empty.fq.bz2', bz2.compress(b''))
        self.write('combined.fq', a + b)
        self.write('truncated.fq.bz2', packed[:len(packed) // 2])
        corrupt = bytearray(packed)
        corrupt[10] ^= 0xff                  # first block's CRC: data decodes, CRC check fails
        self.write('bad-crc.fq.bz2', bytes(corrupt))
        corrupt = bytearray(packed)
        corrupt[len(corrupt) // 2] ^= 0xff   # inside the block: decoder or read parser fails
        self.write('corrupt.fq.bz2', bytes(corrupt))
        for mate in [1, 2]:
            self.write(f'pe_{mate}.fq.bz2', bz2.compress((fixture/f'pe_{mate}.fq').read_bytes()))
        lines = base.decode().splitlines()
        sam = '@HD\tVN:1.6\n@RG\tID:source0\tSM:sample0\n@CO\tcomment0\n' + ''.join(
            f'{lines[i][1:]}\t4\t*\t0\t0\t*\t*\t0\t0\t{lines[i+1]}\t{lines[i+3]}\tRG:Z:source0\tZZ:Z:retained\n'
            for i in range(0, 40, 4))
        self.write('input.sam.bz2', bz2.compress(sam.encode()))

        plain = self.records(self.run('plain', ['--outSAMtype', 'SAM'])/'Aligned.out.sam')
        combined = self.records(self.run('plain-combined', ['--outSAMtype', 'SAM'],
                                         reads=[self.data/'combined.fq'])/'Aligned.out.sam')
        paired = self.records(self.run('plain-paired', ['--outSAMtype', 'SAM'],
                                       reads=[fixture/'pe_1.fq', fixture/'pe_2.fq'])/'Aligned.out.sam')

        for name, file in [('bzip2_single', 'single.fq.bz2'),
                           ('bzip2_detected_by_bytes_not_name', 'single-noext.fq'),
                           ('bzip2_non_ascii_path', 'reads_λ_🧬.fq.bz2'),
                           ('bzip2_trailing_garbage_ignored', 'garbage.fq.bz2')]:
            self.check(name, lambda name=name, file=file: self.same(name, [self.data/file], plain))
        self.check('bzip2_concatenated_streams',
                   lambda: self.same('bzip2_concatenated_streams', [self.data/'streams.fq.bz2'], combined))
        self.check('bzip2_paired',
                   lambda: self.same('bzip2_paired', [self.data/'pe_1.fq.bz2', self.data/'pe_2.fq.bz2'], paired))

        def mixed():
            files = ','.join(str(self.data/f) for f in ['empty.fq.bz2', 'a.fq.bz2', 'b.fq.gz'])
            out = self.run('bzip2_mixed_multifile', ['--outSAMtype', 'SAM', '--outSAMattrRGline',
                                                     'ID:E', ',', 'ID:A', ',', 'ID:B'], reads=[files])
            records = self.records(out/'Aligned.out.sam', len(combined))
            names_a = {line[1:].split()[0] for line in a.splitlines()[::4]}
            for row in records:
                fields = row.split(b'\t')
                expected = b'RG:Z:A' if fields[0] in names_a else b'RG:Z:B'
                require(expected in fields[11:], f'wrong per-file read group for {fields[0]!r}')
            stripped = [b'\t'.join(f for f in r.split(b'\t') if not f.startswith(b'RG:Z:')) for r in records]
            require(sorted(stripped) == sorted(combined), 'alignments differ from plain input')
            self.fingerprint('bzip2_mixed_multifile', records)
        self.check('bzip2_mixed_multifile_read_groups', mixed)

        def sam_input():
            out = self.run('bzip2_sam_input', ['--outSAMtype', 'SAM', '--readFilesType', 'SAM', 'SE',
                                               '--readFilesSAMattrKeep', 'All'], reads=[self.data/'input.sam.bz2'])
            header = self.text(out/'Aligned.out.sam', True)
            require(b'@RG\tID:source0\tSM:sample0' in header and b'@CO\tcomment0' in header, 'SAM headers lost')
            records = self.records(out/'Aligned.out.sam', 10)
            require(all(b'ZZ:Z:retained' in r for r in records), 'SAM attributes lost')
            self.fingerprint('bzip2_sam_input', records)
        self.check('bzip2_sam_input_headers', sam_input)

        # Like gzip, bzip2 verifies a block's CRC only after handing out its
        # bytes, so damage inside a block may first trip STAR's read parser.
        for name, message in [('truncated.fq.bz2', b'truncated bzip2 input'),
                              ('bad-crc.fq.bz2', b'invalid bzip2 data'), ('corrupt.fq.bz2', None)]:
            def bad(name=name, message=message):
                out = self.run('bad-' + name, [], reads=[self.data/name], success=False)
                log = (out/'run.log').read_bytes()
                if message:
                    require(b'fatal input ERROR: ' in log and (name.encode() + b': ' + message) in log,
                            'error does not name the file and the bzip2 problem')
            self.check(name + '_is_error', bad)

        if os.name == 'posix':   # a pipe is not sniffed: plain and gzip still stream through it
            for label, payload in [('plain', base), ('gzip', gzip.compress(base, mtime=0))]:
                def fifo(label=label, payload=payload):
                    path = self.data/f'pipe-{label}.fq'
                    os.mkfifo(path)
                    def feed():
                        with open(path, 'wb') as pipe:
                            pipe.write(payload)
                    writer = threading.Thread(target=feed, daemon=True)
                    writer.start()
                    try:
                        self.same('fifo_' + label, [path], plain, fingerprint=False)
                    finally:
                        writer.join(5)
                        path.unlink()
                self.check('fifo_' + label + '_not_sniffed', fifo)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--star', required=True)
    p.add_argument('--fixture', type=Path, default=Path('.'))
    p.add_argument('--output', type=Path, default=Path('bzip2'))
    p.add_argument('--reference', type=Path)
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--only', help='run checks whose names match this regular expression')
    args = p.parse_args()
    args.foreign_index = None
    args.samtools = None
    suite = Bzip2Suite(args)
    try:
        suite.execute()
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as exc:
        suite.results.append(dict(name='suite_setup', status='FAIL', error=str(exc)))
        print('FAIL: suite setup: ' + str(exc), flush=True)
    return suite.finish()


if __name__ == '__main__':
    raise SystemExit(main())
