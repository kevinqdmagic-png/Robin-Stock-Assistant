#!/usr/bin/env python3
"""Atomically publish linked append-only archives, preserving concurrent writers.

Only new records are merged. A changed/deleted historical record or conflicting
new ID aborts publication. Each push is a normal fast-forward with a fresh
parent, never a force push. Credentials remain in the checkout's git transport.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from research_archive import validate_document, verify_append_only
from task_center import validate_runs

PATHS = ("backend/data/research.json", "backend/data/task_runs.json")


def git(*args, cwd=ROOT, data=None, env=None):
    return subprocess.check_output(["git", *args], cwd=cwd, input=data,
                                   env=env, stderr=subprocess.PIPE)


def merge_append_only(base, proposed, current, kind):
    verify_append_only(base, proposed, kind)
    verify_append_only(base, current, kind)
    old = {r["id"]: r for r in base["items"]}
    online = {r["id"]: r for r in current["items"]}
    additions = []
    for row in proposed["items"]:
        if row["id"] in old:
            continue
        if row["id"] in online:
            if online[row["id"]] != row:
                raise ValueError("conflicting_new_record:" + row["id"])
        else:
            additions.append(row)
    # Never copy stale top-level metadata over another writer's metadata.
    merged = {**current, "items": [*current["items"], *additions]}
    verify_append_only(current, merged, kind)
    return merged


def check_links(reports, runs, new_receipt_ids):
    index = {r["id"]: r for r in reports["items"]}
    for row in runs["items"]:
        if row["id"] not in new_receipt_ids:
            continue
        for rid in row.get("report_ids", []):
            report = index.get(rid)
            if report is None or report.get("task_id") != row["task_id"] or report.get("date") != row["date"]:
                raise ValueError("receipt_report_link_invalid:" + row["id"])


def publish(base_sha, *, cwd=ROOT, remote="origin", branch="main", attempts=4):
    cwd = Path(cwd)
    base = {p: json.loads(git("show", base_sha + ":" + p, cwd=cwd)) for p in PATHS}
    proposed = {p: json.loads((cwd / p).read_text(encoding="utf-8")) for p in PATHS}
    for p, kind in zip(PATHS, ("research", "task_runs")):
        verify_append_only(base[p], proposed[p], kind)
    new_ids = {r["id"] for r in proposed[PATHS[1]]["items"]} - {r["id"] for r in base[PATHS[1]]["items"]}
    for attempt in range(1, attempts + 1):
        git("fetch", remote, branch, cwd=cwd)
        parent = git("rev-parse", "FETCH_HEAD", cwd=cwd).decode().strip()
        if subprocess.run(["git", "merge-base", "--is-ancestor", base_sha, parent], cwd=cwd).returncode:
            raise ValueError("publication_base_not_ancestor")
        current = {p: json.loads(git("show", parent + ":" + p, cwd=cwd)) for p in PATHS}
        merged = {p: merge_append_only(base[p], proposed[p], current[p], kind)
                  for p, kind in zip(PATHS, ("research", "task_runs"))}
        tasks = json.loads(git("show", parent + ":backend/data/tasks.json", cwd=cwd))
        validate_document(merged[PATHS[0]], "research")
        validate_runs(merged[PATHS[1]], tasks)
        check_links(merged[PATHS[0]], merged[PATHS[1]], new_ids)
        if merged == current:
            return {"published": True, "changed": False, "commit": parent, "attempts": attempt}
        # Construct a tree from the remote parent using a private index. Other
        # files in this checkout cannot accidentally enter the publication.
        with tempfile.TemporaryDirectory(prefix="robin-publish-") as tmp:
            env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
            git("read-tree", parent, cwd=cwd, env=env)
            for p in PATHS:
                content = (json.dumps(merged[p], ensure_ascii=False, indent=2) + "\n").encode()
                blob = git("hash-object", "-w", "--stdin", cwd=cwd, data=content).decode().strip()
                git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + p, cwd=cwd, env=env)
            tree = git("write-tree", cwd=cwd, env=env).decode().strip()
            commit = git("commit-tree", tree, "-p", parent, cwd=cwd,
                         data=b"research: atomically append linked research and receipts\n").decode().strip()
        pushed = subprocess.run(["git", "push", remote, commit + ":refs/heads/" + branch],
                                cwd=cwd, capture_output=True)
        if pushed.returncode == 0:
            return {"published": True, "changed": True, "commit": commit, "attempts": attempt}
        # A rejected fast-forward can simply mean another writer won. Refresh
        # and repeat the ID-aware merge. Auth/network failures stay bounded too.
    raise RuntimeError("atomic_publication_failed_after_bounded_retries")


def stage_bundle(bundle, *, cwd=ROOT):
    cwd = Path(cwd)
    staged = {}
    for path, key in zip(PATHS, ("research", "task_runs")):
        current = json.loads((cwd / path).read_text(encoding="utf-8"))
        proposed = {**current, "items": bundle[key]}
        staged[path] = merge_append_only({"items": []}, proposed, current,
                                         "research" if key == "research" else "task_runs")
    # Validate both documents and every bundle link before writing either file.
    tasks = json.loads((cwd / 'backend/data/tasks.json').read_text(encoding='utf-8'))
    validate_document(staged[PATHS[0]], 'research')
    validate_runs(staged[PATHS[1]], tasks)
    check_links(staged[PATHS[0]], staged[PATHS[1]], {r['id'] for r in bundle['task_runs']})
    for path, document in staged.items():
        (cwd / path).write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--result", default="linked-publication.json")
    parser.add_argument("--bundle", type=Path, help="JSON containing only new research and task_runs items")
    args = parser.parse_args()
    if args.bundle:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        stage_bundle(bundle)
    result = publish(args.base)
    Path(args.result).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
