# Labware spatial revision

The Labware page must preserve the relationship between the equipment and the display. Shared colors, typography and actions are useful; a generic list/detail layout is not appropriate for every task.

## Tip deck

Restore Col A and Col B beside each other, using the backend's ordered `left_racks` and `right_racks` arrays without sorting. Render every rack's 8-by-12 state pattern. Preserve the existing column-major numbering: positions 1–8 run down the first column, followed by 9–16 in the second. Do not invent a front/back orientation absent from configuration.

Selecting a rack opens an enlarged editor while keeping the deck visible on wide screens. Phones retain the same two-column overview and open the selected rack separately, with a way back. Small overview dots are not editing targets; enlarged controls provide accurate touch and keyboard access.

This is consistent with the [Opentrons deck map and slot spotlight](https://docs.opentrons.com/flex/opentrons-app/protocol-viz/): physical position remains the navigation context while a selected slot gets more detail. RobotControl must retain its own configured rack geometry.

The operator's follow-up removes the separate Paint/Rectangle modes. Choose a state in **Set tips to**, then drag a block or choose two corners; choose the same tip twice for a one-tip selection. Keyboard arrows move focus and Enter/Space chooses a corner. Selection creates an undoable draft. **Set entire rack** is the one additional bulk action. Retain Undo, Discard and Save changes; remove the separate row, column and numeric-range editors.

Size square tip controls from both available width and available height, with a 44px minimum and a bounded maximum. Measure the real content area and footer rather than assuming a screen resolution maps directly to CSS pixels. The rack surface should follow the grid size instead of growing into an empty card. Center and bound the whole workspace on very wide screens; retain both carrier columns on smaller screens. Freeze geometry during a selection gesture. Verify 4K at 100% scaling and a high-DPI equivalent, medium desktops, low-height laptops and phones.

The existing batch PUT already validates rack IDs, positions and states and commits both carrier tables in one database transaction. Bulk selection therefore needs no new write endpoint. Keep server permissions authoritative and send edits only when Save changes is used. Failed writes retain drafts; drafts and writes suspend polling.

## Cytomat

The operator confirmed that position 1 is at the top, position 7 at the bottom, and positions 8 and 9 are currently unused. Display positions 1–7 as one vertical shelf stack, independent of API sort order. Show 8–9 separately as Unused, with any existing plate visible, and without assignment controls.

Use compact inline plate assignment controls beside the active shelf positions, preserving local drafts and batch Save. A missing API row means Unavailable, not Empty; it cannot be edited. Unexpected IDs remain visible under Other positions without inventing a physical location. Keep their exact IDs for existing permission-checked updates. Do not merge names such as A1 or 01 into a numbered shelf. The backend contract and local-only write permissions remain unchanged.

## System Status

Keep service availability and CPU, memory and disk readings. Move technical connection information into a compact disclosure. The streaming session count describes live-view connections, not camera recordings or robot activity. Its utilization field samples application-process CPU with a system-CPU fallback and should not be presented as an independent streaming-health percentage.

## Verification

Record failure scenarios and browser checks before implementation. Use disposable API fixtures for state selection, physical ordering, undo/cancel, save failure and read-only behavior. Preserve screenshots and traces for desktop and phone sizes. These checks establish UI behavior, not agreement with a physical robot; the configured order still needs operator confirmation on the VM.
