import os
import sys
import csv
import zipfile
import tempfile
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.ttk import Progressbar
from threading import Thread

# Optional/extra deps (only used in specific tabs)
try:
    import pandas as pd  # For Validate tab (Excel matching)
except Exception:
    pd = None

try:
    from openpyxl import Workbook  # For Verify Sums tab (Excel export)
except Exception:
    Workbook = None

APP_TITLE = "All-in-One CSV • ZIP • (CSV Validation)"
APP_SIZE = "1000x720"
PRIMARY = "#3949ab"        # Indigo
ACCENT = "#ff7043"         # Deep Orange
BG = "#f7f7fb"
CARD_BG = "#ffffff"
TXT = "#222"
SUCCESS = "#2e7d32"
WARN = "#ef6c00"
ERROR = "#c62828"

# ------------------------------ Shared UI helpers ------------------------------
class LogConsole(tk.Frame):
    def __init__(self, master, *args, **kwargs):
        super().__init__(master, bg=CARD_BG, *args, **kwargs)
        lbl = tk.Label(self, text="Processing Log", font=("Segoe UI", 10, "bold"), bg=CARD_BG, fg=TXT)
        lbl.pack(anchor="w", padx=10, pady=(10, 0))
        self.text = tk.Text(self, height=12, wrap=tk.WORD, bg="#fafafa", relief=tk.FLAT)
        self.text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        y = tk.Scrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=y.set)
        y.place(relx=1, rely=0, relheight=1, anchor='ne')

    def log(self, msg):
        self.text.insert(tk.END, msg + "\n")
        self.text.see(tk.END)
        self.update_idletasks()

# ------------------------------ Tab 1: Clean Data (ZIP -> individual cleaned CSVs) ------------------------------
class CleanCombineTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=BG)
        self.files = []
        self.output_dir = ""
        self.processing = False
        self.cancel = False

        self._build_ui()

    def _card(self, parent, title):
        frm = tk.Frame(parent, bg=CARD_BG, bd=0, highlightthickness=0)
        tk.Label(frm, text=title, font=("Segoe UI", 11, "bold"), bg=CARD_BG, fg=TXT).pack(anchor="w", padx=12, pady=(12, 2))
        return frm

    def _build_ui(self):
        header = tk.Frame(self, bg=PRIMARY)
        header.pack(fill=tk.X)
        tk.Label(header, text="Clean Data (Only ZIP containing CSV) — saves each CSV separately", fg="white", bg=PRIMARY,
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, padx=16, pady=12)

        # File selection
        row = tk.Frame(self, bg=BG)
        row.pack(fill=tk.X, padx=12, pady=8)

        file_card = self._card(row, "1) Choose ZIP Files")
        file_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        btns = tk.Frame(file_card, bg=CARD_BG)
        btns.pack(fill=tk.X, padx=12, pady=(0, 12))
        ttk.Button(btns, text="Browse ZIP Files", command=self.browse_files).pack(side=tk.LEFT)
        self.sel_lbl = tk.Label(file_card, text="No files selected", bg=CARD_BG, fg="#555")
        self.sel_lbl.pack(anchor="w", padx=12)

        out_card = self._card(row, "2) Output Folder")
        out_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        out_row = tk.Frame(out_card, bg=CARD_BG)
        out_row.pack(fill=tk.X, padx=12, pady=(0, 8))
        ttk.Button(out_row, text="Browse Output Folder", command=self.browse_output).pack(side=tk.LEFT)
        self.out_lbl = tk.Label(out_card, text="No folder selected", bg=CARD_BG, fg="#555")
        self.out_lbl.pack(anchor="w", padx=12)

        action_card = self._card(self, "3) Run")
        action_card.pack(fill=tk.X, padx=12, pady=(0, 8))
        bar_row = tk.Frame(action_card, bg=CARD_BG)
        bar_row.pack(fill=tk.X, padx=12, pady=8)
        self.progress = ttk.Progressbar(bar_row, orient=tk.HORIZONTAL, length=400, mode='determinate')
        self.progress.pack(side=tk.LEFT, padx=(0, 10))
        self.status = tk.Label(bar_row, text="Ready", bg=CARD_BG, fg=SUCCESS)
        self.status.pack(side=tk.LEFT)

        ctl = tk.Frame(action_card, bg=CARD_BG)
        ctl.pack(fill=tk.X, padx=12, pady=(0, 12))
        self.run_btn = ttk.Button(ctl, text="Start", command=self.start)
        self.run_btn.pack(side=tk.LEFT)
        self.cancel_btn = ttk.Button(ctl, text="Cancel", command=self.request_cancel, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=8)
        ttk.Button(ctl, text="Export Log", command=self.export_log).pack(side=tk.LEFT, padx=8)

        # Console
        self.console = LogConsole(self)
        self.console.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

    # ----------- Core cleaning logic (from code-1), WITHOUT combining -----------
    def _clean_one_csv(self, csv_path, suffix_label, output_folder, zip_base):
        """Clean a single CSV file and write to output with _processed suffix.
        Adds `suffix_label` as an extra column value on each row.
        Output filename is based on the ZIP file name, not the CSV file name."""
        output_lines = []

        with open(csv_path, "r", encoding="utf-8-sig", newline="") as file:
            sample = file.read(4096)
            file.seek(0)
            sniffer = csv.Sniffer()
            delimiter = ","
            try:
                delimiter = sniffer.sniff(sample).delimiter
            except csv.Error:
                pass

            reader = list(csv.reader(file, delimiter=delimiter))
            if len(reader) > 2:
                reader = reader[1:-1]

            for cols in reader:
                cols = [c.replace('"', '').strip() for c in cols]
                if len(cols) < 3:
                    continue
                if cols[1].strip().lower() == cols[2].strip().lower():
                    continue
                cols.append(suffix_label)
                output_lines.append(cols)

        os.makedirs(output_folder, exist_ok=True)
        out_path = os.path.join(output_folder, f"{zip_base}_processed.csv")
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(output_lines)

        return out_path

    def process_zip_file(self, zip_path, output_folder):
        """Process each CSV inside the ZIP individually (no combining).
        Output filename uses the ZIP name."""
        created = []
        zip_base = os.path.splitext(os.path.basename(zip_path))[0]

        with zipfile.ZipFile(zip_path, 'r') as z:
            with tempfile.TemporaryDirectory() as tmp:
                z.extractall(tmp)
                for root, _, files in os.walk(tmp):
                    for file in files:
                        if file.lower().endswith('.csv'):
                            src_csv = os.path.join(root, file)
                            try:
                                outp = self._clean_one_csv(src_csv, zip_base, output_folder, zip_base)
                                created.append(outp)
                            except Exception as e:
                                self.console.log(f"ERROR cleaning {file}: {e}")
        return created

    def browse_files(self):
        paths = filedialog.askopenfilenames(title="Select ZIP Files", filetypes=[("ZIP files", "*.zip")])
        if paths:
            self.files = list(paths)
            shown = ", ".join(os.path.basename(x) for x in self.files[:3])
            more = f" +{len(self.files)-3} more" if len(self.files) > 3 else ""
            self.sel_lbl.config(text=f"Selected {len(self.files)} file(s): {shown}{more}")
            self.console.log(f"Selected {len(self.files)} ZIP file(s)")

    def browse_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_dir = folder
            self.out_lbl.config(text=folder)
            self.console.log(f"Output folder: {folder}")

    def start(self):
        if self.processing:
            return
        if not self.files:
            messagebox.showwarning("Missing", "Please select ZIP files")
            return
        if not self.output_dir:
            messagebox.showwarning("Missing", "Please select an output folder")
            return
        self.processing = True
        self.cancel = False
        self.run_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.progress['value'] = 0
        self.status.config(text="Working...", fg=WARN)
        Thread(target=self._run, daemon=True).start()

    def request_cancel(self):
        self.cancel = True
        self.status.config(text="Cancelling...", fg=WARN)

    def _run(self):
        t0 = time.time()
        outputs = []
        total = len(self.files)
        for i, path in enumerate(self.files, 1):
            if self.cancel:
                break
            try:
                self.console.log(f"Cleaning ZIP: {os.path.basename(path)}")
                created = self.process_zip_file(path, self.output_dir)
                outputs.extend(created)
                for outp in created:
                    self.console.log(f"  → Saved: {os.path.basename(outp)}")
            except Exception as e:
                self.console.log(f"ERROR processing {os.path.basename(path)}: {e}")
            self.progress['value'] = (i / total) * 100
            self.status.config(text=f"{i}/{total} ZIP(s) done", fg=SUCCESS)
        dt = time.time() - t0
        self.status.config(text="Complete" if not self.cancel else "Cancelled", fg=SUCCESS if not self.cancel else ERROR)
        self.run_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        if not self.cancel:
            msg = f"Processed {len(outputs)} cleaned CSV file(s) in {dt:.2f}s.\nSaved in: {self.output_dir}"
            messagebox.showinfo("Done", msg)

    def export_log(self):
        if not self.console.text.get("1.0", tk.END).strip():
            messagebox.showinfo("Log", "Log is empty")
            return
        f = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")], title="Save Log")
        if f:
            with open(f, 'w', encoding='utf-8') as out:
                out.write(self.console.text.get("1.0", tk.END))
            messagebox.showinfo("Saved", f"Log saved to:\n{f}")

# ------------------------------ Tab 2: Verify Data (sum columns 4,5,6) ------------------------------
class VerifySumsTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=BG)
        self.files = []
        self.output_dir = ""
        self.processing = False
        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg=ACCENT)
        header.pack(fill=tk.X)
        tk.Label(header, text="Verify Data (Sum Columns 4, 5, 6) — Browse CSV only", fg="white", bg=ACCENT,
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, padx=16, pady=12)

        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=12, pady=8)

        file_card = tk.Frame(top, bg=CARD_BG)
        file_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        tk.Label(file_card, text="1) Select CSV files", font=("Segoe UI", 11, "bold"), bg=CARD_BG).pack(anchor="w", padx=12, pady=(12, 6))
        ttk.Button(file_card, text="Browse CSV Files", command=self.browse_files).pack(anchor="w", padx=12)
        self.sel_lbl = tk.Label(file_card, text="No files selected", bg=CARD_BG, fg="#555")
        self.sel_lbl.pack(anchor="w", padx=12, pady=(6, 12))

        out_card = tk.Frame(top, bg=CARD_BG)
        out_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        tk.Label(out_card, text="2) Choose Output Folder", font=("Segoe UI", 11, "bold"), bg=CARD_BG).pack(anchor="w", padx=12, pady=(12, 6))
        ttk.Button(out_card, text="Browse Output Folder", command=self.browse_output).pack(anchor="w", padx=12)
        self.out_lbl = tk.Label(out_card, text="No folder selected", bg=CARD_BG, fg="#555")
        self.out_lbl.pack(anchor="w", padx=12, pady=(6, 12))

        action = tk.Frame(self, bg=CARD_BG)
        action.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.progress = ttk.Progressbar(action, orient=tk.HORIZONTAL, length=400, mode='determinate')
        self.progress.pack(side=tk.LEFT, padx=(12, 10), pady=10)
        self.status = tk.Label(action, text="Ready", bg=CARD_BG, fg=SUCCESS)
        self.status.pack(side=tk.LEFT)
        self.run_btn = ttk.Button(action, text="Start", command=self.start)
        self.run_btn.pack(side=tk.LEFT, padx=10)

        # Console
        self.console = LogConsole(self)
        self.console.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

    def browse_files(self):
        paths = filedialog.askopenfilenames(title="Select CSV Files", filetypes=[("CSV files", "*.csv")])
        if paths:
            self.files = list(paths)
            shown = ", ".join(os.path.basename(x) for x in self.files[:3])
            more = f" +{len(self.files)-3} more" if len(self.files) > 3 else ""
            self.sel_lbl.config(text=f"Selected {len(self.files)} file(s): {shown}{more}")
            self.console.log(f"Selected {len(self.files)} file(s)")

    def browse_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_dir = folder
            self.out_lbl.config(text=folder)
            self.console.log(f"Output folder: {folder}")

    def sum_4_5_6(self, csv_path):
        total4 = total5 = total6 = 0.0
        rows = 0
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                rows += 1
                try:
                    if len(row) > 3:
                        total4 += float(row[3])
                except ValueError:
                    pass
                try:
                    if len(row) > 4:
                        total5 += float(row[4])
                except ValueError:
                    pass
                try:
                    if len(row) > 5:
                        total6 += float(row[5])
                except ValueError:
                    pass
        return rows, round(total4, 2), round(total5, 2), round(total6, 2)

    def start(self):
        if self.processing:
            return
        if not self.files:
            messagebox.showwarning("Missing", "Please select CSV files")
            return
        if not self.output_dir:
            messagebox.showwarning("Missing", "Please select an output folder")
            return
        if Workbook is None:
            messagebox.showerror("Dependency missing", "openpyxl is required for Excel export. Install with: pip install openpyxl")
            return
        self.processing = True
        self.run_btn.config(state=tk.DISABLED)
        self.progress['value'] = 0
        Thread(target=self._run, daemon=True).start()

    def _run(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Summary"
        ws.append(["File Name", "Total Rows", "Sum Col 4", "Sum Col 5", "Sum Col 6"])
        total = len(self.files)
        for i, path in enumerate(self.files, 1):
            try:
                rows, c4, c5, c6 = self.sum_4_5_6(path)
                ws.append([os.path.basename(path), rows, c4, c5, c6])
                self.console.log(f"{os.path.basename(path)} → rows={rows}, c4={c4}, c5={c5}, c6={c6}")
            except Exception as e:
                self.console.log(f"ERROR: {os.path.basename(path)} → {e}")
            self.progress['value'] = (i/total) * 100
            self.status.config(text=f"{i}/{total} done")
        # Auto-fit columns (simple heuristic)
        for column_cells in ws.columns:
            max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
            ws.column_dimensions[column_cells[0].column_letter].width = max(12, min(60, int(max_len * 1.2)))
        out_path = os.path.join(self.output_dir, "Column Totals Summary.xlsx")
        wb.save(out_path)
        self.status.config(text="Complete", fg=SUCCESS)
        self.processing = False
        self.run_btn.config(state=tk.NORMAL)
        messagebox.showinfo("Done", f"Saved summary to:\n{out_path}")

# ------------------------------ Tab 3: Validate Data (CSV + Excel match) ------------------------------
class ValidateCSVTab(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=BG)
        self.csv_files = []
        self.excel_path = ""
        self.output_dir = ""
        self.processing = False
        self.cancel = False
        self.excel_df = None
        self._build_ui()

    def _build_ui(self):
        header = tk.Frame(self, bg="#26a69a")
        header.pack(fill=tk.X)
        tk.Label(header, text="Validate Data (CSV → transform using Excel mapping)", fg="white", bg="#26a69a",
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, padx=16, pady=12)

        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=12, pady=8)

        # CSV selection
        csv_card = tk.Frame(top, bg=CARD_BG)
        csv_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        tk.Label(csv_card, text="1) Select CSV files", font=("Segoe UI", 11, "bold"), bg=CARD_BG).pack(anchor="w", padx=12, pady=(12, 6))
        ttk.Button(csv_card, text="Browse CSV Files", command=self.browse_csvs).pack(anchor="w", padx=12)
        self.csv_lbl = tk.Label(csv_card, text="No files selected", bg=CARD_BG, fg="#555")
        self.csv_lbl.pack(anchor="w", padx=12, pady=(6, 12))

        # Excel + Output
        right = tk.Frame(top, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        xls_card = tk.Frame(right, bg=CARD_BG)
        xls_card.pack(fill=tk.X, padx=8, pady=8)
        tk.Label(xls_card, text="2) Select Excel (columns: 'File Name', 'Add in File')", font=("Segoe UI", 11, "bold"), bg=CARD_BG).pack(anchor="w", padx=12, pady=(12, 6))
        ttk.Button(xls_card, text="Browse Excel", command=self.browse_excel).pack(anchor="w", padx=12)
        self.xls_lbl = tk.Label(xls_card, text="No Excel selected", bg=CARD_BG, fg="#555")
        self.xls_lbl.pack(anchor="w", padx=12, pady=(6, 12))

        out_card = tk.Frame(right, bg=CARD_BG)
        out_card.pack(fill=tk.X, padx=8, pady=8)
        tk.Label(out_card, text="3) Output Folder", font=("Segoe UI", 11, "bold"), bg=CARD_BG).pack(anchor="w", padx=12, pady=(12, 6))
        ttk.Button(out_card, text="Browse Output", command=self.browse_output).pack(anchor="w", padx=12)
        self.out_lbl = tk.Label(out_card, text="No folder selected", bg=CARD_BG, fg="#555")
        self.out_lbl.pack(anchor="w", padx=12, pady=(6, 12))

        action = tk.Frame(self, bg=CARD_BG)
        action.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.progress = ttk.Progressbar(action, orient=tk.HORIZONTAL, length=400, mode='determinate')
        self.progress.pack(side=tk.LEFT, padx=(12, 10), pady=10)
        self.status = tk.Label(action, text="Ready", bg=CARD_BG, fg=SUCCESS)
        self.status.pack(side=tk.LEFT)
        self.run_btn = ttk.Button(action, text="Start", command=self.start)
        self.run_btn.pack(side=tk.LEFT, padx=10)
        self.cancel_btn = ttk.Button(action, text="Cancel", command=self.request_cancel, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=8)

        # Console
        self.console = LogConsole(self)
        self.console.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

    def browse_csvs(self):
        paths = filedialog.askopenfilenames(title="Select CSV Files", filetypes=[("CSV files", "*.csv")])
        if paths:
            self.csv_files = list(paths)
            shown = ", ".join(os.path.basename(x) for x in self.csv_files[:3])
            more = f" +{len(self.csv_files)-3} more" if len(self.csv_files) > 3 else ""
            self.csv_lbl.config(text=f"Selected {len(self.csv_files)} file(s): {shown}{more}")
            self.console.log(f"Selected {len(self.csv_files)} CSV file(s)")

    def browse_excel(self):
        if pd is None:
            messagebox.showerror("Dependency missing", "pandas is required. Install with: pip install pandas openpyxl")
            return
        path = filedialog.askopenfilename(title="Select Excel", filetypes=[("Excel", "*.xlsx *.xls")])
        if path:
            self.excel_path = path
            self.xls_lbl.config(text=os.path.basename(path))
            self.console.log(f"Excel: {os.path.basename(path)}")

    def browse_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_dir = folder
            self.out_lbl.config(text=folder)
            self.console.log(f"Output folder: {folder}")

    def load_excel(self):
        try:
            df = pd.read_excel(self.excel_path, engine='openpyxl')
            df['File Name'] = (df['File Name'].astype(str).str.strip().str.lower().str.replace(r"\s+", "", regex=True).str.replace('sales_', 'sale_'))
            self.excel_df = df
            return True, None
        except Exception as e:
            return False, f"Failed to read Excel: {e}"

    def find_match_value(self, csv_filename):
        base = os.path.basename(csv_filename).lower().replace(' ', '').replace('sales_', 'sale_')
        m = self.excel_df[self.excel_df['File Name'].str.fullmatch(base, case=False)]
        if not m.empty:
            return m.iloc[0]['Add in File']
        self.console.log(f"No match in Excel for: {os.path.basename(csv_filename)}")
        return None

    def request_cancel(self):
        self.cancel = True
        self.status.config(text="Cancelling...", fg=WARN)

    def start(self):
        if self.processing:
            return
        if not self.csv_files:
            messagebox.showwarning("Missing", "Please select CSV files")
            return
        if not self.excel_path:
            messagebox.showwarning("Missing", "Please select Excel file")
            return
        if not self.output_dir:
            messagebox.showwarning("Missing", "Please select output folder")
            return
        ok, err = self.load_excel()
        if not ok:
            messagebox.showerror("Excel", err)
            return
        self.processing = True
        self.cancel = False
        self.run_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.progress['value'] = 0
        Thread(target=self._run, daemon=True).start()

    def _run(self):
        t0 = time.time()
        total = len(self.csv_files)
        done = 0
        for i, csv_path in enumerate(self.csv_files, 1):
            if self.cancel:
                break
            try:
                produced = self.process_single_csv(csv_path)
                done += 1 if produced else 0
            except Exception as e:
                self.console.log(f"ERROR {os.path.basename(csv_path)}: {e}")
            self.progress['value'] = (i/total) * 100
            self.status.config(text=f"{i}/{total} file(s)")
        self.processing = False
        self.run_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.status.config(text="Complete" if not self.cancel else "Cancelled", fg=SUCCESS if not self.cancel else ERROR)
        if not self.cancel:
            messagebox.showinfo("Done", f"Processed {done} file(s) in {time.time()-t0:.2f}s")

    def process_single_csv(self, csv_path):
        number_from_excel = self.find_match_value(csv_path)
        if number_from_excel is None:
            return False
        try:
            with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().splitlines()
            out_lines = []
            for line in content:
                parts = line.split(',')
                if len(parts) >= 7:
                    try:
                        third_col_value = parts[2].strip().split()[0]
                        new_line = f"{','.join(parts[:6])},{number_from_excel},0,0,{third_col_value}"
                        out_lines.append(new_line)
                    except Exception:
                        out_lines.append(line)
            out_name = f"processed_{os.path.splitext(os.path.basename(csv_path))[0]}.csv"
            out_path = os.path.join(self.output_dir, out_name)
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(out_lines))
            self.console.log(f"Created: {out_name}")
            return True
        except Exception as e:
            self.console.log(f"Error {os.path.basename(csv_path)}: {e}")
            return False

# ------------------------------ Main App ------------------------------

# ----------------------------------------
# Tab 4: Master SKU's (Refactored to Frame)
# ----------------------------------------

class MasterSKUTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)

        self.files = []

        # Title
        title = tk.Label(self, text="✨ CSV Comparator Tool ✨",
                         font=("Arial Black", 18, "bold"),
                         bg=PRIMARY, fg="white", pady=10)
        title.pack(fill=tk.X)

        # Buttons
        frame = tk.Frame(self, bg=BG)
        frame.pack(pady=20)

        self.upload_btn = tk.Button(frame, text="📂 Upload CSV Files", command=self.upload_files,
                                    font=("Arial", 12, "bold"), bg="#32cd32", fg="white", width=20)
        self.upload_btn.grid(row=0, column=0, padx=10)

        self.logic1_btn = tk.Button(frame, text="🔎 Run Find New SKU", command=self.run_logic1,
                                    font=("Arial", 12, "bold"), bg="#1e90ff", fg="white", width=20, state="disabled")
        self.logic1_btn.grid(row=0, column=1, padx=10)

        self.unique_corporate_list_btn = tk.Button(
            frame, text="✨ Run Unique Corporate List", command=self.run_unique_corporate_list,
            font=("Arial", 12, "bold"), bg="#ff6347", fg="white", width=25, state="disabled"
        )
        self.unique_corporate_list_btn.grid(row=0, column=2, padx=10)

        # Status area
        self.status = tk.Text(self, height=12, wrap="word", font=("Consolas", 11))
        self.status.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)
        self.status.insert(tk.END, "👉 Please upload at least 2 CSV files to start.\n")

        # Progress bar
        self.progress = ttk.Progressbar(self, orient="horizontal", length=600, mode="determinate")
        self.progress.pack(pady=10)

    def log(self, msg):
        self.status.insert(tk.END, msg + "\n")
        self.status.see(tk.END)

    def upload_files(self):
        self.files = filedialog.askopenfilenames(filetypes=[("CSV Files", "*.csv")])
        if len(self.files) < 2:
            messagebox.showwarning("Warning", "Please select at least 2 CSV files!")
            return

        self.log(f"✅ Selected {len(self.files)} CSV files")
        for f in self.files:
            self.log(f"   - {os.path.basename(f)}")

        self.logic1_btn.config(state="normal")
        self.unique_corporate_list_btn.config(state="normal")

    def run_logic1(self):
        try:
            self.progress["value"] = 0
            self.log("⚙️ Running Find New SKU...")

            df1 = pd.read_csv(self.files[0])
            df2 = pd.read_csv(self.files[1])

            col1 = df1.iloc[:, 3]  # 4th column
            col2 = df2.iloc[:, 3]

            not_found = col1[~col1.isin(col2)].drop_duplicates()

            out_file = os.path.join(os.getcwd(), "Logic1_New_SKU.csv")
            not_found.to_csv(out_file, index=False, header=["NotFound_Values"])

            self.progress["value"] = 100
            self.log(f"✅ Find New SKU Completed. Output saved as {out_file}")
            messagebox.showinfo("Success", f"Find New SKU Completed.\nOutput saved as:\n{out_file}")

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.log(f"❌ Error: {e}")

    def run_unique_corporate_list(self):
        try:
            self.progress["value"] = 0
            self.log("⚙️ Running Unique Corporate List...")

            df1 = pd.read_csv(self.files[0])
            df2 = pd.read_csv(self.files[1])

            col1 = df1.iloc[:, 0]
            col2 = df2.iloc[:, 0]

            unique_values = pd.Series(pd.concat([col1, col2]).drop_duplicates())

            out_file = os.path.join(os.getcwd(), "Unique_Corporate_List.csv")
            unique_values.to_csv(out_file, index=False, header=["Unique_Values"])

            self.progress["value"] = 100
            self.log(f"✅ Unique Corporate List Completed. Output saved as {out_file}")
            messagebox.showinfo("Success", f"Unique Corporate List Completed.\nOutput saved as:\n{out_file}")

        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.log(f"❌ Error: {e}")

# Main App Class
# -------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(APP_SIZE)
        self.configure(bg=BG)
        try:
            self.iconbitmap(default='')  # placeholder
        except Exception:
            pass
        self._style()
        self._build()

    def _style(self):
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('TButton', padding=8)
        style.configure('TNotebook', tabposition='n')
        style.configure('TNotebook.Tab', padding=(18, 8), font=('Segoe UI', 10, 'bold'))
        style.configure('Horizontal.TProgressbar', thickness=14)

    def _build(self):
        # Title Bar
        title_bar = tk.Frame(self, bg=PRIMARY)
        title_bar.pack(fill=tk.X)
        tk.Label(title_bar, text=APP_TITLE, fg='white', bg=PRIMARY, font=('Segoe UI', 16, 'bold')).pack(side=tk.LEFT, padx=16, pady=10)
        tk.Label(title_bar, text='v1.1', fg='white', bg=PRIMARY, font=('Segoe UI', 10)).pack(side=tk.RIGHT, padx=16)

        # Notebook Tabs
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True)

        self.tab1 = CleanCombineTab(nb)
        self.tab2 = VerifySumsTab(nb)
        self.tab3 = ValidateCSVTab(nb)
        self.tab4 = MasterSKUTab(nb)

        nb.add(self.tab1, text="Clean Data")
        nb.add(self.tab2, text="Verify Sums")
        nb.add(self.tab3, text="Validate CSV")
        nb.add(self.tab4, text="Master SKU's")

# -------------------------------------------------
# Main Entry
# -------------------------------------------------

def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
