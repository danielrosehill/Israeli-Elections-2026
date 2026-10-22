"""Publish the three datasets under data/ to Hugging Face.

Run from the repo root:
    with-secrets uv run --with huggingface_hub python3 scripts/publish_hf.py [--private]

Repos are created public unless --private is passed. Each dataset card is
data/<folder>/README.md (HF YAML front matter + description); SOURCES.md and
the CSVs are uploaded alongside it.
"""

import argparse
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
DATASETS = {
    "knesset-25": "danielrosehill/Israel-Knesset-25-Members",
    "candidate-lists": "danielrosehill/Israel-Election-2026-Candidate-Lists",
    "polls": "danielrosehill/Israel-Election-2026-Polls",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private", action="store_true")
    parser.add_argument("only", nargs="*", help=f"subset of {list(DATASETS)}")
    args = parser.parse_args()
    unknown = set(args.only) - set(DATASETS)
    if unknown:
        parser.error(f"unknown dataset(s): {sorted(unknown)}")

    api = HfApi()
    for folder, repo_id in DATASETS.items():
        if args.only and folder not in args.only:
            continue
        src = ROOT / "data" / folder
        api.create_repo(repo_id, repo_type="dataset", private=args.private, exist_ok=True)
        api.upload_folder(
            repo_id=repo_id,
            repo_type="dataset",
            folder_path=src,
            allow_patterns=["*.csv", "README.md", "SOURCES.md"],
            ignore_patterns=["raw/*"],
            commit_message="Update dataset from Israeli-Elections-2026 repo",
        )
        print(f"{folder} -> https://huggingface.co/datasets/{repo_id}")


if __name__ == "__main__":
    main()
