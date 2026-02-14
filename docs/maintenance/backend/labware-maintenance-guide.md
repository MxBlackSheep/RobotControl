# Labware Backend Maintenance Guide

This guide covers Labware backend APIs for both `TipTracking` and `Cytomat`.

---

## 1. Where The Code Lives

- API router: `backend/api/labware.py`
- TipTracking service: `backend/services/labware_tip_tracking.py`
- Cytomat service: `backend/services/labware_cytomat.py`
- Router registration: `backend/main.py`

---

## 2. Endpoint Summary

Base path: `/api/labware`

- `GET /tip-tracking`
  - Return full tip snapshot (families, status metadata, permissions).
  - Access: authenticated `admin` or `user`.
  - Locality: local and remote allowed.

- `PUT /tip-tracking`
  - Apply batch tip status updates to one family.
  - Access: authenticated `admin` or `user`.
  - Locality: local only (`require_local_access`).

- `POST /tip-tracking/reset`
  - Reset one tip family to configured baseline.
  - Access: authenticated `admin` or `user`.
  - Locality: local only (`require_local_access`).

- `GET /cytomat`
  - Return Cytomat rows (`CytomatPos`, `PlateID`) and dropdown options from `Plates.PlateID`.
  - Access: authenticated `admin` or `user`.
  - Locality: local and remote allowed.

- `PUT /cytomat`
  - Apply batch `PlateID` updates for Cytomat positions.
  - Access: authenticated `admin` or `user`.
  - Locality: local only (`require_local_access`).

---

## 3. Permission Rules

1. Role guard is `_require_labware_role` (`admin` or `user` only).
2. Every write route uses `require_local_access`.
3. Read routes include a `permissions` block (`can_update`, `is_local_session`, IP metadata).

Frontend must treat `can_update=false` as read-only mode.

---

## 4. Service Configuration

- `TipTrackingService` uses DB config from `settings.DB_CONFIG_PRIMARY` and forces database `Labwares`.
- `CytomatService` uses DB config from `settings.DB_CONFIG_PRIMARY` and forces database `EvoYeast`.
- Both use `backend/utils/odbc_driver.py` (`resolve_driver_clause`) to safely pick an installed SQL Server ODBC driver.

---

## 5. TipTracking Rules

- Family definitions are in `TIP_FAMILY_CONFIGS` (`1000ul`, `300ul`).
- Core calls:
  - `build_snapshot()`
  - `fetch_tip_map(family_id)`
  - `apply_updates(family_id, updates)`
  - `reset_family(family_id)`
- Validation:
  - family must exist
  - position must be 1..96
  - status must be in `STATUS_ORDER`
  - rack must belong to selected family

---

## 6. Cytomat Rules

- Data source table: `[dbo].[Cytomat]` with columns `CytomatPos`, `PlateID`.
- Dropdown source table: `[dbo].[Plates]` column `PlateID`.
- `plate_options` ordering in snapshot:
  1. empty option (`""`) first
  2. then numeric `PlateID` values descending
  3. then non-numeric values descending
- Write validation:
  - `cytomat_pos` must exist in `Cytomat`
  - `plate_id` must be empty or exist in `Plates`
- Empty dropdown choice is persisted as SQL `NULL` in `Cytomat.PlateID`.

---

## 7. Auditing and Logging

Write operations call `log_action(...)` with:
- scope: `labware`
- tip actions: `tip_tracking_update`, `tip_tracking_reset`
- cytomat action: `cytomat_update`

Keep this pattern for any new write endpoint.

---

## 8. Extending Safely

1. Keep each labware sub-module in its own service file.
2. Keep read and write endpoints separate and explicit.
3. Keep local-access checks at API layer even if frontend already disables controls.
4. Add tests for:
   - role rejection
   - remote write rejection
   - local write success
   - invalid payload validation

---

## 9. Troubleshooting

1. `500 Unable to load Cytomat state` or tip state:
   - Check SQL connectivity and ODBC driver installation.
   - Confirm DB target (`EvoYeast` for Cytomat, `Labwares` for tip tracking).

2. Cytomat `PlateID` validation failures:
   - Verify the value exists in `Plates.PlateID`.
   - Use empty option when clearing a slot.

3. Writes blocked with local-access error:
   - Confirm request IP resolves to loopback/local in `X-Forwarded-For`.
