"""Pure Champions fluorescence, selection and transfer planning.

Version 1 preserves the legacy calibration and volume cap. Well allocation is
column-major and total OD is the sum of the fluorescence-derived components.
"""

from collections import Counter
from copy import deepcopy
import json
import math
import re


PLAN_VERSION = 1
PROPAGATION_FRACTIONS = (0.25, 0.5, 1.0)
PARAMETER_NAMES = ("TargetWellVolume", "InoculationOD", "TopFractionToPropagate", "V_OD_Sample")


def finite_number(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{label} must be a finite number.") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number.")
    return number


def validate_fraction(value):
    fraction = finite_number(value, "TopFractionToPropagate")
    if fraction not in PROPAGATION_FRACTIONS:
        raise ValueError("TopFractionToPropagate must be 0.25, 0.5 or 1 (25%, 50% or 100%).")
    return fraction


def well_key(well):
    """Use the existing 96-well address space, without lexical column sorting."""
    if not isinstance(well, str) or not re.fullmatch(r"[A-H](?:[1-9]|1[0-2])", well):
        raise ValueError(f"Invalid 96-well address: {well!r}.")
    return int(well[1:]), ord(well[0]) - ord("A") + 1


def culture_id(plate_id, well):
    column, row = well_key(well)
    result = plate_id * 100000 + column * 100 + row
    if not 0 < result <= 2147483647:
        raise ValueError("Generated culture ID is outside the SQL int range.")
    return result


def corrected_readings(gfp, rfp):
    gfp = max(10.0, finite_number(gfp, "GFP reading"))
    rfp = max(10.0, finite_number(rfp, "RFP reading"))
    denominator = 4669.1 * 2262.3 + 773.1 * 305.0
    od_gfp = (2262.3 * gfp - 773.1 * rfp) / denominator
    od_rfp = (4669.1 * rfp - 305.0 * gfp) / denominator
    total = od_gfp + od_rfp
    for value in (od_gfp, od_rfp, total):
        finite_number(value, "Corrected OD")
    if total <= 0:
        raise ValueError("Combined fluorescence-derived OD must be positive.")
    # Individual components may be negative under the legacy unmixing formula.
    return {"gfp": gfp, "rfp": rfp, "od_gfp": od_gfp, "od_rfp": od_rfp, "od": total}


def rank_for_propagation(history, fraction):
    """Rank by OD (ties column-major, then CultureID) and keep the top fraction.

    Shared by planning and by exports that check what the robot selected.
    """
    splits = int(1 / validate_fraction(fraction))
    ranked = sorted(history, key=lambda s: (-s["od"], *well_key(s["well"]), s["culture_id"]))
    return ranked, ranked[:len(ranked) // splits]


def validate_parameters(parameters):
    values = {name: finite_number(parameters.get(name), name) for name in PARAMETER_NAMES}
    validate_fraction(values["TopFractionToPropagate"])
    target = values["TargetWellVolume"]
    if target <= 0 or values["InoculationOD"] <= 0:
        raise ValueError("TargetWellVolume and InoculationOD must be positive.")
    if not 0 <= values["V_OD_Sample"] < target:
        raise ValueError("V_OD_Sample must be nonnegative and below TargetWellVolume.")
    return values


def calculate_plan(snapshot, source_labware, spillover_labware, layout_path):
    """Return a JSON-compatible plan. This function performs no I/O."""
    snapshot = deepcopy(snapshot)
    params = validate_parameters(snapshot["parameters"])
    snapshot["parameters"] = params
    target = params["TargetWellVolume"]
    sample = params["V_OD_Sample"]
    splits = int(1 / params["TopFractionToPropagate"])
    sources = snapshot["sources"]
    if not sources:
        raise ValueError("No eligible source cultures.")
    if len(sources) % splits:
        raise ValueError(f"{len(sources)} eligible cultures is not divisible by split count {splits}.")
    if len({s["culture_id"] for s in sources}) != len(sources) or len({s["well"] for s in sources}) != len(sources):
        raise ValueError("Duplicate source culture or well.")
    history = []
    for source in sorted(sources, key=lambda s: (*well_key(s["well"]), s["culture_id"])):
        if not isinstance(source["iteration"], int) or source["iteration"] < 1:
            raise ValueError("Invalid source history iteration.")
        history.append({**source, **corrected_readings(source["raw_gfp"], source["raw_rfp"]),
                        "next_iteration": source["iteration"] + 1,
                        "dilution_factor": target / (target - sample), "mature": False})
    _, selected = rank_for_propagation(history, params["TopFractionToPropagate"])
    for source in selected:
        source["mature"] = True
    selected.sort(key=lambda s: (*well_key(s["well"]), s["culture_id"]))

    available = sorted(snapshot["destinations"], key=lambda d: (d["plate_id"], *well_key(d["well"])))
    if len({(d["plate_id"], d["well"]) for d in available}) != len(available):
        raise ValueError("Duplicate available destination well.")
    if any(d["plate_id"] == snapshot["context"]["source_plate_id"] for d in available):
        raise ValueError("Source plate cannot be used as the destination labware.")
    if len(available) < len(sources):
        raise ValueError(f"Insufficient destination capacity: need {len(sources)}, have {len(available)}.")
    destinations = available[:len(sources)]
    if len({d["plate_id"] for d in destinations}) != 1:
        raise ValueError("Allocation requires multiple destination plates; VENUS supports one per invocation.")
    identities = {(d["barcode"], tuple(d["cytomat_positions"])) for d in destinations}
    if len(identities) != 1:
        raise ValueError("Inconsistent destination plate metadata.")
    barcode, positions = identities.pop()
    if not barcode or len(positions) != 1 or not isinstance(positions[0], int) or positions[0] < 0:
        raise ValueError("Destination requires exactly one valid Cytomat location and a barcode.")

    limit = target / 3.0 / splits
    transfers = []
    for round_index in range(splits):
        for parent in selected:
            destination = destinations[len(transfers)]
            inoculation = min(params["InoculationOD"] * target / parent["od"], limit)
            dilution = inoculation / target
            transfers.append({
                "round": round_index + 1, "parent_culture_id": parent["culture_id"],
                "source_well": parent["well"], "child_culture_id": culture_id(destination["plate_id"], destination["well"]),
                "destination_plate_id": destination["plate_id"], "destination_barcode": barcode,
                "destination_well": destination["well"], "cytomat_position": positions[0],
                "culture_volume": inoculation, "media_volume": target - inoculation,
                **{key: parent[key] * dilution for key in ("od", "gfp", "rfp", "od_gfp", "od_rfp")},
            })
    plan = {"version": PLAN_VERSION, "snapshot": snapshot,
            "export": {"source_labware": source_labware, "spillover_labware": spillover_labware,
                       "layout_path": layout_path}, "parent_history": history, "transfers": transfers}
    validate_plan(plan)
    return plan


def validate_plan(plan):
    if plan.get("version") != PLAN_VERSION:
        raise ValueError("Unsupported saved propagation plan version.")
    context = plan["snapshot"]["context"]
    run_id = context["run_id"]
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,255}", run_id):
        raise ValueError("Run ID must be a safe task-file identifier.")
    for value in plan["export"].values():
        if not isinstance(value, str) or not value or any(c in value for c in ",\r\n"):
            raise ValueError("Labware/layout values must be nonempty and contain no CSV separators.")
    params = validate_parameters(plan["snapshot"]["parameters"])
    rows = plan["transfers"]
    splits = int(1 / params["TopFractionToPropagate"])
    if not rows or len(rows) != len(plan["snapshot"]["sources"]):
        raise ValueError("Transfer count must equal the eligible population.")
    if len({r["child_culture_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate destination culture ID.")
    counts = Counter(r["parent_culture_id"] for r in rows)
    if any(count != splits for count in counts.values()):
        raise ValueError("Every selected parent must have the exact split count.")
    withdrawals = Counter()
    for row in rows:
        for key in ("culture_volume", "media_volume", "od", "gfp", "rfp", "od_gfp", "od_rfp"):
            finite_number(row[key], key)
        if row["culture_volume"] <= 0 or row["media_volume"] < 0:
            raise ValueError("Invalid transfer volume.")
        if not math.isclose(row["culture_volume"] + row["media_volume"], params["TargetWellVolume"], rel_tol=1e-12):
            raise ValueError("Transfer volumes do not sum to target volume.")
        withdrawals[row["parent_culture_id"]] += row["culture_volume"]
    remaining = params["TargetWellVolume"] - params["V_OD_Sample"]
    if any(v > remaining + 1e-9 for v in withdrawals.values()):
        raise ValueError("Total withdrawal exceeds culture remaining after OD sampling.")


def serialize_plan(plan):
    validate_plan(plan)
    return json.dumps(plan, sort_keys=True, separators=(",", ":"), allow_nan=False)


def deserialize_plan(payload):
    plan = json.loads(payload)
    validate_plan(plan)
    expected = calculate_plan(plan["snapshot"], **plan["export"])
    if plan != expected:
        raise ValueError("Saved propagation plan does not match its input snapshot.")
    return plan
