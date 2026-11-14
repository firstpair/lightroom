"""Validate a prepared stage binding, never a runtime admission.

The caller authenticates file contents and the native proof separately. This
pure check binds one eight-record claim to the exact build/source dependencies;
all execution and resource-acquisition flags must remain false.
"""
import json

from .work_queue import pin


SCHEMA = 'PREPARED_CONTINUOUS_EIGHT_SAVED_NATIVE_STAGE_CONTEXT_V1'
FIELDS = {'schema', 'claim', 'inputs', 'priorNative', 'nativeDocument', 'checkpoint',
          'build', 'sources', 'selectedEngine', 'selectedExecutable',
          'pairs', 'sourceCohortJobs', 'engineStageJobs',
          'stageWorkers', 'configuredPhotoCPUIndexes', 'EXglobalRequired',
          'nativeInvocationsPlanned', 'originalPhotoPayloadReadsPlanned',
          'readbackEncodedCopiesPlanned', 'executionReleased', 'runtimeGrantAcquired'}


def same(a, b):
    return json.dumps(a, sort_keys=True, separators=(',', ':'), allow_nan=False) == \
        json.dumps(b, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate(value, *, claim, expected_build, expected_sources, expected_cpu_indexes,
             expected_engine, expected_executable):
    if type(value) is not dict or set(value) != FIELDS or value['schema'] != SCHEMA:
        raise ValueError('EXACT_PREPARED_STAGE_CONTEXT_REQUIRED')
    if (type(claim) is not dict or set(claim) != {'id', 'phase', 'records'}
            or type(claim['id']) is not str or not claim['id']
            or claim['phase'] != 'stage' or type(claim['records']) is not list
            or len(claim['records']) != 8 or not same(value['claim'], claim)):
        raise ValueError('EXACT_EIGHT_STAGE_CLAIM_REQUIRED')
    keys = []
    for record in claim['records']:
        if (type(record) is not dict or set(record) != {'key', 'source'}
                or type(record['key']) is not str or not record['key']):
            raise ValueError('EXACT_STAGE_RECORD_REQUIRED')
        keys.append(record['key'])
        pin(record['source'])
    if len(set(keys)) != 8:
        raise ValueError('DISTINCT_STAGE_RECORDS_REQUIRED')
    for name in ('priorNative', 'nativeDocument', 'checkpoint', 'build'):
        pin(value[name])
    pin(expected_build)
    if not same(value['build'], expected_build):
        raise ValueError('EXACT_STAGE_BUILD_REQUIRED')
    pin(expected_executable)
    pin(value['selectedExecutable'])
    if (expected_engine not in ('Rust', 'Ox') or value['selectedEngine'] != expected_engine
            or not same(value['selectedExecutable'], expected_executable)):
        raise ValueError('ONE_EXACT_QUALIFIED_STAGE_ENGINE_REQUIRED')
    if (type(expected_sources) is not list or not expected_sources
            or not same(value['sources'], expected_sources)):
        raise ValueError('EXACT_STAGE_DEPENDENCIES_REQUIRED')
    for source in expected_sources:
        pin(source)
    if len({s['path'] for s in expected_sources}) != len(expected_sources):
        raise ValueError('DISTINCT_STAGE_DEPENDENCIES_REQUIRED')
    if (type(value['inputs']) is not list or len(value['inputs']) != 8
            or any(not same(v, dict(r, prior=value['priorNative']))
                   for v, r in zip(value['inputs'], claim['records']))):
        raise ValueError('ONE_NATIVE_RECEIPT_FOR_EXACT_STAGE_RECORDS')
    for name, expected in (('sourceCohortJobs', 8), ('engineStageJobs', 2),
                           ('stageWorkers', 6), ('nativeInvocationsPlanned', 0),
                           ('originalPhotoPayloadReadsPlanned', 0),
                           ('readbackEncodedCopiesPlanned', 32)):
        if type(value[name]) is not int or value[name] != expected:
            raise ValueError('QUALIFIED_STAGE_COUNTS_REQUIRED')
    if not same(value['pairs'], [[1, 2], [3, 4], [5, 6], [7, 8]]):
        raise ValueError('EXACT_STAGE_PAIR_ORDER_REQUIRED')
    if (type(expected_cpu_indexes) is not list or len(expected_cpu_indexes) != 8
            or any(type(i) is not int or not 0 <= i < 64 for i in expected_cpu_indexes)
            or expected_cpu_indexes != sorted(set(expected_cpu_indexes))
            or not same(value['configuredPhotoCPUIndexes'], expected_cpu_indexes)):
        raise ValueError('EXACT_EXPECTED_EIGHT_CPU_INDEXES_REQUIRED')
    if (value['EXglobalRequired'] is not True or value['executionReleased'] is not False
            or value['runtimeGrantAcquired'] is not False):
        raise ValueError('PREPARATION_CANNOT_CLAIM_EXECUTION_OR_GRANTS')
    return dict(prepared=True, records=8, nativeInvocations=0,
                executionAuthorized=False, resourceReleaseAuthorized=False)
