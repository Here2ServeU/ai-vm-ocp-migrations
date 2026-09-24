# Contributing

`main` is protected. Only the repository owner pushes to it directly.
Everyone else works on a branch and opens a pull request.

## How to contribute

1. Create a branch: `git switch -c my-change`
2. Make your change and run the checks below.
3. Push the branch and open a pull request against `main`.
4. CI must pass and the owner must approve before it can merge.

## Run the checks before you push

```bash
pip install -r requirements-dev.txt
ruff check . --fix         # lint + security rules, auto-fixes what it can
ruff format .              # formats Python code
yamllint --strict .        # YAML files
shellcheck migration-copilot/scripts/*.sh
pip-audit -r migration-copilot/requirements-local.txt -r requirements-dev.txt
```

## What CI checks on every pull request

| Check | What it does |
| --- | --- |
| Lint | Ruff (style, bugs, security rules), formatting, shellcheck, yamllint |
| Test (Python 3.11 / 3.13) | Runs the demo, loads every tool, confirms the approval guardrail still blocks unapproved migrations |
| Security | `pip-audit` for vulnerable packages, `gitleaks` for leaked secrets |
| Dependency review | Blocks PRs that add vulnerable (moderate+) or GPL/AGPL-licensed dependencies |
| CodeQL | GitHub code scanning for security bugs in the Python code and the workflows |

Dependabot opens PRs every Monday to update Python packages and GitHub Actions.
Those PRs go through the same checks.

## Never commit secrets

`.env` is git-ignored. Put real values there, never in code. If you commit a secret by
mistake, tell the owner right away. The secret must be rotated, because removing it from
git history is not enough.
