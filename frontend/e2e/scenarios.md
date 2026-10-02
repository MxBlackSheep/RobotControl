# Work in progress: failure cases

Before changing behavior, list here how the change could go wrong. Once the checks
exist, move the lasting cases into the header comment of the spec or backend check
that covers them, then delete them from this file. Keep this file short; finished
work stays in Git history, not here.

## Package connections and release notes (PR #45 follow-up)

- An in-app publish (Edit → Publish update with a change note) loses earlier CHANGELOG
  sections, writes a second section for the same version, or drops CHANGELOG.md when
  "Replace all files" omitted it.
- Download package returns bytes whose sha256 differs from the installed (pinned) one.
- The import review's CHANGELOG prefill replaces a note the administrator typed.
