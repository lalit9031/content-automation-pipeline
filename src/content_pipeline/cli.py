from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from content_pipeline.config import Settings
from content_pipeline.pipeline import run_linkedin_mvp


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the daily content automation pipeline.")
    parser.add_argument("command", choices=["run"], help="Pipeline action to execute.")
    parser.add_argument("--date", default=date.today().isoformat(), help="Date in YYYY-MM-DD.")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory containing .env and output/.",
    )
    args = parser.parse_args()
    date.fromisoformat(args.date)
    settings = Settings.from_environment(args.project_dir.resolve())
    result = run_linkedin_mvp(args.date, settings)
    print(json.dumps(result, indent=2))
    return 0
