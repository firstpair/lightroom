#!/usr/bin/env python3
# /// script
# requires-python = ">=3.14"
# dependencies = ["rocksdict==0.3.29"]
# ///
"""Export exact C2PA payloads from an isolated APFS copy; never publish to Cloud."""
from pathlib import Path
import argparse
import ctypes
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess


def family(root):
    result = {}
    for path in root.iterdir():
        s = path.lstat()
        if not stat.S_ISREG(s.st_mode):
            raise ValueError('Source must contain regular files only')
        result[path.name] = [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]
    return result


def manifest_rows(path):
    rows = json.loads(Path(path).read_bytes())
    if not isinstance(rows, list) or not rows:
        raise ValueError('Manifest must be a nonempty array')
    for row in rows:
        if (row.get('type') != 'c2pa'
                or not re.fullmatch('[0-9A-F]{32}', row.get('digest', ''))
                or not re.fullmatch('[0-9a-f]{64}', row.get('sha256', ''))
                or type(row.get('fileSize')) is not int or row['fileSize'] <= 0):
            raise ValueError('Expected c2pa type, uppercase digest, SHA256 and positive integer fileSize')
    return rows


def clone_closed_source(source, target):
    if source.resolve(strict=True) != source or not (source/'CURRENT').is_file():
        raise ValueError('Expected a canonical RocksDB directory')
    before = family(source)
    opened = subprocess.run(['lsof', '-t', '--', *map(str, source.iterdir())], capture_output=True, text=True)
    if opened.returncode != 1 or opened.stdout.strip():
        raise RuntimeError('Source has open handles or opener check failed; leave it untouched')
    target.mkdir()
    native = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True).fclonefileat
    native.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    native.restype = ctypes.c_int
    directory = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name, expected in before.items():
            fd = os.open(source/name, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                s = os.fstat(fd)
                if [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns] != expected:
                    raise RuntimeError('Source descriptor identity changed')
                if native(fd, directory, os.fsencode(name), 0):
                    raise OSError(ctypes.get_errno(), 'APFS clone failed; no copying fallback')
            finally:
                os.close(fd)
    finally:
        os.close(directory)
    if family(source) != before:
        raise RuntimeError('Source family changed during snapshot; do not open this copy')
    return before


def extract_snapshot(snapshot, rows, output):
    """Only an owned private copy: bindings may write housekeeping in read-only mode."""
    from rocksdict import AccessType, Options, Rdict
    options = Options(raw_mode=True)
    options.create_if_missing(False)
    options.create_missing_column_families(False)
    options.set_db_log_dir(str(output/'reader-log'))
    db = Rdict(str(snapshot), options=options, access_type=AccessType.read_only())
    results = []
    try:
        for row in rows:
            value = db.get(row['digest'].encode('ascii'))
            result = {key: row[key] for key in ('digest', 'sha256', 'fileSize')}
            result['status'] = 'KEY_ABSENT'
            if value is not None:
                actual = hashlib.sha256(value).hexdigest()
                result.update(actualSHA256=actual, actualBytes=len(value), status='HASH_OR_SIZE_HELD')
                if actual == row['sha256'] and len(value) == row['fileSize']:
                    path = output/actual
                    try:
                        with path.open('xb') as stream:
                            stream.write(value); stream.flush(); os.fsync(stream.fileno())
                    except FileExistsError:
                        if path.is_symlink() or path.read_bytes() != value:
                            raise RuntimeError('Existing output differs; no overwrite')
                    result.update(status='EXACT_EXPORT', output=path.name)
            results.append(result)
    finally:
        db.close()
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Closed Classic .lrcat-data directory')
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New private run directory on the same APFS volume')
    args = parser.parse_args()
    rows = manifest_rows(args.manifest)
    source = args.source.expanduser().absolute()
    output = args.output.expanduser().absolute()
    if output.parent.resolve(strict=True) != output.parent:
        raise ValueError('Output parent must be canonical, without symlinks or ..')
    if output.is_relative_to(source):
        raise ValueError('Output must be outside the source')
    output.mkdir()
    owner = (output/'OWNER.lock').open('x')
    fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        snapshot = output/'snapshot.lrcat-data'
        before = clone_closed_source(source, snapshot)
        (output/'SOURCE-FAMILY.json').write_text(json.dumps(before, indent=2))
        results = extract_snapshot(snapshot, rows, output)
        if family(source) != before:
            raise RuntimeError('Original source family changed; qualify exports separately')
        report = {'state': 'EXTRACTION_FINISHED_NOT_NATIVE_ADOPTION', 'rows': results,
                  'sourceFamilyUnchanged': True, 'cloudCacheWrites': 0, 'nativeRequests': 0}
        (output/'RESULT.json').write_text(json.dumps(report, indent=2))
        print(json.dumps({r: sum(x['status'] == r for x in results) for r in sorted({x['status'] for x in results})}))
    except Exception as error:
        (output/'FAILURE.json').write_text(json.dumps({'error': repr(error), 'nativeRequests': 0}))
        raise
    finally:
        owner.close()


if __name__ == '__main__':
    main()
