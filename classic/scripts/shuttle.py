#!/usr/bin/env python3
"""Closed-catalog Unison shuttle. No SQLite, UI control, or application launch.

State/configuration/receipts are private. A successful Unison exit is transport
evidence only; an independently verified receipt must release or accept ownership.
"""
from pathlib import Path, PurePosixPath
import argparse
import ctypes
import datetime
import fcntl
import hashlib
import json
import os
import plistlib
import re
import stat
import subprocess
import sys
import uuid

SCHEMA = 1
VERSION = '15.6'
TIERS = ('full', 'main-core')
HOST_RE = re.compile(r'[a-z][a-z0-9-]{0,40}\Z')
SHA_RE = re.compile(r'[0-9a-f]{64}\Z')
UNSAFE_ENV = ('UNISON', 'UNISONLOCALHOSTNAME', 'UNISONBACKUPDIR', 'UNISONMIRRORDIR')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def five(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def safe_path(value):
    require(isinstance(value, str) and value.startswith('/'), 'Paths must be absolute')
    require(not any(ord(c) < 32 or c in '\\' for c in value), 'Unsafe path characters')
    path = Path(value)
    require(str(path) == value and '..' not in path.parts, 'Use literal normalized paths')
    return path


def guarded(path, exists=True, regular=False):
    path = safe_path(str(path))
    current = Path('/')
    for part in path.parts[1:]:
        current /= part
        try:
            item = current.lstat()
        except FileNotFoundError:
            if not exists:
                return None
            raise
        require(not stat.S_ISLNK(item.st_mode), 'Unexpected symlink: ' + str(current))
        if current != path:
            require(stat.S_ISDIR(item.st_mode), 'Non-directory ancestor: ' + str(current))
    require(path.resolve() == path, 'Canonical path differs: ' + str(path))
    item = path.lstat()
    if regular:
        require(stat.S_ISREG(item.st_mode), 'Not a regular file: ' + str(path))
    return item


def outside(path, roots):
    return all(path != root and root not in path.parents for root in roots)


def sha_file(path):
    before = guarded(path, regular=True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        require(five(os.fstat(fd)) == five(before), 'File changed at open')
        digest = hashlib.sha256()
        with os.fdopen(os.dup(fd), 'rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        require(five(os.fstat(fd)) == five(before) == five(path.lstat()), 'File changed during hashing')
        return digest.hexdigest()
    finally:
        os.close(fd)


def read_json(path):
    guarded(path, regular=True)
    return json.loads(path.read_text())


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_new(path, value):
    guarded(path.parent)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(path.parent)


def replace_json(path, value, expected=None):
    if path.exists():
        require(expected is not None and read_json(path) == expected, 'Foreign/changed owner marker')
    else:
        require(expected is None, 'Owner marker disappeared')
    temp = path.parent / ('.owner-' + uuid.uuid4().hex + '.tmp')
    save_new(temp, value)
    os.replace(temp, path)
    sync_dir(path.parent)


def mkdir_safe(path):
    guarded(path, exists=False)
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    guarded(path)


def load_config(path):
    for key in UNSAFE_ENV:
        require(key not in os.environ, 'Inherited ' + key + ' must be unset')
    config = read_json(safe_path(str(path)))
    require(config.get('schema') == SCHEMA, 'Unsupported private configuration schema')
    require(HOST_RE.fullmatch(config.get('host', '')), 'Invalid host identity')
    peers = config.get('peers')
    require(isinstance(peers, list) and len(peers) >= 1 and len(set(peers)) == len(peers)
            and all(isinstance(x, str) and HOST_RE.fullmatch(x) for x in peers)
            and config['host'] not in peers, 'Invalid peer identities')
    for name in ('local_root', 'photo_root', 'photo_mount', 'state_dir', 'local_backup_root',
                 'photo_backup_root', 'journal_root', 'owner_marker', 'shared_io_lease', 'classic_app'):
        config[name] = str(safe_path(config[name]))
    roots = [Path(config['local_root']), Path(config['photo_root'])]
    require(outside(roots[0], [roots[1]]) and outside(roots[1], [roots[0]]), 'Overlapping replica roots')
    for name in ('state_dir', 'local_backup_root', 'photo_backup_root', 'journal_root', 'owner_marker'):
        require(outside(Path(config[name]), roots), name + ' must be outside synchronization roots')
    mount = Path(config['photo_mount'])
    require(mount in Path(config['photo_root']).parents, 'Photo root must be below its mount')
    require(mount in Path(config['photo_backup_root']).parents
            and mount in Path(config['owner_marker']).parents, 'Photo backup/owner paths must be on Photo')
    relative = PurePosixPath(config.get('main_catalog', ''))
    require(len(relative.parts) == 2 and relative.suffix == '.lrcat'
            and all(x not in ('', '.', '..') for x in relative.parts), 'Main catalog must be folder/name.lrcat')
    require(not any(ord(c) < 32 or c in '\\*?[]{}!' for c in str(relative)),
            'Unsafe catalog path or Unison pattern metacharacter')
    config['main_catalog'] = str(relative)
    require(isinstance(config.get('photo_uuid'), str)
            and re.fullmatch(r'[0-9A-Fa-f-]{36}', config['photo_uuid']), 'Invalid private Photo UUID')
    tool = config.get('unison', {})
    require(isinstance(tool, dict) and SHA_RE.fullmatch(tool.get('sha256', '')), 'Unison executable SHA required')
    tool['path'] = str(safe_path(tool['path']))
    require(re.fullmatch(r'2\.(?:5[2-9]|[6-9][0-9])\.\d+', tool.get('version', '')), 'Require qualified Unison 2.52+')
    for tier in TIERS:
        budget = config.get('transfer_budget_bytes', {}).get(tier)
        require(type(budget) is int and budget >= 0, 'Declare measured transfer budget for each tier')
    require(type(config.get('minimum_free_bytes')) is int and config['minimum_free_bytes'] > 0, 'Reserve required')
    links = config.get('photo_preview_links', {})
    require(isinstance(links, dict), 'Invalid preview-link declaration')
    stem = relative.stem
    allowed = {str(relative.parent / (stem + ' Smart Previews.lrdata'))}
    for name, target in links.items():
        require(name in allowed and target == str(Path(config['photo_root']) / name), 'Only exact excluded Photo Smart Previews links allowed')
    config['photo_preview_links'] = links
    return config


def classic_gate(config):
    app = Path(config['classic_app'])
    guarded(app)
    guarded(app / 'Contents/Info.plist', regular=True)
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    require(info.get('CFBundleShortVersionString') == VERSION, 'Stable Lightroom Classic 15.6 is required')
    labels = ' '.join(str(info.get(key, '')) for key in
                      ('CFBundleName', 'CFBundleDisplayName', 'CFBundleIdentifier', 'CFBundleVersion'))
    require(not re.search(r'beta|prerelease|pre-release|development|preview', labels, re.I), 'Prerelease app is not admitted')
    return {'version': VERSION, 'bundleVersion': info.get('CFBundleVersion'), 'path': str(app)}


def volume_gate(config):
    result = subprocess.run(['/usr/sbin/diskutil', 'info', '-plist', config['photo_mount']],
                            capture_output=True, check=True, timeout=30)
    info = plistlib.loads(result.stdout)
    require(str(info.get('VolumeUUID', '')).upper() == config['photo_uuid'].upper(), 'Wrong Photo volume UUID')
    require(('Mounted' not in info or info['Mounted'] is True)
            and info.get('MountPoint') == config['photo_mount']
            and os.path.ismount(config['photo_mount']), 'Photo is not mounted at its exact path')
    item = guarded(Path(config['photo_mount']))
    require(item.st_dev != os.stat('/').st_dev, 'Photo resolves to boot filesystem')
    guarded(Path(config['photo_root']))
    return {'uuid': info['VolumeUUID'], 'mount': info['MountPoint'], 'device': item.st_dev,
            'inode': item.st_ino}


def parse_main_fds(raw, roots, identities=(), excluded_ignored=None):
    pid, command, record = None, '', {}
    hits = []
    def finish():
        descriptor, name = record.get('f', ''), record.get('n', '')
        if not re.match(r'^\d', descriptor):
            return
        clean = name.removesuffix(' (deleted)')
        lexical = clean.startswith('/') and any(clean.casefold() == str(root).casefold()
                    or clean.casefold().startswith(str(root).casefold() + '/') for root in roots)
        physical = False
        if 'D' in record and 'i' in record:
            physical = (int(record['D'], 16), int(record['i'])) in identities
        if lexical or physical:
            observation = {'pid': pid, 'command': command, 'descriptor': descriptor, 'path': name,
                           'access': record.get('a'), 'physicalMainCatalogMatch': physical}
            # Only the explicitly ignored basename, with captured read-only
            # access and no catalog inode alias, can be omitted from closure.
            if lexical and not physical and Path(clean).name == '.DS_Store' and record.get('a') == 'r':
                if excluded_ignored is not None:
                    excluded_ignored.append(observation)
            else:
                hits.append(observation)
    for token in raw.split(b'\0'):
        token = token.lstrip(b'\n')
        if not token:
            continue
        text = token[1:].decode('utf-8', errors='strict')
        if token[:1] == b'p':
            finish()
            pid, command, record = int(text), '', {}
        elif token[:1] == b'c':
            command = text
        elif token[:1] == b'f':
            finish()
            record = {'f': text}
        elif token[:1] in (b'a', b'n', b'D', b'i'):
            record[token[:1].decode()] = text
    finish()
    return hits


def closed_gate(config):
    folder = PurePosixPath(config['main_catalog']).parent
    roots = [Path(config[k]) / str(folder) for k in ('local_root', 'photo_root')]
    files = [Path(config[k]) / config['main_catalog'] for k in ('local_root', 'photo_root')]
    identities = {(x.stat().st_dev, x.stat().st_ino) for x in files if x.exists()}
    result = subprocess.run(['/usr/sbin/lsof', '-nP', '-F0pcfanDi'], capture_output=True, timeout=60)
    require(result.returncode in (0, 1), 'lsof failed; closure is unproved')
    require(not result.stderr.strip(), 'lsof reported incomplete observation')
    excluded = []
    hits = parse_main_fds(result.stdout, roots, identities, excluded)
    require(not hits, 'Main family has open file descriptors: ' + json.dumps(hits))
    return {'mainRoots': list(map(str, roots)), 'openMainDescriptors': 0,
            'excludedIgnoredReadOnlyFDs': excluded,
            'method': 'all-process lsof numeric descriptors, Main path/case aliases and catalog device+inode; AI elsewhere may stay open', 'observedUtc': utc()}


def tool_gate(config):
    tool = config['unison']
    path = Path(tool['path'])
    require(sha_file(path) == tool['sha256'] and os.access(path, os.X_OK), 'Pinned Unison executable differs')
    result = subprocess.run([str(path), '-version'], capture_output=True, text=True, check=True, timeout=20)
    require(re.search(r'\bunison version ' + re.escape(tool['version']) + r'\b', result.stdout), 'Unison version differs')
    return {'path': str(path), 'sha256': tool['sha256'], 'version': result.stdout.strip()}


def critical_names(config):
    catalog = PurePosixPath(config['main_catalog'])
    folder, stem = str(catalog.parent), catalog.stem
    names = [str(catalog) + suffix for suffix in ('', '-wal', '-shm', '-journal')]
    names += [folder + '/' + stem + '.lrcat-data', folder + '/' + stem + ' Sync.lrdata',
              folder + '/' + stem + ' Helper.lrdata']
    return names


def inventory_critical(root, config, require_catalog=False):
    root = Path(root)
    rows, absent = [], []
    def visit(path):
        item = guarded(path)
        require(item.st_dev == root.stat().st_dev, 'Nested mount in critical family')
        if stat.S_ISDIR(item.st_mode):
            rows.append({'path': str(path.relative_to(root)), 'kind': 'directory', 'identity': five(item), 'mode': stat.S_IMODE(item.st_mode)})
            for child in sorted(path.iterdir()):
                visit(child)
        else:
            require(stat.S_ISREG(item.st_mode), 'Unsupported critical entry')
            rows.append({'path': str(path.relative_to(root)), 'kind': 'file', 'identity': five(item), 'mode': stat.S_IMODE(item.st_mode)})
    for name in critical_names(config):
        path = root / name
        if path.exists() or path.is_symlink():
            visit(path)
        else:
            absent.append(name)
    lock = root / (config['main_catalog'] + '.lock')
    require(not lock.exists() and not lock.is_symlink(), 'Catalog lock remains; normal closure/recovery required')
    if require_catalog:
        item = guarded(root / config['main_catalog'], regular=True)
        require(item.st_size > 0, 'Source Main catalog is empty')
    return {'root': str(root), 'rows': rows, 'absent': absent,
            'fileBytes': sum(x['identity'][2] for x in rows if x['kind'] == 'file'),
            'assurance': 'bounded filesystem membership/identity only; no database or content read'}


def preview_gate(config, tier):
    folder = Path(config['local_root']) / str(PurePosixPath(config['main_catalog']).parent)
    if not folder.exists():
        return
    for entry in folder.iterdir():
        if entry.is_symlink():
            name = str(entry.relative_to(config['local_root']))
            target = config['photo_preview_links'].get(name)
            require(tier == 'main-core' and name in excluded_paths(config, tier)
                    and target is not None and os.readlink(entry) == target,
                    'Unexpected or included symlink: ' + str(entry))
            require(stat.S_ISDIR(guarded(Path(target)).st_mode), 'Photo preview target is not a directory')


def preflight(config, tier, source):
    volume, app, tool = volume_gate(config), classic_gate(config), tool_gate(config)
    guarded(Path(config['local_root']))
    preview_gate(config, tier)
    closure = closed_gate(config)
    families = {name: inventory_critical(config[name + '_root'], config, name == source)
                for name in ('local', 'photo')}
    destination = Path(config[('photo' if source == 'local' else 'local') + '_root'])
    space = os.statvfs(destination)
    free = space.f_bavail * space.f_frsize
    budget = config['transfer_budget_bytes'][tier]
    require(free - budget >= config['minimum_free_bytes'], 'Declared transfer budget/reserve does not fit destination')
    return {'schema': SCHEMA, 'utc': utc(), 'host': config['host'], 'tier': tier,
            'source': source, 'volume': volume, 'app': app, 'tool': tool, 'closure': closure,
            'families': families, 'capacity': {'destination': str(destination), 'availableBytes': free,
            'declaredAdditionalBytes': budget, 'minimumRemainingBytes': config['minimum_free_bytes'],
            'assurance': 'operator measured delta budget; no exhaustive preview inventory by this tool'},
            'scope': scope_description(config, tier)}


def scope_description(config, tier):
    return {'catalogFolder': str(PurePosixPath(config['main_catalog']).parent), 'tier': tier,
            'excluded': excluded_paths(config, tier), 'wholeLightroomFolderComplete': False,
            'diagnosticsCopied': False, 'otherCatalogsCopied': False,
            'catalogAtomicMeans': 'conflict grouping, not a filesystem transaction'}


def excluded_paths(config, tier):
    catalog = PurePosixPath(config['main_catalog'])
    folder, stem = str(catalog.parent), catalog.stem
    result = [folder + '/.ruff_cache']
    if tier == 'main-core':
        result += [folder + '/Backups', folder + '/' + stem + ' Smart Previews.lrdata']
    return result


def render_profile(config, tier, backup_dir, logfile, bootstrap=False):
    folder = str(PurePosixPath(config['main_catalog']).parent)
    lines = ['root = ' + config['local_root'], 'root = ' + config['photo_root'],
             'path = ' + folder,
             'times = true', 'xattrs = true', 'rsrc = true', 'fastcheck = true',
             'maxthreads = 2', 'links = true', 'batch = true', 'confirmbigdel = true',
             'backup = Name *', 'backuploc = central', 'backupdir = ' + str(backup_dir),
             'maxbackups = 2', 'log = true', 'logfile = ' + str(logfile),
             'mountpoint = .', 'ignore = Name .DS_Store']
    # 2.54's atomic existing-directory + force combination can copy properties
    # only while omitting children. Bootstrap is explicitly authoritative and
    # protected by coherent snapshots and independently verified closed-family
    # hashes. Routine bidirectional sync keeps atomic conflict grouping.
    if not bootstrap:
        lines.append('atomic = Path ' + folder)
    lines += ['ignore = Path ' + name for name in excluded_paths(config, tier)]
    return '\n'.join(lines) + '\n'


def archive_environment(config):
    env = os.environ.copy()
    for key in UNSAFE_ENV:
        require(key not in env, 'Inherited ' + key + ' must be unset')
    env['UNISON'] = config['state_dir']
    env['UNISONLOCALHOSTNAME'] = config['host']
    return env


def read_owner(config):
    path = Path(config['owner_marker'])
    if not path.exists():
        return None
    owner = read_json(path)
    require(owner.get('schema') == SCHEMA and owner.get('photoUuid', '').upper() == config['photo_uuid'].upper()
            and owner.get('mainCatalog') == config['main_catalog'], 'Owner marker belongs to another setup')
    require(owner.get('owner') in [None, config['host'], *config['peers']], 'Unknown catalog owner')
    return owner


def owned_state(config, tier):
    require(tier in TIERS, 'Unknown synchronization tier')
    directory = Path(config['state_dir'])
    path = directory / 'SETUP.json'
    binding = {'schema': SCHEMA, 'host': config['host'], 'photoUuid': config['photo_uuid'].upper(),
               'mainCatalog': config['main_catalog'], 'localRoot': config['local_root'],
               'photoRoot': config['photo_root'], 'tier': tier}
    if path.exists():
        require(read_json(path) == binding, 'Dedicated state belongs to a different host/root pair or tier')
    else:
        require({x.name for x in directory.iterdir()} <= {'SHUTTLE.lock'}, 'Refuse foreign/legacy Unison state directory')
        save_new(path, binding)
    return binding


def admission(config, marker, command, source):
    host = config['host']
    if marker is None:
        require(command == 'bootstrap' and source == 'local', 'First bootstrap must publish the local closed master')
        return 'initial-outgoing'
    if marker.get('phase') == 'active' and marker.get('owner') == host:
        require(source == 'local', 'Active owner must publish its local copy')
        return 'outgoing'
    if marker.get('phase') == 'in-transit' and marker.get('releaseTo') == host and marker.get('owner') is None:
        require(source == 'photo', 'Incoming handoff must use Photo as source')
        return 'incoming'
    raise ValueError('Catalog is owned elsewhere or has an unresolved held/verification-required transfer')


def open_lock(path, blocking=False, create=False):
    guarded(path, exists=not create)
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if create:
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CREAT
    fd = os.open(path, flags, 0o600)
    try:
        item = os.fstat(fd)
        require(stat.S_ISREG(item.st_mode) and five(item) == five(path.lstat()), 'Lease/lock identity differs')
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        require(five(os.fstat(fd)) == five(path.lstat()), 'Lease replaced while waiting')
        return fd
    except BaseException:
        os.close(fd)
        raise


def clone_file(source, destination):
    require(sys.platform == 'darwin', 'Same-volume APFS clone snapshots require macOS')
    require(source.stat().st_dev == destination.parent.stat().st_dev, 'Rollback snapshot must stay on the destination volume')
    libc = ctypes.CDLL(None, use_errno=True)
    libc.clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    libc.clonefile.restype = ctypes.c_int
    # CLONE_NOFOLLOW | CLONE_NOOWNERCOPY; no hard links or byte-copy fallback.
    if libc.clonefile(os.fsencode(source), os.fsencode(destination), 1 | 2) != 0:
        error = ctypes.get_errno()
        raise OSError(error, 'APFS rollback clone failed', str(source))
    before, after = source.lstat(), destination.lstat()
    require(before.st_dev == after.st_dev and before.st_ino != after.st_ino
            and before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns,
            'Rollback clone is not an independent same-volume equivalent file')


def preserve_previous(config, destination, family, run_id):
    backup_root = Path(config[destination + '_backup_root'])
    mkdir_safe(backup_root)
    require(backup_root.stat().st_dev == Path(config[destination + '_root']).stat().st_dev,
            'Previous-family snapshot root is on another volume')
    target = backup_root / ('critical-family-' + run_id)
    target.mkdir(mode=0o700)
    root = Path(config[destination + '_root'])
    for row in family['rows']:
        source, dest = root / row['path'], target / row['path']
        require(five(guarded(source)) == row['identity'], 'Previous critical source changed before preservation')
        if row['kind'] == 'directory':
            dest.mkdir(parents=True, mode=row['mode'], exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            clone_file(source, dest)
            require(five(source.lstat()) == row['identity'], 'Previous critical source changed during preservation')
    require(inventory_critical(root, config) == family, 'Previous critical family changed during preservation')
    save_new(target / 'PRESERVED.json', {'schema': SCHEMA, 'runId': run_id, 'utc': utc(),
             'family': family, 'method': 'same-volume APFS clonefile, independent inodes, no hard links',
             'wholeFileSHARead': False, 'snapshotRoot': str(target)})
    return str(target)


def execute_transfer(config, command, tier, source):
    mkdir_safe(Path(config['state_dir']))
    lock = open_lock(Path(config['state_dir']) / 'SHUTTLE.lock', create=True)
    lease = None
    run, pending = None, None
    try:
        owned_state(config, tier)
        marker = read_owner(config)
        direction = admission(config, marker, command, source)
        # A valid existing lease blocks, rather than treating another reader as failure.
        lease = open_lock(Path(config['shared_io_lease']), blocking=True)
        facts = preflight(config, tier, source)
        destination = 'photo' if source == 'local' else 'local'
        run_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex
        mkdir_safe(Path(config['journal_root']))
        run = Path(config['journal_root']) / run_id
        run.mkdir(mode=0o700)
        prior = {destination: preserve_previous(config, destination, facts['families'][destination], run_id)}
        if command == 'sync':
            prior[source] = preserve_previous(config, source, facts['families'][source], run_id)
        central = Path(config['photo_backup_root']) / ('unison-' + config['host'])
        mkdir_safe(central)
        # Profiles/archives belong to this host's pair and stay outside replicated data.
        profile_name = 'lightroom-shuttle-' + config['host']
        profile_path = Path(config['state_dir']) / (profile_name + '.prf')
        profile = render_profile(config, tier, central, run / 'unison.log', bootstrap=command == 'bootstrap')
        if profile_path.exists():
            guarded(profile_path, regular=True)
        temp = profile_path.parent / ('.profile-' + run_id + '.tmp')
        with temp.open('x') as stream:
            stream.write(profile); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, profile_path); sync_dir(profile_path.parent)
        (run / 'EXECUTED.prf').write_text(profile)
        argv = [config['unison']['path'], profile_name, '-ui', 'text']
        if command == 'bootstrap':
            argv += ['-force', config[source + '_root']]
        intent = {'schema': SCHEMA, 'runId': run_id, 'utc': utc(), 'host': config['host'],
                  'command': command, 'direction': direction, 'source': source, 'destination': destination,
                  'tier': tier, 'preflight': facts, 'previousOwner': marker,
                  'previousCriticalFamily': prior, 'argv': argv,
                  'atomicDirectoryGroupingEnabled': command != 'bootstrap',
                  'profileSha256': hashlib.sha256(profile.encode()).hexdigest(),
                  'unisonState': config['state_dir'], 'catalogWritesByThisTool': False}
        save_new(run / 'INTENT.json', intent)
        pending = {'schema': SCHEMA, 'photoUuid': config['photo_uuid'], 'mainCatalog': config['main_catalog'],
                   'owner': marker.get('owner') if marker else config['host'],
                   'phase': 'verification-required', 'host': config['host'], 'runId': run_id,
                   'direction': direction, 'tier': tier, 'resultPath': str(run / 'RESULT.json'),
                   'generation': marker.get('generation', 0) if marker else 0, 'utc': utc()}
        replace_json(Path(config['owner_marker']), pending, marker)
        require(sha_file(profile_path) == intent['profileSha256'], 'Executed profile changed')
        with (run / 'stdout.txt').open('xb') as out, (run / 'stderr.txt').open('xb') as err:
            process = subprocess.run(argv, env=archive_environment(config), stdout=out, stderr=err,
                                     stdin=subprocess.DEVNULL, check=False)
        save_new(run / 'UNISON-EXIT.json', {'runId': run_id, 'utc': utc(), 'unisonExit': process.returncode,
                 'profileSha256': intent['profileSha256'], 'ownerTransferred': False})
        # No SQL: source readers cannot create WAL/SHM here.
        closed_gate(config)
        volume_gate(config)
        source_after = inventory_critical(config[source + '_root'], config, True)
        if command == 'bootstrap':
            require(source_after == facts['families'][source], 'Authoritative source changed during bootstrap')
        result = {'schema': SCHEMA, 'runId': run_id, 'utc': utc(), 'host': config['host'],
                  'unisonExit': process.returncode, 'direction': direction, 'tier': tier,
                  'roots': {'local': config['local_root'], 'photo': config['photo_root']},
                  'criticalFamiliesAfter': {name: inventory_critical(config[name + '_root'], config, True)
                                           for name in ('local', 'photo')},
                  'status': 'verification-required' if process.returncode == 0 else 'held',
                  'wholeLightroomFolderComplete': False, 'ownerTransferred': False,
                  'unisonState': config['state_dir'], 'scope': facts['scope'],
                  'previousCriticalFamily': prior, 'criticalContentVerificationByThisTool': False}
        result['atomicDirectoryGroupingEnabled'] = command != 'bootstrap'
        save_new(run / 'RESULT.json', result)
        if process.returncode != 0:
            held = dict(pending, phase='held', unisonExit=process.returncode, utc=utc())
            replace_json(Path(config['owner_marker']), held, pending)
        print(json.dumps({'result': str(run / 'RESULT.json'), 'resultSha256': sha_file(run / 'RESULT.json'),
                          'unisonExit': process.returncode, 'status': result['status'],
                          'ownerTransferred': False}, indent=2))
        return 0 if process.returncode == 0 else 1
    except BaseException as error:
        if run is not None:
            save_new(run / 'FAILURE.json', {'utc': utc(), 'actualError': repr(error), 'ownerTransferred': False,
                                          'unisonExitRecorded': (run / 'UNISON-EXIT.json').exists()})
        if pending is not None and read_owner(config) == pending:
            replace_json(Path(config['owner_marker']), dict(pending, phase='held', utc=utc()), pending)
        raise
    finally:
        if lease is not None:
            os.close(lease)
        os.close(lock)


def verification(config, marker, receipt_path):
    require(marker is not None and marker.get('phase') == 'verification-required'
            and marker.get('host') == config['host'], 'No completed transfer awaiting this host verification')
    result_path = safe_path(marker['resultPath'])
    require(Path(config['journal_root']) in result_path.parents, 'Result is outside the owned journal root')
    result, receipt = read_json(result_path), read_json(safe_path(str(receipt_path)))
    require(result.get('unisonExit') == 0 and result.get('status') == 'verification-required', 'Skipped/conflicted/failed transfer cannot hand off')
    require(receipt.get('schema') == SCHEMA and receipt.get('runId') == marker['runId'] == result['runId']
            and receipt.get('resultSha256') == sha_file(result_path), 'Independent receipt is not bound to this result')
    require(receipt.get('roots') == result['roots'] and receipt.get('tier') == result['tier'], 'Verification scope/roots differ')
    require(receipt.get('sourceStable') is True and receipt.get('criticalFamilySHA256Equal') is True
            and receipt.get('databaseFamilyMembershipEqual') is True
            and receipt.get('missingExpectedFiles') == [] and receipt.get('staleDatabaseSidecars') == [],
            'Independent critical byte/family proof is incomplete')
    hashes = receipt.get('criticalFiles')
    expected = {r['path']: r for r in result['criticalFamiliesAfter']['local']['rows'] if r['kind'] == 'file'}
    require(isinstance(hashes, list) and len(hashes) == len(expected)
            and len({r.get('path') for r in hashes}) == len(hashes), 'Verification critical-file coverage differs')
    for row in hashes:
        require(row.get('path') in expected and SHA_RE.fullmatch(row.get('localSha256', ''))
                and row.get('localSha256') == row.get('photoSha256')
                and row.get('size') == expected[row['path']]['identity'][2], 'Critical SHA/size proof differs')
    for name in ('local', 'photo'):
        require(inventory_critical(config[name + '_root'], config, True) == result['criticalFamiliesAfter'][name],
                'Critical family changed since transfer/verification')
    return {'path': str(receipt_path), 'sha256': sha_file(Path(receipt_path)), 'result': result}


def change_owner(config, command, receipt_path, target=None):
    mkdir_safe(Path(config['state_dir']))
    lock = open_lock(Path(config['state_dir']) / 'SHUTTLE.lock', create=True)
    lease = None
    try:
        marker = read_owner(config)
        require(marker is not None, 'No completed transfer awaiting this host verification')
        owned_state(config, marker.get('tier'))
        lease = open_lock(Path(config['shared_io_lease']), blocking=True)
        volume_gate(config); classic_gate(config); closed_gate(config)
        proof = verification(config, marker, receipt_path)
        if command == 'release':
            require(target in config['peers'] and marker.get('owner') == config['host']
                    and marker.get('direction') in ('outgoing', 'initial-outgoing'), 'Only the outgoing owner can release to a declared peer')
            successor = dict(marker, phase='in-transit', owner=None, previousOwner=config['host'],
                             releaseTo=target, generation=marker['generation'] + 1, utc=utc(),
                             verification={'path': proof['path'], 'sha256': proof['sha256']})
        else:
            require(marker.get('direction') in ('incoming', 'initial-outgoing', 'outgoing'), 'Invalid acceptance direction')
            successor = dict(marker, phase='active', owner=config['host'], releaseTo=None, utc=utc(),
                             verification={'path': proof['path'], 'sha256': proof['sha256']})
        replace_json(Path(config['owner_marker']), successor, marker)
        print(json.dumps(successor, indent=2))
        return 0
    finally:
        if lease is not None:
            os.close(lease)
        os.close(lock)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    for name in ('preflight', 'bootstrap', 'sync'):
        command = commands.add_parser(name)
        command.add_argument('--tier', choices=TIERS, default='main-core')
        command.add_argument('--source', choices=('local', 'photo'), default='local')
        if name != 'preflight':
            command.add_argument('--execute', action='store_true')
    for name in ('release', 'accept'):
        command = commands.add_parser(name)
        command.add_argument('--receipt', required=True, type=Path)
        command.add_argument('--execute', action='store_true')
        if name == 'release':
            command.add_argument('--to', required=True)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command == 'status':
        print(json.dumps({'host': config['host'], 'owner': read_owner(config),
                          'stateDirectory': config['state_dir'], 'roots': {name: config[name + '_root'] for name in ('local', 'photo')},
                          'doesNotAuthorizeOpeningCatalog': True}, indent=2))
        return 0
    if args.command == 'preflight' or not args.execute:
        if args.command in ('release', 'accept'):
            raise ValueError('Ownership changes require --execute after independent verification')
        print(json.dumps(preflight(config, args.tier, args.source), indent=2))
        return 0
    if args.command in ('release', 'accept'):
        return change_owner(config, args.command, args.receipt, getattr(args, 'to', None))
    return execute_transfer(config, args.command, args.tier, args.source)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'status': 'held', 'error': str(error), 'ownerTransferred': False}), file=sys.stderr)
        raise SystemExit(1)
