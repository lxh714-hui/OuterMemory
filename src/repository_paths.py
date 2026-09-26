from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def repository_root(root=None):
    return Path(root).resolve() if root is not None else REPOSITORY_ROOT
