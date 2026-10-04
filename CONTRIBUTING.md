# Contributing

Thanks for helping out. This page covers how changes get into `main` and how releases are
tagged. For setting up a development copy, see the [README](README.md#development).

## Making a change

`main` is protected: every change goes in through a pull request, including small ones.

1. Start from an up-to-date `main` and make a branch for the one thing you are changing:

   ```powershell
   git switch main
   git pull
   git switch -c fix/scheduler-restore-lock
   ```

   Use `feature/`, `fix/`, `docs/` or `chore/` at the front of the name. If you notice
   something unrelated along the way, put it on its own branch.

2. Commit, test what your change affects, and push:

   ```powershell
   git push -u origin fix/scheduler-restore-lock
   ```

3. Open a pull request into `main`. Say what changed, why, and how you checked it.

4. When it has been reviewed, merge it with **Squash and merge**. GitHub deletes the branch on
   its side.

5. Clean up your local copy:

   ```powershell
   git switch main
   git pull
   git fetch --prune
   git branch -D fix/scheduler-restore-lock
   ```

   You need `-D` rather than `-d` because squashing gives `main` a new commit, so Git can't
   tell that your branch was merged. Check on GitHub that the pull request says **Merged**
   before you delete it.

Don't keep long-lived or "backup" branches. If a commit needs to be easy to find later, tag it.

## Pull request titles

The title becomes the one commit on `main`, so it is worth a moment. Start with a verb and say
what changes for whoever uses or maintains RobotControl, in about 70 characters or fewer:

- Good: `Preserve scheduling drafts during status refresh`
- Not useful: `UI improvement`, `Fix`, `feat: scheduling`

Leave out type prefixes and file lists. Reasons, trade-offs and test notes belong in the
description. Commits inside your branch can be as rough as you like.

## Releases

Release tags look like `v0.1.5`, with a lowercase `v`. The older tags `V0.1.1` to `V0.1.4` keep
their capital `V`; don't add lowercase copies of them, because Windows treats `V0.1.1` and
`v0.1.1` as the same name and fetching breaks.

Before tagging, make sure the version is the same in `backend/version.py`, `pyproject.toml`
and `frontend/package.json`, and that `docs/implementation-notes.md` says what the release
contains.

## Repository settings

For admins, so the rules above are enforced rather than just written down:

- Settings → Branches, rule for `main`: require a pull request before merging, and block force
  pushes and deletion.
- Settings → General → Pull Requests: allow squash merging only, with "Pull request title" as
  the default message, and turn on "Automatically delete head branches".
