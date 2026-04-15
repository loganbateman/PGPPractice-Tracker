from __future__ import annotations

import csv
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from scraper import collect_attendance


class AttendanceApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PGP Practice Attendance Checker")
        self.root.geometry("1080x700")

        self.results: dict | None = None

        self.event_url_var = tk.StringVar()
        self.min_practice_var = tk.StringVar(value="4")

        self._build_ui()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Speedhive Event URL:").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.event_url_var, width=100).grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10)
        )

        ttk.Label(frame, text="Minimum practices required:").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.min_practice_var, width=10).grid(
            row=2, column=1, sticky="w"
        )

        self.run_button = ttk.Button(frame, text="Run Attendance Check", command=self.run_check)
        self.run_button.grid(row=2, column=2, sticky="e")

        ttk.Label(
            frame,
            text="Optional: paste direct session URLs (one per line) to skip event-page discovery:",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(10, 0))

        self.session_text = tk.Text(frame, height=6, wrap="word")
        self.session_text.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(0, 10))

        columns = (
            "driver",
            "counted_practices",
            "fastest_time_overall",
            "total_laps_overall",
            "meets_minimum",
            "counted_sessions",
        )
        self.table = ttk.Treeview(frame, columns=columns, show="headings", height=16)
        for col in columns:
            self.table.heading(col, text=col.replace("_", " ").title())

        self.table.column("driver", width=220, anchor="w")
        self.table.column("counted_practices", width=140, anchor="center")
        self.table.column("fastest_time_overall", width=140, anchor="center")
        self.table.column("total_laps_overall", width=130, anchor="center")
        self.table.column("meets_minimum", width=120, anchor="center")
        self.table.column("counted_sessions", width=420, anchor="w")
        self.table.grid(row=5, column=0, columnspan=3, sticky="nsew")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=5, column=3, sticky="ns")

        button_row = ttk.Frame(frame)
        button_row.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        self.export_summary_button = ttk.Button(
            button_row,
            text="Export Summary CSV",
            command=self.export_summary,
            state=tk.DISABLED,
        )
        self.export_summary_button.pack(side=tk.LEFT)

        self.export_raw_button = ttk.Button(
            button_row,
            text="Export Raw Records CSV",
            command=self.export_raw,
            state=tk.DISABLED,
        )
        self.export_raw_button.pack(side=tk.LEFT, padx=8)

        self.status_label = ttk.Label(frame, text="Ready.")
        self.status_label.grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))

        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)

    def run_check(self) -> None:
        event_url = self.event_url_var.get().strip()
        if not event_url:
            messagebox.showerror("Missing URL", "Please provide a Speedhive event URL.")
            return

        try:
            minimum_practices = int(self.min_practice_var.get())
            if minimum_practices < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid minimum", "Minimum practices must be a positive integer.")
            return

        manual_links_text = self.session_text.get("1.0", tk.END).strip()

        self.run_button.config(state=tk.DISABLED)
        self.export_summary_button.config(state=tk.DISABLED)
        self.export_raw_button.config(state=tk.DISABLED)
        self.status_label.config(text="Running... this may take a minute.")
        self._clear_table()

        def worker() -> None:
            try:
                result = collect_attendance(
                    event_url=event_url,
                    minimum_practices=minimum_practices,
                    manual_session_links_text=manual_links_text,
                )
                self.root.after(0, lambda: self._on_success(result))
            except Exception as exc:
                self.root.after(0, lambda: self._on_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, result: dict) -> None:
        self.results = result
        for row in result["summary_rows"]:
            self.table.insert(
                "",
                tk.END,
                values=(
                    row["driver"],
                    row["counted_practices"],
                    row["fastest_time_overall"],
                    row["total_laps_overall"],
                    row["meets_minimum"],
                    row["counted_sessions"],
                ),
            )

        summary_count = len(result["summary_rows"])
        session_count = len(result["session_links"])
        error_count = len(result["errors"])

        status = f"Done. Drivers found: {summary_count}. Sessions processed: {session_count}."
        if error_count:
            status += f" Warnings: {error_count}."
            messagebox.showwarning(
                "Some sessions failed",
                "\n".join(result["errors"][:10]),
            )

        self.status_label.config(text=status)
        self.run_button.config(state=tk.NORMAL)
        self.export_summary_button.config(state=tk.NORMAL)
        self.export_raw_button.config(state=tk.NORMAL)

    def _on_error(self, message: str) -> None:
        self.status_label.config(text="Failed. See error dialog.")
        self.run_button.config(state=tk.NORMAL)
        messagebox.showerror("Attendance check failed", message)

    def _clear_table(self) -> None:
        for item in self.table.get_children():
            self.table.delete(item)

    def export_summary(self) -> None:
        if not self.results:
            return
        rows = self.results["summary_rows"]
        path = filedialog.asksaveasfilename(
            title="Save summary CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="attendance_summary.csv",
        )
        if not path:
            return

        self._write_csv(
            path,
            rows,
            [
                "driver",
                "counted_practices",
                "fastest_time_overall",
                "total_laps_overall",
                "meets_minimum",
                "counted_sessions",
            ],
        )
        messagebox.showinfo("Saved", f"Summary saved to {Path(path).name}")

    def export_raw(self) -> None:
        if not self.results:
            return
        rows = self.results["raw_rows"]
        path = filedialog.asksaveasfilename(
            title="Save raw records CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="attendance_raw_records.csv",
        )
        if not path:
            return

        self._write_csv(path, rows, ["session_name", "session_url", "driver", "time", "laps"])
        messagebox.showinfo("Saved", f"Raw records saved to {Path(path).name}")

    @staticmethod
    def _write_csv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    root = tk.Tk()
    app = AttendanceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
