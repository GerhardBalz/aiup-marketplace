"""Exercise complete candidate checks in a disposable Git repository.

The complete selected candidate is HEAD plus explicit working-tree paths in a
disposable GIT_INDEX_FILE: read-tree HEAD; add -- <paths>; diff --cached --check.
The real index, unrelated pending work and protected Markdown remain unchanged.
Run: python -B -m unittest discover -s skills/issue-resolve/tests -p test_candidate_scope.py -v
"""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SELECTED = (".agents/skills/new-skill/SKILL.md", "selected/tracked.txt")


class CompleteCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="git scope ")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.repo = self.directory / "repo"
        self.repo.mkdir()
        self.scratch = self.directory / "scratch"
        self.scratch.mkdir()
        template = self.scratch / "empty-template"
        template.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
        self.git("init", "--quiet", "--template", str(template))
        initial = {
            ".gitattributes": b".agents/** -text\n",
            ".agents/pinned/SKILL.md": b"\xef\xbb\xbf# Pinned\r\nIntentional hard break.  \r\nNext line.\r\n",
            "docs/UC-001.md": b"**Status:** Approved\n",
            ".aiup/workflow/UC-001.json": b'{"phase":"stale","evidence":"retained"}\n',
            "selected/tracked.txt": b"original selected content\n",
            "unrelated/staged.txt": b"original staged content\n",
            "unrelated/dirty.txt": b"original pending content\n",
        }
        for name, data in initial.items():
            self.write(name, data)
        self.git("add", "--", *initial)
        self.git("commit", "--quiet", "--no-gpg-sign", "-m", "fixture baseline")
        self.write("selected/tracked.txt", b"revised selected content\n")
        self.new_skill = b"---\nname: new-skill\ndescription: Reference fixture.\n---\n# New skill\n"
        self.write(SELECTED[0], self.new_skill + b"\n")
        self.write("unrelated/staged.txt", b"retained user staged edit\n\n")
        self.git("add", "--", "unrelated/staged.txt")
        self.write("unrelated/dirty.txt", b"retained user unstaged edit\n")
        self.write("unrelated/private.txt", b"retained untracked user content\n\n")
        self.fixture_paths = tuple(initial) + (SELECTED[0], "unrelated/private.txt")

    def git(self, *args, index=None, check=True):
        env = self.env.copy()
        if index is not None:
            env["GIT_INDEX_FILE"] = str(index)
        result = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-c", "core.quotepath=false",
             "-c", "core.hooksPath=" + str(self.scratch / "empty-hooks"),
             "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             "-c", "commit.gpgsign=false", *args],
            cwd=self.repo, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def write(self, name, data):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def snapshot(self):
        return {
            "index": hashlib.sha256((self.repo / ".git/index").read_bytes()).hexdigest(),
            "status": self.git("status", "--porcelain=v1", "--untracked-files=all").stdout,
            "refs": self.git("for-each-ref", "--format=%(refname) %(objectname)").stdout,
            "staged": self.git("diff", "--cached", "--binary").stdout,
            "contents": {name: (self.repo / name).read_bytes() for name in self.fixture_paths},
        }

    def complete_check(self):
        index = self.scratch / "candidate.index"
        self.assertFalse(index.exists())
        self.git("read-tree", "HEAD", index=index)
        self.git("add", "--", *SELECTED, index=index)
        paths = self.git("diff", "--cached", "--name-only", index=index).stdout.splitlines()
        self.assertEqual(sorted(paths), sorted(SELECTED))
        return self.git("diff", "--cached", "--check", index=index, check=False)

    def test_tracked_only_misses_new_eof_complete_candidate_detects_it(self):
        before = self.snapshot()
        self.git("diff", "--check")  # Tracked-only check misses the new skill.
        result = self.complete_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".agents/skills/new-skill/SKILL.md", result.stdout)
        self.assertIn("new blank line at EOF", result.stdout)
        self.assertNotIn("unrelated/", result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_selected_candidate_passes_after_eof_fix_without_touching_other_work(self):
        self.write(SELECTED[0], self.new_skill)
        before = self.snapshot()
        unrelated = self.git("diff", "--cached", "--check", check=False)
        self.assertNotEqual(unrelated.returncode, 0)
        self.assertIn("unrelated/staged.txt", unrelated.stdout)
        result = self.complete_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertIn(b"  \r\n", before["contents"][".agents/pinned/SKILL.md"])


if __name__ == "__main__":
    unittest.main()
