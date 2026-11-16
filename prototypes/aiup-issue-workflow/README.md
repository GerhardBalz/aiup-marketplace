# AIUP Issue Workflow

An optional, stack-agnostic prototype for AIUP projects. It packages two skills in one install.

- `issue-capture` gathers evidence, checks the owning tracker for duplicates, and drafts a report. Tracker writes require explicit authorization.
- `issue-resolve` starts from an existing issue and works through the requested stage. It hands specification, implementation, and test work to the existing AIUP skills and uses `issue-capture` for new findings and authorized tracker updates.

## Try the prototype

Clone the fork and set `package` to the package directory.

```bash
git clone --single-branch \
  https://github.com/GerhardBalz/aiup-marketplace.git aiup-marketplace-prototype
package="$(cd aiup-marketplace-prototype/prototypes/aiup-issue-workflow && pwd)"
```

On Windows Git Bash, convert the path with `package="$(cygpath -am "$package")"`.
Keep the package directory on disk and change to the root of the Git checkout where you want to use the skills.

### Codex via Tessl

For a checkout without Tessl configuration, run `tessl init --agent codex`. Then install the prototype and open a fresh Codex session.

```bash
tessl install --agent codex "file:$package"
```

### Claude Code

Load the package in a fresh session from your project root.

```bash
claude --plugin-dir "$package"
```

Use `aiup-issue-workflow:issue-capture` and `aiup-issue-workflow:issue-resolve` to select the packaged skills. The helpers require Git and Python 3.10 or later. Live tracker operations also require the host's authenticated tracker tooling and your authorization.

## Offline checks

Run these commands from this directory. The tests use synthetic tracker data and disposable Git repositories.

```bash
python -B -m unittest discover -s skills/issue-capture/tests
python -B -m unittest discover -s skills/issue-resolve/tests
```

The prototype uses the existing AIUP workflow for repair and retains the product owner's authority over lifecycle decisions. See the upstream adoption proposal for context. [AIUP Marketplace #67](https://github.com/AI-Unified-Process/marketplace/issues/67)

## License and attribution

This community prototype extends the AI Unified Process Marketplace by Simon Martinelli.
See [LICENSE](LICENSE) and [NOTICE](NOTICE).
