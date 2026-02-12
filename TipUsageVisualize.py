import tkinter as tk
from tkinter import ttk, messagebox
import pyodbc
from collections import defaultdict
import time
from typing import List, Tuple, Optional, Dict


# CONFIG
DRIVER = "{ODBC Driver 11 for SQL Server}"   # change to 17 or 18 if needed
SERVER = r"LOCALHOST\HAMILTON"
DATABASE = "Labwares"
UID = "Hamilton"
PWD = "mkdpw:V43"
TRUSTED = "no"  # "yes" for Windows auth
TRUST_SERVER_CERT = "yes"

AUTO_REFRESH_MS = 15_000  # 15 seconds
GRID_COLS = 12            # 96 tips = 12 x 8
GRID_ROWS = 8
DOT_R = 4
CELL_W = 14
CELL_H = 14
PADDING = 10

# 1000ul racks
HT_LEFT_TOP_TO_BOTTOM = ["VER_HT_0005", "VER_HT_0001", "VER_HT_0002", "VER_HT_0006", "VER_HT_0009"]
HT_RIGHT_TOP_TO_BOTTOM = ["VER_HT_0003", "VER_HT_0004", "VER_HT_0007", "VER_HT_0008", "VER_HT_0010"]

# 300ul racks (fixed order)
ST_LEFT_TOP_TO_BOTTOM = ["VER_ST_0001", "VER_ST_0002", "VER_ST_0003", "VER_ST_0006", "VER_ST_0009"]
ST_RIGHT_TOP_TO_BOTTOM = ["VER_ST_0004", "VER_ST_0005", "VER_ST_0007", "VER_ST_0008", "VER_ST_0010"]

RESET_MAP_1000 = {
    "ColA": {
        "clean": ["VER_HT_0005", "VER_HT_0001", "VER_HT_0002", "VER_HT_0006"],
        "empty": ["VER_HT_0009"],
    },
    "ColB": {
        "clean": ["VER_HT_0003", "VER_HT_0004", "VER_HT_0007", "VER_HT_0008"],
        "empty": ["VER_HT_0010"],
    },
}

RESET_MAP_300 = {
    "ColA": {
        "clean": ["VER_ST_0001", "VER_ST_0006", "VER_ST_0003", "VER_ST_0002"],
        "empty": ["VER_ST_0009"],
    },
    "ColB": {
        "clean": ["VER_ST_0004", "VER_ST_0008", "VER_ST_0007", "VER_ST_0005"],
        "empty": ["VER_ST_0010"],
    },
}

STATUS_ORDER = ["clean", "empty", "dirty", "rinsed", "washed", "reserved", "unclear"]
STATUS_COLOR = {
    "clean":    "#22c55e",
    "empty":    "#d1d5db",
    "dirty":    "#ef4444",
    "rinsed":   "#3b82f6",
    "washed":   "#a855f7",
    "reserved": "#f59e0b",
    "unclear":  "#6b7280",
}
UNKNOWN_COLOR = "#9ca3af"


# DB
def connect():
    conn_str = (
        "DRIVER={driver};SERVER={server};DATABASE={db};UID={uid};PWD={pwd};"
        "Trusted_Connection={trusted};TrustServerCertificate={tsc};"
    ).format(
        driver=DRIVER,
        server=SERVER,
        db=DATABASE,
        uid=UID,
        pwd=PWD,
        trusted=TRUSTED,
        tsc=TRUST_SERVER_CERT,
    )
    return pyodbc.connect(conn_str, autocommit=True)


# UI helpers
def pos_to_row_col(pos: int) -> Tuple[int, int]:
    i = pos - 1
    row = i % GRID_ROWS
    col = i // GRID_ROWS
    return row, col


def col_index_from_pos(pos: int) -> int:
    i = pos - 1
    return i // GRID_ROWS


def positions_for_column(pos: int) -> List[int]:
    col = col_index_from_pos(pos)
    base = col * GRID_ROWS + 1
    return list(range(base, base + GRID_ROWS))


# Pane for a tip family
class TipPane(ttk.Frame):
    def __init__(
        self,
        master,
        title: str,
        left_racks: List[str],
        right_racks: List[str],
        table_cola: str,
        table_colb: str,
        reset_map: Dict[str, Dict[str, List[str]]],
        clean_exclude: Optional[Tuple[str, ...]] = None,
        non_dirty_exclude: Optional[Tuple[str, ...]] = None,
    ):
        super().__init__(master)

        self.title_text = title
        self.left_racks = left_racks
        self.right_racks = right_racks
        self.cola_set = set(left_racks)
        self.colb_set = set(right_racks)
        self.table_cola = table_cola
        self.table_colb = table_colb
        self.reset_map = reset_map
        self.clean_exclude = tuple(clean_exclude) if clean_exclude else None
        self.non_dirty_exclude = tuple(non_dirty_exclude) if non_dirty_exclude else None

        self.tipmap = defaultdict(dict)   # labware -> {pos: status}
        self.pending: Dict[Tuple[str, int], str] = {}  # (labware, pos) -> new_status
        self.dot_items: Dict[int, Tuple[str, int]] = {}  # canvas item id -> (labware, pos)
        self.selected: Optional[Tuple[str, int]] = None  # (labware, pos)

        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x", pady=6, padx=8)

        ttk.Label(toolbar, text=self.title_text, font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 12))
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Save", command=self.on_save).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Discard Changes", command=self.discard_changes).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Reset", command=self.on_reset).pack(side="left", padx=4)

        self.pending_var = tk.StringVar(value="Pending: 0")
        ttk.Label(toolbar, textvariable=self.pending_var).pack(side="left", padx=16)

        self.last_ref_var = tk.StringVar(value=" ")
        ttk.Label(toolbar, textvariable=self.last_ref_var).pack(side="right")

        panel = ttk.Frame(self)
        panel.pack(side="right", fill="y", padx=8, pady=6)

        ttk.Label(panel, text="Selected Tip").pack(anchor="w")
        self.sel_lab_var = tk.StringVar(value="-")
        self.sel_pos_var = tk.StringVar(value="-")
        self.sel_status_var = tk.StringVar(value="-")
        ttk.Label(panel, textvariable=self.sel_lab_var).pack(anchor="w")
        ttk.Label(panel, textvariable=self.sel_pos_var).pack(anchor="w")
        ttk.Label(panel, textvariable=self.sel_status_var).pack(anchor="w")

        ttk.Label(panel, text="Set status").pack(anchor="w", pady=(10, 2))
        self.status_choice = tk.StringVar(value=STATUS_ORDER[0])
        ttk.Combobox(
            panel,
            textvariable=self.status_choice,
            values=STATUS_ORDER,
            width=12,
            state="readonly",
        ).pack(anchor="w")

        ttk.Button(panel, text="Apply to Tip", command=self.apply_to_tip).pack(anchor="w", pady=4)
        ttk.Button(panel, text="Apply to Column (8)", command=self.apply_to_column).pack(anchor="w", pady=2)

        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=8)

        ttk.Label(panel, text="Apply to Rack").pack(anchor="w")
        rack_values = self.left_racks + self.right_racks
        self.rack_choice = tk.StringVar(value=rack_values[0] if rack_values else "")
        ttk.Combobox(
            panel,
            textvariable=self.rack_choice,
            values=rack_values,
            width=18,
            state="readonly",
        ).pack(anchor="w")

        self.rack_status_choice = tk.StringVar(value="clean")
        ttk.Combobox(
            panel,
            textvariable=self.rack_status_choice,
            values=STATUS_ORDER,
            width=12,
            state="readonly",
        ).pack(anchor="w", pady=2)

        ttk.Button(panel, text="Apply to Whole Rack", command=self.apply_to_rack).pack(anchor="w", pady=4)
        ttk.Label(panel, text="Queued, click Save to write to DB").pack(anchor="w")

        self.canvas = tk.Canvas(self, bg="#f9fafb")
        self.canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        self.after(200, self.refresh)
        self.after(AUTO_REFRESH_MS, self._tick)

    # DB ops
    def fetch_tip_map(self):
        q = """
            SELECT labware_id, position_id, status FROM {cola}
            UNION ALL
            SELECT labware_id, position_id, status FROM {colb}
        """.format(cola=self.table_cola, colb=self.table_colb)

        tipmap = defaultdict(dict)
        with connect() as conn:
            cur = conn.cursor()
            cur.execute(q)
            for labware_id, pos, status in cur.fetchall():
                tipmap[str(labware_id)][int(pos)] = str(status).lower().strip()
        return tipmap

    def save_changes(self, changes: Dict[Tuple[str, int], str]) -> int:
        if not changes:
            return 0

        cola_updates = []
        colb_updates = []
        for (lw, pos), new_status in changes.items():
            if lw in self.cola_set:
                cola_updates.append((new_status, lw, pos))
            elif lw in self.colb_set:
                colb_updates.append((new_status, lw, pos))

        updated = 0
        with connect() as conn:
            cur = conn.cursor()
            if cola_updates:
                cur.executemany(
                    "UPDATE {cola} SET status=? WHERE labware_id=? AND position_id=?".format(cola=self.table_cola),
                    cola_updates,
                )
                updated += cur.rowcount if cur.rowcount != -1 else len(cola_updates)
            if colb_updates:
                cur.executemany(
                    "UPDATE {colb} SET status=? WHERE labware_id=? AND position_id=?".format(colb=self.table_colb),
                    colb_updates,
                )
                updated += cur.rowcount if cur.rowcount != -1 else len(colb_updates)
        return updated

    # Draw
    def draw(self):
        self.canvas.delete("all")
        self.dot_items.clear()

        col_gap = 40
        rack_w = GRID_COLS * CELL_W + 2 * PADDING
        rack_h = GRID_ROWS * CELL_H + 2 * PADDING
        left_x = 20
        right_x = left_x + rack_w + col_gap
        top_y = 40
        v_gap = 18

        self.canvas.create_text(left_x, 20, text="ColA", anchor="w", font=("Segoe UI", 11, "bold"))
        self.canvas.create_text(right_x, 20, text="ColB", anchor="w", font=("Segoe UI", 11, "bold"))

        y = top_y
        for lw in self.left_racks:
            self.draw_rack(left_x, y, lw, self.tipmap.get(lw, {}))
            y += rack_h + v_gap

        y = top_y
        for lw in self.right_racks:
            self.draw_rack(right_x, y, lw, self.tipmap.get(lw, {}))
            y += rack_h + v_gap

        legend_x = right_x + rack_w + 24
        legend_y = top_y
        self.canvas.create_text(legend_x, legend_y - 12, text="Legend", font=("Segoe UI", 10, "bold"), anchor="w")
        for k in STATUS_ORDER:
            legend_y += 18
            color = STATUS_COLOR.get(k, UNKNOWN_COLOR)
            self.canvas.create_oval(legend_x, legend_y, legend_x + 12, legend_y + 12, fill=color, outline="white")
            self.canvas.create_text(legend_x + 20, legend_y + 6, text=k, anchor="w", font=("Segoe UI", 9))

    def draw_rack(self, x: int, y: int, labware_id: str, tips_for_labware: Dict[int, str]):
        rack_w = GRID_COLS * CELL_W + 2 * PADDING
        rack_h = GRID_ROWS * CELL_H + 2 * PADDING
        self.canvas.create_rectangle(x, y, x + rack_w, y + rack_h, outline="#93c5fd", width=2)
        self.canvas.create_text(
            x + rack_w / 2,
            y - 8,
            text=labware_id,
            fill="#111827",
            font=("Segoe UI", 9, "bold"),
        )

        for pos in range(1, GRID_COLS * GRID_ROWS + 1):
            row, col = pos_to_row_col(pos)
            cx = x + PADDING + col * CELL_W + CELL_W / 2
            cy = y + PADDING + row * CELL_H + CELL_H / 2
            status = self.pending.get((labware_id, pos), tips_for_labware.get(pos, None))
            color = STATUS_COLOR.get(status, UNKNOWN_COLOR)
            oid = self.canvas.create_oval(
                cx - DOT_R,
                cy - DOT_R,
                cx + DOT_R,
                cy + DOT_R,
                fill=color,
                outline="white",
                width=1,
            )
            self.dot_items[oid] = (labware_id, pos)

    # Interactions
    def on_canvas_click(self, event):
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for oid in reversed(items):
            if oid in self.dot_items:
                lw, pos = self.dot_items[oid]
                self.select_tip(lw, pos)
                return

    def select_tip(self, labware_id: str, pos: int):
        self.selected = (labware_id, pos)
        current = self.pending.get((labware_id, pos), self.tipmap.get(labware_id, {}).get(pos, "-"))
        self.sel_lab_var.set("Labware: {0}".format(labware_id))
        self.sel_pos_var.set("Position: {0}".format(pos))
        self.sel_status_var.set("Current: {0}".format(current))

    def apply_to_tip(self):
        if not self.selected:
            messagebox.showinfo("No selection", "Click a tip to select it first.")
            return
        lw, pos = self.selected
        new_status = self.status_choice.get()
        self.pending[(lw, pos)] = new_status
        self.pending_var.set("Pending: {0}".format(len(self.pending)))
        self.refresh_preview_only()

    def apply_to_column(self):
        if not self.selected:
            messagebox.showinfo("No selection", "Click a tip to select it first.")
            return
        lw, pos = self.selected
        new_status = self.status_choice.get()
        for p in positions_for_column(pos):
            self.pending[(lw, p)] = new_status
        self.pending_var.set("Pending: {0}".format(len(self.pending)))
        self.refresh_preview_only()

    def apply_to_rack(self):
        lw = self.rack_choice.get()
        if not lw:
            return
        new_status = self.rack_status_choice.get()
        for pos in range(1, GRID_ROWS * GRID_COLS + 1):
            self.pending[(lw, pos)] = new_status
        self.pending_var.set("Pending: {0}".format(len(self.pending)))
        self.refresh_preview_only()

    def discard_changes(self):
        if not self.pending:
            return
        if not messagebox.askyesno("Discard", "Discard all pending changes?"):
            return
        self.pending.clear()
        self.pending_var.set("Pending: 0")
        self.refresh()

    def on_save(self):
        if not self.pending:
            messagebox.showinfo("Nothing to save", "No pending changes.")
            return
        try:
            updated = self.save_changes(self.pending)
            self.pending.clear()
            self.pending_var.set("Pending: 0")
            messagebox.showinfo("Saved", "Updated {0} positions.".format(updated))
            self.refresh()
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def on_reset(self):
        if self.pending:
            if not messagebox.askyesno(
                "Reset",
                "Reset will discard pending changes and write the initial state to the database. Continue?",
            ):
                return
            self.pending.clear()
            self.pending_var.set("Pending: 0")

        changes: Dict[Tuple[str, int], str] = {}

        for col_name, status_map in self.reset_map.items():
            for status, racks in status_map.items():
                for rack in racks:
                    for pos in range(1, GRID_ROWS * GRID_COLS + 1):
                        changes[(rack, pos)] = status

        try:
            updated = self.save_changes(changes)
            messagebox.showinfo("Reset", "Reset complete. Updated {0} positions.".format(updated))
            self.refresh()
        except Exception as e:
            messagebox.showerror("Reset failed", str(e))

    # Refresh
    def refresh(self):
        if self.pending:
            self.last_ref_var.set(time.strftime("Pending changes, last DB read: %H:%M:%S"))
            self.draw()
            return
        try:
            self.tipmap = self.fetch_tip_map()
            self.last_ref_var.set(time.strftime("Last DB read: %H:%M:%S"))
            self.draw()
        except Exception as e:
            self.last_ref_var.set("Error: {0}".format(e))

    def refresh_preview_only(self):
        self.draw()

    def _tick(self):
        self.refresh()
        self.after(AUTO_REFRESH_MS, self._tick)


# APP
class TipApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tip Usage Viewer and Editor")
        self.geometry("980x900")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        pane_1000 = TipPane(
            master=nb,
            title="1000ul tips",
            left_racks=HT_LEFT_TOP_TO_BOTTOM,
            right_racks=HT_RIGHT_TOP_TO_BOTTOM,
            table_cola="dbo.TipUsage_ColA",
            table_colb="dbo.TipUsage_ColB",
            reset_map=RESET_MAP_1000,
        )
        nb.add(pane_1000, text="1000ul")

        pane_300 = TipPane(
            master=nb,
            title="300ul tips",
            left_racks=ST_LEFT_TOP_TO_BOTTOM,
            right_racks=ST_RIGHT_TOP_TO_BOTTOM,
            table_cola="dbo.TipUsage_300ul_ColA",
            table_colb="dbo.TipUsage_300ul_ColB",
            reset_map=RESET_MAP_300,
        )
        nb.add(pane_300, text="300ul")


if __name__ == "__main__":
    app = TipApp()
    app.mainloop()