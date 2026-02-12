# Labware Backend Maintenance Guide

This guide covers the new Labware API module, focused on TipTracking.

---

## 1. Where The Code Lives

- API router: `backend/api/labware.py`
- Service layer: `backend/services/labware_tip_tracking.py`
- Router registration: `backend/main.py`

---

## 2. Endpoint Summary

Base path: `/api/labware`

- `GET /tip-tracking`
  - Purpose: return full tip tracking snapshot (both families), plus permissions.
  - Access: authenticated `admin` or `user`.
  - Locality: local and remote allowed.

- `PUT /tip-tracking`
  - Purpose: apply batch updates to one family.
  - Access: authenticated `admin` or `user`.
  - Locality: local only (`require_local_access`).

- `POST /tip-tracking/reset`
  - Purpose: reset one family to baseline state.
  - Access: authenticated `admin` or `user`.
  - Locality: local only (`require_local_access`).

---

## 3. Permission Rules

1. Role gate is enforced in `backend/api/labware.py` via `_require_labware_role`.
2. Write endpoints also use `require_local_access` from `backend/api/dependencies.py`.
3. Read endpoint returns a `permissions` object:
   - `role`
   - `is_local_session`
   - `can_update`
   - `ip_classification`
   - `client_ip`

Frontend uses these flags to show read-only mode for remote sessions.

---

## 4. Service Configuration

`TipTrackingService` builds its DB config from `settings.DB_CONFIG_PRIMARY` and overrides database name using:

- env var: `ROBOTCONTROL_LABWARE_DATABASE`
- default fallback: `Labwares`

Driver resolution uses `backend/utils/odbc_driver.py` so installed SQL Server ODBC drivers are selected safely.

---

## 5. Family Definitions

Family definitions are constants in `backend/services/labware_tip_tracking.py` (`TIP_FAMILY_CONFIGS`).

Each family includes:
- rack ordering for `left_racks` and `right_racks`,
- source tables (`ColA`, `ColB`),
- reset map (`reset_map`).

Current families:
- `1000ul`
- `300ul`

If you add a new family, update this dictionary first.

---

## 6. Core Service Behavior

- `build_snapshot()`
  - Reads all families and returns a single payload with grid/status metadata.

- `fetch_tip_map(family_id)`
  - Reads both tables for one family and maps rack/position -> normalized status.

- `apply_updates(family_id, updates)`
  - Validates family/rack/position/status.
  - Deduplicates by `(labware_id, position_id)`.
  - Splits updates by ColA/ColB and writes with `executemany`.

- `reset_family(family_id)`
  - Converts reset map to full position updates and reuses `apply_updates`.

---

## 7. Validation Rules

- `family_id` must exist in `TIP_FAMILY_CONFIGS`.
- `position_id` must be 1..96.
- `status` must be in `STATUS_ORDER`.
- `labware_id` must belong to the target family.

Validation errors raise `TipTrackingValidationError` and return 4xx responses.

---

## 8. Auditing and Logging

Write operations use `log_action(...)` with:
- action: `tip_tracking_update` or `tip_tracking_reset`
- scope: `labware`
- actor and client IP
- success/failure details

Keep this auditing when extending write functionality.

---

## 9. Extending Safely

If you add features (example: plate tracking):

1. Create a separate service module (do not overload tip service).
2. Add new endpoints under `/api/labware/...` with explicit role/locality checks.
3. Reuse `require_local_access` for any state-changing operation.
4. Add tests that cover:
   - role rejection,
   - remote write rejection,
   - local write success.

---

## 10. Troubleshooting

1. `500 Unable to load tip tracking state`:
   - Verify SQL Server connectivity and `ROBOTCONTROL_LABWARE_DATABASE` value.
   - Verify ODBC driver availability.

2. Updates always rejected with local-access error:
   - Check reverse proxy `X-Forwarded-For` behavior.
   - Confirm client IP resolves to local classification.

3. Family not found errors:
   - Confirm payload `family` exactly matches configured IDs.

4. Updates report success but data unchanged:
   - Validate rack names match table rows exactly.
   - Check if table rows for those rack/position combinations exist.

