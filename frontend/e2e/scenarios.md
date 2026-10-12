# Work in progress: failure cases

Before changing behavior, list here how the change could go wrong. Once the checks
exist, move the lasting cases into the header comment of the spec or backend check
that covers them, then delete them from this file. Keep this file short; finished
work stays in Git history, not here.

## Phone shell: paged bottom bar, section header, Overview deck (below 900px)

- The fixed bottom bar covers page content, the pinned paging bars (#62) or a dialog's actions.
- Off-screen pill groups stay focusable or announced; the bar opens on the wrong group.
- A swipe on the bar opens a page; tapping a pill after a short drag navigates.
- A user without Scheduling, Labware or Admin sees them in the bar; Account is missing.
- A held run is invisible because its pill's group is off-screen (group dot must carry the colour).
- Section dots pick a section the user may not open, lose it on reload/back, or are too small to tap.
- Overview deck: polling stops or doubles; the held run is not the first card; a card is clipped at 320px.
- Desktop (900px and wider) changes at all.
