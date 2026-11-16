"""Local activation evidence only: back up, check a plan, verify or recover.

Never switches, restores, stages, refreshes an index, fetches or changes refs.
Python standard library + Git; JSON output, nonzero on an unsafe/unsupported state.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


PROTECTED = (".aiup", "docs/use_cases", "docs/test_cases",
             "docs/requirements.md", "docs/open-questions.md")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(root, *args, check=True):
    result = subprocess.run(["git", "-C", str(root), *args],
                            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
                            capture_output=True, timeout=30)
    require(not check or result.returncode == 0,
            "Git failed: " + " ".join(args) + ": " + result.stderr.decode("utf-8", errors="replace"))
    return result


def text(root, *args):
    return git(root, *args).stdout.decode("utf-8").strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(root, name):
    path = root / name
    require(not Path(name).is_absolute() and path.resolve().is_relative_to(root),
            "Path escapes workspace: " + name)
    require(not any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)),
            "Symlink paths require a separate plan: " + name)
    return path


def status(root):
    entries = git(root, "status", "--porcelain=v1", "--untracked-files=all", "-z").stdout
    values = {}
    for entry in entries.decode("utf-8").split("\0"):
        if not entry:
            continue
        require("R" not in entry[:2] and "C" not in entry[:2],
                "Renames/copies require a separate plan")
        values[entry[3:]] = entry[:2]
    return values


def snapshot(root, protected):
    require(not any(os.environ.get(n) for n in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")),
            "Custom Git workspace/index environment requires a separate plan")
    require(text(root, "rev-parse", "--show-toplevel").replace("\\", "/") == root.as_posix(),
            "Workspace must be the repository root")
    require(not git(root, "diff", "--cached", "--quiet", check=False).returncode,
            "Staged changes require a separate plan; no index changes made")
    require(not text(root, "ls-files", "--unmerged"), "Unmerged entries require a separate plan")
    flags = git(root, "ls-files", "-v", "-z").stdout.decode("utf-8").split("\0")
    require(all(not entry or entry.startswith("H ") for entry in flags),
            "Special index flags/sparse checkouts require a separate plan")
    index_entries = git(root, "ls-files", "--stage", "-z").stdout.decode("utf-8")
    require(not any(x.startswith(("120000 ", "160000 ")) for x in index_entries.split("\0")),
            "Symlinks/submodules require a separate plan")
    pending = status(root)
    protected_files = set()
    for name in protected:
        path = inside(root, name)
        if path.is_dir():
            protected_files.update(p.relative_to(root).as_posix() for p in path.rglob("*")
                                   if p.is_file())
        if path.is_file():
            protected_files.add(name)
    hashes = {}
    for name in set(pending) | protected_files:
        path = inside(root, name)
        require(not path.exists() or path.is_file(), "Unsupported pending file: " + name)
        hashes[name] = digest(path) if path.is_file() else None
    index = Path(text(root, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    refs = {name: value.strip() for name, value in (line.split(" ", 1) for line in text(
        root, "for-each-ref", "--format=%(refname) %(objectname) %(symref)").splitlines())}
    worktrees = dict(block.split("\n", 1) for block in text(
        root, "worktree", "list", "--porcelain").split("\n\n"))
    return dict(head=text(root, "rev-parse", "HEAD"), branch=text(root, "branch", "--show-current"),
                pending=pending, hashes=hashes, protected=sorted(protected_files),
                index=digest(index), index_entries=index_entries, refs=refs, worktrees=worktrees)


def prepare(workspace, target, branch, packet, protect=()):
    root, packet = Path(workspace).resolve(), Path(packet).resolve()
    require(not any(os.environ.get(n) for n in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")),
            "Custom Git workspace/index environment requires a separate plan")
    require(re.fullmatch(r"[0-9a-f]{40}", target), "Pin a full 40-character commit SHA")
    require(text(root, "rev-parse", "--verify", target + "^{commit}") == target,
            "Target must be a commit")
    require(branch.startswith("codex/"), "Use a new codex/ activation branch")
    text(root, "check-ref-format", "--branch", branch)
    require(git(root, "show-ref", "--verify", "--quiet", "refs/heads/" + branch,
                check=False).returncode == 1, "Activation branch already exists")
    require(not git(root, "merge-base", "--is-ancestor", "HEAD", target, check=False).returncode,
            "Non-descendant target requires a separate plan")
    require(not packet.exists(), "Packet must be a new directory")
    if packet.is_relative_to(root):
        require(not packet.is_relative_to(Path(text(root, "rev-parse", "--absolute-git-dir"))),
                "Packet cannot be inside Git metadata")
        require(git(root, "check-ignore", "-q", str(packet), check=False).returncode == 0,
                "Packet inside the workspace must be ignored")
    protected = sorted(set(PROTECTED) | set(protect))
    before = snapshot(root, protected)
    incoming = [p for p in git(root, "diff", "--name-only", "-z", "HEAD", target).stdout.decode("utf-8").split("\0") if p]
    require(not any(n == p or n.startswith(p.rstrip("/") + "/") for n in incoming for p in protected),
            "Target changes protected content; stop for its owner's separate plan")
    fold = str.casefold if os.name == "nt" else str
    collisions = [p for p, state in before["pending"].items() if state == "??" and any(
        fold(p) == fold(n) or fold(p).startswith(fold(n) + "/") or fold(n).startswith(fold(p) + "/")
        for n in incoming)]
    tracked = set(git(root, "ls-files", "-z").stdout.decode("utf-8").split("\0"))
    for name in incoming:
        path = inside(root, name)
        if name not in tracked and (path.exists() or any(
                p.is_file() for p in path.parents if p.is_relative_to(root))):
            collisions.append(name)  # Includes ignored private files.
    require(not collisions, "New-path collision; stop without switching: " + ", ".join(collisions))
    for line in text(root, "ls-tree", "-r", "--format=%(objectmode)", target).splitlines():
        require(line not in ("120000", "160000"), "Target symlinks/submodules require a separate plan")
    packet.mkdir(parents=True)
    for name, value in before["hashes"].items():
        if value is not None:
            destination = packet / "files" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(inside(root, name), destination)
            require(digest(destination) == value, "Backup verification failed: " + name)
    index = Path(text(root, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    shutil.copyfile(index, packet / "index.before")
    require(digest(packet / "index.before") == before["index"], "Index backup changed")
    require(snapshot(root, protected) == before, "Inputs changed while backing up; do not use this packet")
    plan = dict(schema=1, workspace=str(root), target=target, branch=branch,
                protected=protected, before=before, incoming=incoming,
                overlaps=sorted(set(incoming) & set(before["pending"])))
    (packet / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return plan


def verify(packet, phase, reconciled=None):
    packet = Path(packet).resolve()
    plan = json.loads((packet / "plan.json").read_text(encoding="utf-8"))
    root, before = Path(plan["workspace"]), plan["before"]
    for name, value in before["hashes"].items():
        if value is not None:
            require(digest(packet / "files" / name) == value, "Backup changed: " + name)
    require(digest(packet / "index.before") == before["index"], "Index backup changed")
    now = snapshot(root, plan["protected"])
    if phase == "before":
        require(not reconciled and now == before, "Inputs changed after planning; stop and replan")
    else:
        require(phase in ("after", "recovery"), "Unknown verification phase")
        previews = reconciled or {}
        require(phase == "after" or not previews, "Recovery must restore original bytes")
        for name, (preview, approved_hash) in previews.items():
            require(name in plan["overlaps"] and name not in before["protected"],
                    "Reconciliation outside the approved overlap or in protected content: " + name)
            require(Path(preview).resolve().is_relative_to(packet) and Path(preview).is_file(),
                    "Retain the reviewed preview inside the packet")
            require(re.fullmatch(r"[0-9a-f]{64}", approved_hash) and digest(Path(preview)) == approved_hash,
                    "Preview differs from its explicitly supplied reviewed hash: " + name)
        expected = dict(before["hashes"])
        expected.update({name: value[1] for name, value in previews.items()})
        require(now["protected"] == before["protected"], "Protected file set changed")
        require(all((digest(inside(root, n)) if inside(root, n).is_file() else None) == h
                    for n, h in expected.items()),
                "Pending/protected bytes differ from original or explicitly supplied preview")
        require({n: s for n, s in now["pending"].items() if n not in previews} ==
                {n: s for n, s in before["pending"].items() if n not in previews},
                "Unexpected pending/staged status change")
        require(now["head"] == (plan["target"] if phase == "after" else before["head"]), "Unexpected HEAD")
        require(now["branch"] == (plan["branch"] if phase == "after" else before["branch"]), "Unexpected branch")
        require(all(now["refs"].get(n) == v for n, v in before["refs"].items()), "Existing ref changed")
        new_refs = {n: v for n, v in now["refs"].items() if n not in before["refs"]}
        allowed = {"refs/heads/" + plan["branch"]: plan["target"]}
        require(all(allowed.get(n) == v for n, v in new_refs.items()), "Unexpected new ref")
        own = "worktree " + root.as_posix()
        require({n: v for n, v in now["worktrees"].items() if n != own} ==
                {n: v for n, v in before["worktrees"].items() if n != own}, "Other worktree changed")
        if phase == "recovery":
            require(now["index_entries"] == before["index_entries"], "Index content changed during recovery")
    return dict(result="verified", phase=phase, head=now["head"], branch=now["branch"],
                pending=len(now["pending"]), index_raw_unchanged=now["index"] == before["index"],
                reconciled=sorted(reconciled or {}), authority="Caller must hold activation/preview approval; flags are not consent")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "before", "after", "recovery"))
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--branch")
    parser.add_argument("--protect", action="append", default=[])
    parser.add_argument("--reconciled", action="append", default=[], metavar="PATH=SHA256=PREVIEW")
    args = parser.parse_args()
    try:
        if args.phase == "prepare":
            require(args.workspace and args.target and args.branch and not args.reconciled,
                    "prepare requires workspace, target and branch; reconciliation is verified after explicit approval")
            plan = prepare(args.workspace, args.target, args.branch, args.packet, args.protect)
            result = dict(result="prepared", target=plan["target"], overlaps=plan["overlaps"], packet=str(args.packet))
        else:
            previews = {}
            for value in args.reconciled:
                name, approved_hash, preview = value.split("=", 2)
                require(name not in previews, "Duplicate reconciliation path: " + name)
                previews[name] = (preview, approved_hash)
            result = verify(args.packet, args.phase, previews)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps(dict(result="blocked", reason=str(error)), ensure_ascii=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
