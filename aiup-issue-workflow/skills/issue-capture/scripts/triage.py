"""Offline capture-packet validation. Reads local Git metadata; never writes to a tracker."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, expected, label):
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == set(expected.split()), f"{label} has missing or unsupported fields")


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label} must be nonempty text")
    return value


def text_list(value, label, nonempty=False):
    require(isinstance(value, list), f"{label} must be a list")
    require(not nonempty or bool(value), f"{label} must not be empty")
    for item in value:
        text(item, label)


def repository(value):
    text(value, "repository")
    require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", value)),
            "repository must be owner/name")
    require(value.split("/")[1] not in {".", ".."}, "invalid repository name")
    return value.casefold()


def repository_from_remote(remote):
    """Accept ordinary GitHub URLs without leaking credentials from an invalid remote."""
    remote = remote.strip()
    if remote.startswith("git@github.com:"):
        path = remote[len("git@github.com:"):]
    else:
        parsed = urlsplit(remote)
        require(parsed.hostname == "github.com" and not parsed.query and not parsed.fragment,
                "origin must identify a GitHub repository")
        require(parsed.scheme in {"https", "ssh"} and parsed.password is None,
                "unsupported origin URL")
        require((parsed.scheme == "https" and parsed.username is None and parsed.port is None)
                or (parsed.scheme == "ssh" and parsed.username == "git"
                    and parsed.port in {None, 22}), "unsupported origin URL")
        path = parsed.path.removeprefix("/")
    path = path.removesuffix(".git")
    repository(path)
    return path


def checkout_repository(workspace):
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("cannot establish ownership from the checkout's origin") from error
    return repository_from_remote(result.stdout)


def triage(packet, owner):
    fields(packet, "repository finding duplicate_check", "packet")
    require(repository(packet["repository"]) == repository(owner),
            "finding repository does not match the owning checkout")
    finding = packet["finding"]
    fields(finding, "title type observed_at evidence impact priority priority_rationale "
           "completion_criteria links unconfirmed_causes", "finding")
    for key in ("title", "type", "observed_at", "impact", "priority_rationale"):
        text(finding[key], key)
    require(finding["priority"] in ("High", "Medium", "Low"), "invalid provisional priority")
    for key in ("evidence", "completion_criteria", "links", "unconfirmed_causes"):
        text_list(finding[key], key, nonempty=key in {"evidence", "completion_criteria"})

    check = packet["duplicate_check"]
    fields(check, "repository source checked_at method states complete items", "duplicate_check")
    require(repository(check["repository"]) == repository(owner),
            "duplicate search repository does not match the owning checkout")
    require(check["source"] in ("live", "offline"), "invalid duplicate-check source")
    for key in ("checked_at", "method"):
        text(check[key], key)
    text_list(check["states"], "states")
    require(len(check["states"]) == 2 and set(check["states"]) == {"open", "closed"},
            "duplicate check must cover open and closed issues")
    require(check["complete"] is True, "duplicate check is incomplete")
    require(isinstance(check["items"], list), "duplicate candidates must be a list")

    candidates = {}
    for item in check["items"]:
        fields(item, "number title state disposition rationale", "duplicate candidate")
        number = item["number"]
        require(type(number) is int and number > 0, "invalid issue number")
        require(number not in candidates, "duplicate issue number in review")
        for key in ("title", "rationale"):
            text(item[key], key)
        require(item["state"] in ("open", "closed"), "invalid issue state")
        require(item["disposition"] in ("duplicate", "related", "distinct", "unresolved"),
                "invalid duplicate disposition")
        candidates[number] = item

    def identity(item):
        return {"repository": owner, "number": item["number"], "state": item["state"],
                "url": f"https://github.com/{owner}/issues/{item['number']}"}

    duplicates = [item for item in candidates.values() if item["disposition"] == "duplicate"]
    unresolved = [item for item in candidates.values() if item["disposition"] == "unresolved"]
    result = {
        "repository": owner,
        "context": "offline/simulated" if check["source"] == "offline" else "live-source packet",
        "tracker_write_performed": False,
        "implementation_authorized": False,
        "canonical_issue": None,
        "related_issues": [identity(item) for item in candidates.values()
                           if item["disposition"] == "related"],
        "capture": finding,
        "duplicate_check": check,
        "new_issue": None,
    }
    if unresolved or len(duplicates) > 1:
        result.update(outcome="needs_review", candidates=[identity(item)
                      for item in duplicates + unresolved])
    elif duplicates:
        result.update(outcome="existing", canonical_issue=identity(duplicates[0]))
    else:
        body = [f"**Type:** {finding['type']}",
                f"**Observed:** {finding['observed_at']}",
                f"**Priority:** {finding['priority']} (provisional)",
                finding["priority_rationale"], "## Finding and impact", finding["impact"],
                "## Evidence", *[f"- {item}" for item in finding["evidence"]],
                "## Unconfirmed causes", *([f"- {item}" for item in finding["unconfirmed_causes"]]
                                          or ["No cause established by this capture."]),
                "## Completion criteria", *[f"- [ ] {item}" for item in finding["completion_criteria"]],
                "## Links", *([f"- {item}" for item in finding["links"]] or ["None supplied."]),
                "## Duplicate check", f"{result['context']}; {check['checked_at']}; {check['method']}",
                "Open and closed issues covered by the supplied review.",
                *[f"- #{item['number']} ({item['state']}): {item['disposition']}; {item['rationale']}"
                  for item in candidates.values()],
                "## Scope", "Capture and triage only. This draft grants no implementation authority."]
        result.update(outcome="draft", new_issue={"title": finding["title"], "body": "\n\n".join(body)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--input", type=Path, help="JSON packet; default: standard input")
    args = parser.parse_args()
    try:
        owner = checkout_repository(args.workspace)
        raw = args.input.read_text(encoding="utf-8-sig") if args.input else sys.stdin.read()
        result = triage(json.loads(raw), owner)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 2 if result["outcome"] == "needs_review" else 0
    except (OSError, ValueError) as error:
        print(json.dumps({"outcome": "blocked", "reason": str(error),
                          "tracker_write_performed": False, "new_issue": None}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
