# Labware spatial revision

The Labware page must preserve the relationship between the equipment and the display. Shared colors, typography and actions are useful; a generic list/detail layout is not appropriate for every task.

## Tip deck

Restore Col A and Col B beside each other, using the backend's ordered `left_racks` and `right_racks` arrays without sorting. Render every rack's 8-by-12 state pattern. Preserve the existing column-major numbering: positions 1–8 run down the first column, followed by 9–16 in the second. Do not invent a front/back orientation absent from configuration.

Selecting a rack opens an enlarged editor while keeping the deck visible on wide screens. Phones retain the same two-column overview and open the selected rack separately, with a way back. Small overview dots are not editing targets; enlarged controls provide accurate touch and keyboard access.

This is consistent with the [Opentrons deck map and slot spotlight](https://docs.opentrons.com/flex/opentrons-app/protocol-viz/): physical position remains the navigation context while a selected slot gets more detail. RobotControl must retain its own configured rack geometry.

Select the intended state first. Click a tip or drag a rectangular selection to apply that state to a draft. Keyboard movement changes focus without painting; activation paints. Cancellation must leave the draft unchanged. Provide whole-row, column and rack actions, Undo, Discard and Save changes. Preserve the selected state when moving between tips and racks.

The existing batch PUT already validates rack IDs, positions and states and commits both carrier tables in one database transaction. Painting therefore needs no new write endpoint. Keep server permissions authoritative and send edits only when Save changes is used. Failed writes retain drafts; drafts and writes suspend polling.

## Cytomat

The API currently supplies only `cytomat_pos` and `plate_id`, sorted by the database position string. There is no physical rack, shelf or orientation metadata. A faithful map requires the operator's position-to-rack/shelf mapping. Do not infer a physical layout from names such as A1 or from alphabetical ordering. The current editor remains functional until this mapping is established.

The intended design uses stable rack/shelf positions with occupied/empty plate slots, the same selection outline and local draft/save behavior as the deck, and an enlarged assignment control. Finding a plate should highlight its original slot rather than rearranging the storage map.

## System Status

Keep service availability and CPU, memory and disk readings. Move technical connection information into a compact disclosure. The streaming session count describes live-view connections, not camera recordings or robot activity. Its utilization field samples application-process CPU with a system-CPU fallback and should not be presented as an independent streaming-health percentage.

## Verification

Record failure scenarios and browser checks before implementation. Use disposable API fixtures for state painting, physical ordering, undo/cancel, save failure and read-only behavior. Preserve screenshots and traces for desktop and phone sizes. These checks establish UI behavior, not agreement with a physical robot; the configured order still needs operator confirmation on the VM.
