"""Resolve a single explicitly recorded workspace relocation.

This is a metadata path policy, not a file reader, lock or lifetime proof.
Callers must authenticate the supplied roots/identities, fence their reads and
retain ownership on uncertainty. Historical receipt strings are never changed.
"""

import os
from pathlib import Path
import stat


def identity(path):
    """Identity fields that do not change when children are added."""
    value = Path(path).lstat()
    return (value.st_dev, value.st_ino, value.st_uid, value.st_mode)


class RelocatedWorkspace:
    def __init__(self, old_root, new_root, old_link_identity, new_root_identity):
        self.old_root = self._absolute(old_root)
        self.new_root = self._absolute(new_root)
        if (self.old_root == self.new_root
                or self.old_root.is_relative_to(self.new_root)
                or self.new_root.is_relative_to(self.old_root)):
            raise ValueError("ROOTS_MUST_BE_DISJOINT")
        self.old_link_identity = tuple(old_link_identity)
        self.new_root_identity = tuple(new_root_identity)
        self.verify_roots()

    @staticmethod
    def _absolute(value):
        raw = os.fspath(value)
        path = Path(raw)
        if not path.is_absolute() or ".." in path.parts or str(path) != raw:
            raise ValueError("EXACT_ABSOLUTE_PATH_REQUIRED")
        return path

    def verify_roots(self):
        if identity(self.old_root) != self.old_link_identity:
            raise ValueError("OLD_LINK_IDENTITY_CHANGED")
        if not stat.S_ISLNK(self.old_link_identity[3]):
            raise ValueError("OLD_ROOT_MUST_BE_RECORDED_LINK")
        if os.readlink(self.old_root) != str(self.new_root):
            raise ValueError("OLD_LINK_TARGET_CHANGED")
        if identity(self.new_root) != self.new_root_identity:
            raise ValueError("NEW_ROOT_IDENTITY_CHANGED")
        if (not stat.S_ISDIR(self.new_root_identity[3])
                or self.new_root.resolve(strict=True) != self.new_root
                or self.old_root.resolve(strict=True) != self.new_root):
            raise ValueError("CANONICAL_RELOCATION_REQUIRED")

    def resolve(self, value):
        """Return a canonical descendant, rejecting every additional symlink."""
        self.verify_roots()
        path = self._absolute(value)
        if path.is_relative_to(self.old_root):
            candidate = self.new_root / path.relative_to(self.old_root)
        elif path.is_relative_to(self.new_root):
            candidate = path
        else:
            raise ValueError("OUTSIDE_RECORDED_WORKSPACE")
        if candidate == self.new_root:
            raise ValueError("DESCENDANT_REQUIRED")
        if candidate.resolve(strict=True) != candidate:
            raise ValueError("ADDITIONAL_SYMLINK_REFUSED")
        self.verify_roots()
        return candidate
