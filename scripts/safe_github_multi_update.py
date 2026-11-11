#!/usr/bin/env python3
"""Atomically append several evidence files to a GitHub branch.

Every existing target is checked against the blob SHA observed by the caller,
and archive targets are validated as append-only before a single Git tree and
commit are created. The branch ref update is never forced, so a concurrent
branch advance fails closed instead of losing either writer's work.
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from safe_github_update import request, validate_archive_change


ABSENT = "ABSENT"


def _contents_url(repo, path, branch):
    encoded = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
    return (f"https://api.github.com/repos/{repo}/contents/{encoded}?"
            + urllib.parse.urlencode({"ref": branch}))


def _read_existing(repo, path, branch, token):
    try:
        current = request("GET", _contents_url(repo, path, branch), token)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, None
        raise
    inline = current.get("content")
    if not inline:
        blob = request("GET", current["git_url"], token)
        if blob.get("encoding") != "base64" or not blob.get("content"):
            raise RuntimeError("TARGET_BLOB_UNREADABLE")
        inline = blob["content"]
    raw = base64.b64decode(inline.replace("\r", "").replace("\n", ""), validate=True)
    return current["sha"], raw


def safe_multi_update(repo, changes, token, branch="main", message="Safe atomic update"):
    """Publish ``[(path, bytes, expected_blob_sha), ...]`` as one commit."""
    if not changes:
        raise ValueError("no_changes")
    paths = [path for path, _proposed, _expected in changes]
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate_target_path")

    prepared = []
    for path, proposed, expected in changes:
        current_sha, old = _read_existing(repo, path, branch, token)
        if expected == ABSENT:
            if current_sha is not None:
                raise RuntimeError(f"CONCURRENT_FILE_CREATION:{path}")
        elif current_sha != expected:
            raise RuntimeError(f"CONCURRENT_FILE_CHANGE:{path}")
        if old is not None:
            validate_archive_change(path, old, proposed)
        prepared.append((path, proposed, old))

    ref_url = f"https://api.github.com/repos/{repo}/git/ref/heads/{urllib.parse.quote(branch, safe='')}"
    ref = request("GET", ref_url, token)
    parent_sha = ref["object"]["sha"]
    commit = request("GET", f"https://api.github.com/repos/{repo}/git/commits/{parent_sha}", token)
    tree_rows = []
    for path, proposed, old in prepared:
        if old == proposed:
            continue
        blob = request("POST", f"https://api.github.com/repos/{repo}/git/blobs", token, {
            "content": base64.b64encode(proposed).decode("ascii"), "encoding": "base64"})
        tree_rows.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    if not tree_rows:
        return {"commit_sha": parent_sha, "changed": False, "paths": []}
    tree = request("POST", f"https://api.github.com/repos/{repo}/git/trees", token, {
        "base_tree": commit["tree"]["sha"], "tree": tree_rows})
    created = request("POST", f"https://api.github.com/repos/{repo}/git/commits", token, {
        "message": message, "tree": tree["sha"], "parents": [parent_sha]})
    try:
        request("PATCH", ref_url, token, {"sha": created["sha"], "force": False})
    except urllib.error.HTTPError as error:
        if error.code in (409, 422):
            raise RuntimeError("BRANCH_CONFLICT: atomic commit was not published") from error
        raise
    return {"commit_sha": created["sha"], "changed": True,
            "paths": [row["path"] for row in tree_rows]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo")
    parser.add_argument("--file", action="append", nargs=3,
                        metavar=("PATH", "SOURCE", "BASE_SHA"), required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--message", default="Safe atomic evidence update")
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        parser.error("GITHUB_TOKEN is required")
    changes = [(path, Path(source).read_bytes(), base_sha)
               for path, source, base_sha in args.file]
    try:
        result = safe_multi_update(args.repo, changes, token, args.branch, args.message)
    except (RuntimeError, ValueError, urllib.error.HTTPError) as error:
        print(f"Safe atomic update stopped: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
