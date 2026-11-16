"""Exercise Git activation, stop conditions and recovery in disposable repositories."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("local_activation", HERE / "scripts/local_activation.py")
activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activation)


class LocalActivationTests(unittest.TestCase):
    def setUp(self):
        temp_root = HERE.parents[2] / ".local/activation-tests"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="Unicode caf\u00e9 ", dir=temp_root)
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to(temp_root.resolve()))
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()
        self.repo = self.folder / "repo"; self.repo.mkdir()
        self.packet = self.folder / "packet"
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_OPTIONAL_LOCKS="0")
        patch = mock.patch.dict(os.environ, env, clear=True); patch.start(); self.addCleanup(patch.stop)
        template = self.folder / "empty-template"; template.mkdir()
        self.git("init", "-q", "--template", str(template), "-b", "main")
        self.git("config", "user.name", "Fixture"); self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "commit.gpgsign", "false"); self.git("config", "core.autocrlf", "false")
        self.write(".gitignore", b".local/\n")
        self.write("README.md", b"catalog\n")
        self.write("unrelated.txt", b"original\n")
        self.write("docs/use_cases/UC-001.md", b"**Status:** Approved\n")
        self.write(".aiup/workflow/UC-001.json", b'{"outcome":"wip"}\n')
        self.commit("baseline"); self.base = self.git("rev-parse", "HEAD").stdout.decode().strip()
        self.git("tag", "retained-tag")
        self.write("README.md", b"catalog\n36 skills\n")
        self.write("incoming.txt", b"incoming content\n")
        self.commit("workflow target"); self.target = self.git("rev-parse", "HEAD").stdout.decode().strip()
        self.git("switch", "--detach", self.base); self.git("switch", "main"); self.git("reset", "--hard", self.base)
        self.branch = "codex/activate"

    def git(self, *args, check=True):
        r = subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, timeout=15)
        if check:
            self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", errors="replace"))
        return r

    def write(self, name, data):
        path = self.repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)

    def commit(self, message):
        self.git("add", "-A"); self.git("commit", "-qm", message)

    def prepare(self):
        return activation.prepare(self.repo, self.target, self.branch, self.packet)

    def switch(self):
        self.git("switch", "-c", self.branch, self.target)

    def clean_index(self, *paths, head=None, check=True):
        # Execute the actual runbook snippet; do not maintain a second remedy.
        source = (HERE / "references/local-activation.md").read_text(encoding="utf-8")
        script = self.folder / "clean-index.py"
        script.write_text(source.split("```python\n", 1)[1].split("\n```", 1)[0], encoding="utf-8")
        result = subprocess.run([os.sys.executable, "-X", "utf8", "-B", str(script),
                                 head or self.base, *paths], cwd=self.repo,
                                capture_output=True, timeout=15)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout.decode() + result.stderr.decode())
        return result

    def test_clean_activation_keeps_old_refs_and_other_worktree(self):
        other = self.folder / "other"
        self.git("worktree", "add", "--detach", str(other), self.base)
        plan = self.prepare()
        self.assertEqual(plan["overlaps"], [])
        activation.verify(self.packet, "before"); self.switch()
        result = activation.verify(self.packet, "after")
        self.assertEqual(result["pending"], 0)
        self.assertEqual(self.git("rev-parse", "main").stdout.decode().strip(), self.base)
        self.assertTrue((other / "unrelated.txt").is_file())

    def test_nonoverlapping_dirty_deleted_untracked_and_receipt_bytes_survive(self):
        self.write("unrelated.txt", b"user \xff bytes\r\n")
        (self.repo / "docs/use_cases/UC-001.md").unlink()
        self.write("private.txt", b"untracked \x00 bytes")
        self.write(".aiup/workflow/UC-001.json", b'{"outcome":"wip","local":true}\r\n')
        self.prepare(); activation.verify(self.packet, "before"); self.switch()
        self.assertEqual(activation.verify(self.packet, "after")["pending"], 4)

    def test_overlap_requires_explicit_retained_preview_and_clean_entry_refresh(self):
        original = b"catalog\r\nuser note caf\xc3\xa9\r\n"
        self.write("README.md", original)
        unrelated = b"unrelated user \xff bytes\r\n"
        self.write("unrelated.txt", unrelated)
        self.write("private.txt", b"untracked \x00 bytes")
        receipt = b'{"outcome":"wip","local":true}\r\n'
        self.write(".aiup/workflow/UC-001.json", receipt)
        plan = self.prepare(); self.assertEqual(plan["overlaps"], ["README.md"])
        preview = self.packet / "README.preview"
        preview.write_bytes(b"catalog\r\n36 skills\r\nuser note caf\xc3\xa9\r\n")
        activation.verify(self.packet, "before")
        self.git("restore", "--worktree", "--", "README.md")
        # Reproduce an index refresh failure with an unrelated dirty path.
        os.utime(self.repo / "README.md", (1_000_000_000, 1_000_000_000))
        self.assertEqual(self.git("hash-object", "--path=README.md", "README.md").stdout,
                         self.git("rev-parse", "HEAD:README.md").stdout)
        entries = self.git("ls-files", "--stage", "-z").stdout
        old = self.git("update-index", "--refresh", "--", "README.md", check=False)
        self.assertNotEqual(old.returncode, 0)
        self.assertIn(b"unrelated.txt: needs update", old.stdout)
        self.assertEqual(self.git("ls-files", "--stage", "-z").stdout, entries)
        self.clean_index("README.md")
        self.assertEqual(self.git("ls-files", "--stage", "-z").stdout, entries)
        self.assertEqual(self.git("diff", "--cached", "--quiet").returncode, 0)
        self.switch(); shutil.copyfile(preview, self.repo / "README.md")
        with self.assertRaisesRegex(ValueError, "bytes differ"):
            activation.verify(self.packet, "after")
        approval = {"README.md": (preview, activation.digest(preview))}
        result = activation.verify(self.packet, "after", approval)
        self.assertEqual(result["reconciled"], ["README.md"])
        self.assertEqual((self.packet / "files/README.md").read_bytes(), original)
        self.assertEqual((self.repo / "unrelated.txt").read_bytes(), unrelated)
        self.assertEqual((self.repo / ".aiup/workflow/UC-001.json").read_bytes(), receipt)
        self.assertEqual((self.repo / "private.txt").read_bytes(), b"untracked \x00 bytes")
        preview.write_bytes(b"replacement after review\n")
        with self.assertRaisesRegex(ValueError, "reviewed hash"):
            activation.verify(self.packet, "after", approval)

    def test_dirty_selected_path_refuses_before_any_index_update(self):
        for changed_after_plan in (False, True):
            with self.subTest(changed_after_plan=changed_after_plan):
                self.write("README.md", b"catalog\nlocal user note\n")
                self.packet = self.folder / ("after-plan" if changed_after_plan else "still-dirty")
                self.prepare()
                if changed_after_plan:
                    self.git("restore", "--worktree", "--", "README.md")
                    self.write("README.md", b"new writer after planning\n")
                index_path = self.repo / ".git/index"
                before = index_path.read_bytes()
                raw = (self.repo / "README.md").read_bytes()
                # Even with an earlier clean argument, guard all paths first.
                refused = self.clean_index("unrelated.txt", "README.md", check=False)
                self.assertEqual(refused.returncode, 2)
                self.assertIn("Selected path is dirty", json.loads(refused.stdout)["reason"])
                self.assertEqual(index_path.read_bytes(), before)
                self.assertEqual((self.repo / "README.md").read_bytes(), raw)
                self.assertEqual((self.packet / "files/README.md").read_bytes(), b"catalog\nlocal user note\n")
                self.assertEqual(self.git("rev-parse", "HEAD").stdout.strip().decode(), self.base)

    def test_clean_index_rejects_wrong_head_or_staged_work_without_mutation(self):
        index_path = self.repo / ".git/index"
        before = index_path.read_bytes()
        refused = self.clean_index("README.md", head=self.target, check=False)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("HEAD changed", json.loads(refused.stdout)["reason"])
        self.assertEqual(index_path.read_bytes(), before)
        self.write("unrelated.txt", b"staged user content\n")
        self.git("add", "--", "unrelated.txt")
        before = index_path.read_bytes()
        refused = self.clean_index("README.md", check=False)
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(index_path.read_bytes(), before)
        self.assertEqual((self.repo / "unrelated.txt").read_bytes(), b"staged user content\n")

    def test_crlf_checkout_lf_preview_continues_with_dirty_work_and_preserved_refs(self):
        self.git("switch", "--detach", self.target)
        preview_bytes = b"catalog\n36 skills\nuser note\n"
        self.write("README.md", preview_bytes); self.commit("target includes retained note")
        self.target = self.git("rev-parse", "HEAD").stdout.decode().strip()
        self.git("switch", "main"); self.git("config", "core.autocrlf", "true")
        # Force a fresh checkout; restore may keep an already-clean LF file.
        (self.repo / "README.md").unlink()
        self.git("restore", "--worktree", "--", "README.md")
        self.assertIn(b"\r\n", (self.repo / "README.md").read_bytes())
        self.write("README.md", preview_bytes)
        unrelated = b"private user bytes \xff\r\n"
        self.write("unrelated.txt", unrelated); self.write("private.txt", b"untracked\x00")
        receipt = b'{"outcome":"wip","local":true}\n'
        self.write(".aiup/workflow/UC-001.json", receipt)
        other = self.folder / "other"; self.git("worktree", "add", "--detach", str(other), self.base)
        plan = self.prepare(); self.assertEqual(plan["overlaps"], ["README.md"])
        preview = self.packet / "README.preview"; preview.write_bytes(preview_bytes)
        approval = {"README.md": (preview, activation.digest(preview))}
        activation.verify(self.packet, "before")
        self.git("restore", "--worktree", "--", "README.md"); self.clean_index("README.md")
        self.switch(); self.assertIn(b"\r\n", (self.repo / "README.md").read_bytes())
        shutil.copyfile(preview, self.repo / "README.md")
        self.clean_index("README.md", head=self.target)
        self.assertEqual(self.git("status", "--porcelain", "--", "README.md").stdout, b"")
        result = activation.verify(self.packet, "after", approval)
        self.assertEqual(result["reconciled"], ["README.md"])
        self.assertEqual((self.repo / "README.md").read_bytes(), preview_bytes)
        self.assertEqual((self.repo / "unrelated.txt").read_bytes(), unrelated)
        self.assertEqual((self.repo / "private.txt").read_bytes(), b"untracked\x00")
        self.assertEqual((self.repo / ".aiup/workflow/UC-001.json").read_bytes(), receipt)
        self.assertEqual((other / "README.md").read_bytes(), b"catalog\r\n")
        self.assertEqual(self.git("rev-parse", "main").stdout.strip().decode(), self.base)

    def test_new_path_collision_blocks_before_any_switch_or_backup(self):
        self.write("incoming.txt", b"private collision\n")
        with self.assertRaisesRegex(ValueError, "New-path collision"):
            self.prepare()
        self.assertFalse(self.packet.exists())
        self.assertEqual(self.git("rev-parse", "HEAD").stdout.decode().strip(), self.base)

    def test_ignored_new_path_collision_also_blocks(self):
        self.write(".git/info/exclude", b"incoming.txt\n")
        self.write("incoming.txt", b"ignored private content\n")
        with self.assertRaisesRegex(ValueError, "New-path collision"):
            self.prepare()
        self.assertEqual((self.repo / "incoming.txt").read_bytes(), b"ignored private content\n")
        self.assertFalse(self.packet.exists())

    def test_prepared_packet_detects_index_only_change(self):
        self.prepare()
        self.git("update-index", "--assume-unchanged", "unrelated.txt")
        with self.assertRaisesRegex(ValueError, "Special index flags"):
            activation.verify(self.packet, "before")

    def test_changed_input_after_plan_blocks_before_switch(self):
        self.write("unrelated.txt", b"first edit\n"); self.prepare()
        self.write("unrelated.txt", b"later edit\n")
        with self.assertRaisesRegex(ValueError, "Inputs changed"):
            activation.verify(self.packet, "before")
        self.assertEqual(self.git("branch", "--show-current").stdout.strip(), b"main")

    def test_failed_switch_restores_original_bytes_and_semantic_index(self):
        self.write("README.md", b"catalog\r\noriginal local edit\r\n")
        self.prepare(); activation.verify(self.packet, "before")
        self.git("restore", "--worktree", "--", "README.md")
        self.clean_index("README.md")
        # A collision appears after the check. Real Git must reject the switch.
        self.write("incoming.txt", b"new concurrent private content\n")
        failure = self.git("switch", "-c", self.branch, self.target, check=False)
        self.assertNotEqual(failure.returncode, 0)
        shutil.copyfile(self.packet / "files/README.md", self.repo / "README.md")
        with self.assertRaisesRegex(ValueError, "status change"):
            activation.verify(self.packet, "recovery")
        self.assertEqual((self.repo / "incoming.txt").read_bytes(), b"new concurrent private content\n")
        # Preserve the unexpected writer's content separately; do not delete it
        # as a routine rollback. Its explicit fixture owner then moves it aside.
        (self.repo / "incoming.txt").rename(self.folder / "concurrent-content.saved")
        result = activation.verify(self.packet, "recovery")
        self.assertEqual(result["head"], self.base)
        self.assertEqual((self.folder / "concurrent-content.saved").read_bytes(), b"new concurrent private content\n")

    def test_protected_target_change_and_reconciliation_are_blocked(self):
        self.write("docs/use_cases/UC-001.md", b"**Status:** Done\n"); self.commit("separate lifecycle change")
        self.target = self.git("rev-parse", "HEAD").stdout.decode().strip()
        self.git("reset", "--hard", self.base)
        with self.assertRaisesRegex(ValueError, "protected content"):
            self.prepare()

    def test_staged_changes_existing_branch_and_floating_target_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "40-character"):
            activation.prepare(self.repo, "HEAD", self.branch, self.packet)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self._existing_branch()
        self.write("unrelated.txt", b"staged edit"); self.git("add", "unrelated.txt")
        with self.assertRaisesRegex(ValueError, "Staged changes"):
            self.prepare()
        self.assertTrue(self.git("diff", "--cached", "--name-only").stdout)

    def _existing_branch(self):
        self.git("branch", "codex/existing")
        return activation.prepare(self.repo, self.target, "codex/existing", self.packet)

    def test_corrupted_backup_and_unrequested_ref_changes_are_not_accepted(self):
        self.write("unrelated.txt", b"local edit"); self.prepare()
        backup = self.packet / "files/unrelated.txt"; original = backup.read_bytes(); backup.write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "Backup changed"):
            activation.verify(self.packet, "before")
        backup.write_bytes(original); self.switch(); self.git("tag", "unrequested-tag")
        with self.assertRaisesRegex(ValueError, "Unexpected new ref"):
            activation.verify(self.packet, "after")

    def test_cli_emits_blocked_json_without_mutation(self):
        run = subprocess.run([os.sys.executable, "-B", str(HERE / "scripts/local_activation.py"),
                              "prepare", "--workspace", str(self.repo), "--target", "main",
                              "--branch", self.branch, "--packet", str(self.packet)], capture_output=True)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(json.loads(run.stdout)["result"], "blocked")
        self.assertFalse(self.packet.exists())


if __name__ == "__main__":
    unittest.main()
