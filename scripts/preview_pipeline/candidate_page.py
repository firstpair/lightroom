"""Pure bounded planning-page selection, without runtime or completion authority.

The caller authenticates the sealed planning queue and completion evidence,
issues an indexed image-ID query, and freshly checks catalog/source metadata.
Every consumed row is returned, including exclusions and aliases; a cursor
never means those rows have been rendered or otherwise resolved.
"""
from collections.abc import Iterable


def select_page(rows: Iterable[dict], *, after_image_id: int,
                completed_keys: set[tuple[str, str]], batch_limit: int = 32,
                scan_limit: int = 512) -> dict:
    if type(after_image_id) is not int or after_image_id < 0:
        raise ValueError('nonnegative integer cursor required')
    if (type(batch_limit) is not int or type(scan_limit) is not int
            or not 1 <= batch_limit <= 32 or not batch_limit <= scan_limit <= 512):
        raise ValueError('bounded batch and scan limits required')
    if type(completed_keys) is not set or any(
            type(k) is not tuple or len(k) != 2
            or any(type(v) is not str or not v for v in k) for k in completed_keys):
        raise ValueError('explicit authenticated completion keys required')
    cursor = after_image_id
    observations, candidates, seen = [], [], set()
    iterator = iter(rows)
    exhausted = False
    while len(observations) < scan_limit and len(candidates) < batch_limit:
        try:
            row = next(iterator)
        except StopIteration:
            exhausted = True
            break
        if (type(row) is not dict or set(row) != {'image_id', 'key'}
                or type(row['image_id']) is not int or row['image_id'] <= cursor
                or type(row['key']) is not tuple or len(row['key']) != 2
                or any(type(v) is not str or not v for v in row['key'])):
            raise ValueError('strictly ordered unique image IDs and exact key pairs required')
        cursor = row['image_id']
        key = row['key']
        if key in completed_keys:
            state = 'EXCLUDED_COMPLETED_KEY'
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
