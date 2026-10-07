"""Per-plate charts and the Excel workbook for the plate data export.

Propagated cultures are blue and solid; cultures that were not propagated are orange
and dotted, so the split never relies on colour alone.

RobotControl package: the matplotlib figure (time course, ranking and growth panels, saved
as a PNG beside the workbook) is replaced by one native Excel chart per plate sheet that
draws the time course the same way. Its points live on a hidden "Chart data" sheet.
"""

from datetime import datetime
import math
from pathlib import Path

import pandas as pd

from .plate_export import build_plate, wide_readings
from .runtime import discard_log


PROPAGATED = "2A78D6"
NOT_PROPAGATED = "EB6834"
MUTED = "898781"
GRID = "E1E0D9"
CHART_DATA = "Chart data"


# ---------------------------------------------------------------- chart

def plate_title(plate):
    meta = plate.plate
    parents = f", parent plate {meta['ParentPlates']}" if meta.get("ParentPlates") else ""
    return f"Plate {meta['PlateID']} ({meta.get('BarCode') or 'no barcode'}), generation {meta['Generation']}{parents}"


def time_course(plate):
    """The time-course figure's lines: positive OD per culture, in the figure's order.

    Returns (lines, lone, events, start): ``lines`` and ``lone`` map True (propagated) or
    False to lists of [(hours, od), ...]; a culture with one reading is ``lone`` (a dot).
    """
    readings = plate.readings
    lines, lone = {True: [], False: []}, {True: [], False: []}
    for culture, rows in readings.groupby("CultureID", sort=False):
        rows = rows[rows["TotalOD"] > 0].sort_values("TimeStamp")
        propagated = bool(rows["Propagated"].iloc[0]) if len(rows) else False
        points = list(zip(rows["Hours"].astype(float), rows["TotalOD"].astype(float)))
        if len(points) == 1:
            lone[propagated].append(points)
        elif points:
            lines[propagated].append(points)
    start = readings["TimeStamp"].min()
    events = [(event.Event, (event.EventTime - start).total_seconds() / 3600) for event in plate.events.itertuples()]
    return lines, lone, events, start


def _write_runs(ws, column, runs, label):
    """Write runs of (x, y) points into two columns, a blank row between runs.

    The chart shows blank cells as gaps, so one series draws many separate lines.
    Returns the last row written (1 when there are no points).
    """
    ws.cell(row=1, column=column, value=f"{label} hours")
    ws.cell(row=1, column=column + 1, value=f"{label} OD")
    row = 1
    for points in runs:
        if row > 1:
            row += 1
        for x, y in points:
            row += 1
            ws.cell(row=row, column=column, value=x)
            ws.cell(row=row, column=column + 1, value=y)
    return row


def add_chart(workbook, ws, plate, anchor):
    """Draw the plate's time course as a native Excel scatter chart at ``anchor``.

    All propagated cultures form one series and all others another, so the legend has two
    entries however many cultures the plate holds. Returns False when nothing can be drawn.
    """
    from openpyxl.chart import Reference, ScatterChart, Series
    from openpyxl.chart.axis import ChartLines
    from openpyxl.chart.marker import Marker
    from openpyxl.chart.shapes import GraphicalProperties
    from openpyxl.drawing.line import LineProperties

    lines, lone, events, start = time_course(plate)
    ods = [y for group in (*lines.values(), *lone.values()) for points in group for _, y in points]
    if not ods:
        return False
    # Log base 2 keeps a narrow OD range (often within one decade) from filling a tenth of the
    # plot; gridlines fall on doublings, and the axis bounds also span the propagation lines.
    low = 2.0 ** math.floor(math.log2(min(ods)))
    high = 2.0 ** math.ceil(math.log2(max(ods)))
    if high <= low:
        high = low * 2

    if CHART_DATA not in workbook.sheetnames:
        workbook.create_sheet(CHART_DATA).sheet_state = "hidden"
    data = workbook[CHART_DATA]
    first = data.max_column + 1 if data.max_row > 1 or data["A1"].value is not None else 1
    name = f"Plate {plate.plate['PlateID']}"
    blocks = [
        # (runs, legend, colour, dotted, lone-reading dot filled)
        (lines[False], "Not propagated", NOT_PROPAGATED, True, None),
        (lone[False], "Not propagated, one reading", NOT_PROPAGATED, None, False),
        (lines[True], "Propagated", PROPAGATED, False, None),
        (lone[True], "Propagated, one reading", PROPAGATED, None, True),
        ([[(hours, low), (hours, high)] for _, hours in events], "Propagation", MUTED, False, None),
    ]

    chart = ScatterChart()
    chart.style = None
    title = f"{plate_title(plate)}: OD over time, one line per culture"
    if not events:
        title += " (no propagation recorded from this plate yet)"
    chart.title = title
    chart.display_blanks = "gap"
    chart.width, chart.height = 32, 13
    chart.legend.position = "t"
    chart.x_axis.title = f"Hours since first measurement ({start:%Y-%m-%d %H:%M})"
    chart.y_axis.title = "OD (GFP + RFP, log scale)"
    chart.y_axis.scaling.logBase = 2
    chart.y_axis.scaling.min, chart.y_axis.scaling.max = low, high
    hours = [x for group in (*lines.values(), *lone.values()) for points in group for x, _ in points]
    # Readings all at one time (e.g. only the propagation reading): centre them, as the figure does.
    chart.x_axis.scaling.min, chart.x_axis.scaling.max = (0, None) if max(hours) > 0 else (-1, 1)
    chart.x_axis.number_format = "General"
    chart.y_axis.number_format = "0.0##"
    chart.x_axis.crosses = chart.y_axis.crosses = "min"
    # Without overlay=False, Excel draws the titles and legend over the plot and tick labels.
    chart.title.overlay = chart.legend.overlay = False
    for axis in (chart.x_axis, chart.y_axis):
        axis.delete = False
        axis.title.overlay = False
        axis.majorGridlines = ChartLines(spPr=GraphicalProperties(ln=LineProperties(solidFill=GRID)))

    column = first
    for runs, legend, colour, dotted, filled in blocks:
        last = _write_runs(data, column, runs, f"{name} {legend}")
        if last > 1:
            x = Reference(data, min_col=column, min_row=2, max_row=last)
            y = Reference(data, min_col=column + 1, min_row=2, max_row=last)
            series = Series(y, x, title=legend)
            series.smooth = False
            if filled is None:
                series.marker = Marker(symbol="none")
                series.graphicalProperties.line.solidFill = colour
                series.graphicalProperties.line.width = 15875  # 1.25 pt
                series.graphicalProperties.line.prstDash = "sysDot" if dotted else "solid"
            else:
                series.marker = Marker(symbol="circle", size=6)
                series.marker.graphicalProperties = GraphicalProperties(solidFill=colour if filled else None)
                if not filled:
                    series.marker.graphicalProperties.noFill = True
                series.marker.graphicalProperties.line.solidFill = colour
                series.graphicalProperties.line.noFill = True
            chart.series.append(series)
        column += 2
    ws.add_chart(chart, anchor)
    return True


# ---------------------------------------------------------------- workbook (Data.py style)

# Data.py fills by column type; propagated cultures' headers use the darker shade.
FILLS = {"id": ("E2EFDA", "A9D08E"), "od": ("FFF2CC", "FFD966"), "flu": ("F8CBAD", "F4B084"),
         "loc": ("D9E1F2", "B4C6E7"), "event": ("E7E6E6", "E7E6E6")}
CULTURE_COLUMNS = {"Plate": "Plate", "Well": "Well", "CultureID": "CultureID", "ParentCultureID": "Parent ID",
                   "ParentWell": "Parent Plate:Well", "Propagated": "Propagated", "PropagatedAt": "Propagated time",
                   "Children": "Children", "ChildWells": "Child Plate:Well", "Readings": "Readings",
                   "LastOD": "Last OD", "GrowthRate": "Growth rate"}
SELECTION_COLUMNS = {"Plate": "Plate", "EventTime": "Propagation time", "Well": "Well", "CultureID": "CultureID",
                     "OD": "OD", "RobotRank": "Robot rank", "Expected": "Expected", "Selected": "Propagated",
                     "Match": "Match", "StatusMature": "Status_mature", "GrowthRate": "Growth rate",
                     "GrowthRank": "Growth rank"}
READING_COLUMNS = {"Plate": "Plate", "TimeStamp": "time", "Hours": "cumulative Time", "Well": "Well",
                   "CultureID": "CultureID", "Table": "Table", "Iteration": "Iteration", "TotalOD": "OD",
                   "OD_FlEx482Em510": "OD_FlEx482Em510", "OD_FlEx587Em611": "OD_FlEx587Em611",
                   "FlEx482Em510": "FlEx482Em510", "FlEx587Em611": "FlEx587Em611",
                   "Status_mature": "Status_mature", "OD": "OD (DB column)", "Propagated": "Propagated"}


def _kind(header):
    name = str(header)
    if name == "event":
        return "event"
    if name.endswith("ID"):
        return "id"
    if "FlEx" in name and "OD_" not in name:
        return "flu"
    if "OD" in name:
        return "od"
    if name in ("Plate", "Well", "BarCode", "Parent plate", "Parent Plate:Well", "Child Plate:Well"):
        return "loc"
    return None


def _cell_value(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        return _cell_value(value.item())
    return value


def _write_sheet(ws, frame, freeze="B2", marked=frozenset()):
    """One table, header in row 1, styled like Data.py. ``marked`` headers get the darker shade."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    flagged = Font(color="9C0006", bold=True)
    for column, header in enumerate(frame.columns, 1):
        kind = _kind(header)
        light, dark = FILLS.get(kind, (None, None))
        cell = ws.cell(row=1, column=column, value=header)
        cell.font = Font(bold=True)
        cell.alignment = center
        if light:
            cell.fill = PatternFill("solid", fgColor=dark if header in marked else light)
        for row, value in enumerate(frame.iloc[:, column - 1], 2):
            cell = ws.cell(row=row, column=column, value=_cell_value(value))
            cell.alignment = center
            if light:
                cell.fill = PatternFill("solid", fgColor=light)
            if isinstance(cell.value, datetime):
                cell.number_format = "yyyy/mm/dd hh:mm"
            elif header == "cumulative Time":
                cell.number_format = "0.00"
            elif cell.value == "FAIL" or (header == "Match" and cell.value == "No"):
                cell.font = flagged
        ws.column_dimensions[get_column_letter(column)].width = 18 if column <= 2 else 16
    ws.freeze_panes = freeze


def plate_check(plate):
    if plate.events.empty:
        return "No propagation"
    results = set(plate.events["RankingCheck"])
    return "FAIL" if "FAIL" in results else "N/A" if "N/A" in results else "PASS"


def _overview(plates, fraction):
    rows = []
    for plate in plates:
        meta, events = plate.plate, plate.events
        compared = int(events["GrowthCompared"].sum()) if len(events) else 0
        rows.append({
            "Plate": meta["PlateID"], "BarCode": meta.get("BarCode"), "Generation": meta["Generation"],
            "Parent plate": meta.get("ParentPlates") or None, "Discarded": bool(meta.get("Discarded")),
            "Cultures": len(plate.cultures), "Propagated": int(plate.cultures["Propagated"].sum()),
            "Propagation time": "; ".join(f"{t:%Y/%m/%d %H:%M}" for t in events["EventTime"]) or None,
            "TopFractionToPropagate": fraction, "Ranking check": plate_check(plate),
            "Check note": "; ".join(n for n in events["CheckNote"] if n) or None,
            "Growth agreement": f"{int(events['GrowthOverlap'].sum())}/{compared}" if compared else None})
    return pd.DataFrame(rows)


def _with_plate(plates, attribute, columns):
    frames = [getattr(p, attribute).assign(Plate=p.plate["PlateID"]) for p in plates]
    frame = pd.concat([f for f in frames if not f.empty] or [pd.DataFrame(columns=list(columns))], ignore_index=True)
    return frame.reindex(columns=list(columns)).rename(columns=columns)


def export_plates(data, plate_ids, out_dir, log=discard_log):
    """Write the workbook, with one chart per plate sheet; returns the workbook path."""
    from openpyxl import Workbook
    from openpyxl.worksheet.hyperlink import Hyperlink
    exported_at = datetime.now()
    stem = f"Experiment_{data.experiment['ExperimentID']}_PlateHistory_{exported_at:%Y%m%d_%H%M%S}"
    out_dir = Path(out_dir)
    chosen = data.plates[data.plates["PlateID"].isin(plate_ids)]["PlateID"].tolist()
    plates = [build_plate(data, plate_id) for plate_id in chosen]

    workbook = Workbook()
    overview = workbook.active
    overview.title = "Overview"
    _write_sheet(overview, _overview(plates, data.fraction))
    _write_sheet(workbook.create_sheet("Cultures"), _with_plate(plates, "cultures", CULTURE_COLUMNS), freeze="D2")
    _write_sheet(workbook.create_sheet("Selection"), _with_plate(plates, "selection", SELECTION_COLUMNS), freeze="D2")
    _write_sheet(workbook.create_sheet("Readings"), _with_plate(plates, "readings", READING_COLUMNS), freeze="D2")
    for row, plate in enumerate(plates, 2):
        name = str(plate.plate["PlateID"])
        ws = workbook.create_sheet(name)
        wide = wide_readings(plate)
        propagated = set(plate.cultures.loc[plate.cultures["Propagated"], "Well"])
        _write_sheet(ws, wide, freeze="D2", marked={c for c in wide.columns if c.split(" ")[0] in propagated})
        add_chart(workbook, ws, plate, f"A{len(wide) + 4}")
        link = overview.cell(row=row, column=1)
        link.hyperlink = Hyperlink(ref=link.coordinate, location=f"'{name}'!A1", display=name)
        log(f"Plate {name}: {len(plate.cultures)} cultures, {len(plate.events)} propagations, check {plate_check(plate)}")
    if CHART_DATA in workbook.sheetnames:
        workbook.move_sheet(CHART_DATA, len(workbook.sheetnames) - 1 - workbook.sheetnames.index(CHART_DATA))
    path = out_dir / f"{stem}.xlsx"
    workbook.save(path)
    log(f"Saved {path}")
    return path

