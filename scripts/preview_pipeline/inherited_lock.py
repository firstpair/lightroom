"""Validate and exclusively lock one borrowed file description.

No open, close or unlock is performed. The parent must pass this description,
retain its own copy, and collect actual child settlement before closing it.
This does not exclude in-process native timers or prove parent ownership.
"""

import fcntl
import os
from pathlib import Path
import stat


def identity(value):
    return dict(device=value.st_dev, inode=value.st_ino, uid=value.st_uid,
                mode=value.st_mode, nlink=value.st_nlink)


def verify_exclusive(fd, path, expected):
    if type(fd) is not int or fd < 0:
        raise ValueError("BORROWED_DESCRIPTOR_REQUIRED")
    if type(expected) is not dict or set(expected) != {"device", "inode", "uid", "mode", "nlink"}:
        raise ValueError("EXACT_LOCK_IDENTITY_REQUIRED")
    if any(type(value) is not int for value in expected.values()):
        raise ValueError("INTEGER_LOCK_IDENTITY_REQUIRED")
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("ABSOLUTE_LOCK_PATH_REQUIRED")

    def check():
        held = os.fstat(fd)
        visible = path.lstat()
        if (not stat.S_ISREG(held.st_mode) or held.st_nlink != 1
                or identity(held) != expected or identity(visible) != expected):
            raise ValueError("HELD_VISIBLE_LOCK_IDENTITY_CHANGED")

    check()
    # A passed description shares its existing flock with the parent. This is
    # nonblocking and also refuses a separately opened competing description.
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    check()
    return dict(identity=dict(expected), exclusiveLockConfirmed=True,
                descriptorClosed=False, unlockCalled=False,
                parentOwnershipAndChildSettlementProven=False)
