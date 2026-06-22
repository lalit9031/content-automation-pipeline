from __future__ import annotations

from pathlib import Path


def archive_and_purge_project(project_name: str, projects_root: str) -> None:
    """
    Safe local no-op for the MVP shadow runtime.

    The external compiler already does its main output work. We avoid touching
    restricted cleanup markers on the external drive during smoke tests.
    """
    root = Path(projects_root)
    project_dir = root / project_name
    print(f"🧹 Shadow janitor: skipping purge for {project_dir}")


def run_global_housekeeping_if_due(*args, **kwargs) -> None:
    """
    Safe local no-op for the MVP shadow runtime.
    """
    print("🧹 Shadow janitor: housekeeping skipped in shadow runtime.")
