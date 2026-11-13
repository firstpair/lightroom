"""Durable metadata queue for serial preview phases, with no media operations.

Claims are committed before launching work. An unfinished claim survives a
restart and blocks new work until an explicitly audited completion or recovery.
The executor authenticates receipts and owns all processes and leases; this
queue never retries, launches a process, or authorizes publication.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import uuid

TRANSITIONS = {'render': ('PENDING', 'NATIVE_READY'),
               'stage': ('NATIVE_READY', 'STAGED'),
               'publish': ('STAGED', 'PUBLISHED'),
               'recognize': ('PUBLISHED', 'COMPLETE')}
STATES = {'PENDING', 'NATIVE_READY', 'STAGED', 'PUBLISHED', 'COMPLETE'}
RETAINED = []


class UnsettledBatch(RuntimeError):
    pass


class QueueOwnershipUnknown(RuntimeError):
    def __init__(self, owner, error):
        super().__init__('QUEUE_OWNERSHIP_UNKNOWN_NO_RETRY')
        self.owner, self.cause = owner, error
        RETAINED.append(owner)


def pin(value):
    if (type(value) is not dict or set(value) != {'path', 'bytes', 'sha256'}
            or type(value['path']) is not str or not Path(value['path']).is_absolute()
            or type(value['bytes']) is not int or value['bytes'] <= 0
            or type(value['sha256']) is not str
            or not re.fullmatch('[0-9a-f]{64}', value['sha256'])):
        raise ValueError('AUTHENTICATED_RECEIPT_PIN_REQUIRED')
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class Queue:
    def __init__(self, path, *, create=False):
        self.path = Path(path)
        parent = self.path.parent
        st = parent.lstat()
        if (parent.resolve() != parent or not stat.S_ISDIR(st.st_mode)
                or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700):
            raise ValueError('OWNED_PRIVATE_QUEUE_DIRECTORY_REQUIRED')
        if create:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            descriptor = dict(fd=fd, closeAttempted=True, path=str(self.path))
            try:
                os.close(fd)
            except BaseException as error:
                raise QueueOwnershipUnknown(descriptor, error) from error
        st = self.path.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) != 0o600):
            raise ValueError('OWNED_PRIVATE_QUEUE_FILE_REQUIRED')
        self.identity = st.st_dev, st.st_ino
        self.owner = dict(connection=None, closeAttempted=False, uncertain=False)
        self.db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=2)
        self.owner['connection'] = self.db
        try:
            self._fence()
            self.db.execute('PRAGMA synchronous=FULL')
            if create:
                self.db.executescript('''
                CREATE TABLE jobs(key TEXT PRIMARY KEY, ordinal INTEGER UNIQUE NOT NULL,
                                  source TEXT NOT NULL, state TEXT NOT NULL, claim TEXT,
                                  proof TEXT);
                CREATE INDEX job_frontier ON jobs(state,claim,ordinal);
                CREATE TABLE batches(id TEXT PRIMARY KEY, phase TEXT NOT NULL,
                                     state TEXT NOT NULL, keys TEXT NOT NULL, proof TEXT,
                                     recovered INTEGER NOT NULL DEFAULT 0);
                PRAGMA user_version=1;
                ''')
            if self.db.execute('PRAGMA user_version').fetchone()[0] != 1:
                raise ValueError('QUEUE_SCHEMA')
        except BaseException as original:
            self.owner['original'] = original
            self.close()
            raise

    def _fence(self):
        st = self.path.lstat()
        if ((st.st_dev, st.st_ino) != self.identity or st.st_nlink != 1
                or not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or stat.S_IMODE(st.st_mode) != 0o600):
            raise ValueError('QUEUE_IDENTITY_CHANGED')

    def _change(self, operation):
        if self.owner['uncertain'] or self.owner['closeAttempted']:
            raise UnsettledBatch('QUEUE_OWNER_UNSETTLED')
        self._fence()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            result = operation()
        except BaseException as original:
            try:
                self.db.rollback()
            except BaseException as error:
                self.owner.update(uncertain=True, original=original)
                raise QueueOwnershipUnknown(self.owner, error) from original
            raise
        try:
            self.db.commit()
        except BaseException as error:
            self.owner['uncertain'] = True
            raise QueueOwnershipUnknown(self.owner, error) from error
        return result

    def enqueue(self, records, *, state='PENDING', adoption=None):
        if type(records) is not list or not 1 <= len(records) <= 10000 or state not in STATES:
            raise ValueError('BOUNDED_QUEUE_INPUT')
        receipt = pin(adoption) if adoption is not None else None
        if state != 'PENDING' and receipt is None:
            raise ValueError('EXPLICIT_SAVED_RESULT_ADOPTION_REQUIRED')
        rows = []
        for item in records:
            if (type(item) is not dict or set(item) != {'key', 'source'}
                    or type(item['key']) is not str or not 1 <= len(item['key']) <= 4096):
                raise ValueError('QUEUE_ITEM')
            rows.append((item['key'], pin(item['source'])))
        def operation():
            first = self.db.execute('SELECT coalesce(max(ordinal),0)+1 FROM jobs').fetchone()[0]
            self.db.executemany('INSERT INTO jobs VALUES(?,?,?,?,NULL,?)',
                                [(key, first + i, source, state, receipt)
                                 for i, (key, source) in enumerate(rows)])
        self._change(operation)

    def claim(self, phase, *, limit=8):
        if phase not in TRANSITIONS or type(limit) is not int or not 1 <= limit <= 8:
            raise ValueError('QUALIFIED_FINITE_PHASE_SIZE')
        def operation():
            if self.db.execute("SELECT 1 FROM batches WHERE state!='FINISHED' LIMIT 1").fetchone():
                raise UnsettledBatch('PRIOR_BATCH_REQUIRES_AUDIT_NOT_REPLAY')
            before, _ = TRANSITIONS[phase]
            rows = self.db.execute('SELECT key,source FROM jobs INDEXED BY job_frontier '
                                   'WHERE state=? AND claim IS NULL ORDER BY ordinal LIMIT ?',
                                   (before, limit)).fetchall()
            if not rows:
                return None
            nonce = uuid.uuid4().hex
            keys = [r[0] for r in rows]
            self.db.execute('INSERT INTO batches(id,phase,state,keys) VALUES(?,?,?,?)',
                            (nonce, phase, 'RUNNING', json.dumps(keys)))
            self.db.executemany('UPDATE jobs SET claim=? WHERE key=?', [(nonce, k) for k in keys])
            return dict(id=nonce, phase=phase,
                        records=[dict(key=k, source=json.loads(s)) for k, s in rows])
        return self._change(operation)

    def hold(self, batch, failure):
        receipt = pin(failure)
        def operation():
            changed = self.db.execute("UPDATE batches SET state='HELD',proof=? "
                                      "WHERE id=? AND state='RUNNING'", (receipt, batch)).rowcount
            if changed != 1:
                raise ValueError('RUNNING_BATCH_REQUIRED')
        self._change(operation)

    def finish(self, batch, result, *, recovered=False):
        receipt = pin(result)
        if type(recovered) is not bool:
            raise ValueError('EXPLICIT_RECOVERY_DISPOSITION')
        def operation():
            row = self.db.execute('SELECT phase,state,keys FROM batches WHERE id=?', (batch,)).fetchone()
            if row is None or row[1] != ('HELD' if recovered else 'RUNNING'):
                raise ValueError('EXACT_BATCH_DISPOSITION_REQUIRED')
            before, after = TRANSITIONS[row[0]]
            keys = json.loads(row[2])
            for key in keys:
                changed = self.db.execute('UPDATE jobs SET state=?,claim=NULL,proof=? '
                                          'WHERE key=? AND state=? AND claim=?',
                                          (after, receipt, key, before, batch)).rowcount
                if changed != 1:
                    raise ValueError('CLAIM_MEMBERSHIP_CHANGED')
            self.db.execute("UPDATE batches SET state='FINISHED',proof=?,recovered=? WHERE id=?",
                            (receipt, int(recovered), batch))
        self._change(operation)

    def counts(self):
        self._fence()
        return dict(self.db.execute('SELECT state,count(*) FROM jobs GROUP BY state'))

    def close(self):
        if self.owner['uncertain'] or self.owner['closeAttempted']:
            raise UnsettledBatch('CLOSE_ALREADY_ATTEMPTED_OR_UNCERTAIN')
        self.owner['closeAttempted'] = True
        try:
            self.db.close()
        except BaseException as error:
            self.owner['uncertain'] = True
            raise QueueOwnershipUnknown(self.owner, error) from error
