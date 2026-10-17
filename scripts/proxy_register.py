#!/usr/bin/env python3
"""Register already-placed Smart Preview clones with Lightroom Cloud's own proxy loader.

Subcommands run in order: ledger -> launch -> arm -> bind -> stage -> guard -> select -> postaudit.
Python never writes to any Lightroom store. The only native action is one ordinary user
Script selected from Cloud's Scripts menu; it issues the normal `getProxyPaths` request
per batch and records before/after documents. See docs/CLOUD-PROXY-REGISTRATION.md.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import re
import secrets
import stat
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / 'scripts/proxy_register.lua'
SCRIPT_NAME = 'Register known-hash Smart previews'
CLOUD_EXECUTABLE = '/Applications/Adobe Lightroom CC/Adobe Lightroom.app/Contents/MacOS/Adobe Lightroom'
APP_DATA = Path.home() / 'Library/Application Support/Adobe/Lightroom CC'
NATIVE_FIELDS = {'_id', '_revId', '_localId', '_changeCounter', '_labels', '_spaceId', '_localOnly',
                 '_serverProvidedMetadata', '_initialChangeCounter'}
DOC_SQL = ('SELECT d.localDocId,d.fullDocId,d.winningRevSequence,d.mostRecentRevSequence,d.spaceId,d.deleted,'
           'd.hasConflicts,d.type,d.subtype,r.revId,CAST(r.content AS BLOB),CAST(d.annotation AS BLOB) '
           'FROM docs d JOIN revs r ON r.sequence=d.winningRevSequence WHERE d.fullDocId=?')
LABELS_SQL = 'SELECT localDocId,revSequence,name FROM labels INDEXED BY sqlite_autoindex_labels_1 WHERE localDocId=? ORDER BY name'
CANDIDATES_SQL = ("SELECT a.assetId,a.docId,l.needsProxyDownload,l.needsDevelopXmpDownload,l.proxySize,"
                  "l.needsOriginalDownload,l.hasLocalOriginal FROM assets a JOIN localStatusAndOzStatus l ON l.docId=a.docId "
                  "WHERE l.subtype='image' AND l.isVersionDocument=0 AND l.hasLocalProxy=0 ORDER BY a.docId")


def need(ok, message):
    if not ok:
        raise RuntimeError(message)


def five(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def sha_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def pin(path, sha=None):
    path = Path(path)
    st = path.lstat()
    need(stat.S_ISREG(st.st_mode), 'pin is not a regular file: ' + str(path))
    digest = sha_file(path)
    need(sha is None or digest == sha, 'pin SHA differs: ' + str(path))
    return {'path': str(path), 'sha256': digest, 'bytes': st.st_size, 'fiveDecimal': [str(v) for v in five(st)]}


def write_new(path, data):
    data = data.encode() if isinstance(data, str) else data
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def atomic_replace(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data.encode())
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def lua_string(value):
    return '"' + ''.join(chr(c) if 32 <= c <= 126 and c not in (34, 92) else '\\%03d' % c for c in value.encode()) + '"'


def lua(value):
    """Lossless Lua 5.1 literal for JSON-like data; dict values of None are dropped like native nil."""
    if value is None:
        return 'nil'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if type(value) is int:
        need(abs(value) < 2 ** 53, 'lossless Lua integer guard')
        return str(value)
    if type(value) is float:
        need(math.isfinite(value), 'nonfinite number')
        text = repr(value)
        need(float(text) == value, 'lossless float representation')
        return text
    if isinstance(value, str):
        return lua_string(value)
    if isinstance(value, list):
        return '{' + ','.join(lua(v) for v in value) + '}'
    need(isinstance(value, dict) and all(isinstance(k, str) for k in value), 'unsupported value for Lua literal')
    return '{' + ','.join('[' + lua_string(k) + ']=' + lua(v) for k, v in sorted(value.items()) if v is not None) + '}'


def library_paths(library):
    library = Path(library).resolve()
    need(library.is_dir() and re.fullmatch('[0-9a-f]{32}', library.name), 'library must be <Lightroom Library.lrlibrary>/<32-hex catalog id>')
    return {'pixelsPath': str(library), 'catalogID': library.name,
            'wfindex': library / 'Managed Catalog.wfindex', 'mcat': library / 'Managed Catalog.mcat',
            'proxies': library / 'proxies/2560', 'appData': str(APP_DATA)}


def volume_uuid(path):
    plist = subprocess.check_output(['diskutil', 'info', '-plist', str(path)])
    import plistlib
    info = plistlib.loads(plist)
    uuid = info.get('VolumeUUID')
    need(isinstance(uuid, str) and uuid, 'volume UUID unavailable for ' + str(path))
    return uuid


def connect_readonly(path):
    import sqlite3
    con = sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
    con.execute('PRAGMA query_only=1')
    con.execute('PRAGMA trusted_schema=OFF')
    con.execute('BEGIN')
    return con


def check_keys(value, path=''):
    if isinstance(value, dict):
        for key, item in value.items():
            need(isinstance(key, str), 'non-string key at ' + path)
            check_keys(item, path + '/' + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            check_keys(item, path + '/' + str(index))


def check_nulls(value, path=''):
    if isinstance(value, dict):
        for key, item in value.items():
            need(item is not None, 'null value at ' + path + '/' + str(key))
            check_nulls(item, path + '/' + str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            need(item is not None, 'null in list at ' + path)
            check_nulls(item, path + '/' + str(index))


def scan_clones(proxies):
    """Map asset UUID -> {suffix: path} for every regular file under proxies/2560."""
    files = {}
    for directory in os.scandir(proxies):
        if not directory.is_dir():
            continue
        for entry in os.scandir(directory.path):
            if not entry.is_file(follow_symlinks=False):
                continue
            match = re.fullmatch(r'([0-9a-f]{29})(.*)', entry.name)
            if match:
                files.setdefault(directory.name + match.group(1), {})[match.group(2)] = entry.path
    return files


def classify_row(assetId, docId, flags, files, doc_row, label_rows, unpack, volume_guid):
    """Return a ledger row or raise RuntimeError with a hold reason."""
    npd, nxmp, psize, nod, hlo = flags
    clones = files.get(assetId)
    need(clones, 'NO_PHYSICAL_CLONE')
    need('' in clones, 'ONLY_SUFFIXED_CLONE:' + ','.join(sorted(clones)))
    path = clones['']
    st = os.lstat(path)
    need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, 'CLONE_NOT_REGULAR_OR_LINKED')
    need(doc_row is not None, 'NO_MCAT_DOC')
    localDocId, fullDocId, winSeq, mostSeq, spaceId, deleted, conflicts, typ, sub, revId, content, ann = doc_row
    need(localDocId == docId, 'LOCALID_MISMATCH')
    need(not deleted and not conflicts and typ == 'asset' and sub == 'image', 'DOC_STATE')
    need(isinstance(revId, str) and revId, 'NO_REVID')
    need(type(mostSeq) is int and 0 <= mostSeq < 2 ** 53 and type(winSeq) is int, 'SEQ_TYPE')
    body = unpack(content)
    annot = unpack(ann) if ann else {}
    need(not (NATIVE_FIELDS & set(body)), 'BODY_HAS_NATIVE_FIELDS')
    need(set(annot) <= {'_localOnly', '_serverProvidedMetadata'}, 'ANNOTATION_KEYS')
    need(body.get('subtype') == 'image', 'BODY_SUBTYPE')
    imp = body.get('importSource')
    need(isinstance(imp, dict), 'NO_IMPORTSOURCE')
    psha = imp.get('proxySHA256')
    need(isinstance(psha, str) and re.fullmatch('[0-9a-f]{64}', psha), 'NO_EXPECTED_PROXY_SHA' if psha is None else 'BAD_EXPECTED_PROXY_SHA')
    local = annot.get('_localOnly') or {}
    need(isinstance(local, dict), 'LOCALONLY_TYPE')
    files_annotation = local.get('files') or {}
    need(isinstance(files_annotation, dict), 'FILES_TYPE')
    proxy = files_annotation.get('proxy')
    need(proxy is None or (isinstance(proxy, dict) and proxy.get('2560') is None), 'PROXY_ANNOTATION_PRESENT')
    links = (annot.get('_serverProvidedMetadata') or {}).get('links')
    need(isinstance(links, dict), 'NO_SERVER_LINKS')
    relations = sorted(k for k, v in links.items() if isinstance(k, str) and 'proxy_type' in k and k.rsplit('/', 1)[-1] == '2560'
                       and isinstance(v, dict) and isinstance(v.get('href'), str) and v['href'])
    need(relations, 'NO_2560_RELATION')
    link = links.get('/rels/proxy_type/2560') or {}
    check_keys(body, 'body')
    check_keys(annot, 'annotation')
    check_nulls(body, 'body')
    check_nulls(annot, 'annotation')
    need(len(label_rows) <= 32, 'LABEL_CAP')
    labels = {}
    for ld, rs, name in label_rows:
        need(ld == localDocId and isinstance(name, str) and type(rs) is int and name not in labels, 'LABEL_ROW')
        labels[name] = True
    return {'assetUUID': assetId, 'localID': localDocId, 'revisionID': revId, 'changeCounter': mostSeq,
            'winningRevSequence': winSeq, 'spaceID': spaceId, 'deleted': False, 'hasConflicts': False,
            'expectedBody': body, 'expectedAnnotation': annot, 'storedLabels': labels, 'storedLabelRows': [list(r) for r in label_rows],
            'expectedPath': path, 'expectedVolumeGuid': volume_guid, 'expectedRelativePath': path.lstrip('/'),
            'expectedProxySHA256': psha, 'destinationFiveDecimal': [str(v) for v in five(st)], 'supportedProxyRelations': relations,
            'indexFlags': {'needsProxyDownload': npd, 'needsDevelopXmpDownload': nxmp, 'needsOriginalDownload': nod,
                           'hasLocalOriginal': hlo, 'proxyClass': psize},
            'proxyLinkFacts': {'invalid': bool(link.get('invalid')), 'linkSHA256': link.get('sha256')},
            'deniedByPresent': 'deniedBy' in local,
            'originalMasterAnnotationPresent': isinstance(files_annotation.get('original'), dict) and 'master' in files_annotation['original'],
            'willNotUploadMaster': imp.get('willNotUploadMaster')}


def cmd_ledger(args):
    import msgpack
    lib = library_paths(args.library)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    files = scan_clones(lib['proxies'])
    volume_guid = args.volume_uuid or volume_uuid(lib['pixelsPath'])
    wf = connect_readonly(lib['wfindex'])
    mc = connect_readonly(lib['mcat'])
    plans = {'doc': [list(r) for r in mc.execute('EXPLAIN QUERY PLAN ' + DOC_SQL, ('x',))],
             'labels': [list(r) for r in mc.execute('EXPLAIN QUERY PLAN ' + LABELS_SQL, (1,))]}
    candidates = wf.execute(CANDIDATES_SQL).fetchall()

    def unpack(raw):
        value = msgpack.unpackb(raw, raw=False, strict_map_key=False)
        need(isinstance(value, dict), 'msgpack document is not a map')
        return value

    rows = open(out / 'NATIVE-INPUTS.jsonl', 'wb')
    holds = open(out / 'HELD.jsonl', 'wb')
    count = held = 0
    hold_counts = {}
    for assetId, docId, *flags in candidates:
        try:
            doc_row = mc.execute(DOC_SQL, (assetId,)).fetchone()
            labels = mc.execute(LABELS_SQL, (docId,)).fetchall() if doc_row else []
            row = classify_row(assetId, docId, flags, files, doc_row, labels, unpack, volume_guid)
            row = {'ordinal0': count, **row}
            rows.write((json.dumps(row, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode())
            count += 1
        except RuntimeError as error:
            reason = str(error).split(':')[0]
            hold_counts[reason] = hold_counts.get(reason, 0) + 1
            held += 1
            holds.write((json.dumps({'assetUUID': assetId, 'docId': docId, 'reason': str(error)[:300]}) + '\n').encode())
    for handle in (rows, holds):
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
    for con in (mc, wf):
        con.rollback()
        con.close()
    result = {'state': 'COMPLETE_KNOWN_SHA_PROXY_LEDGER_READONLY_NOT_DISPATCHED', 'library': lib['pixelsPath'],
              'candidates': len(candidates), 'rows': count, 'holds': held, 'holdCounts': hold_counts,
              'physicalUUIDs': len(files), 'volumeGuid': volume_guid, 'seconds': time.time() - started, 'queryPlans': plans,
              'rowsFile': pin(out / 'NATIVE-INPUTS.jsonl'), 'holdsFile': pin(out / 'HELD.jsonl'),
              'nativeOperations': 0, 'databaseWrites': False}
    write_new(out / 'COMPLETE.json', json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != 'queryPlans'}))


def sandbox_profile(lib, extra_denied):
    denied = [str(Path(p).resolve()) for p in extra_denied] + [str(Path(lib['pixelsPath']) / 'originals'), '/Volumes']
    lines = ['(version 1)', '(allow default)', '(deny network-outbound (remote ip "*:*"))']
    lines += ['(deny file-read* (subpath "%s"))' % p.replace('"', '\\"') for p in denied]
    return ' '.join(lines) + '\n'


def process_identity(pid):
    text = subprocess.check_output(['ps', '-p', str(pid), '-o', 'pid=', '-o', 'lstart=', '-o', 'comm='], text=True).strip()
    need(text.split()[0] == str(pid) and text.endswith(CLOUD_EXECUTABLE), 'Cloud process owner/executable differs')
    return text


def cmd_launch(args):
    """Launch Cloud under network and original-source denial; records launcher evidence. Does not quit a running Cloud."""
    lib = library_paths(args.library)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    need(not subprocess.run(['pgrep', '-x', 'Adobe Lightroom'], capture_output=True).stdout.strip(), 'Lightroom Cloud is already running; quit it normally first')
    profile = out / 'cloud-offline.sb'
    profile.write_text(sandbox_profile(lib, args.deny))
    subprocess.Popen(['/usr/bin/sandbox-exec', '-f', str(profile), CLOUD_EXECUTABLE],
                     stdout=open(out / 'cloud-stdout.log', 'wb'), stderr=open(out / 'cloud-stderr.log', 'wb'), stdin=subprocess.DEVNULL, start_new_session=True)
    pid = None
    for _ in range(60):
        time.sleep(2)
        found = subprocess.run(['pgrep', '-x', 'Adobe Lightroom'], capture_output=True, text=True).stdout.split()
        if found:
            pid = int(found[0])
            break
    need(pid, 'Cloud did not start')
    for _ in range(180):
        menus = subprocess.run(['osascript', '-e', 'tell application "System Events" to tell process "Adobe Lightroom" to get name of every menu bar item of menu bar 1'], capture_output=True, text=True).stdout
        if 'Scripts' in menus:
            break
        time.sleep(2)
    sockets = subprocess.run(['lsof', '-nP', '-p', str(pid), '-a', '-i'], capture_output=True, text=True).stdout.strip().splitlines()
    evidence = {'state': 'FRESH_CLOUD_LAUNCHED_WITH_NETWORK_AND_SOURCE_DENIAL', 'observedUTC': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'profile': pin(profile), 'cloudPID': pid, 'cloudProcessIdentity': process_identity(pid), 'networkDenied': True,
                'originalSourceReadDenied': True, 'networkSocketLines': len(sockets), 'nativeRequestsByLauncher': 0}
    write_new(out / 'LAUNCHER-EVIDENCE.json', json.dumps(evidence, indent=1))
    print(json.dumps({'cloudPID': pid, 'sockets': len(sockets)}))


def cmd_arm(args):
    lib = library_paths(args.library)
    evidence = json.loads(Path(args.launcher_evidence).read_bytes())
    need(evidence['networkDenied'] is True and evidence['networkSocketLines'] == 0, 'launcher evidence does not show a network-denied process')
    need(process_identity(evidence['cloudPID']) == evidence['cloudProcessIdentity'], 'Cloud process identity changed since launch')
    arm = {'state': 'ARMED_KNOWN_SHA_PROXY_NATIVE_REGISTRATION', 'epoch': int(time.time()), 'nonce': secrets.token_hex(16),
           'cloudPID': evidence['cloudPID'], 'cloudProcessIdentity': evidence['cloudProcessIdentity'], 'catalogID': lib['catalogID'],
           'pixelsPath': lib['pixelsPath'], 'appData': lib['appData'], 'volumeGuid': args.volume_uuid or volume_uuid(lib['pixelsPath']),
           'launcherEvidence': pin(args.launcher_evidence), 'armWindowSeconds': args.arm_window, 'guardFreshnessSeconds': args.guard_freshness,
           'parallelBatches': args.parallel, 'authorization': args.authorization}
    path = Path(args.output) / ('ARM-' + arm['nonce'] + '.json')
    write_new(path, json.dumps(arm, indent=1))
    print(path)


def persisted_doc(row):
    doc = {**row['expectedBody'], **row['expectedAnnotation'], '_id': row['assetUUID'], '_localId': row['localID'],
           '_revId': row['revisionID'], '_changeCounter': row['changeCounter']}
    if row['spaceID'] is not None:
        doc['_spaceId'] = row['spaceID']
    return doc


def runtime_row(row):
    return {'ordinal0': row['ordinal0'], 'assetUUID': row['assetUUID'], 'localID': row['localID'], 'revisionID': row['revisionID'],
            'expectedPath': row['expectedPath'], 'expectedVolumeGuid': row['expectedVolumeGuid'], 'expectedRelativePath': row['expectedRelativePath'],
            'expectedProxySHA256': row['expectedProxySHA256'], 'storedLabels': row['storedLabels'],
            'supportedProxyRelations': row['supportedProxyRelations'], 'expectedPersistedDoc': persisted_doc(row)}


def build_batches(rows_path, out, arm, limit=0):
    batches, guard_batches, literals, physical = [], [], [], []
    seen = set()
    count = 0

    def publish():
        if not literals:
            return
        number = len(batches) + 1
        q = write_new(out / ('BATCH-%05d.lua' % number), 'return {' + ','.join(literals) + '}\n')
        q.update(count=len(literals), batch=number)
        batches.append(q)
        g = write_new(out / ('GUARD-BATCH-%05d.json' % number), json.dumps(physical, separators=(',', ':')) + '\n')
        g.update(count=len(physical), batch=number)
        guard_batches.append(g)
        literals.clear()
        physical.clear()

    with open(rows_path, 'rb') as handle:
        for line in handle:
            row = json.loads(line)
            need(row['ordinal0'] == count, 'ordinal sequence')
            need(re.fullmatch('[0-9a-f]{32}', row['assetUUID']) and type(row['localID']) is int, 'row identity')
            need(re.fullmatch('[0-9a-f]{64}', row['expectedProxySHA256']), 'expected proxy SHA')
            need(row['expectedVolumeGuid'] == arm['volumeGuid'], 'volume GUID differs from arm')
            need(row['expectedPath'].startswith(arm['pixelsPath'] + '/proxies/2560/'), 'expected path outside library')
            key = (row['localID'], row['assetUUID'])
            need(key not in seen, 'duplicate row')
            seen.add(key)
            literals.append(lua(runtime_row(row)))
            physical.append({'ordinal0': count, 'assetUUID': row['assetUUID'], 'destinationPath': row['expectedPath'],
                             'destinationFiveDecimal': row['destinationFiveDecimal']})
            count += 1
            if len(literals) == 256:
                publish()
            if limit and count >= limit:
                break
    publish()
    need(count > 0, 'no rows')
    config = write_new(out / 'BATCHES.lua', 'return ' + lua(batches) + '\n')
    guards = write_new(out / 'GUARD-BATCHES.json', json.dumps(guard_batches, separators=(',', ':')) + '\n')
    return count, config, guards


def cmd_bind(args):
    complete = json.loads(Path(args.ledger_complete).read_bytes())
    need(complete['state'] == 'COMPLETE_KNOWN_SHA_PROXY_LEDGER_READONLY_NOT_DISPATCHED', 'ledger not complete')
    rows_pin = pin(complete['rowsFile']['path'], complete['rowsFile']['sha256'])
    arm = json.loads(Path(args.arm).read_bytes())
    arm_pin = pin(args.arm)
    need(arm['state'] == 'ARMED_KNOWN_SHA_PROXY_NATIVE_REGISTRATION', 'arm state')
    launcher_pin = pin(arm['launcherEvidence']['path'], arm['launcherEvidence']['sha256'])
    out = Path(args.output)
    need(not out.exists(), 'output must be new')
    out.mkdir(parents=True, mode=0o700)
    template = TEMPLATE.read_bytes()
    need(template.count(b'__PLAN__') == 1, 'template plan slot')
    if args.batches_from:
        previous = json.loads((Path(args.batches_from) / 'CONTROLLER-PLAN.json').read_bytes())
        need(previous['rows']['sha256'] == rows_pin['sha256'], 'previous batches were built from different rows')
        count = previous['count']
        config = pin(previous['batchConfig']['path'], previous['batchConfig']['sha256'])
        guards = pin(previous['guardBatches']['path'], previous['guardBatches']['sha256'])
    else:
        count, config, guards = build_batches(rows_pin['path'], out, arm, args.limit)
    plan = {'state': 'ROOT_BOUND_KNOWN_SHA_PROXY_REGISTRATION', 'epoch': int(time.time()), 'armWindowSeconds': arm['armWindowSeconds'],
            'guardFreshnessSeconds': arm['guardFreshnessSeconds'], 'nonce': arm['nonce'], 'cloudPID': arm['cloudPID'],
            'catalogID': arm['catalogID'], 'pixelsPath': arm['pixelsPath'], 'appData': arm['appData'], 'run': str(out), 'count': count,
            'batchSize': 256, 'parallelBatches': arm['parallelBatches'], 'arm': arm_pin, 'rows': rows_pin, 'launcherEvidence': launcher_pin,
            'batchConfig': config, 'guardBatches': guards, 'guardPath': str(out / 'LIVE-SOURCE-GUARD.lua'),
            'maxReceiptBytes': count * 16384 + 64 * 1024 * 1024, 'annotationOnlyProxyLabelsQualified': True, 'initialEmptyDeadlineSeconds': 15,
            'batchesReusedFrom': args.batches_from}
    plan_pin = write_new(out / 'CONTROLLER-PLAN.json', json.dumps(plan, separators=(',', ':')) + '\n')
    script = write_new(out / (SCRIPT_NAME + '.lua'), template.replace(b'__PLAN__', lua(plan).encode()))
    result = {'state': 'SOURCE_CONSTRUCTED_NOT_STAGED_NOT_INVOKED', 'nonce': arm['nonce'], 'run': str(out), 'script': script,
              'plan': plan_pin, 'count': count, 'batches': (count + 255) // 256}
    write_new(out / 'CONSTRUCTOR-READY.json', json.dumps(result, separators=(',', ':')) + '\n')
    print(json.dumps(result))


def cmd_stage(args):
    """Copy the bound script into Cloud's user Scripts folder. The menu lists names present at launch; contents are read at selection."""
    source = Path(args.run) / (SCRIPT_NAME + '.lua')
    target = APP_DATA / 'Scripts' / (SCRIPT_NAME + '.lua')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    print(json.dumps({'staged': str(target), 'sha256': sha_file(target), 'sourceSHA256': sha_file(source)}))


def cmd_select(args):
    """Select the Scripts menu entry once through ordinary UI scripting (Accessibility permission required)."""
    script = 'tell application "System Events" to tell process "Adobe Lightroom" to click menu item "%s" of menu 1 of menu bar item "Scripts" of menu bar 1' % SCRIPT_NAME
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    print(json.dumps({'exit': result.returncode, 'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}))
    need(result.returncode == 0, 'menu selection failed')


def cmd_guard(args):
    """Refresh the live guard every second; approve batch 1, then the rest once CONTROL-ACCEPTED.json exists."""
    plan = json.loads(Path(args.plan).read_bytes())
    need(sha_file(args.plan) == args.plan_sha256, 'plan SHA differs')
    arm = json.loads(Path(plan['arm']['path']).read_bytes())
    expected_process = arm['cloudProcessIdentity']
    need(process_identity(plan['cloudPID']) == expected_process, 'process identity')
    guard_batches = json.loads(Path(plan['guardBatches']['path']).read_bytes())
    need(len(guard_batches) == (plan['count'] + 255) // 256, 'batch coverage')
    run = Path(plan['run'])
    events = run / 'ACTUAL-PROXY-EVENTS.jsonl'
    offset, partial, active, begun, closed, cache, verified = 0, b'', set(), 0, set(), {}, set()
    terminal, journal_identity, last_progress, recognized, held = None, None, 0, 0, 0
    write_new(run / 'GUARD-INTENT.json', json.dumps({'state': 'SOURCE_PROCESS_GUARD_RUNNING_NOT_NATIVE_DISPATCH', 'nonce': plan['nonce'],
                                                     'pid': os.getpid(), 'cloudPID': plan['cloudPID'], 'nativeInvocations': 0}) + '\n')
    try:
        while True:
            need(process_identity(plan['cloudPID']) == expected_process, 'Cloud process/start changed')
            if events.exists():
                st = events.lstat()
                identity = [st.st_dev, st.st_ino]
                journal_identity = journal_identity or identity
                need(identity == journal_identity and st.st_size >= offset, 'native journal replaced/truncated')
                with open(events, 'rb') as handle:
                    handle.seek(offset)
                    new = handle.read()
                    offset += len(new)
                partial += new
                lines = partial.split(b'\n')
                partial = lines.pop()
                for line in lines:
                    event = json.loads(line)
                    need(event['nonce'] == plan['nonce'], 'foreign journal')
                    name, value = event['event'], event['value']
                    if name == 'BATCH_READONLY_BEGIN':
                        number = value['batch']
                        need(1 <= number <= len(guard_batches) and number not in closed, 'batch sequence')
                        active.add(number)
                        begun = max(begun, number)
                    elif name == 'BATCH_CLOSED_CHECKPOINT':
                        number = value['batch']
                        need(number in active and value['allOwnedHandlesClosed'] is True, 'batch closure')
                        active.remove(number)
                        closed.add(number)
                        recognized += value.get('recognized', 0)
                        held += value.get('held', 0)
                    elif name in ('CONTROLLER_CLOSED', 'ZERO_REQUEST_OWNER_HELD_CLOSED'):
                        terminal = event
                    elif name in ('TOP_ERROR_RETAINED', 'OWNER_ERROR_RETAINED', 'PUMP_ERROR_RETAINED'):
                        stop = run / 'STOP-NEW-ADMISSIONS.json'
                        if not stop.exists():
                            write_new(stop, json.dumps({'nonce': plan['nonce'], 'event': name, 'noCancellation': True, 'noReplay': True}) + '\n')
            if terminal and (run / 'OWNED-JOURNAL-CLOSED.json').exists():
                closure = json.loads((run / 'OWNED-JOURNAL-CLOSED.json').read_bytes())
                need(closure['nonce'] == plan['nonce'] and closure['journalClosed'] is True, 'journal closure')
                need(not active and not partial, 'pending batches at terminal')
                write_new(run / 'GUARD-NATIVE-CLOSED-OBSERVATION.json', json.dumps({
                    'state': 'GENUINE_NATIVE_REQUEST_MODEL_AND_JOURNAL_CLOSURE_OBSERVED_POST_GATE_PENDING', 'nonce': plan['nonce'],
                    'terminal': terminal, 'closedBatches': len(closed), 'recognized': recognized, 'held': held, 'nativeReplay': 0}) + '\n')
                break
            control_ok = (run / 'CONTROL-ACCEPTED.json').exists()
            upcoming = set(range(begun + 1, min(len(guard_batches), begun + max(4, 8 - len(active))) + 1))
            approved = {}
            for number in sorted(active | upcoming):
                if number > 1 and not control_ok:
                    continue
                if number not in cache:
                    cache[number] = json.loads(Path(guard_batches[number - 1]['path']).read_bytes())
                if number not in verified:
                    for row in cache[number]:
                        st = os.lstat(row['destinationPath'])
                        need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and five(st) == [int(v) for v in row['destinationFiveDecimal']],
                             'destination clone identity changed: ' + row['destinationPath'])
                    verified.add(number)
                approved[str(number)] = True
            guard = {'nonce': plan['nonce'], 'epoch': int(time.time()), 'cloudPID': plan['cloudPID'], 'catalogID': plan['catalogID'],
                     'pixelsPath': plan['pixelsPath'], 'networkDenied': True, 'originalSourceReadDenied': True, 'exactProcessOwnerUnchanged': True,
                     'physicalSourceDestUnchanged': True, 'approvedBatches': approved, 'rowsSHA256': plan['rows']['sha256'],
                     'batchConfigSHA256': plan['batchConfig']['sha256'], 'launcherEvidenceSHA256': plan['launcherEvidence']['sha256'],
                     'guardProducerPID': os.getpid(), 'controlAccepted': control_ok}
            atomic_replace(plan['guardPath'], 'return ' + lua(guard) + '\n')
            cache = {n: rows for n, rows in cache.items() if n in active or n in upcoming}
            if time.time() - last_progress >= 30:
                last_progress = time.time()
                atomic_replace(run / 'GUARD-PROGRESS.json', json.dumps({'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'begun': begun,
                                                                       'closed': len(closed), 'active': sorted(active), 'recognized': recognized,
                                                                       'held': held, 'controlAccepted': control_ok, 'terminal': terminal is not None}) + '\n')
            if not events.exists() and time.time() > plan['epoch'] + plan['armWindowSeconds']:
                raise RuntimeError('no native entry before arm expiry')
            time.sleep(1)
    except Exception as error:
        stop = run / 'STOP-NEW-ADMISSIONS.json'
        if not stop.exists():
            write_new(stop, json.dumps({'nonce': plan['nonce'], 'error': repr(error), 'noCancellation': True, 'noReplay': True}) + '\n')
        write_new(run / 'GUARD-FAILURE.json', json.dumps({'state': 'STOP_NEW_ADMISSIONS_ONLY_GUARD_FAILURE_RETAINED', 'error': repr(error)}) + '\n')
        raise


def cmd_postaudit(args):
    """Closed audit after a normal Cloud quit: body, annotation (minus the added proxy entry), labels and index flags per ledger row."""
    import msgpack
    import collections
    lib = library_paths(args.library)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    running = subprocess.run(['pgrep', '-x', 'Adobe Lightroom'], capture_output=True, text=True).stdout.strip()
    wf = connect_readonly(lib['wfindex'])
    mc = connect_readonly(lib['mcat'])
    categories = collections.Counter()
    holds = open(out / 'HOLDS.jsonl', 'wb')
    count = 0
    with open(args.ledger_rows, 'rb') as handle:
        for line in handle:
            row = json.loads(line)
            count += 1
            uuid = row['assetUUID']
            try:
                doc_row = mc.execute(DOC_SQL, (uuid,)).fetchone()
                need(doc_row is not None, 'NO_DOC')
                localDocId, _, _, most, _, deleted, conflicts, _, _, revId, content, ann = doc_row
                need(localDocId == row['localID'], 'LOCALID')
                need(not deleted and not conflicts, 'DELETED_OR_CONFLICT')
                body = msgpack.unpackb(content, raw=False, strict_map_key=False)
                annot = msgpack.unpackb(ann, raw=False, strict_map_key=False) if ann else {}
                local = annot.get('_localOnly') or {}
                proxy = ((local.get('files') or {}).get('proxy') or {}).get('2560')
                registered = (isinstance(proxy, dict) and proxy.get('volumeGuid') == row['expectedVolumeGuid']
                              and proxy.get('relativePath') == row['expectedRelativePath'] and set(proxy) == {'volumeGuid', 'relativePath', 'lastSaveTimestamp'})
                stripped = json.loads(json.dumps(annot))
                if registered:
                    del stripped['_localOnly']['files']['proxy']['2560']
                    if not stripped['_localOnly']['files']['proxy']:
                        del stripped['_localOnly']['files']['proxy']
                labels = sorted(r[0] for r in mc.execute('SELECT name FROM labels INDEXED BY sqlite_autoindex_labels_1 WHERE localDocId=?', (localDocId,)))
                flags = wf.execute('SELECT hasLocalProxy,needsProxyDownload FROM localStatusAndOzStatus WHERE docId=?', (localDocId,)).fetchone()
                key = ('registered' if registered else 'unregistered', 'body=%s' % (body == row['expectedBody']), 'rev=%s' % (revId == row['revisionID']),
                       'ann=%s' % (stripped == row['expectedAnnotation']), 'labels=%s' % (labels == sorted(row['storedLabels'])),
                       'index=%s' % (flags is not None and float(flags[0]) == 1.0 and float(flags[1]) == 0.0), 'counterAdvanced=%s' % (most > row['changeCounter']))
                categories[key] += 1
                if not (registered and all(part.endswith('True') for part in key[1:6])):
                    holds.write((json.dumps({'assetUUID': uuid, 'localID': localDocId, 'category': key}) + '\n').encode())
            except RuntimeError as error:
                categories[('ERROR', str(error))] += 1
                holds.write((json.dumps({'assetUUID': uuid, 'error': str(error)}) + '\n').encode())
    holds.close()
    for con in (mc, wf):
        con.rollback()
        con.close()
    result = {'state': 'COMPLETE_CLOSED_POST_AUDIT_READONLY', 'cloudRunningPIDsAtAudit': running, 'rows': count,
              'fullyVerified': sum(v for k, v in categories.items() if k[0] == 'registered' and all(p.endswith('True') for p in k[1:6])),
              'categories': {' | '.join(k): v for k, v in categories.most_common()}, 'nativeOperations': 0, 'databaseWrites': False}
    write_new(out / 'COMPLETE.json', json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('ledger', help='read-only ledger of placed, unregistered, known-hash clones')
    p.add_argument('--library', required=True, help='<Lightroom Library.lrlibrary>/<catalog id> directory')
    p.add_argument('--output', required=True)
    p.add_argument('--volume-uuid', default=None)
    p.set_defaults(func=cmd_ledger)
    p = sub.add_parser('launch', help='launch Cloud with network and original-source denial (Cloud must not be running)')
    p.add_argument('--library', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--deny', action='append', default=[], help='additional paths Cloud may not read (Classic Smart Previews, originals)')
    p.set_defaults(func=cmd_launch)
    p = sub.add_parser('arm', help='write the one-run arm bound to the launched process')
    p.add_argument('--library', required=True)
    p.add_argument('--launcher-evidence', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--arm-window', type=int, default=7200)
    p.add_argument('--guard-freshness', type=int, default=30)
    p.add_argument('--parallel', type=int, default=4)
    p.add_argument('--volume-uuid', default=None)
    p.add_argument('--authorization', required=True, help='who authorized this run and when')
    p.set_defaults(func=cmd_arm)
    p = sub.add_parser('bind', help='build batch configs, plan and the user Script (not staged, not invoked)')
    p.add_argument('--ledger-complete', required=True)
    p.add_argument('--arm', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--batches-from', default=None)
    p.set_defaults(func=cmd_bind)
    p = sub.add_parser('stage', help='copy the bound Script into the Cloud Scripts folder')
    p.add_argument('--run', required=True)
    p.set_defaults(func=cmd_stage)
    p = sub.add_parser('guard', help='live source/process guard; run before selecting the menu entry')
    p.add_argument('--plan', required=True)
    p.add_argument('--plan-sha256', required=True)
    p.set_defaults(func=cmd_guard)
    p = sub.add_parser('select', help='select the Scripts menu entry once')
    p.set_defaults(func=cmd_select)
    p = sub.add_parser('postaudit', help='closed read-only audit after a normal Cloud quit')
    p.add_argument('--library', required=True)
    p.add_argument('--ledger-rows', required=True)
    p.add_argument('--output', required=True)
    p.set_defaults(func=cmd_postaudit)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == '__main__':
    main()
