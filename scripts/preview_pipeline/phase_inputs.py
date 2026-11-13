"""Read prior receipts for an exact active claim on the owned work queue.

The queue connection is borrowed and remains open. Only private bookkeeping is
read; receipt files, catalog files and media are not opened or authenticated.
"""
import json

from .work_queue import TRANSITIONS, UnsettledBatch, pin


def read_claim_inputs(queue, claim):
    if (type(claim) is not dict or set(claim) != {'id', 'phase', 'records'}
            or type(claim['id']) is not str or type(claim['phase']) is not str
            or claim['phase'] not in TRANSITIONS
            or type(claim['records']) is not list or not 1 <= len(claim['records']) <= 8):
        raise ValueError('EXACT_ACTIVE_PHASE_CLAIM_REQUIRED')
    if queue.owner['uncertain'] or queue.owner['closeAttempted']:
        raise UnsettledBatch('BORROWED_QUEUE_OWNER_UNSETTLED_OR_CLOSED')
    for record in claim['records']:
        if (type(record) is not dict or set(record) != {'key', 'source'}
                or type(record['key']) is not str):
            raise ValueError('EXACT_CLAIM_RECORD_REQUIRED')
    queue._fence()
    batch = queue.db.execute('SELECT phase,state,keys FROM batches WHERE id=?',
                             (claim['id'],)).fetchone()
    keys = [r['key'] for r in claim['records']]
    if (batch is None or batch[0] != claim['phase'] or batch[1] != 'RUNNING'
            or json.loads(batch[2]) != keys or len(set(keys)) != len(keys)):
        raise ValueError('ACTIVE_BATCH_MEMBERSHIP_REQUIRED')
    state = TRANSITIONS[claim['phase']][0]
    result = []
    for record in claim['records']:
        row = queue.db.execute('SELECT source,state,claim,proof FROM jobs WHERE key=?',
                               (record['key'],)).fetchone()
        if (row is None or json.loads(row[0]) != record['source']
                or row[1] != state or row[2] != claim['id']):
            raise ValueError('CLAIM_INPUT_BINDING_CHANGED')
        pin(record['source'])
        prior = None if row[3] is None else json.loads(row[3])
        if prior is not None:
            pin(prior)
        if claim['phase'] != 'render' and prior is None:
            raise ValueError('PRIOR_PHASE_RECEIPT_REQUIRED')
        result.append(dict(key=record['key'], source=record['source'], prior=prior))
    queue._fence()
    return result
