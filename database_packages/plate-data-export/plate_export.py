"""Read-only, plate-centric export of culture readings and propagation selection.

Loaders only SELECT; ``build_plate`` is pure so the selection check can be tested
without SQL Server. The ranking rule is the robot's own ``rank_for_propagation``.
"""

from dataclasses import dataclass
import math

import pandas as pd

from .propagation import rank_for_propagation, validate_fraction, well_key
from .propagation_store import query


READING_COLUMNS = ["CultureID", "Table", "Iteration", "TimeStamp", "OD", "FlEx482Em510", "FlEx587Em611",
                   "OD_FlEx482Em510", "OD_FlEx587Em611", "Status_mature"]
EDGE_COLUMNS = ["ParentCultureID", "ParentPlateID", "ParentWellID",
                "ChildCultureID", "ChildPlateID", "ChildWellID", "ChildBirth"]
PLATE_COLUMNS = ["PlateID", "BarCode", "Description", "Discarded", "Generation", "ParentPlates", "Cultures"]
SELECTION_COLUMNS = ["Event", "EventTime", "Well", "CultureID", "OD", "RobotRank", "Expected", "Selected", "Match",
                     "StatusMature", "GrowthRate", "GrowthRank"]
EVENT_COLUMNS = ["Event", "EventTime", "Eligible", "Expected", "Selected", "Mismatches", "RankingCheck", "CheckNote",
                 "GrowthCompared", "GrowthOverlap"]
CULTURES_TABLE = "CulturesHistory"
CHAMPIONS_TABLE = "ChampionsCulturesHistory"


@dataclass
class ExperimentData:
    experiment: dict
    fraction: float | None
    plates: pd.DataFrame
    cultures: pd.DataFrame
    readings: pd.DataFrame
    edges: pd.DataFrame


@dataclass
class PlateExport:
    plate: dict
    fraction: float | None
    cultures: pd.DataFrame
    selection: pd.DataFrame
    events: pd.DataFrame
    readings: pd.DataFrame


# ---------------------------------------------------------------- queries

def _in(values):
    return ",".join("?" * len(values))


def _frame(rows, columns):
    return pd.DataFrame(rows, columns=columns)


def list_experiments(cursor):
    """Experiments that have ancestor plates, newest first, with their first reading time."""
    experiments = query(cursor, "SELECT ExperimentID, UserDefinedID, Note, ScheduledToRun FROM dbo.Experiments")
    starts = {}
    for row in query(cursor, """
        SELECT a.ExperimentID, MIN(h.TimeStamp) AS Started
        FROM dbo.AncestPlatesInExperiments a
        LEFT JOIN dbo.Cultures c ON c.PlateID=a.PlateID
        LEFT JOIN dbo.CulturesHistory h ON h.CultureID=c.CultureID
        GROUP BY a.ExperimentID
    """):
        starts[row["ExperimentID"]] = row["Started"]
    rows = [{**e, "Started": starts[e["ExperimentID"]]} for e in experiments if e["ExperimentID"] in starts]
    return sorted(rows, key=lambda e: e["ExperimentID"], reverse=True)


def plate_generations(plate_ids, links):
    """Generation per plate (ancestors are 0) and sorted parent plates, from plate-level links."""
    plate_ids = set(plate_ids)
    parents = {p: sorted(set(links.loc[links["ChildPlateID"] == p, "ParentPlateID"]) & plate_ids - {p})
               for p in plate_ids}
    generations = {}

    def generation(plate, seen=()):
        if plate not in generations:
            ups = [q for q in parents[plate] if q not in seen]
            generations[plate] = 1 + max(generation(q, (*seen, plate)) for q in ups) if ups else 0
        return generations[plate]

    for plate in plate_ids:
        generation(plate)
    return generations, parents


def experiment_plates(cursor, experiment_id):
    """All plates in the experiment chain, with lineage generation and culture counts."""
    roots = [r["PlateID"] for r in query(cursor,
             "SELECT DISTINCT PlateID FROM dbo.AncestPlatesInExperiments WHERE ExperimentID=?", (experiment_id,))]
    ids = set(roots)
    for root in roots:
        # Descendants() can list a plate more than once.
        ids.update(r["DescPlateID"] for r in query(cursor, "SELECT DISTINCT DescPlateID FROM dbo.Descendants(?)", (root,)))
    ids = sorted(i for i in ids if i is not None)
    if not ids:
        return _frame([], PLATE_COLUMNS)
    plates = _frame(query(cursor, f"""
        SELECT p.PlateID, p.BarCode, p.Description, p.Discarded,
               (SELECT COUNT(*) FROM dbo.Cultures c WHERE c.PlateID=p.PlateID AND c.WellID IS NOT NULL) AS Cultures
        FROM dbo.Plates p WHERE p.PlateID IN ({_in(ids)})
    """, ids), ["PlateID", "BarCode", "Description", "Discarded", "Cultures"])
    # Anchor cultures (no well) chain plates for storage, not lineage; ignore them.
    links = _frame(query(cursor, f"""
        SELECT DISTINCT pc.PlateID AS ParentPlateID, cc.PlateID AS ChildPlateID
        FROM dbo.Propagation pr
        JOIN dbo.Cultures pc ON pc.CultureID=pr.ParentCultureID
        JOIN dbo.Cultures cc ON cc.CultureID=pr.ChldCultureID
        WHERE pc.WellID IS NOT NULL AND cc.WellID IS NOT NULL AND cc.PlateID IN ({_in(ids)})
    """, ids), ["ParentPlateID", "ChildPlateID"])
    generations, parents = plate_generations(plates["PlateID"].tolist(), links)
    plates["Generation"] = plates["PlateID"].map(generations)
    plates["ParentPlates"] = plates["PlateID"].map(lambda p: ", ".join(map(str, parents[p])))
    return plates[PLATE_COLUMNS].sort_values(["Generation", "PlateID"], ignore_index=True)


def _fraction(cursor, experiment_id):
    value = query(cursor, """
        SELECT ParamValueTxt AS value FROM dbo.ExperimentParameters
        WHERE ExperimentID=? AND ParameterName='TopFractionToPropagate'
    """, (experiment_id,))
    try:
        return validate_fraction(value[0]["value"]) if len(value) == 1 else None
    except ValueError:
        return None


def load_experiment(cursor, experiment_id, plates, plate_ids):
    """Load cultures, readings from both history tables and lineage for the chosen plates."""
    plate_ids = [int(p) for p in plate_ids]
    experiment = query(cursor, "SELECT ExperimentID, UserDefinedID, Note FROM dbo.Experiments WHERE ExperimentID=?",
                       (experiment_id,))[0]
    cultures = _frame(query(cursor, f"""
        SELECT CultureID, PlateID, WellID FROM dbo.Cultures
        WHERE WellID IS NOT NULL AND PlateID IN ({_in(plate_ids)})
    """, plate_ids), ["CultureID", "PlateID", "WellID"])
    has_champions = query(cursor, f"SELECT OBJECT_ID('dbo.{CHAMPIONS_TABLE}', 'U') AS id")[0]["id"] is not None
    tables = [CULTURES_TABLE] + ([CHAMPIONS_TABLE] if has_champions else [])
    readings = []
    for table in tables:
        # Table names come from the fixed list above, never from a caller.
        mature = "h.Status_mature" if table == CULTURES_TABLE else "NULL"
        readings += query(cursor, f"""
            SELECT h.CultureID, '{table}' AS [Table], h.Iteration, h.TimeStamp, h.OD,
                   h.FlEx482Em510, h.FlEx587Em611, h.OD_FlEx482Em510, h.OD_FlEx587Em611,
                   {mature} AS Status_mature
            FROM dbo.{table} h JOIN dbo.Cultures c ON c.CultureID=h.CultureID
            WHERE c.WellID IS NOT NULL AND c.PlateID IN ({_in(plate_ids)})
        """, plate_ids)
    births = " UNION ALL ".join(f"SELECT TimeStamp FROM dbo.{t} WHERE CultureID=pr.ChldCultureID" for t in tables)
    edges = query(cursor, f"""
        SELECT pr.ParentCultureID, pc.PlateID AS ParentPlateID, pc.WellID AS ParentWellID,
               pr.ChldCultureID AS ChildCultureID, cc.PlateID AS ChildPlateID, cc.WellID AS ChildWellID,
               (SELECT MIN(b.TimeStamp) FROM ({births}) b) AS ChildBirth
        FROM dbo.Propagation pr
        JOIN dbo.Cultures pc ON pc.CultureID=pr.ParentCultureID
        JOIN dbo.Cultures cc ON cc.CultureID=pr.ChldCultureID
        WHERE pc.WellID IS NOT NULL AND cc.WellID IS NOT NULL
          AND (pc.PlateID IN ({_in(plate_ids)}) OR cc.PlateID IN ({_in(plate_ids)}))
    """, plate_ids * 2)
    return ExperimentData(experiment=experiment, fraction=_fraction(cursor, experiment_id), plates=plates,
                          cultures=cultures, readings=_frame(readings, READING_COLUMNS),
                          edges=_frame(edges, EDGE_COLUMNS))


# ---------------------------------------------------------------- shaping

def total_od(readings):
    """Robot OD: sum of the fluorescence-derived components; the DB OD column holds sentinels."""
    od = readings[["OD_FlEx482Em510", "OD_FlEx587Em611"]].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)
    stored = pd.to_numeric(readings["OD"], errors="coerce")
    return od.fillna(stored.where(stored > 0))


def growth_rate(hours, ods):
    """Least-squares slope of ln(OD) per hour; NaN without two positive readings."""
    points = [(float(h), math.log(float(o))) for h, o in zip(hours, ods)
              if pd.notna(h) and pd.notna(o) and float(o) > 0]
    if len(points) < 2:
        return math.nan
    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    sxx = sum((x - mean_x) ** 2 for x, _ in points)
    if sxx == 0:
        return math.nan
    return sum((x - mean_x) * (y - mean_y) for x, y in points) / sxx


def _location(plate, well):
    return f"{int(plate)}:{well}"


def _plate_readings(data, ids, wells, births):
    readings = data.readings[data.readings["CultureID"].isin(ids)].copy()
    readings["TimeStamp"] = pd.to_datetime(readings["TimeStamp"])
    # A propagated culture's first row is the robot's calculated inoculation OD (usually 0.03),
    # not a reading; drop it so hour zero is the plate's first measurement.
    # RobotControl package: map through a dict; pandas 3 cannot map through an empty datetime
    # Series (a plate without parents). The rows kept are the same as upstream under pandas 2.
    readings = readings[readings["TimeStamp"] != readings["CultureID"].map(births.to_dict())].copy()
    readings["Status_mature"] = pd.to_numeric(readings["Status_mature"], errors="coerce")
    readings["TotalOD"] = total_od(readings) if not readings.empty else pd.Series(dtype=float)
    readings["Well"] = readings["CultureID"].map(wells)
    start = readings["TimeStamp"].min()
    readings["Hours"] = (readings["TimeStamp"] - start).dt.total_seconds() / 3600
    readings["_well"] = readings["Well"].map(well_key)
    readings["_table"] = (readings["Table"] != CULTURES_TABLE).astype(int)
    return readings.sort_values(["TimeStamp", "_well", "_table"], ignore_index=True).drop(columns=["_well", "_table"])


def _growth(readings, culture, until=None):
    rows = readings[readings["CultureID"] == culture]
    if until is not None:
        rows = rows[rows["TimeStamp"] <= until]
    return growth_rate(rows["Hours"], rows["TotalOD"])


def _selection_event(number, time, readings, selected_ids, fraction):
    # Every eligible parent gets a history row at the run timestamp; prefer CulturesHistory.
    at = readings[readings["TimeStamp"] == time].sort_values("Table", key=lambda t: t != CULTURES_TABLE)
    at = at.drop_duplicates("CultureID")
    history = [{"culture_id": int(r.CultureID), "well": r.Well, "od": float(r.TotalOD),
                "mature": r.Status_mature} for r in at.itertuples() if pd.notna(r.TotalOD)]
    if not history:
        note = "no readings at the propagation time"
    elif len(history) != len(at):
        note = "an eligible culture has no OD"
    elif not selected_ids <= {h["culture_id"] for h in history}:
        note = "a propagated culture has no reading at the propagation time"
    elif fraction is None:
        note = "TopFractionToPropagate not set"
    else:
        note = ""
    checked = not note
    ranked, expected = rank_for_propagation(history, fraction if checked else 1.0)
    expected_ids = {h["culture_id"] for h in expected}
    rows = []
    for rank, h in enumerate(ranked, 1):
        actual = h["culture_id"] in selected_ids
        rows.append({"Event": number, "EventTime": time, "Well": h["well"], "CultureID": h["culture_id"],
                     "OD": h["od"], "RobotRank": rank,
                     "Expected": (h["culture_id"] in expected_ids) if checked else pd.NA,
                     "Selected": actual,
                     "Match": (actual == (h["culture_id"] in expected_ids)) if checked else pd.NA,
                     "StatusMature": h["mature"],
                     "GrowthRate": _growth(readings, h["culture_id"], time)})
    frame = pd.DataFrame(rows, columns=SELECTION_COLUMNS[:-1])
    frame["GrowthRank"] = frame["GrowthRate"].rank(ascending=False, method="min")
    chosen = frame[frame["Selected"].astype(bool)]
    compared = chosen["GrowthRate"].notna().sum()
    event = {"Event": number, "EventTime": time, "Eligible": len(at),
             "Expected": len(expected_ids) if checked else pd.NA, "Selected": len(selected_ids),
             "Mismatches": int((~frame["Match"].astype(bool)).sum()) if checked else pd.NA,
             "RankingCheck": ("PASS" if not (~frame["Match"].astype(bool)).any() else "FAIL") if checked else "N/A",
             "CheckNote": note,
             "GrowthCompared": int(compared),
             "GrowthOverlap": int((chosen["GrowthRank"] <= compared).sum()) if compared else 0}
    return frame, event


def build_plate(data, plate_id):
    """Shape one plate: culture summary, per-event selection check and long readings."""
    meta = data.plates.set_index("PlateID").loc[plate_id].to_dict()
    cultures = data.cultures[(data.cultures["PlateID"] == plate_id) & data.cultures["WellID"].notna()].copy()
    cultures["_well"] = cultures["WellID"].map(well_key)
    cultures = cultures.sort_values(["_well", "CultureID"], ignore_index=True)
    ids = set(cultures["CultureID"].astype(int))
    wells = dict(zip(cultures["CultureID"].astype(int), cultures["WellID"]))
    edges = data.edges.copy()
    edges["ChildBirth"] = pd.to_datetime(edges["ChildBirth"])
    children = edges[edges["ParentCultureID"].isin(ids)]
    parents = edges[edges["ChildCultureID"].isin(ids)]
    readings = _plate_readings(data, ids, wells, parents.groupby("ChildCultureID")["ChildBirth"].min())

    selection, events = [], []
    for number, time in enumerate(sorted(children["ChildBirth"].dropna().unique()), 1):
        selected_ids = set(children.loc[children["ChildBirth"] == time, "ParentCultureID"].astype(int))
        frame, event = _selection_event(number, pd.Timestamp(time), readings, selected_ids, data.fraction)
        selection.append(frame)
        events.append(event)

    summary = []
    for culture in cultures.itertuples():
        own = children[children["ParentCultureID"] == culture.CultureID].copy()
        own["_well"] = own["ChildWellID"].map(well_key)
        own = own.sort_values(["ChildPlateID", "_well"])
        parent = parents[parents["ChildCultureID"] == culture.CultureID]
        rows = readings[readings["CultureID"] == culture.CultureID]
        summary.append({
            "Well": culture.WellID, "CultureID": int(culture.CultureID),
            "ParentCultureID": int(parent.iloc[0]["ParentCultureID"]) if len(parent) else pd.NA,
            "ParentWell": _location(parent.iloc[0]["ParentPlateID"], parent.iloc[0]["ParentWellID"]) if len(parent) else "",
            "Propagated": not own.empty,
            "PropagatedAt": own["ChildBirth"].min() if not own.empty else pd.NaT,
            "Children": len(own),
            "ChildWells": "; ".join(_location(r.ChildPlateID, r.ChildWellID) for r in own.itertuples()),
            "Readings": len(rows),
            "LastOD": rows["TotalOD"].iloc[-1] if len(rows) else math.nan,
            "GrowthRate": _growth(readings, culture.CultureID),
        })
    summary = pd.DataFrame(summary, columns=["Well", "CultureID", "ParentCultureID", "ParentWell", "Propagated",
                                             "PropagatedAt", "Children", "ChildWells", "Readings", "LastOD",
                                             "GrowthRate"])
    summary["ParentCultureID"] = summary["ParentCultureID"].astype("Int64")
    propagated = set(summary.loc[summary["Propagated"], "CultureID"])
    readings["Propagated"] = readings["CultureID"].isin(propagated)
    readings = readings[["TimeStamp", "Hours", "Well", "CultureID", "Table", "Iteration", "TotalOD",
                         "OD_FlEx482Em510", "OD_FlEx587Em611", "FlEx482Em510", "FlEx587Em611",
                         "Status_mature", "OD", "Propagated"]]
    return PlateExport(
        plate={"PlateID": plate_id, **meta}, fraction=data.fraction, cultures=summary,
        selection=pd.concat([s for s in selection if not s.empty] or [pd.DataFrame(columns=SELECTION_COLUMNS)],
                            ignore_index=True),
        events=pd.DataFrame(events, columns=EVENT_COLUMNS), readings=readings)


WIDE_BLOCKS = (("OD", "TotalOD"), ("FlEx482Em510", "FlEx482Em510"), ("FlEx587Em611", "FlEx587Em611"),
               ("OD_FlEx482Em510", "OD_FlEx482Em510"), ("OD_FlEx587Em611", "OD_FlEx587Em611"), ("ID", "CultureID"))


def wide_readings(plate):
    """Data.py layout: one row per time (newest first), event, cumulative Time, then per-culture blocks."""
    readings = plate.readings.drop_duplicates(["TimeStamp", "CultureID"])  # CulturesHistory sorts first
    times = sorted(readings["TimeStamp"].unique(), reverse=True)
    event_times = set(plate.events["EventTime"])
    wide = pd.DataFrame({"time": pd.to_datetime(pd.Series(times, dtype="datetime64[ns]"))})
    wide["event"] = ["propagation" if t in event_times else "start" if i == len(times) - 1 else "intermediate_fl"
                     for i, t in enumerate(wide["time"])]
    start = readings["TimeStamp"].min()
    wide["cumulative Time"] = (wide["time"] - start).dt.total_seconds() / 3600
    wells = plate.cultures["Well"].tolist()
    blocks = []
    for label, column in WIDE_BLOCKS:
        table = readings.pivot(index="TimeStamp", columns="Well", values=column).reindex(index=times, columns=wells)
        if column == "CultureID":
            # Every row names the culture in the well, as Data.py did.
            table = pd.DataFrame([plate.cultures["CultureID"].tolist()] * len(times), columns=wells)
        table.columns = [f"{well} {label}" for well in wells]
        blocks.append(table.reset_index(drop=True))
    return pd.concat([wide, *blocks], axis=1)
