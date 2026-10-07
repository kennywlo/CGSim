from pathlib import Path


def get_project_root() -> Path: # new feature in Python 3.x i.e. annotations
    """Returns project root folder."""
    return Path(__file__).parent.parent