"""Validate one finite, owner-pinned preview publication admission.

Pure validation only. The caller authenticates the document bytes, filesystem
namespace, prerequisite receipts and inherited resource descriptions. A passing
result never proves process settlement, grants a lock or authorizes a retry.
"""
import math

SCHEMA = 'ROOT_RELEASED_ONE_SAVED_PREVIEW_PUBLICATION_V1'
FIELDS = {'schema', 'runtime', 'normalClose', 'reservation', 'worker', 'workerSHA256',
          'selectedKeys', 'sourcePins', 'prerequisitePins', 'expiresUnix',
          'maximumKeys', 'nativeRenderCalls', 'originalPayloadReads',
          'preserveTenOriginals', 'automaticRetry', 'fullCatalogReleased'}


def validate(value, *, runtime, normal_close, reservation, worker, worker_sha256,
             selected_keys, source_pins, prerequisite_pins, now):
    """Bind the exact finite operation; return its already-validated expiry."""
    if type(value) is not dict or set(value) != FIELDS:
        raise ValueError('EXACT_PUBLICATION_ADMISSION_FIELDS')
    if value['schema'] != SCHEMA:
        raise ValueError('PUBLICATION_ADMISSION_SCHEMA')
    expected = {'runtime': str(runtime), 'normalClose': str(normal_close),
                'reservation': str(reservation), 'worker': str(worker),
                'workerSHA256': worker_sha256, 'selectedKeys': selected_keys,
                'sourcePins': source_pins, 'prerequisitePins': prerequisite_pins}
    for name, wanted in expected.items():
        if value[name] != wanted:
            raise ValueError('PUBLICATION_ADMISSION_BINDING_' + name)
    if (type(selected_keys) is not list or not 1 <= len(selected_keys) <= 8
            or any(type(key) is not list or len(key) != 2
                   or any(type(part) is not str or not part for part in key)
                   for key in selected_keys)
            or len({tuple(key) for key in selected_keys}) != len(selected_keys)):
        raise ValueError('FINITE_UNIQUE_PREVIEW_KEYS')
    if type(value['maximumKeys']) is not int or value['maximumKeys'] != len(selected_keys):
        raise ValueError('EXACT_PREVIEW_KEY_LIMIT')
    if (type(value['nativeRenderCalls']) is not int or value['nativeRenderCalls'] != 0
            or type(value['originalPayloadReads']) is not int
            or value['originalPayloadReads'] != 0
            or value['preserveTenOriginals'] is not True
            or value['automaticRetry'] is not False
            or value['fullCatalogReleased'] is not False):
        raise ValueError('FINITE_SAVED_PREVIEW_AUTHORITY')
    expiry = value['expiresUnix']
    if (type(now) not in (int, float) or not math.isfinite(now)
            or type(expiry) not in (int, float) or not math.isfinite(expiry)
            or not 0 < expiry - now <= 900):
        raise ValueError('FINITE_PUBLICATION_DEADLINE')
    return expiry
