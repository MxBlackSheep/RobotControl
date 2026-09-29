# Contributing

These rules keep `main` readable for people and coding agents alike.

## Branches

- `main` only changes through a pull request. Never commit or push to it directly.
- Start each change from an up-to-date `main` on a short-lived branch named by purpose:
  `feature/<topic>`, `fix/<topic>`, `docs/<topic>` or `chore/<topic>`
  (for example `fix/scheduler-restore-lock`).
- One topic per branch. Unrelated edits go on their own branch.
- Pull requests are squash-merged, and GitHub deletes the branch afterwards.
  Do not keep long-lived or "backup" branches; tag a commit instead if it must be found again.

## Commit messages and pull request titles

With squash merging, the pull request title becomes the single commit on `main`,
so it matters most.

- Start with a verb and say what changes for the user or maintainer, in under about 70 characters:
  `Preserve scheduling drafts during status refresh`, not `UI Improvement` or `Fix`.
- No type prefixes (`feat:`, `New Feature:`) and no file lists in the title.
- Put the reason, trade-off and verification in the body or pull request description.
- Commits inside a branch may be rough; the pull request title and description must not be.

## Versions and tags

- Tag released commits on `main` as `v<major>.<minor>.<patch>` with a lowercase `v`, for example `v0.1.5`.
  The older tags `V0.1.1`–`V0.1.4` keep their capital `V`. Do not add lowercase copies:
  Windows treats `V0.1.1` and `v0.1.1` as the same file name, so both in one repository breaks fetches there.
- The version in `backend/version.py`, `pyproject.toml` and `frontend/package.json` must match the tag.
- Record what the release contains in `docs/implementation-notes.md`.

## GitHub settings that enforce this

Repository admins keep these on:

- Settings → Branches → rule for `main`: require a pull request before merging; block force pushes and deletion.
- Settings → General → Pull Requests: allow squash merging only, default message "Pull request title";
  enable "Automatically delete head branches".
