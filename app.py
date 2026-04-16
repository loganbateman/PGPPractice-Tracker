from __future__ import annotations

import csv
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from scraper import SpeedhiveScrapeError, collect_session_results


class SessionTrackerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PGP Practice Session Tracker")
        self.root.geometry("1200x760")
        self.root.minsize(980, 640)

        self.results: dict | None = None
        self.sort_descending: dict[str, bool] = {}
        self.session_url_var = tk.StringVar()

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

        ttk.Label(card, text="PGP Practice Session Tracker", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            card,
            text="Single-session mode: paste one Speedhive session URL and rank drivers by best lap.",
            style="Sub.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 14))

        ttk.Label(card, text="Speedhive Session URL", style="FieldLabel.TLabel").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Entry(card, textvariable=self.session_url_var, width=120).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(5, 12)
        )

        self.run_button = ttk.Button(
            card,
            text="Load Session",
            style="Modern.TButton",
            command=self.run_check,
        )
        self.run_button.grid(row=3, column=2, sticky="e", padx=(10, 0))

        columns = ("position", "driver", "kart_number", "best_lap", "laps")
        self.table = ttk.Treeview(
            card,
            columns=columns,
            show="headings",
            style="Modern.Treeview",
            height=16,
        )
        self.table.column("position", width=90, anchor="center")
        self.table.column("driver", width=360, anchor="w")
        self.table.column("kart_number", width=120, anchor="center")
        self.table.column("best_lap", width=140, anchor="center")
        self.table.column("laps", width=100, anchor="center")

        for col in columns:
            self.table.heading(
                col,
                text=col.replace("_", " ").title(),
                command=lambda c=col: self.sort_table(c),
            )

        self.table.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        self.table.tag_configure("row_odd", background=self.colors["surface"])
        self.table.tag_configure("row_even", background=self.colors["row_alt"])

        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=4, column=3, sticky="ns", pady=(8, 0))

        button_row = ttk.Frame(card, style="Card.TFrame")
        button_row.grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 0))

        self.export_button = ttk.Button(
            button_row,
            text="Export Session CSV",
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
        self.status_label.grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))

        card.columnconfigure(0, weight=1)
        card.rowconfigure(4, weight=1)

    def run_check(self) -> None:
        session_url = self.session_url_var.get().strip()
        if not session_url:
            messagebox.showerror("Missing URL", "Please provide a Speedhive session URL.")
            return

        self.run_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        self.status_label.config(text="Loading session... this may take a moment.")
        self._clear_table()

        def worker() -> None:
            try:
                result = collect_session_results(session_url=session_url)
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
            text=f"Loaded {result['session_name']} — {len(result['results'])} drivers ranked."
        )

    def _on_error(self, message: str) -> None:
        self.run_button.config(state=tk.NORMAL)
        self.export_button.config(state=tk.DISABLED)
        self.status_label.config(text="Failed to load session.")
        messagebox.showerror("Session load failed", message)

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
                    row["position"],
                    row["driver"],
                    row["kart_number"],
                    row["best_lap"],
                    row["laps"],
                ),
                tags=(tag,),
            )

    def sort_table(self, column: str) -> None:
        if not self.results:
            return

        rows = list(self.results["results"])
        descending = self.sort_descending.get(column, False)

        if column in {"position", "laps"}:
            key_fn = lambda row: int(row[column])
        elif column == "best_lap":
            key_fn = lambda row: self._parse_time_for_sort(row[column])
        else:
            key_fn = lambda row: str(row[column]).lower()

        rows.sort(key=key_fn, reverse=descending)
        self.sort_descending[column] = not descending
        self.results["results"] = rows
        self._render_table_rows(rows)

        sort_order = "descending" if descending else "ascending"
        self.status_label.config(text=f"Sorted by {column.replace('_', ' ')} ({sort_order}).")

    @staticmethod
    def _parse_time_for_sort(value: str) -> float:
        cleaned = value.strip().replace(",", ".")
        if ":" in cleaned:
            parts = cleaned.split(":")
            try:
                if len(parts) == 2:
                    return int(parts[0]) * 60 + float(parts[1])
                if len(parts) == 3:
                    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            except ValueError:
                return float("inf")
        try:
            return float(cleaned)
        except ValueError:
            return float("inf")

    def export_results(self) -> None:
        if not self.results:
            return

        path = filedialog.asksaveasfilename(
            title="Save session results CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="session_results.csv",
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["position", "driver", "kart_number", "best_lap", "laps"],
            )
            writer.writeheader()
            writer.writerows(self.results["results"])

        messagebox.showinfo("Saved", f"Session results saved to {Path(path).name}")


def main() -> None:
    root = tk.Tk()
    SessionTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
