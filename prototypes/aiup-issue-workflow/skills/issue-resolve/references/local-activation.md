# Activate a pinned merge in an existing checkout

Use only with the caller's activation grant. This procedure does not publish, merge,
close an issue or renew lifecycle/phase evidence. It updates an existing checkout;
new-project setup is a separate operation.

The smallest reusable machinery is a backup/check helper, not an automatic Git
switcher. `../scripts/local_activation.py` uses Python 3's standard library and
Git. It writes a new private evidence directory, but never restores a working file,
refreshes/stages an index, switches, commits, fetches or changes refs. JSON `blocked`
and exit 2 mean stop. It cannot establish human consent or semantic preservation.

## 1. Pin and bound the work

- Verify the owning repository, requested endpoint, original workspace and a full
  40-character merged commit SHA against canonical remote/review evidence. Confirm
  the commit is available locally; any needed fetch requires the existing grant.
  Record intended tracking-ref changes separately, before the helper's snapshot.
- Choose a new `codex/` activation branch; retain all existing branches and other
  worktrees. Check applicable instructions in both source and target. Coordinate
  other writers: checks detect changed inputs at checkpoints, not concurrent writes
  atomically. Never infer absence of a writer from a passing check.
- Use the reviewed helper from a stable checkout, with its recorded source identity.
  For first activation, invoke its absolute path in the isolated reviewed worktree.
  Prepare from the original checkout; keep the packet outside tracked content,
  normally in an ignored `.local/activation-<id>/` directory which does not exist yet.
- The bounded implementation requires an empty staging area, a descendant target,
  ordinary files/index entries and a new branch. It stops for staged/unmerged work,
  special index flags, sparse checkouts, symlinks/submodules, custom Git workspace/index
  environment, non-descendant targets or incoming-path collisions with untracked
  or ignored private files. These
  need a separate preservation plan; never clear/stash/reset them to make it pass.

## 2. Capture a recoverable baseline

From the original root, substitute the verified helper, full SHA and branch:

```powershell
python -X utf8 -B <reviewed-helper> prepare --workspace . --target <full-SHA> --branch codex/<new-branch> --packet .local/activation-<id>
```

Require exit 0. `plan.json` binds the target, incoming paths, overlaps, HEAD/branch,
raw pending bytes/status, Git index bytes/entries, existing refs and worktrees.
`files/` contains verified raw copies (including binary/CRLF content and untracked
files), and `index.before` retains the index. Deletions are recorded as absent.
Record the helper and `plan.json` hashes beside the pinned target in the delivery
record outside the packet, and recheck them before subsequent steps. A packet is
caller-controlled evidence, not a signed authorization or an independent oracle.
Default protected content includes `.aiup`, UC/TC specifications, requirements and
open questions; `--protect <relative-path>` adds other lifecycle/evidence/pin paths.
Protected bytes are preserved, not semantically interpreted. The helper blocks a
target that changes those paths. A broader authorized artifact update needs its
owner's separate plan, not removal of protection to silence a mismatch.

This is not a global backup of ignored directories: incoming ignored-path collisions
are checked, and relevant ignored evidence should be named with `--protect`.
The packet is ignored/private, not fresh-clone evidence. Keep it until recovery and
preservation are established. No cleanup/deletion is part of activation.

## 3. Resolve overlaps before mutation

No overlap: retain all pending bytes exactly. Check incoming new-path collisions,
including file/directory ancestors, before switching.

Overlap: default to stopping. Prepare a separate text preview inside the packet
which visibly retains every existing local edit while incorporating the pinned
target's required change. Record the original, target and preview hashes, intended
scope and the human's exact approval (or an already applicable grant). Review the
actual preview, not just its hash. Never silently reconcile statuses, receipts or
protected content. Binary ambiguity or unresolved ownership means stop.

Approval binds that exact preview. `--reconciled PATH=SHA256=PREVIEW` only checks a supplied
retained file; it neither authorizes nor performs reconciliation. The helper cannot
prove the preview was approved, nor that it preserves the meaning of local edits.
Retain its reviewed identity and recheck it immediately before applying/verifying;
if it changed, do not treat the replacement as approved.

## 4. Recheck, then perform the authorized switch

```powershell
python -X utf8 -B <reviewed-helper> before --packet .local/activation-<id>
```

Require exit 0 immediately before intended mutations. A changed file, index, ref,
worktree or receipt after planning means stop and replan; do not overwrite the old
packet or recapture over changed work and call it approved.

For each approved overlap only, temporarily restore that path to old HEAD with
`git restore --worktree -- <exact-path>`. Its original raw bytes must already be
verified in the packet. Confirm `git hash-object --path=<path> <path>` equals
`git rev-parse HEAD:<path>`, and `git diff --cached --quiet` succeeds. Update only
those verified-clean entries with `git update-index -- <exact-path>`, requiring
unchanged semantic index entries and an empty staged diff afterward. Do not use
`--refresh`: it can check unrelated dirty entries and exit nonzero despite the
selected paths being clean. Plain per-path update can stage content, so its
clean-content guards are mandatory; it is never permission to stage a user edit.

Save this reviewed snippet as `clean-index.py` inside the private packet. From the
original root run `python -X utf8 -B <packet>/clean-index.py <expected-current-SHA>
<exact-path> ...`, substituting the pinned old HEAD before switching. It checks all
selected paths before updating any. Coordinate writers; these checks are not an
atomic lock against concurrent edits. A failed guard/native command or changed
index entry means stop and inspect/recover, never clear the index to silence it.

```python
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def require(ok, message):
    if not ok:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(
        ["git", "--literal-pathspecs", *args],
        env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"), stderr=subprocess.PIPE)


try:
    require(len(sys.argv) >= 3, "Supply expected HEAD and exact clean paths")
    expected, *paths = sys.argv[1:]
    require(re.fullmatch(r"[0-9a-f]{40}", expected), "Pin expected HEAD")
    require(not any(os.environ.get(n) for n in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")),
            "Custom Git environment requires a separate plan")
    root = Path.cwd().resolve()
    require(Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve() == root,
            "Run from the original repository root")
    require(git("rev-parse", "HEAD").decode().strip() == expected, "HEAD changed")
    git("diff", "--cached", "--quiet")
    entries = git("ls-files", "--stage", "-z")
    for name in paths:
        path = root / name
        require(not Path(name).is_absolute() and path.resolve().is_relative_to(root)
                and path.is_file() and not path.is_symlink(), "Invalid selected path")
        flags = git("ls-files", "-v", "-z", "--", name).split(b"\0")
        require(len(flags) == 2 and flags[0].startswith(b"H "), "Require one ordinary tracked path")
        require(git("hash-object", "--path=" + name, name).strip()
                == git("rev-parse", "HEAD:" + name).strip(), "Selected path is dirty: " + name)
    for name in paths:
        require(git("rev-parse", "HEAD").decode().strip() == expected, "HEAD changed")
        require(git("hash-object", "--path=" + name, name).strip()
                == git("rev-parse", "HEAD:" + name).strip(), "Selected path changed: " + name)
        git("update-index", "--", name)
        require(git("ls-files", "--stage", "-z") == entries, "Index entries changed; stop and inspect")
        git("diff", "--cached", "--quiet")
    print(json.dumps({"result": "verified", "paths": paths}))
except (ValueError, OSError, subprocess.CalledProcessError) as error:
    print(json.dumps({"result": "blocked", "reason": str(error)}))
    sys.exit(2)
```

If Git still rejects the switch, stop and recover. Do not force it.

Switch to the recorded target with `git switch -c <recorded-branch> <recorded-SHA>`.
Check every native command's exit code immediately; PowerShell does not stop on
native failure by default. On success, copy only each approved preview's verified
raw bytes to its exact overlapping path. Do not rewrite other files. If a restored
path is intended to be clean against the target (for example LF raw bytes restored
over a CRLF checkout), repeat the guarded snippet for only that path using the
pinned target SHA. Require its normalized blob to equal target HEAD and preserve
the restored raw bytes. Intentionally dirty previews remain pending; do not update
their entries. No other index mutation is part of this procedure.

## 5. Verify success or recover

```powershell
python -X utf8 -B <reviewed-helper> after --packet .local/activation-<id>
```

For a reconciled path add
`--reconciled <relative-path>=<reviewed-SHA256>=<absolute-preview-file>`.
Require exit 0 and inspect its result. It verifies target/branch, pending/protected
raw bytes, status, an empty staging area, old refs and other worktrees. Only the
requested new branch may be added; existing refs cannot move. Reconciled paths
may intentionally change raw bytes and Git status; distinguish them from exact-byte
preservation and retain approval/evidence. An unexplained mismatch is not success.

On a failed switch, inspect actual HEAD, branch, refs, index and status before any
retry; do not assume Git left everything untouched. If still on the original
HEAD/branch, restore only temporarily changed overlap paths from the verified raw
backups. Never blanket-restore, reset, stash, clean or blindly copy an old index
over concurrent work. Use `recovery --packet <packet>` to verify original bytes,
status and semantic index entries. A refreshed clean index's stat bytes may differ;
the original raw index remains retained. An unexpected writer's new file must be
preserved and reported; it is not rollback debris to delete. Stop for unresolved
conflicts, unexpected HEAD/ref changes or ambiguous recovery. Retain any branch Git
created at the pinned target. Prepare a new packet before an authorized retry.

Finally check the incoming reviewed identities and relevant read-only smoke checks,
then record repository delivery and original-checkout activation separately. No
passing helper result establishes application qualification or fresh phase evidence.

Offline regression command (disposable repositories; no network/application/model):

```text
python -X utf8 -B -m unittest discover -s skills/issue-resolve/tests -p test_local_activation.py -v
```
