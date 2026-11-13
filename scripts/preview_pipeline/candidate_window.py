"""Bounded metadata selection; supplied coverage is authenticated by the caller.

Published keys awaiting recognition and reusable keys are excluded from render
selection without being relabelled as completed. No catalog or payload access,
cursor persistence, runtime admission or release authority is supplied here.
"""
from .candidate_page import select_page


def select_window(rows, *, after_image_id, completed_keys, published_keys,
                  reusable_keys, batch_limit=10000, scan_limit=65536):
    if (type(batch_limit) is not int or type(scan_limit) is not int
            or not 1 <= batch_limit <= 10000
            or not batch_limit <= scan_limit <= 65536):
        raise ValueError('bounded window limits required')
    # Reuse the existing exact key/cursor validation without consuming input.
    for keys in (completed_keys, published_keys, reusable_keys):
        select_page([], after_image_id=after_image_id, completed_keys=keys)
    if (completed_keys & published_keys or completed_keys & reusable_keys
            or published_keys & reusable_keys):
        raise ValueError('coverage states must be disjoint')
    classifications = {}
    for keys, state in (
            (completed_keys, 'EXCLUDED_COMPLETED_KEY'),
            (published_keys, 'PUBLISHED_RECOGNITION_PENDING'),
            (reusable_keys, 'EXCLUDED_AUTHENTICATED_REUSABLE_KEY')):
        classifications.update((key, state) for key in keys)
    cursor, observations, candidates, seen = after_image_id, [], [], set()
    iterator, exhausted = iter(rows), False
    while len(observations) < scan_limit and len(candidates) < batch_limit:
        try:
            row = next(iterator)
        except StopIteration:
            exhausted = True
            break
        # The original selector checks exact row shape and strict ordering.
        one = select_page([row], after_image_id=cursor, completed_keys=set(),
                          batch_limit=1, scan_limit=1)
        cursor = one['next_image_id']
        key = row['key']
        if key in classifications:
            state = classifications[key]
        elif key in seen:
            state = 'PENDING_DUPLICATE_KEY_ALIAS'
        else:
            state = 'NEEDS_FRESH_METADATA_AND_NATIVE_BINDING'
            candidates.append(dict(image_id=cursor, key=key))
        seen.add(key)
        observations.append(dict(image_id=cursor, key=key, state=state))
    return dict(candidates=candidates, observations=observations,
                next_image_id=cursor, input_exhausted=exhausted,
                runtime_authorized=False, full_catalog_complete=False)
