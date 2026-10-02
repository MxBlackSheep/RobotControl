# Work in progress: failure cases

Before changing behavior, list here how the change could go wrong. Once the checks
exist, move the lasting cases into the header comment of the spec or backend check
that covers them, then delete them from this file. Keep this file short; finished
work stays in Git history, not here.

## Tip tracking: reserved and unclear are no longer choices (frontend only)

The backend still stores and reports `reserved` and `unclear` (missing or unrecognised
values arrive as `unclear`). Ways the change could go wrong:

- The palette still offers Reserved or Unclear, or loses one of the five allowed statuses.
- A saved reserved/unclear tip renders as clean, empty or uncoloured, or its accessible
  name changes to another status, because the hidden status was dropped from the list
  that drives colours, names or counts.
- The deck legend hides a status that tips on the deck still show, or keeps one that no
  tip shows any more (including after drafts repaint every such tip).
- "After saving" omits tips that keep a hidden status.
- Repainting a reserved/unclear tip saves something other than the chosen allowed status,
  or Undo does not restore the tip to its saved hidden status.
- A draft on a hidden-status tip is lost across a family change.
