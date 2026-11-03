"""Workspace path boundary. Every filesystem path derived from user or model input
must go through ``resolve_inside`` so there is exactly one implementation to audit.

Symlinks are resolved before the containment check, so a link pointing outside
the base directory is rejected. This protects the host directory layout; it is
not a sandbox against a malicious local user.
"""

from pathlib import Path


def resolve_inside(base: Path, relative: str | Path, message: str) -> Path:
    """Resolve ``relative`` under ``base`` and require the result to be strictly inside it.

    ``base`` must already be resolved. The base directory itself is rejected.
    """
    path = (base / relative).resolve()
    if base not in path.parents:
        raise ValueError(message)
    return path


def ensure_inside(path: Path, base: Path, message: str) -> None:
    """Require an already-resolved ``path`` to be strictly inside resolved ``base``."""
    if base not in path.parents:
        raise ValueError(message)


class Workspace:
    """The only directory the agent's file tools may read from or write to."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, relative: str) -> Path:
        return resolve_inside(self.root, relative, "Path must be a file inside workspace")

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.root))
