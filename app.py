from __future__ import annotations

import csv
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from openpyxl import Workbook
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    Workbook = None

from scraper import SpeedhiveScrapeError, collect_participation


class SessionTrackerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PGP Session Participation Tracker")
        self.root.geometry("1280x760")
        self.root.minsize(1040, 640)

        self.results: dict | None = None
        self.sort_descending: dict[str, bool] = {}
        self.event_url_var = tk.StringVar()
        self.minimum_sessions_var = tk.StringVar(value="4")

        self._configure_theme()
        self._build_ui()

    def _configure_theme(self) -> None:
        self.colors = {
            "bg": "#0f1115",
            "panel": "#1b1f2a",
            "surface": "#232837",
            "gold": "#cfb991",
            "gold_bright": "#f4d35e",
            "text": "#f5f2e9",
            "muted": "#b7ae9c",
            "row_alt": "#202635",
        }

        self.root.configure(bg=self.colors["bg"])
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Root.TFrame", background=self.colors["bg"])
        style.configure("Card.TFrame", background=self.colors["panel"])
        style.configure(
            "Header.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["gold_bright"],
            font=("Segoe UI", 20, "bold"),
        )
        style.configure(
            "Sub.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "FieldLabel.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "Modern.TButton",
            background=self.colors["gold"],
            foreground="#15171f",
            borderwidth=0,
            focusthickness=2,
            focuscolor=self.colors["gold_bright"],
            padding=(16, 10),
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Modern.TButton",
            background=[("active", self.colors["gold_bright"]), ("disabled", "#756b5b")],
            foreground=[("disabled", "#d0c4ad")],
        )

        style.configure(
            "Modern.Treeview",
            background=self.colors["surface"],
            fieldbackground=self.colors["surface"],
            foreground=self.colors["text"],
            borderwidth=0,
            rowheight=34,
            font=("Segoe UI", 10),
        )
        style.map(
            "Modern.Treeview",
            background=[("selected", "#3a2f16")],
            foreground=[("selected", self.colors["gold_bright"])],
        )
        style.configure(
            "Modern.Treeview.Heading",
            background="#151925",
            foreground=self.colors["gold_bright"],
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 10, "bold"),
            padding=(8, 8),
        )
        style.map("Modern.Treeview.Heading", background=[("active", "#1f2535")])

    def _build_ui(self) -> None:
        root_frame = ttk.Frame(self.root, style="Root.TFrame", padding=16)
        root_frame.pack(fill=tk.BOTH, expand=True)

        card = ttk.Frame(root_frame, style="Card.TFrame", padding=18)
        card.pack(fill=tk.BOTH, expand=True)

        ttk.Label(card, text="PGP Session Participation Tracker", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            card,
            text="Use Speedhive event or session URLs to calculate attendance eligibility.",
            style="Sub.TLabel",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 14))

        ttk.Label(card, text="Speedhive Event or Session URL", style="FieldLabel.TLabel").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Entry(card, textvariable=self.event_url_var, width=110).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(5, 12)
        )

        ttk.Label(card, text="Minimum sessions", style="FieldLabel.TLabel").grid(
            row=2, column=2, sticky="w", padx=(10, 0)
        )
        ttk.Entry(card, textvariable=self.minimum_sessions_var, width=12).grid(
            row=3, column=2, sticky="w", padx=(10, 0), pady=(5, 12)
        )

        self.run_button = ttk.Button(
            card,
            text="Calculate Attendance",
            style="Modern.TButton",
            command=self.run_check,
        )
        self.run_button.grid(row=3, column=3, sticky="e", padx=(10, 0))

        ttk.Label(
            card,
            text="Additional Session URLs or IDs (optional, one per line)",
            style="FieldLabel.TLabel",
        ).grid(row=4, column=0, columnspan=4, sticky="w")
        self.session_urls_text = tk.Text(
            card,
            height=4,
            width=110,
            bg=self.colors["surface"],
            fg=self.colors["text"],
            insertbackground=self.colors["gold_bright"],
            relief=tk.FLAT,
            padx=8,
            pady=8,
            wrap=tk.WORD,
            font=("Segoe UI", 10),
        )
        self.session_urls_text.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(5, 12))

        columns = (
            "kart_number",
            "driver",
            "fastest_lap",
            "total_laps",
            "sessions_attended_count",
            "over_minimum",
            "sessions_attended",
        )
        self.table = ttk.Treeview(
            card,
            columns=columns,
            show="headings",
            style="Modern.Treeview",
            height=16,
        )
        self.table.column("kart_number", width=120, anchor="center")
        self.table.column("driver", width=320, anchor="w")
        self.table.column("fastest_lap", width=120, anchor="center")
        self.table.column("total_laps", width=120, anchor="center")
        self.table.column("sessions_attended_count", width=170, anchor="center")
        self.table.column("over_minimum", width=130, anchor="center")
        self.table.column("sessions_attended", width=430, anchor="w")

        for col in columns:
            self.table.heading(
                col,
                text=col.replace("_", " ").title(),
                command=lambda c=col: self.sort_table(c),
            )

        self.table.grid(row=6, column=0, columnspan=4, sticky="nsew", pady=(8, 0))
        self.table.tag_configure("row_odd", background=self.colors["surface"])
        self.table.tag_configure("row_even", background=self.colors["row_alt"])

        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=6, column=4, sticky="ns", pady=(8, 0))

        button_row = ttk.Frame(card, style="Card.TFrame")
        button_row.grid(row=7, column=0, columnspan=4, sticky="w", pady=(12, 0))

        self.export_button = ttk.Button(
            button_row,
            text="Export Participation File",
            style="Modern.TButton",
            command=self.export_results,
            state=tk.DISABLED,
        )
        self.export_button.pack(side=tk.LEFT)

        self.status_label = ttk.Label(
            card,
            text="Ready.",
            style="Sub.TLabel",
        )
        self.status_label.grid(row=8, column=0, columnspan=4, sticky="w", pady=(12, 0))

        card.columnconfigure(0, weight=1)
        card.rowconfigure(6, weight=1)

    def run_check(self) -> None:
        event_url = self.event_url_var.get().strip()
        session_urls = self.session_urls_text.get("1.0", tk.END).strip()
        if not event_url and not session_urls:
            messagebox.showerror(
                "Missing URL",
                "Please provide a Speedhive event/session URL or at least one session URL/ID.",
            )
            return

        try:
            minimum_sessions = int(self.minimum_sessions_var.get().strip())
            if minimum_sessions < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid minimum", "Minimum sessions must be a positive integer.")
            return

        self.run_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        self.status_label.config(text="Calculating attendance... this may take a moment.")
        self._clear_table()

        def worker() -> None:
            try:
                result = collect_participation(
                    event_url=event_url or None,
                    minimum_sessions=minimum_sessions,
                    session_urls=session_urls or None,
                )
                self.root.after(0, lambda: self._on_success(result))
            except (SpeedhiveScrapeError, ValueError, RuntimeError) as exc:
                self.root.after(0, lambda: self._on_error(str(exc)))
            except Exception as exc:  # pragma: no cover
                self.root.after(0, lambda: self._on_error(f"Unexpected error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, result: dict) -> None:
        self.results = result
        self._render_table_rows(result["results"])
        self.run_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.NORMAL)
        self.status_label.config(
            text=(
                f"Loaded {result['event_name']} — {len(result['results'])} drivers across "
                f"{result['total_sessions']} sessions."
            )
        )

    def _on_error(self, message: str) -> None:
        self.run_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.DISABLED)
        self.status_label.config(text="Failed to calculate attendance.")
        messagebox.showerror("Attendance calculation failed", message)

    def _clear_table(self) -> None:
        for item in self.table.get_children():
            self.table.delete(item)

    def _render_table_rows(self, rows: list[dict]) -> None:
        self._clear_table()
        for idx, row in enumerate(rows):
            tag = "row_even" if idx % 2 else "row_odd"
            self.table.insert(
                "",
                tk.END,
                values=(
                    row["kart_number"],
                    row["driver"],
                    row["fastest_lap"],
                    row["total_laps"],
                    row["sessions_attended_count"],
                    row["over_minimum"],
                    row["sessions_attended"],
                ),
                tags=(tag,),
            )

    def sort_table(self, column: str) -> None:
        if not self.results:
            return

        rows = list(self.results["results"])
        descending = self.sort_descending.get(column, False)

        if column in {"total_laps", "sessions_attended_count"}:
            key_fn = lambda row: int(row[column])
        else:
            key_fn = lambda row: str(row[column]).lower()

        rows.sort(key=key_fn, reverse=descending)
        self.sort_descending[column] = not descending
        self.results["results"] = rows
        self._render_table_rows(rows)

        sort_order = "descending" if descending else "ascending"
        self.status_label.config(text=f"Sorted by {column.replace('_', ' ')} ({sort_order}).")

    def export_results(self) -> None:
        if not self.results:
            return

        excel_available = Workbook is not None
        default_extension = ".xlsx" if excel_available else ".csv"
        default_filename = (
            "session_participation.xlsx" if excel_available else "session_participation.csv"
        )
        filetypes = [("CSV files", "*.csv")]
        if excel_available:
            filetypes.insert(0, ("Excel workbook", "*.xlsx"))

        path = filedialog.asksaveasfilename(
            title="Save participation results",
            defaultextension=default_extension,
            filetypes=filetypes,
            initialfile=default_filename,
        )
        if not path:
            return

        export_fields = [
            "kart_number",
            "driver",
            "fastest_lap",
            "total_laps",
            "sessions_attended_count",
            "over_minimum",
            "sessions_attended",
            "fast_times",
        ]

        rows = [{field: row.get(field, "") for field in export_fields} for row in self.results["results"]]
        output_path = Path(path)
        if output_path.suffix.lower() == ".xlsx":
            if Workbook is None:
                messagebox.showerror(
                    "Excel export unavailable",
                    "openpyxl is not installed. Install it with:\n\npip install openpyxl",
                )
                return
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Participation"
            sheet.append(export_fields)
            for row in rows:
                sheet.append([row[field] for field in export_fields])
            workbook.save(output_path)
        else:
            with open(output_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=export_fields)
                writer.writeheader()
                writer.writerows(rows)

        messagebox.showinfo("Saved", f"Participation results saved to {output_path.name}")


def main() -> None:
    root = tk.Tk()
    SessionTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
