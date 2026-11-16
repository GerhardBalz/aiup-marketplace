#!/usr/bin/env python3
#
# Copyright 2025-2026 Simon Martinelli and the AI Unified Process contributors.
# Part of the AI Unified Process — https://unifiedprocess.ai
# Licensed under the Apache License, Version 2.0. See LICENSE and NOTICE.
"""Project-local delivered review receipts; never edit specifications or approve them."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import tempfile


# Helpers for review inputs and retained evidence.
def digest(value):
    return hashlib.sha256(value).hexdigest()


def inside(root, path):
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("handoff paths must stay inside the workspace")
    return target


def specification(root, uid):
    if not re.fullmatch(r"UC-\d{3,}", uid):
        raise ValueError("use a normalized use-case ID, e.g. UC-001")
    matches = [p for folder in ("use_cases", "use-cases")
               for p in (root / "docs" / folder).rglob(uid + "-*.md")]
    if len(matches) != 1:
        raise ValueError("the use-case ID must resolve to exactly one specification")
    return matches[0]


def question_bytes(path, spec, uid):
    """Hash owned questions; keep shared/unknown scopes conservative."""
    requirement_lines = [line for line in spec.read_text(encoding="utf-8-sig").splitlines()
                         if re.match(r"\*\*(?:Requirements|Anforderungen):\*\*", line)]
    linked = set(re.findall(r"(?<![\w-])(?:FR|NFR|C)-\d{3,}(?![\w-])",
                            "\n".join(requirement_lines), re.IGNORECASE))
    linked = {rid.upper() for rid in linked}
    text = "\n".join(path.read_text(encoding="utf-8-sig").splitlines())
    selected = []
    for section in re.split(r"(?m)(?=^##[ \t]+)", text):
        if not section.startswith("##"):
            continue  # The file title/template is not a question.
        elements = re.findall(r"(?mi)^[ \t]*\*\*Element:\*\*[ \t]*([^\n]*)", section)
        element = elements[0].strip().strip("`").upper() if len(elements) == 1 else ""
        owner = re.match(r"^(UC-\d{3,})(?=\s|$)", element)
        requirement = re.fullmatch(r"(?:FR|NFR|C)-\d{3,}", element)
        if owner and owner[1] != uid or requirement and element not in linked:
            continue
        selected.append("\n".join(line.rstrip() for line in section.splitlines()).strip())
    return "\n\n".join(sorted(selected)).encode("utf-8")


def evidence_current(root, items):
    return all(inside(root, item["path"]).is_file() and
               digest(inside(root, item["path"]).read_bytes()) == item["sha256"]
               for item in items)

OWNERS = {
    "use-case-spec": r"UC-\d{3,}", "use-case-diagram": r"",
    "requirements": r"", "entity-model": r"",
    "open-questions": r"(?:OQ-\d{3,})?", "test-case": r"(?:TC-\d{3,})?",
    "architecture-decision": r"(?:ADR-\d{3,})?", "business-process": r"(?:BP-\d{3,})?",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(root, uid):
    """Documents used by a scoped review, including cross-use-case rules; no code/tests."""
    spec = specification(root, uid)
    docs = root / "docs"
    paths = {docs / name for name in ("requirements.md", "entity_model.md", "glossary.md",
                                     ".spec-lint-baseline.json", "architecture/stack.md")}
    for folder in ("use_cases", "use-cases", "test_cases", "test-cases", "entity_model"):
        paths.update((docs / folder).rglob("*.md"))
    paths.update(docs.rglob("*.puml"))
    paths.update(docs.rglob("BP-*.bpmn"))
    paths.update(p for p in docs.rglob("ADR-*.md")
                 if set(p.parts) & {"decisions", "adr", "adrs"})
    values = {p.relative_to(root).as_posix(): digest(
        "\n".join(p.read_text(encoding="utf-8-sig").splitlines()).encode("utf-8"))
              for p in paths if p.is_file()}
    for question_name in ("open_questions.md", "open-questions.md"):
        questions = docs / question_name
        if questions.is_file():
            relevant = question_bytes(questions, spec, uid)
            if relevant:
                values[questions.relative_to(root).as_posix()] = digest(relevant)
    return digest(json.dumps(values, sort_keys=True).encode("utf-8"))


def record_path(root, uid):
    specification(root, uid)
    return inside(root, Path(".aiup/reviews") / (uid + ".json"))


def command(finding):
    owner, target = finding["owner"], finding["target"]
    if owner == "open-questions" and target:
        return "/open-questions answer " + target
    return "/" + owner + (" " + target if target else "")


def validate_result(root, result):
    require(isinstance(result, dict) and set(result) == {
        "lint_exit_code", "ready_for_approval", "findings"}, "invalid review result fields")
    require(type(result["lint_exit_code"]) is int and result["lint_exit_code"] in (0, 1),
            "review needs a completed lint run, not a usage/execution failure")
    require(type(result["ready_for_approval"]) is bool, "readiness must be explicit")
    require(isinstance(result["findings"], list), "findings must be a list")
    active = []
    errors = False
    semantic_warning = False
    for finding in result["findings"]:
        required = {"kind", "severity", "disposition", "file", "line", "element",
                    "code", "message", "owner", "target"}
        require(isinstance(finding, dict) and required <= set(finding)
                and set(finding) <= required | {"decision"}, "invalid finding fields")
        require(finding["kind"] in ("lint", "semantic"), "invalid finding kind")
        require(finding["severity"] in ("error", "warning", "info"), "invalid severity")
        require(finding["kind"] != "semantic" or finding["severity"] != "error",
                "semantic findings stay advisory")
        require(finding["disposition"] in ("open", "accepted", "declined"), "invalid disposition")
        if finding["disposition"] != "open":
            require(finding["kind"] == "semantic" and isinstance(finding.get("decision"), str)
                    and bool(finding["decision"].strip()), "retain the human finding decision")
        for key in ("file", "element", "code", "message"):
            require(isinstance(finding[key], str) and bool(finding[key].strip()), "missing " + key)
        path = inside(root, finding["file"])
        require(path.is_relative_to(root / "docs") and path.is_file(), "finding must name a document")
        require(type(finding["line"]) is int and 0 <= finding["line"] <= len(
            path.read_text(encoding="utf-8-sig").splitlines()), "invalid finding line")
        owner, target = finding["owner"], finding["target"]
        require(isinstance(owner, str) and owner in OWNERS and isinstance(target, str)
                and re.fullmatch(OWNERS[owner], target), "unsupported correction owner/target")
        if owner == "use-case-spec":
            specification(root, target)
        if finding["disposition"] == "open" and finding["severity"] != "info":
            active.append(finding)
            errors |= finding["kind"] == "lint" and finding["severity"] == "error"
            semantic_warning |= finding["kind"] == "semantic" and finding["severity"] == "warning"
    require(bool(result["lint_exit_code"]) == errors, "lint exit code disagrees with errors")
    if result["ready_for_approval"]:
        require(not errors and not semantic_warning, "open errors/semantic warnings prevent readiness")
    else:
        require(bool(active), "a not-ready review needs an explicit correction finding")
    return active


def inspect(root, uid):
    root = Path(root).resolve()
    try:
        path = record_path(root, uid)
        if not path.exists():
            return {"state": "missing"}
        record = json.loads(path.read_text(encoding="utf-8"))
        require(type(record.get("schema_version")) is int and record["schema_version"] == 1
                and record.get("use_case") == uid,
                "invalid review receipt identity")
        if record.get("input_digest") != fingerprint(root, uid):
            return {"state": "stale"}
        if record.get("outcome") == "in-progress":
            return {"state": "in-progress"}
        require(record.get("outcome") == "reported" and isinstance(record.get("summary"), str)
                and bool(record["summary"].strip())
                and isinstance(record.get("evidence"), list) and len(record["evidence"]) >= 2,
                "incomplete delivered review receipt")
        items = record["evidence"]
        require(all(isinstance(item, dict) and set(item) == {"path", "sha256"}
                    and isinstance(item["path"], str) and isinstance(item["sha256"], str)
                    and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) for item in items),
                "invalid review evidence metadata")
        require(len({item["path"] for item in items}) == len(items)
                and isinstance(record.get("result_file"), str)
                and record["result_file"] in {item["path"] for item in items},
                "retain distinct result and report evidence")
        active = validate_result(root, record["result"])
        if not evidence_current(root, items):
            return {"state": "stale"}
        source = inside(root, record["result_file"])
        require(json.loads(source.read_text(encoding="utf-8-sig")) == record["result"],
                "receipt result differs from the retained result JSON")
        if record["result"]["ready_for_approval"]:
            return {"state": "ready", "findings": record["result"]["findings"], "actions": []}
        return {"state": "rework", "findings": record["result"]["findings"],
                "actions": list(dict.fromkeys(command(f) for f in active))}
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        return {"state": "invalid"}


def write(root, uid, action, result_path=None, summary="", evidence=()):
    root = Path(root).resolve()
    path = record_path(root, uid)
    require(action in ("begin", "report"), "unsupported review action")
    current_digest = fingerprint(root, uid)
    if action == "begin":
        record = {"schema_version": 1, "use_case": uid, "outcome": "in-progress",
                  "input_digest": current_digest}
    else:
        require(path.is_file() and inspect(root, uid)["state"] == "in-progress",
                "begin the review against current inputs before recording delivery")
        record = json.loads(path.read_text(encoding="utf-8"))
        require(result_path and summary.strip() and evidence, "retain the result, summary and full report")
        source = inside(root, result_path)
        require(source.is_file() and source != path, "result must be a retained JSON file")
        result = json.loads(source.read_text(encoding="utf-8-sig"))
        validate_result(root, result)
        targets = [source] + [inside(root, name) for name in evidence]
        require(any(p != source for p in targets[1:]), "full report must be separate from result JSON")
        require(all(p.is_file() and p != path for p in targets), "invalid report evidence")
        record.update(outcome="reported", summary=summary.strip(), result=result,
                      result_file=source.relative_to(root).as_posix(),
                      evidence=[{"path": p.relative_to(root).as_posix(),
                                 "sha256": digest(p.read_bytes())} for p in dict.fromkeys(targets)])
    record["recorded_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as file:
        temporary = Path(file.name)
    try:
        temporary.write_bytes((json.dumps(record, indent=2) + "\n").encode("utf-8"))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return inspect(root, uid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("begin", "report"))
    parser.add_argument("use_case")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--result", type=Path)
    parser.add_argument("--summary", default="")
    parser.add_argument("--evidence", action="append", default=[])
    args = parser.parse_args()
    try:
        print(json.dumps(write(args.workspace, args.use_case, args.action,
                               args.result, args.summary, args.evidence)))
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        print(json.dumps({"error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
