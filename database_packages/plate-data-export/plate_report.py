"""Per-plate charts and the Excel workbook for the plate data export.

Propagated cultures are blue and solid; cultures that were not propagated are orange
and dotted (lines), dot-patterned (bars) or open (points), so the split never relies on
colour alone.

RobotControl package: the matplotlib figure (saved as a PNG beside the workbook) is replaced
by native Excel charts on each plate sheet that draw the same panels: the time course, then
per propagation its summary line, the robot ranking and the growth scatter. Their points live
on a hidden "Chart data" sheet.
"""

from datetime import datetime
import math
from pathlib import Path

import pandas as pd

from .plate_export import build_plate, wide_readings
from .runtime import discard_log


PROPAGATED = "2A78D6"
NOT_PROPAGATED = "EB6834"
CRITICAL = "D03B3B"
INK_SECONDARY = "52514E"
MUTED = "898781"
GRID = "E1E0D9"
CHART_DATA = "Chart data"
# Rows a chart covers at Excel's default row height (20 px), plus a blank row below it.
TIME_COURSE_ROWS = 26
PANEL_ROWS = 21


# ---------------------------------------------------------------- chart

def plate_title(plate):
    meta = plate.plate
    parents = f", parent plate {meta['ParentPlates']}" if meta.get("ParentPlates") else ""
    return f"Plate {meta['PlateID']} ({meta.get('BarCode') or 'no barcode'}), generation {meta['Generation']}{parents}"


def event_summary(event):
    check = f"N/A ({event.CheckNote})" if event.RankingCheck == "N/A" else f"{event.RankingCheck}"
    growth = f", growth agreement {event.GrowthOverlap}/{event.GrowthCompared}" if event.GrowthCompared else ""
    return (f"Propagation {event.Event}, {event.EventTime:%Y-%m-%d %H:%M}: {event.Selected} of {event.Eligible} "
            f"propagated, ranking check {check}{growth}")


def event_panels(plate):
    """The figure's rows under the time course, one per propagation, as plate_figure draws them.

    Yields (event, ranking, growth): ``ranking`` is the event's Selection rows by robot rank (one
    bar each, as ``_ranking``); ``growth`` maps False/True (propagated) to its rows (as ``_growth``).
    """
    for event in plate.events.itertuples():
        rows = plate.selection[plate.selection["Event"] == event.Event]
        yield event, rows.sort_values("RobotRank"), {s: rows[rows["Selected"] == s] for s in (False, True)}


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


def _chart_data(workbook):
    """The hidden sheet holding chart points, and its first free column."""
    if CHART_DATA not in workbook.sheetnames:
        workbook.create_sheet(CHART_DATA).sheet_state = "hidden"
    data = workbook[CHART_DATA]
    return data, data.max_column + 1 if data.max_row > 1 or data["A1"].value is not None else 1


def _write_column(ws, column, header, values):
    """One labelled column of chart values; NaN becomes a blank, which the chart skips."""
    from openpyxl.chart import Reference
    ws.cell(row=1, column=column, value=header)
    for row, value in enumerate(values, 2):
        ws.cell(row=row, column=column, value=_cell_value(value))
    return Reference(ws, min_col=column, min_row=2, max_row=max(2, len(values) + 1))


def _nice_bounds(values, pad=0.05):
    """(min, max, step) on round numbers around ``values``, with a margin like the figure's.

    Set explicitly because Excel starts a value axis at 0 whenever the data's minimum is below
    5/6 of its maximum, which would squeeze OD 0.29-0.37 into the top fifth of the plot.
    """
    low, high = min(values), max(values)
    span = high - low or abs(high) or 1.0
    low, high = low - span * pad, high + span * pad
    raw = (high - low) / 5
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    return round(math.floor(low / step) * step, 10), round(math.ceil(high / step) * step, 10), step


def _style_chart(chart, title, x_title, y_title):
    """Title, axis titles and light gridlines, kept off the plot area."""
    from openpyxl.chart.axis import ChartLines
    from openpyxl.chart.shapes import GraphicalProperties
    from openpyxl.drawing.line import LineProperties
    chart.style = None
    # Excel treats a missing varyColors as on: a chart with one series (a plate with no
    # propagation yet) then gets one legend entry and one colour per point.
    chart.varyColors = False
    chart.title = title
    chart.display_blanks = "gap"
    chart.legend.position = "t"
    chart.x_axis.title, chart.y_axis.title = x_title, y_title
    # Without overlay=False, Excel draws the titles and legend over the plot and tick labels.
    chart.title.overlay = chart.legend.overlay = False
    for axis in (chart.x_axis, chart.y_axis):
        axis.delete = False
        if axis.title:
            axis.title.overlay = False
        axis.majorGridlines = ChartLines(spPr=GraphicalProperties(ln=LineProperties(solidFill=GRID)))


def _markers(series, symbol, colour, filled, size=7):
    """Points without a line: filled, or open (outline only)."""
    from openpyxl.chart.marker import Marker
    from openpyxl.chart.shapes import GraphicalProperties
    series.marker = Marker(symbol=symbol, size=size)
    series.marker.graphicalProperties = GraphicalProperties(solidFill=colour if filled else None)
    if not filled:
        series.marker.graphicalProperties.noFill = True
    series.marker.graphicalProperties.line.solidFill = colour
    series.graphicalProperties.line.noFill = True


def add_chart(workbook, ws, plate, anchor):
    """Draw the plate's time course as a native Excel scatter chart at ``anchor``.

    All propagated cultures form one series and all others another, so the legend has two
    entries however many cultures the plate holds. Returns False when nothing can be drawn.
    """
    from openpyxl.chart import Reference, ScatterChart, Series
    from openpyxl.chart.marker import Marker

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

    data, first = _chart_data(workbook)
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
    title = f"{plate_title(plate)}: OD over time, one line per culture"
    if not events:
        title += " (no propagation recorded from this plate yet)"
    _style_chart(chart, title, f"Hours since first measurement ({start:%Y-%m-%d %H:%M})", "OD (GFP + RFP, log scale)")
    chart.width, chart.height = 32, 13
    chart.y_axis.scaling.logBase = 2
    chart.y_axis.scaling.min, chart.y_axis.scaling.max = low, high
    hours = [x for group in (*lines.values(), *lone.values()) for points in group for x, _ in points]
    # Readings all at one time (e.g. only the propagation reading): centre them, as the figure does.
    chart.x_axis.scaling.min, chart.x_axis.scaling.max = (0, None) if max(hours) > 0 else (-1, 1)
    chart.x_axis.number_format = "General"
    chart.y_axis.number_format = "0.0##"
    chart.x_axis.crosses = chart.y_axis.crosses = "min"

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
                _markers(series, "circle", colour, filled, size=6)
            chart.series.append(series)
        column += 2
    ws.add_chart(chart, anchor)
    return True


def add_ranking_chart(workbook, ws, plate, event, rows, anchor):
    """The robot ranking: one bar per culture in robot-rank order, and the robot's cutoff.

    A column chart cannot draw a vertical line, so the cutoff (between rank N and N + 1) and the
    crosses where the robot rule disagrees are scatter series on the same axes, where Excel puts
    category k at x = k.
    """
    from openpyxl.chart import BarChart, ScatterChart, Series
    from openpyxl.chart.data_source import AxDataSource, StrRef
    from openpyxl.chart.text import RichText
    from openpyxl.drawing.fill import ColorChoice, PatternFillProperties
    from openpyxl.drawing.text import CharacterProperties, Paragraph, ParagraphProperties, RichTextProperties

    data, column = _chart_data(workbook)
    label = f"Plate {plate.plate['PlateID']} propagation {event.Event} ranking"
    selected = rows["Selected"].astype(bool).tolist()
    ods = rows["OD"].astype(float).tolist()
    checked = event.RankingCheck != "N/A"
    wrong = [(position, od * 1.04) for position, (od, match) in enumerate(zip(ods, rows["Match"]), 1)
             if checked and not bool(match)]
    low = min([0.0, *ods])  # bars start at zero, as the figure's; an event can have no bars
    _, high, step = _nice_bounds([low, max(ods + [y for _, y in wrong], default=low)], pad=0.04)

    chart = BarChart()
    chart.type, chart.grouping, chart.overlap, chart.gapWidth = "col", "clustered", 100, 25
    _style_chart(chart, "Robot ranking: OD at propagation, highest first", None, "OD at propagation")
    chart.width, chart.height = 22, 10
    chart.y_axis.scaling.min, chart.y_axis.scaling.max, chart.y_axis.majorUnit = low, high, step
    chart.y_axis.number_format = "0.00"
    chart.x_axis.majorGridlines = None
    chart.x_axis.tickLblSkip = 1
    chart.x_axis.txPr = RichText(bodyPr=RichTextProperties(rot=-5400000, vert="horz"), p=[Paragraph(
        pPr=ParagraphProperties(defRPr=CharacterProperties(sz=600 if len(ods) > 48 else 800)),
        endParaRPr=CharacterProperties())])
    wells = _write_column(data, column, f"{label} well", rows["Well"].tolist())
    for offset, (name, propagated) in enumerate((("Propagated", True), ("Not propagated", False)), 1):
        values = [od if s == propagated else None for od, s in zip(ods, selected)]
        series = Series(_write_column(data, column + offset, f"{label} {name} OD", values), title=name)
        series.graphicalProperties.line.solidFill = PROPAGATED if propagated else NOT_PROPAGATED
        series.graphicalProperties.line.width = 12700  # 1 pt
        if propagated:
            series.graphicalProperties.solidFill = PROPAGATED
        else:
            # The figure's dot hatch: orange dots on white, which stays distinct in greyscale.
            series.graphicalProperties.pattFill = PatternFillProperties(
                prst="pct20", fgClr=ColorChoice(srgbClr=NOT_PROPAGATED), bgClr=ColorChoice(srgbClr="FFFFFF"))
        chart.series.append(series)
    for series in chart.series:
        series.cat = AxDataSource(strRef=StrRef(f=str(wells)))

    if checked:
        overlay = ScatterChart()
        overlay.varyColors = False
        # Share the bars' axes; openpyxl otherwise adds a second, autoscaled value axis.
        overlay.x_axis, overlay.y_axis = chart.x_axis, chart.y_axis
        cutoff = event.Expected + 0.5
        x = _write_column(data, column + 3, f"{label} cutoff x", [cutoff, cutoff])
        y = _write_column(data, column + 4, f"{label} cutoff OD", [low, high])
        series = Series(y, x, title=f"Robot cutoff: top {event.Expected}")
        series.marker.symbol = "none"
        series.smooth = False
        series.graphicalProperties.line.solidFill = INK_SECONDARY
        series.graphicalProperties.line.width = 12700
        overlay.series.append(series)
        if wrong:
            x = _write_column(data, column + 5, f"{label} disagrees x", [p for p, _ in wrong])
            y = _write_column(data, column + 6, f"{label} disagrees OD", [y for _, y in wrong])
            series = Series(y, x, title="Robot rule disagrees")
            _markers(series, "x", CRITICAL, False)
            overlay.series.append(series)
        chart += overlay
    ws.add_chart(chart, anchor)


def add_growth_chart(workbook, ws, plate, event, growth, anchor):
    """Growth rate against OD at propagation: propagated filled blue, not propagated open orange."""
    from openpyxl.chart import ScatterChart, Series

    data, column = _chart_data(workbook)
    label = f"Plate {plate.plate['PlateID']} propagation {event.Event} growth"
    chart = ScatterChart()
    _style_chart(chart, "Growth rate vs OD at propagation", "OD at propagation", "Growth rate (ln OD per hour)")
    chart.width, chart.height = 9.6, 10
    for propagated, colour, name in ((False, NOT_PROPAGATED, "Not propagated"), (True, PROPAGATED, "Propagated")):
        rows = growth[propagated]
        x = _write_column(data, column, f"{label} {name} OD", rows["OD"].tolist())
        y = _write_column(data, column + 1, f"{label} {name} rate", rows["GrowthRate"].tolist())
        series = Series(y, x, title=name)
        _markers(series, "circle", colour, propagated)
        chart.series.append(series)
        column += 2
    points = pd.concat(growth.values())
    points = points[points["GrowthRate"].notna()]
    for axis, values, number_format in ((chart.x_axis, points["OD"], "0.00"),
                                        (chart.y_axis, points["GrowthRate"], "0.000")):
        if len(values):
            axis.scaling.min, axis.scaling.max, axis.majorUnit = _nice_bounds(values.astype(float).tolist())
        axis.number_format = number_format
        axis.crosses = "min"
    ws.add_chart(chart, anchor)


def add_panels(workbook, ws, plate, row):
    """From ``row`` down, per propagation: its summary line, then the ranking and growth charts.

    The growth chart starts in column H, just past the 22 cm ranking chart at the plate sheets'
    column widths (A-B 18, others 16), so the pair is as wide as the time course.
    """
    if plate.events.empty:
        ws.cell(row=row, column=1, value="No propagation recorded from this plate yet")
        return
    for event, ranking, growth in event_panels(plate):
        ws.cell(row=row, column=1, value=event_summary(event))
        add_ranking_chart(workbook, ws, plate, event, ranking, f"A{row + 1}")
        add_growth_chart(workbook, ws, plate, event, growth, f"H{row + 1}")
        row += 1 + PANEL_ROWS


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
    """Write the workbook, with the figure's charts on each plate sheet; returns the workbook path."""
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
        below = len(wide) + 4
        if add_chart(workbook, ws, plate, f"A{below}"):
            below += TIME_COURSE_ROWS
        add_panels(workbook, ws, plate, below)
        link = overview.cell(row=row, column=1)
        link.hyperlink = Hyperlink(ref=link.coordinate, location=f"'{name}'!A1", display=name)
        log(f"Plate {name}: {len(plate.cultures)} cultures, {len(plate.events)} propagations, check {plate_check(plate)}")
    if CHART_DATA in workbook.sheetnames:
        workbook.move_sheet(CHART_DATA, len(workbook.sheetnames) - 1 - workbook.sheetnames.index(CHART_DATA))
    path = out_dir / f"{stem}.xlsx"
    workbook.save(path)
    log(f"Saved {path}")
    return path

