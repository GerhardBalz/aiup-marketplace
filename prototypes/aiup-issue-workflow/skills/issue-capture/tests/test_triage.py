"""Fake-tracker behavior only. No network, model, application or tracker-write calls."""

import copy
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("work_item_triage", SKILL / "scripts" / "triage.py")
triage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(triage)
REFERENCE = json.loads((SKILL / "tests" / "reference_packet.json").read_text(encoding="utf-8"))
OWNER = REFERENCE["repository"]


class CaptureAndTriageTest(unittest.TestCase):
    def setUp(self):
        self.packet = copy.deepcopy(REFERENCE)

    def prepare(self):
        return triage.triage(self.packet, OWNER)

    def make_new(self):
        self.packet["finding"]["title"] = "A separately observed manual-test finding"
        self.packet["duplicate_check"]["items"][0].update(
            disposition="related", rationale="Related test tooling, but this observation has a different outcome.")

    def test_existing_open_issue_retains_canonical_identity_and_does_not_draft(self):
        result = self.prepare()
        self.assertEqual("existing", result["outcome"])
        self.assertEqual({"repository": OWNER, "number": 3, "state": "open",
                          "url": f"https://github.com/{OWNER}/issues/3"}, result["canonical_issue"])
        self.assertIsNone(result["new_issue"])
        self.assertFalse(result["tracker_write_performed"])
        self.assertFalse(result["implementation_authorized"])

    def test_closed_duplicate_is_preserved_without_reopening_or_drafting(self):
        self.packet["duplicate_check"]["items"][0]["state"] = "closed"
        result = self.prepare()
        self.assertEqual("existing", result["outcome"])
        self.assertEqual("closed", result["canonical_issue"]["state"])
        self.assertIsNone(result["new_issue"])
        self.assertFalse(result["tracker_write_performed"])

    def test_related_issue_allows_distinct_draft_with_evidence_and_links(self):
        self.make_new()
        result = self.prepare()
        self.assertEqual("draft", result["outcome"])
        self.assertEqual([3, 4], [item["number"] for item in result["related_issues"]])
        for value in (self.packet["finding"]["evidence"][0],
                      self.packet["finding"]["priority_rationale"],
                      self.packet["finding"]["completion_criteria"][0],
                      self.packet["finding"]["links"][0]):
            self.assertIn(value, result["new_issue"]["body"])
        self.assertEqual("offline/simulated", result["context"])
        self.assertFalse(result["tracker_write_performed"])

    def test_empty_complete_fake_tracker_allows_draft(self):
        self.packet["duplicate_check"]["items"] = []
        self.assertEqual("draft", self.prepare()["outcome"])

    def test_wrong_finding_or_search_repository_blocks_draft(self):
        for key in ("finding", "search"):
            with self.subTest(key=key):
                self.packet = copy.deepcopy(REFERENCE)
                target = self.packet if key == "finding" else self.packet["duplicate_check"]
                target["repository"] = "OtherOwner/other-project"
                with self.assertRaisesRegex(ValueError, "owning checkout"):
                    self.prepare()

    def test_repository_names_compare_without_case_sensitivity(self):
        self.packet["repository"] = OWNER.lower()
        self.assertEqual(OWNER, self.prepare()["canonical_issue"]["repository"])

    def test_open_only_closed_only_or_partial_search_blocks_draft(self):
        for states, complete in ((["open"], True), (["closed"], True),
                                 (["open", "closed"], False), (["open", "closed"], "true")):
            with self.subTest(states=states, complete=complete):
                self.packet["duplicate_check"].update(states=states, complete=complete)
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_unresolved_candidate_blocks_creation(self):
        self.packet["duplicate_check"]["items"][0]["disposition"] = "unresolved"
        result = self.prepare()
        self.assertEqual("needs_review", result["outcome"])
        self.assertEqual(3, result["candidates"][0]["number"])
        self.assertIsNone(result["new_issue"])

    def test_multiple_duplicates_require_canonical_review(self):
        self.packet["duplicate_check"]["items"][1]["disposition"] = "duplicate"
        result = self.prepare()
        self.assertEqual("needs_review", result["outcome"])
        self.assertIsNone(result["canonical_issue"])
        self.assertIsNone(result["new_issue"])

    def test_required_finding_fields_cannot_be_omitted(self):
        for field in REFERENCE["finding"]:
            with self.subTest(field=field):
                self.packet = copy.deepcopy(REFERENCE)
                del self.packet["finding"][field]
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_evidence_impact_priority_rationale_and_criteria_cannot_be_empty(self):
        for field, empty in (("title", " "), ("evidence", []), ("impact", ""),
                             ("priority_rationale", ""), ("completion_criteria", [])):
            with self.subTest(field=field):
                self.packet = copy.deepcopy(REFERENCE)
                self.packet["finding"][field] = empty
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_hypotheses_stay_explicit_and_do_not_replace_observations(self):
        self.make_new()
        self.packet["finding"]["unconfirmed_causes"] = ["A loader mismatch is suspected; unconfirmed."]
        result = self.prepare()
        self.assertIn("unconfirmed", result["new_issue"]["body"])
        self.assertEqual(REFERENCE["finding"]["evidence"], result["capture"]["evidence"])

    def test_invalid_priority_candidate_and_duplicate_numbers_are_rejected(self):
        self.packet["finding"]["priority"] = "Critical"
        with self.assertRaises(ValueError):
            self.prepare()
        self.packet = copy.deepcopy(REFERENCE)
        self.packet["duplicate_check"]["items"][0]["number"] = True
        with self.assertRaises(ValueError):
            self.prepare()
        self.packet = copy.deepcopy(REFERENCE)
        self.packet["duplicate_check"]["items"].append(copy.deepcopy(self.packet["duplicate_check"]["items"][0]))
        with self.assertRaises(ValueError):
            self.prepare()

    def test_packet_cannot_authorize_publication_execution_or_agent_dispatch(self):
        for flag in ("publish", "authorization", "execute", "dispatch_agents"):
            with self.subTest(flag=flag):
                self.packet = copy.deepcopy(REFERENCE)
                self.packet[flag] = True
                with self.assertRaises(ValueError):
                    self.prepare()

    def test_triage_does_not_modify_the_supplied_tracker_snapshot(self):
        before = copy.deepcopy(self.packet)
        self.prepare()
        self.assertEqual(before, self.packet)

    def test_supported_git_remotes_bind_the_actual_repository(self):
        for remote in (f"git@github.com:{OWNER}.git", f"https://github.com/{OWNER}.git",
                       f"ssh://git@github.com/{OWNER}.git"):
            with self.subTest(remote=remote):
                self.assertEqual(OWNER, triage.repository_from_remote(remote))
        with patch.object(triage.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, stdout=f"git@github.com:{OWNER}.git\n")) as command:
            self.assertEqual(OWNER, triage.checkout_repository(Path("owning-checkout")))
            self.assertEqual(["git", "-C", "owning-checkout", "remote", "get-url", "origin"],
                             command.call_args.args[0])

    def test_untrusted_or_missing_origin_does_not_select_another_tracker(self):
        for remote in (f"https://example.com/{OWNER}.git", f"https://token@github.com/{OWNER}.git",
                       f"https://github.com/{OWNER}.git?extra=1", "../another-project"):
            with self.subTest(remote=remote), self.assertRaises(ValueError):
                triage.repository_from_remote(remote)
        with patch.object(triage.subprocess, "run", side_effect=subprocess.CalledProcessError(2, "git")):
            with self.assertRaisesRegex(ValueError, "cannot establish ownership"):
                triage.checkout_repository(Path("owning-checkout"))


if __name__ == "__main__":
    unittest.main()
