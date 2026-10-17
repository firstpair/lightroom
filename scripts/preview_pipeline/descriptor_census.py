"""Bounded projection of a complete ``lsof -Fpcftn`` byte stream.

Every field is parsed, including names outside the protected roots. Only
protected descriptors and one real name witness need remain in memory. This
does not run lsof, authenticate its output, prove process settlement, resolve
paths, acquire locks, or authorize publication. The caller supplies EOF only
after its owned capture is complete and separately authenticates that capture.
"""
from dataclasses import dataclass
import hashlib
from pathlib import PurePosixPath


@dataclass(frozen=True)
class Descriptor:
    pid: int
    descriptor: str
    kind: str | None
    name: str


@dataclass(frozen=True)
class Census:
    process_ids: tuple[int, ...]
    named_count: int
    protected: tuple[Descriptor, ...]
    name_witness: Descriptor
    input_bytes: int
    input_sha256: str

    def legacy_fields(self, maximum_bytes=16 * 1024 * 1024):
        """Preserve legacy PID/name guards without synthesizing a name.

        All observed PIDs remain present. Protected records retain their exact
        field values; when none exist, one actual unrelated descriptor supplies
        the legacy nonempty-listing witness. Counts belong to this Census,
        rather than to the smaller projected listing.
        """
        _bound(maximum_bytes, 256 * 1024 * 1024)
        selected = self.protected or (self.name_witness,)
        by_pid = {}
        for record in selected:
            by_pid.setdefault(record.pid, []).append(record)
        result = bytearray()
        for pid in self.process_ids:
            fields = [f'p{pid}\n']
            for record in by_pid.get(pid, ()):
                fields.append('f' + record.descriptor + '\n')
                if record.kind is not None:
                    fields.append('t' + record.kind + '\n')
                fields.append('n' + record.name + '\n')
            block = ''.join(fields).encode('utf-8')
            if len(result) + len(block) > maximum_bytes:
                raise ValueError('PROJECTED_CENSUS_OUTPUT_BOUND')
            result.extend(block)
        return bytes(result)


def _bound(value, ceiling):
    if type(value) is not int or not 1 <= value <= ceiling:
        raise ValueError('POSITIVE_BOUNDED_INTEGER_REQUIRED')


def parse(chunks, protected_roots, *, maximum_bytes=256 * 1024 * 1024,
          maximum_line_bytes=1024 * 1024, maximum_fields=2_000_000,
          maximum_processes=65536, maximum_matches=65536):
    """Consume a complete stream; refuse malformed, truncated or excess input."""
    for value, ceiling in ((maximum_bytes, 1024**3),
                           (maximum_line_bytes, 1024 * 1024),
                           (maximum_fields, 2_000_000),
                           (maximum_processes, 65536),
                           (maximum_matches, 65536)):
        _bound(value, ceiling)
    if type(protected_roots) is not tuple or not 1 <= len(protected_roots) <= 32:
        raise ValueError('EXPLICIT_PROTECTED_ROOTS_REQUIRED')
    for root in protected_roots:
        if (type(root) is not str or not root.startswith('/') or root == '/'
                or str(PurePosixPath(root)) != root or '..' in PurePosixPath(root).parts
                or any(ord(c) < 32 for c in root)):
            raise ValueError('EXACT_LITERAL_PROTECTED_ROOT_REQUIRED')
    if len(set(protected_roots)) != len(protected_roots):
        raise ValueError('DUPLICATE_PROTECTED_ROOT')
    digest = hashlib.sha256()
    pending = bytearray()
    total = fields = named = 0
    pid = descriptor = kind = witness = None
    processes, seen, protected = [], set(), []

    def line(raw):
        nonlocal fields, pid, descriptor, kind, named, witness
        fields += 1
        if fields > maximum_fields:
            raise ValueError('CENSUS_FIELD_BOUND')
        if not raw or len(raw) > maximum_line_bytes:
            raise ValueError('CENSUS_EMPTY_OR_LONG_FIELD')
        text = raw.decode('utf-8', 'strict')
        if any(ord(c) < 32 for c in text):
            raise ValueError('CENSUS_CONTROL_CHARACTER')
        field, value = text[0], text[1:]
        if field == 'p':
            if not value.isascii() or not value.isdecimal() or int(value) <= 0:
                raise ValueError('CENSUS_PID')
            pid, descriptor, kind = int(value), None, None
            if pid not in seen:
                if len(processes) >= maximum_processes:
                    raise ValueError('CENSUS_PROCESS_BOUND')
                seen.add(pid)
                processes.append(pid)
        elif field == 'c':
            if pid is None or not value:
                raise ValueError('CENSUS_COMMAND_CONTEXT')
        elif field == 'f':
            if pid is None or not value:
                raise ValueError('CENSUS_DESCRIPTOR_CONTEXT')
            descriptor, kind = value, None
        elif field == 't':
            if pid is None or descriptor is None or not value:
                raise ValueError('CENSUS_TYPE_CONTEXT')
            kind = value
        elif field == 'n':
            if pid is None or descriptor is None:
                raise ValueError('CENSUS_NAME_CONTEXT')
            if not value:
                if kind not in ('NPOLICY', 'NEXUS', 'PIPE'):
                    raise ValueError('CENSUS_UNNAMED_TYPE')
                return
            named += 1
            record = Descriptor(pid, descriptor, kind, value)
            if witness is None:
                witness = record
            if any(value == root or value.startswith(root + '/')
                   for root in protected_roots):
                if len(protected) >= maximum_matches:
                    raise ValueError('CENSUS_MATCH_BOUND')
                protected.append(record)
        else:
            raise ValueError('UNREQUESTED_CENSUS_FIELD')

    for chunk in chunks:
        if type(chunk) is not bytes or not chunk or len(chunk) > 1024 * 1024:
            raise ValueError('BOUNDED_NONEMPTY_BYTE_CHUNK_REQUIRED')
        total += len(chunk)
        if total > maximum_bytes:
            raise ValueError('CENSUS_INPUT_BOUND')
        digest.update(chunk)
        pending.extend(chunk)
        start = 0
        while True:
            end = pending.find(b'\n', start)
            if end < 0:
                break
            line(bytes(pending[start:end]))
            start = end + 1
        if start:
            del pending[:start]
        if len(pending) > maximum_line_bytes:
            raise ValueError('CENSUS_LINE_BOUND')
    if pending:
        raise ValueError('CENSUS_TRUNCATED_FINAL_FIELD')
    if not processes or witness is None:
        raise ValueError('CENSUS_EMPTY_OR_UNNAMED_LISTING')
    return Census(tuple(processes), named, tuple(protected), witness,
                  total, digest.hexdigest())
