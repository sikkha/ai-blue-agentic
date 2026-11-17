# PR handoff experiment: Claude and Codex

## Purpose

Test whether two external coding assistants, Claude Code and Codex, can hand work
to each other through GitHub pull requests while coordinating in Band. Each
assistant works in its own Git worktree on its own branch. One writes, the other
reviews, and the change reaches `main` only through a PR.

Both PRs were limited to `README.md`, so the test exercised the workflow and not
the code.

## Setup

| Item | Claude | Codex |
|---|---|---|
| Branch | `band/claude-engineer` | `band/codex-engineer` |
| Worktree | its own | its own |
| Role | implements and tests | reviews and can improve the change |

Coordination happened in a Band room that also included the human maintainer.
Neither working branch was deleted after merging.

## Identity limitation

Both agents currently push and open PRs as the same GitHub user, `sikkha`.
GitHub does not let an author approve their own PR, and a second account was not
used. As a result:

- Peer review took place in Band, not on GitHub.
- Neither PR has a GitHub review or an independent GitHub approval (0 reviews on each).
- The review evidence is the Band conversation, plus the commit history.

Separate GitHub identities for the two agents would be needed to get a recorded
GitHub approval.

## Experiment 1: PR #1 (Claude writes, Codex reviews)

- PR: https://github.com/sikkha/ai-blue-agentic/pull/1
- Branch: `band/claude-engineer` into `main`

Steps:

1. Claude added a concise Thai section to `README.md` on the Claude Code and Codex
   development workflow (commit `808fc26`) and pushed the branch.
2. Claude mentioned Codex in Band with the commit SHA and asked for review.
3. Codex reviewed the pushed commit. It found no blocking issues and one minor
   wording issue: separate worktrees let the agents edit independently, but their
   branches can still conflict at merge time, so the text should not imply
   otherwise.
4. Claude applied the suggested wording (commit `affc5da`) and pushed. Codex
   re-reviewed and reported the finding resolved.
5. The PR was opened and merged.

Results:

- Changed files: `README.md` only (+13, -0).
- Checks: `python` and `frontend` passed.
- Merge: merged into `main` as `981238e70c7be142fcd63bdd9b761e771446557d`.
- GitHub reviews: none (see the identity limitation).

## Experiment 2: PR #2 (Codex writes, Claude reviews)

- PR: https://github.com/sikkha/ai-blue-agentic/pull/2
- Branch: `band/codex-engineer` into `main`

Steps:

1. Codex fetched the merged `main`, confirmed a clean worktree, added one Thai
   sentence to the same README section (commit `d489709`), and pushed.
2. Codex mentioned Claude in Band with the commit SHA.
3. Claude reviewed the pushed diff. It was correct and no correction was needed.
4. Claude opened the PR into `main`, waited for the checks, and merged.

Results:

- Changed files: `README.md` only (+2, -0).
- Checks: `python` and `frontend` passed.
- Merge: merged into `main` as `24e47fabed9c5077e68409e09c1192575c7cb824`.
- GitHub reviews: none (see the identity limitation).

## Observations

- The handoff worked in both directions: write on a branch, push, notify the
  reviewer in Band with the commit SHA, review the pushed diff, then PR, checks
  and merge.
- Giving the reviewer a specific commit SHA kept the review unambiguous, and the
  re-review after a fix was cheap.
- The only substantive review finding came in PR #1 and was a wording accuracy
  issue.
- One session was interrupted before its edit was saved. Inspecting the diff on
  resume showed it was empty, so the edit was re-applied without duplication.
- Independent review on GitHub is not yet possible. The two agents need separate
  GitHub identities for that.
