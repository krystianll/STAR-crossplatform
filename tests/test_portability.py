#!/usr/bin/env python3
"""Targeted POSIX/Windows parity checks. Uses run_tests.sh's tiny fixtures.

No third-party Python packages. Logs, checks, and canonical output fingerprints
are retained. --reference compares stable biological outputs across platforms.
"""
import argparse
import gzip
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
from run_unit_tests import sparse_file


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fq(records):
    return ''.join(f'@{name}\n{seq}\n+\n{"I" * len(seq)}\n' for name, seq in records).encode()


class Suite:
    def __init__(self, args):
        self.args = args
        self.fixture = args.fixture.resolve()
        if args.foreign_index:
            args.foreign_index = args.foreign_index.resolve()
        args.output.mkdir(parents=True, exist_ok=False)
        self.root = args.output.resolve()
        self.data = self.root / 'data'
        self.data.mkdir()
        self.results = []
        self.fingerprints = {}
        self.commands = []
        self.prepare()

    def prepare(self):
        genome = {}
        for line in (self.fixture / 'data/genome.fa').read_text().splitlines():
            if line.startswith('>'):
                chrom = line[1:]
                genome[chrom] = ''
            else:
                genome[chrom] += line
        # Canonical annotated and novel splice junctions, plus a translocation.
        seq = list(genome['chr1'])
        for end, start in [(200000, 200300), (220000, 220300)]:
            seq[end:end+2] = 'GT'
            seq[start-2:start] = 'AG'
        genome['chr1'] = ''.join(seq)
        fa = ''.join(f'>{c}\n' + '\n'.join(s[i:i+70] for i in range(0, len(s), 70)) + '\n'
                     for c, s in genome.items()).encode()
        gtf = (self.fixture / 'data/genes.gtf').read_bytes()
        gtf += b'chr1\ttest\texon\t199901\t200000\t.\t+\t.\tgene_id "g4"; transcript_id "t4";\n'
        gtf += b'chr1\ttest\texon\t200301\t200400\t.\t+\t.\tgene_id "g4"; transcript_id "t4";\n'
        self.write('genome.fa', fa)
        self.write('genes.gtf', gtf)
        self.write('genome-crlf.fa', fa.replace(b'\n', b'\r\n'))
        self.write('genes-crlf.gtf', gtf.replace(b'\n', b'\r\n'))
        base = (self.fixture / 'data/single.fq').read_bytes()
        self.write('reads-crlf.fq', base.replace(b'\n', b'\r\n'))
        self.write('reads-crlf.fq.gz', gzip.compress(base.replace(b'\n', b'\r\n'), mtime=0))
        records = base.decode().splitlines()
        self.write('reads.fa', ''.join(f'>{records[i][1:]}\n{records[i+1][:50]}\n{records[i+1][50:]}\n'
                                      for i in range(0, len(records), 4)).encode())
        self.write('reads-crlf.fa', (self.data/'reads.fa').read_bytes().replace(b'\n', b'\r\n'))
        for part in range(2):
            sam = f'@HD\tVN:1.6\n@RG\tID:source{part}\tSM:sample{part}\n@CO\tcomment{part}\n'
            for i in range(part*10, (part+1)*10):
                sam += f'{records[i*4][1:]}\t4\t*\t0\t0\t*\t*\t0\t0\t{records[i*4+1]}\t{records[i*4+3]}\tRG:Z:source{part}\tZZ:Z:retained\n'
            self.write(f'input{part}.sam', sam.encode())
            self.write(f'input{part}.sam.gz', gzip.compress(sam.encode(),mtime=0))
        self.write('empty.fq', b'')
        self.write('empty.fq.gz', gzip.compress(b'', mtime=0))
        a = (self.fixture/'data/a.fq').read_bytes()
        b = (self.fixture/'data/b.fq').read_bytes()
        self.write('a.fq.gz', gzip.compress(a, mtime=0))
        self.write('b.fq.gz', gzip.compress(b, mtime=0))
        self.write('members.fq.gz', gzip.compress(a, mtime=0) + gzip.compress(b, mtime=0))
        self.write('combined.fq', a+b)
        self.write('reads with spaces.fq', base)
        self.write('reads_λ_🧬.fq', base)
        self.write('truncated.fq.gz', gzip.compress(base, mtime=0)[:-8])
        corrupt = bytearray(gzip.compress(base, mtime=0)); corrupt[-8] ^= 1
        self.write('bad-crc.fq.gz', corrupt)
        for mate in [1, 2]:
            lines = (self.fixture/f'data/pe_{mate}.fq').read_bytes().splitlines(keepends=True)
            self.write(f'pe{mate}a.fq', b''.join(lines[:4*700]))
            self.write(f'pe{mate}b.fq.gz', gzip.compress(b''.join(lines[4*700:]), mtime=0))
        self.splice = fq([(f's{i}', genome['chr1'][199950:200000] + genome['chr1'][200300:200350]) for i in range(40)])
        novel = fq([(f'n{i}', genome['chr1'][219950:220000] + genome['chr1'][220300:220350]) for i in range(40)])
        self.unmapped = fq([(f'unmapped{i}', 'N'*100) for i in range(20)])
        chim = fq([(f'chim{i}', genome['chr1'][80000:80050] + genome['chr2'][100000:100050]) for i in range(20)])
        self.write('splice.fq', self.splice + novel)
        self.write('mixed.fq.gz', gzip.compress((self.fixture/'data/genic.fq').read_bytes() + self.splice + novel + self.unmapped,mtime=0))
        self.write('mixed.fq', (self.fixture/'data/genic.fq').read_bytes() + self.splice + novel + self.unmapped)
        self.write('unmapped.fq', self.unmapped)
        self.write('chim.fq', chim)
        # One cell, 40 distinct UMIs, annotated splice reads for nonempty SJ output.
        barcode = 'ACGTACGTACGTACGT'
        umis = [''.join('ACGT'[((i+1) >> (2*j)) & 3] for j in range(10)) for i in range(40)]
        self.write('solo-rna.fq', self.splice)
        self.write('solo-cb.fq', fq([(f's{i}', barcode + umis[i]) for i in range(40)]))
        self.write('whitelist.txt', (barcode+'\n').encode())
        self.write('whitelist-crlf.txt', (barcode+'\r\n').encode())

    def write(self, name, data):
        (self.data/name).write_bytes(data)

    def check(self, name, fn, known=False):
        if self.args.only and not re.search(self.args.only,name):
            return
        try:
            fn()
            result = dict(name=name, status='PASS')
        except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as exc:
            result = dict(name=name, status='KNOWN_LIMITATION' if known and str(exc).startswith('exit 102;') else 'FAIL', error=str(exc))
        self.results.append(result)
        print(result['status'] + ': ' + name + (': '+result['error'] if 'error' in result else ''), flush=True)

    def run(self, name, extra, index=None, reads=None, prefix=None, success=True, stdout=None):
        out = self.root/name
        out.mkdir(parents=True, exist_ok=True)
        if prefix is None:
            prefix = out.as_posix() + '/'
        cmd = [self.args.star, '--runThreadN', str(self.args.threads),
               '--outFileNamePrefix', prefix]
        if index is not False:
            cmd += ['--genomeDir', str(index or self.fixture/'idx')]
        if reads is not False:
            cmd += ['--readFilesIn'] + [str(p) for p in (reads or [self.fixture/'data/single.fq'])]
        cmd += list(map(str, extra))
        with (out/'run.log').open('wb') as log:
            if stdout:
                with (out/stdout).open('wb') as output:
                    proc = subprocess.run(cmd, cwd=self.root, stdout=output, stderr=log, timeout=120)
            else:
                proc = subprocess.run(cmd, cwd=self.root, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        self.commands.append(dict(name=name, command=cmd, returncode=proc.returncode))
        if success:
            require(proc.returncode == 0, f'exit {proc.returncode}; see {out}/run.log')
        else:
            require(0 < proc.returncode < 256, f'expected clean error, got {proc.returncode}')
        return out

    def text(self, path, nonempty=False):
        data = path.read_bytes()
        require(not nonempty or data, f'empty {path}')
        require(b'\r' not in data and b'\0' not in data, f'CR/NUL in {path}')
        return data

    def records(self, path, count=None):
        if path.suffix == '.bam':
            require(self.args.samtools, 'samtools required for BAM parity checks')
            p = subprocess.run([self.args.samtools, 'view', str(path)], capture_output=True, check=True, timeout=30)
            data = p.stdout
        else:
            data = self.text(path, nonempty=True)
        records = [line for line in data.splitlines() if not line.startswith(b'@')]
        require(count is None or len(records) == count, f'{path}: {len(records)} records, expected {count}')
        # SAM optional-tag order is irrelevant; retain every value and all core fields.
        return [b'\t'.join(row.split(b'\t')[:11] + sorted(row.split(b'\t')[11:])) for row in records]

    def fingerprint(self, name, records):
        self.fingerprints[name] = digest(b'\n'.join(sorted(records)))

    def clean(self, out):
        leftovers = list(out.rglob('*_STARtmp'))
        require(not leftovers, f'leaked temporary directories: {leftovers}')

    def index(self, name, fasta='genome.fa', gtf='genes.gtf', existing=None, prefix=None):
        index = existing or self.root/name/'index'
        self.run(name, ['--runMode', 'genomeGenerate', '--genomeDir', str(index),
                       '--genomeFastaFiles', str(self.data/fasta), '--genomeSAindexNbases', '8',
                       '--sjdbGTFfile', str(self.data/gtf), '--sjdbOverhang', '99'],
                 index=False, reads=False, prefix=prefix)
        require((index/'Log.out').is_file(), 'index Log.out missing')
        self.text(index/'Log.out', True)
        self.clean(self.root/name)
        return index

    def execute(self):
        self.idx = self.index('index-lf')
        def rebuild():
            self.index('index-rebuild', existing=self.idx)
            require(not (self.root/'index-rebuild/Log.out').exists(), 'log not moved when target exists')
            require(b'index-rebuild' in (self.idx/'Log.out').read_bytes(), 'index log is stale')
        self.check('index_replaces_existing_log', rebuild)
        def same_log():
            self.index('index-same-log', existing=self.idx, prefix=self.idx.as_posix()+'/')
            require(b'DONE: Genome generation' in (self.idx/'Log.out').read_bytes(), 'same-path log lost')
        self.check('index_log_source_equals_target', same_log)
        def crlf_index():
            other = self.index('index-crlf', 'genome-crlf.fa', 'genes-crlf.gtf')
            for name in ['Genome', 'chrName.txt', 'chrLength.txt', 'geneInfo.tab', 'transcriptInfo.tab', 'exonInfo.tab']:
                require((other/name).read_bytes() == (self.idx/name).read_bytes(), f'CRLF changes {name}')
        self.check('crlf_fasta_gtf_index_parity', crlf_index)

        out = self.run('sam-base', ['--outSAMtype', 'SAM'])
        self.base = self.records(out/'Aligned.out.sam', 2000)
        self.fingerprint('single', self.base)
        for label, reads in [('crlf_fastq', self.data/'reads-crlf.fq'), ('crlf_gzip', self.data/'reads-crlf.fq.gz'),
                             ('spaces_input', self.data/'reads with spaces.fq')]:
            def case(label=label, reads=reads):
                out = self.run(label, ['--outSAMtype', 'SAM'], reads=[reads])
                require(sorted(self.records(out/'Aligned.out.sam', 2000)) == sorted(self.base), 'SAM parity mismatch')
                self.clean(out)
            self.check(label, case)
        def fasta():
            outputs=[]
            for name in ['reads.fa', 'reads-crlf.fa']:
                out=self.run(name, ['--outSAMtype','SAM'], reads=[self.data/name])
                outputs.append(self.records(out/'Aligned.out.sam',2000))
            require(sorted(outputs[0])==sorted(outputs[1]), 'CRLF FASTA read parity mismatch')
            self.fingerprint('fasta_reads',outputs[0])
        self.check('crlf_fasta_reads',fasta)
        def path_case(native=False):
            prefix=self.root/'new parent with spaces'/'nested'/'native' if native else self.root/'new parent with spaces'/'nested'/'forward'
            arg=str(prefix)+'\\' if native else prefix.as_posix()+'/'
            out=self.run('native-path' if native else 'nested-path',['--outSAMtype','SAM'],prefix=arg)
            require(sorted(self.records(prefix/'Aligned.out.sam',2000))==sorted(self.base),'path parity mismatch')
            self.clean(prefix)
        self.check('nested_absolute_paths_with_spaces',path_case)
        if os.name=='nt': self.check('native_backslash_output_path',lambda:path_case(True))
        def unicode():
            out=self.run('unicode', ['--outSAMtype','SAM'],reads=[self.data/'reads_λ_🧬.fq'])
            require(sorted(self.records(out/'Aligned.out.sam',2000))==sorted(self.base),'Unicode parity mismatch')
        self.check('unicode_input_path',unicode,known=os.name=='nt')

        def ordered():
            out=self.run('ordered',['--outSAMtype','SAM','--outSAMorder','PairedKeepInputOrder',
                                     '--limitIObufferSize','250000','100000','--limitOutSAMoneReadBytes','10000'])
            records=self.records(out/'Aligned.out.sam',2000)
            require([r.split(b'\t')[0] for r in records]==[f'u_{i}'.encode() for i in range(2000)],'order/record loss across chunks')
            require(sorted(records)==sorted(self.base),'multi-flush SAM differs')
            self.clean(out)
            self.fingerprint('ordered_sam',records)
        self.check('ordered_multichunk_sam_all_libcpp_write_paths',ordered)
        for label, files in [('gzip_members',[self.data/'members.fq.gz']),
                             ('mixed_multifile',[str(self.fixture/'data/a.fq')+','+str(self.data/'b.fq.gz')]),
                             ('empty_members',[','.join(map(str,[self.data/'empty.fq.gz',self.fixture/'data/a.fq',self.data/'empty.fq',self.data/'b.fq.gz']))])]:
            def multi(label=label,files=files):
                out=self.run(label,['--outSAMtype','SAM'],reads=files)
                records=self.records(out/'Aligned.out.sam',1600)
                self.fingerprint(label,records)
            self.check(label,multi)
        def paired():
            baseline=self.run('paired-base',['--outSAMtype','SAM'],reads=[self.fixture/'data/pe_1.fq',self.fixture/'data/pe_2.fq'])
            out=self.run('paired-multi',['--outSAMtype','SAM','--outSAMattrRGline','ID:A',',','ID:B'],
                         reads=[str(self.data/f'pe{m}a.fq')+','+str(self.data/f'pe{m}b.fq.gz') for m in [1,2]])
            records=self.records(out/'Aligned.out.sam',3000)
            for r in records:
                fields=r.split(b'\t'); i=int(fields[0][2:])
                require((b'RG:Z:A' if i<700 else b'RG:Z:B') in fields[11:],'wrong per-file paired RG')
            stripped=[b'\t'.join(f for f in r.split(b'\t') if not f.startswith(b'RG:Z:')) for r in records]
            require(sorted(stripped)==sorted(self.records(baseline/'Aligned.out.sam',3000)),'paired multifile differs')
            self.fingerprint('paired_multifile',records)
        self.check('paired_mixed_multifile_read_groups',paired)
        for mode in ['single','gzip','multi']:
            def sam_input(mode=mode):
                files=str(self.data/('input0.sam.gz' if mode=='gzip' else 'input0.sam'))
                if mode=='multi': files+=','+str(self.data/'input1.sam.gz')
                out=self.run('sam-input-'+mode,['--outSAMtype','SAM','--readFilesType','SAM','SE',
                                              '--readFilesSAMattrKeep','All'],reads=[files])
                header=self.text(out/'Aligned.out.sam',True)
                require(b'@RG\tID:source0\tSM:sample0' in header and b'@CO\tcomment0' in header,'SAM headers lost')
                if mode=='multi': require(b'@RG\tID:source1\tSM:sample1' in header,'second SAM header lost')
                records=self.records(out/'Aligned.out.sam',20 if mode=='multi' else 10)
                require(all(b'ZZ:Z:retained' in r for r in records),'SAM attributes lost')
                self.fingerprint('sam_input_'+mode,records)
            self.check('native_sam_headers_'+mode,sam_input)
        def missing():
            self.run('missing-later',[],reads=[str(self.fixture/'data/a.fq')+','+str(self.data/'missing.fq')],success=False)
        self.check('missing_later_input_is_error',missing)
        for file in ['truncated.fq.gz','bad-crc.fq.gz']:
            self.check(file,lambda file=file:self.run(file,[],reads=[self.data/file],success=False))

        def large_input():
            path=self.data/'large-sparse.fq'
            first=(self.fixture/'data/single.fq').read_bytes().splitlines(keepends=True)[:4]
            sparse_file(path,b''.join(first))
            try:
                out=self.run('large-input',['--outSAMtype','SAM','--readMapNumber','1'],reads=[path])
                self.records(out/'Aligned.out.sam',1)
            finally:
                path.unlink()
        self.check('readFilesIn_stat_over_2GiB',large_input)

        if self.args.samtools:
            for mode, std in [('SortedByCoordinate','BAM_SortedByCoordinate'),('Unsorted','BAM_Unsorted')]:
                def pipe(mode=mode,std=std):
                    out=self.run(std,['--outSAMtype','BAM',mode,'--outStd',std],stdout='stdout.bam')
                    require(sorted(self.records(out/'stdout.bam',2000))==sorted(self.base),'stdout BAM differs from SAM')
                    self.clean(out)
                self.check('stdout_'+std,pipe)
            def quant_stdout():
                out=self.run('quant-stdout',['--outSAMtype','BAM','Unsorted','--quantMode','TranscriptomeSAM',
                                           '--outStd','BAM_Quant'],index=self.fixture/'idxg',reads=[self.fixture/'data/genic.fq'],stdout='stdout.bam')
                records=self.records(out/'stdout.bam',500)
                require(all(r.split(b'\t')[2]==b't1' for r in records),'wrong transcript reference')
                self.fingerprint('quant_stdout',records)
            self.check('stdout_BAM_Quant',quant_stdout)

        def unmapped():
            out=self.run('fastx',['--outSAMtype','SAM','--outReadsUnmapped','Fastx'],index=self.idx,reads=[self.data/'mixed.fq'])
            data=self.text(out/'Unmapped.out.mate1',True)
            lines=data.splitlines()
            records=[(lines[i].split()[0],lines[i+1],lines[i+2],lines[i+3]) for i in range(0,len(lines),4)]
            expected=self.unmapped.splitlines()
            require(sorted(records)==sorted(tuple(expected[i:i+4]) for i in range(0,len(expected),4)),'unmapped FASTQ content differs')
            self.fingerprint('unmapped_fastx',[b'\n'.join(r) for r in records])
            self.clean(out)
        self.check('unmapped_fastx_content_and_cleanup',unmapped)
        def sj_filter():
            out=self.run('bysj',['--outSAMtype','SAM','--outFilterType','BySJout'],index=self.idx,reads=[self.data/'mixed.fq'])
            records=self.records(out/'Aligned.out.sam',580)
            require(sum(b'N' in r.split(b'\t')[5] for r in records)==80,'missing splice alignments')
            self.fingerprint('bysj_sam',records)
            self.clean(out)
        self.check('BySJout_second_stage_and_cleanup',sj_filter)
        def two_pass():
            out=self.run('two-pass',['--outSAMtype','SAM','--twopassMode','Basic'],index=self.idx,reads=[self.data/'mixed.fq.gz'])
            records=self.records(out/'Aligned.out.sam',580)
            self.fingerprint('two_pass_sam',records)
            self.text(out/'_STARpass1/SJ.out.tab',True)
            self.clean(out)
        self.check('two_pass_gzip_reopen_and_cleanup',two_pass)
        if self.args.samtools:
            def combined():
                out=self.run('two-pass-bysj',['--outSAMtype','BAM','SortedByCoordinate','--outSAMunmapped','Within',
                                             '--outFilterType','BySJout','--twopassMode','Basic','--outReadsUnmapped','Fastx'],
                             index=self.idx,reads=[self.data/'mixed.fq.gz'])
                self.fingerprint('two_pass_bysj',self.records(out/'Aligned.sortedByCoord.out.bam',600))
                self.clean(out)
            self.check('two_pass_BySJout_sorted_fastx_cleanup',combined)
        def chim():
            out=self.run('chimeric',['--outSAMtype','SAM','--chimSegmentMin','20','--chimJunctionOverhangMin','20','--chimOutType','Junctions','SeparateSAMold'],
                         index=self.idx,reads=[self.data/'chim.fq'])
            data=self.text(out/'Chimeric.out.junction',True)
            require(len(data.splitlines())==20,'chimeric junction count mismatch')
            self.fingerprint('chimeric_junctions',data.splitlines())
            self.clean(out)
        self.check('chimeric_output_and_cleanup',chim)
        if self.args.samtools:
            def wiggle():
                out=self.run('wiggle',['--outSAMtype','BAM','SortedByCoordinate','--outWigType','bedGraph',
                                      '--outWigStrand','Unstranded','--outWigNorm','None'],index=self.idx,reads=[self.fixture/'data/genic.fq'])
                data=self.text(out/'Signal.Unique.str1.out.bg',True)
                area=sum((int(f[2])-int(f[1]))*float(f[3]) for f in [line.split() for line in data.splitlines()])
                require(area==50000,'bedGraph coverage integral mismatch')
                self.fingerprints['bedgraph']=digest(data)
                self.clean(out)
            self.check('sorted_bam_wiggle_coverage',wiggle)
            for name, reads, expected in [('empty_sorted',self.data/'empty.fq',0),('unmapped_sorted',self.data/'unmapped.fq',20)]:
                def sorted_case(name=name,reads=reads,expected=expected):
                    out=self.run(name,['--outSAMtype','BAM','SortedByCoordinate','--outSAMunmapped','Within'],index=self.idx,reads=[reads])
                    records=self.records(out/'Aligned.sortedByCoord.out.bam',expected)
                    require(all(int(r.split(b'\t')[1])&4 for r in records),'expected unmapped BAM records')
                    self.clean(out)
                self.check(name,sorted_case)
        def solo(name,absolute,crlf=False):
            prefix=(self.root/name).as_posix()+'/' if absolute else name+'/'
            out=self.run(name,['--outSAMtype','SAM','--soloType','CB_UMI_Simple','--soloFeatures','Gene','SJ',
                               '--soloCBwhitelist',str(self.data/('whitelist-crlf.txt' if crlf else 'whitelist.txt')),
                               '--soloCellFilter','None','--soloUMIdedup','Exact'],index=self.idx,
                         reads=[self.data/'solo-rna.fq',self.data/'solo-cb.fq'],prefix=prefix)
            sj=self.text(out/'SJ.out.tab',True)
            require((out/'Solo.out/SJ/raw/features.tsv').read_bytes()==sj,'Solo SJ feature copy differs')
            for feat in ['Gene','SJ']:
                matrix=self.text(out/f'Solo.out/{feat}/raw/matrix.mtx',True)
                rows=[r.split() for r in matrix.splitlines() if not r.startswith(b'%')]
                require(int(rows[0][2])==1 and int(rows[-1][-1])==40,'wrong Solo UMI matrix')
                self.fingerprints[name+'_'+feat]=digest(matrix)
                self.text(out/f'Solo.out/{feat}/raw/barcodes.tsv',True)
            self.clean(out)
        self.check('solo_relative_prefix',lambda:solo('solo-relative',False))
        self.check('solo_absolute_prefix',lambda:solo('solo-absolute',True))
        self.check('solo_crlf_whitelist',lambda:solo('solo-crlf',False,True))
        if self.args.foreign_index:
            def foreign():
                local=self.run('local-index-control',['--outSAMtype','SAM'],index=self.idx,reads=[self.data/'mixed.fq'])
                out=self.run('foreign-index',['--outSAMtype','SAM'],index=self.args.foreign_index,reads=[self.data/'mixed.fq'])
                require(sorted(self.records(out/'Aligned.out.sam',580))==sorted(self.records(local/'Aligned.out.sam',580)),
                        'index generated on another platform changes alignments')
            self.check('foreign_platform_index_roundtrip',foreign)
        for mode in ['LoadAndKeep','LoadAndExit','LoadAndRemove','Remove']:
            if os.name=='nt':
                self.check('unsupported_shared_'+mode,lambda mode=mode:self.run('shared-'+mode,['--genomeLoad',mode],success=False))
        if os.name=='nt':
            self.check('unsupported_read_command',lambda:self.run('read-command',['--readFilesCommand','zcat'],success=False))

    def finish(self):
        if self.args.reference:
            reference=json.loads(self.args.reference.read_text())['fingerprints']
            def compare():
                require(reference.keys()==self.fingerprints.keys(),'reference/current fingerprint case sets differ')
                mismatches=[k for k in reference if reference[k]!=self.fingerprints[k]]
                require(not mismatches,f'cross-platform output mismatches: {mismatches}')
            self.check('cross_platform_reference',compare)
        payload=dict(platform=os.name,results=self.results,fingerprints=self.fingerprints,commands=self.commands)
        (self.root/'results.json').write_text(json.dumps(payload,indent=2))
        counts={status:sum(r['status']==status for r in self.results) for status in ['PASS','FAIL','KNOWN_LIMITATION']}
        print('Portability result: '+json.dumps(counts),flush=True)
        return int(bool(counts['FAIL']))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--star',required=True)
    p.add_argument('--samtools')
    p.add_argument('--fixture',type=Path,default=Path('.'))
    p.add_argument('--output',type=Path,default=Path('portability'))
    p.add_argument('--reference',type=Path)
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--foreign-index',type=Path,help='tiny index generated from this suite on another platform')
    p.add_argument('--only',help='run checks whose names match this regular expression')
    args=p.parse_args()
    require(args.threads>1,'use at least two threads to cover chunk ordering')
    suite=Suite(args)
    try:
        suite.execute()
    except (AssertionError,OSError,ValueError,subprocess.SubprocessError) as exc:
        suite.results.append(dict(name='suite_setup',status='FAIL',error=str(exc)))
        print('FAIL: suite setup: '+str(exc),flush=True)
    return suite.finish()


if __name__=='__main__':
    raise SystemExit(main())
