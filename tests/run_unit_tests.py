#!/usr/bin/env python3
"""Compile and run the small C++ regressions using the native target compiler."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess


def sparse_file(path, first=b''):
    """Create >2 GiB logical size, with only tiny allocated data extents."""
    with path.open('x+b') as stream:
        if os.name == 'nt':
            import msvcrt
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
            returned = ctypes.c_ulong()
            if not kernel.DeviceIoControl(msvcrt.get_osfhandle(stream.fileno()),
                    0x900C4, None, 0, None, 0, ctypes.byref(returned), None):
                raise ctypes.WinError(ctypes.get_last_error())
        stream.write(first)
        stream.seek((1 << 31) + 17)
        stream.write(b'X')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', required=True, help='native compiler executable')
    parser.add_argument('--output', required=True, type=Path, help='new artifact directory')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    source = Path(__file__).resolve().parent.parent
    results = []
    for name, sources in [('transform_flags', ['ParametersGenome.cpp']),
                          ('platform_io', ['Quantifications.cpp', 'sysRemoveDir.cpp']),
                          ('stream_failures', ['streamFuns.cpp', 'InOutStreams.cpp'])]:
        executable = output / (name + '.exe')
        cmd = [args.cxx, '-std=c++11', '-I'+str(source), str(source/'tests'/('test_'+name+'.cpp'))]
        cmd += [str(source/f) for f in sources] + ['-o', str(executable)]
        result = dict(name=name, compile_command=cmd)
        try:
            with (output/(name+'-build.log')).open('wb') as log:
                subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
            cmd = [str(executable)]
            if name == 'platform_io':
                directory = output/'sparse'
                directory.mkdir()
                sparse_file(directory/'large.bin')
                cmd += [str(directory/'large.bin'), str(directory)]
            elif name == 'stream_failures':
                cmd += [str(output/'partial.bin')]
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
            (output/(name+'.log')).write_bytes(proc.stdout + proc.stderr)
            print(proc.stdout.decode(errors='replace'), end='')
            result.update(returncode=proc.returncode, passed=proc.returncode == 0)
        except (OSError, subprocess.SubprocessError) as exc:
            result.update(passed=False, error=str(exc))
            print('FAIL:', name, exc)
        results.append(result)
    (output/'results.json').write_text(json.dumps(results, indent=2))
    return int(any(not r['passed'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
