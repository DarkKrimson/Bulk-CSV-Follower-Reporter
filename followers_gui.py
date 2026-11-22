#!/usr/bin/env python3

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import followers_report as fr


class App:
    def __init__(self, root):
        self.root = root
        self.busy = False
        self.report_dir = None

        self.folder = tk.StringVar()
        self.found_text = tk.StringVar(value="No folder chosen.")
        self.file_a = tk.StringVar()
        self.file_b = tk.StringVar()
        self.use_lookup = tk.BooleanVar(value=False)
        self.client_id = tk.StringVar()
        self.client_secret = tk.StringVar()
        self.show_secret = tk.BooleanVar(value=False)
        self.creds_status = tk.StringVar()

        root.title("Bulk CSV Follower Reporter")
        root.geometry("680x640")
        root.minsize(600, 560)

        outer = ttk.Frame(root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        # ---- 1. CSV folder ----------------------------------------------------
        report_box = ttk.LabelFrame(outer, text="Follower report", padding=10)
        report_box.grid(row=0, column=0, sticky="ew")
        report_box.columnconfigure(0, weight=1)

        files_box = ttk.LabelFrame(report_box, text="Folder of CSV exports", padding=10)
        files_box.grid(row=0, column=0, sticky="ew")
        files_box.columnconfigure(0, weight=1)
        ttk.Entry(files_box, textvariable=self.folder, state="readonly").grid(
            row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(files_box, text="Browse...", command=self.browse).grid(row=0, column=1)
        ttk.Label(files_box, textvariable=self.found_text, foreground="gray").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # ---- 2. Twitch lookup -------------------------------------------------
        lookup_box = ttk.LabelFrame(report_box, text="Twitch lookup (optional)", padding=10)
        lookup_box.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        lookup_box.columnconfigure(1, weight=1)
        ttk.Checkbutton(lookup_box, text="Look up current usernames on Twitch",
                        variable=self.use_lookup, command=self.toggle_lookup).grid(
            row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(lookup_box, text="Client ID").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.id_entry = ttk.Entry(lookup_box, textvariable=self.client_id)
        self.id_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(8, 0))

        ttk.Label(lookup_box, text="Client Secret").grid(row=2, column=0, sticky="w", pady=4)
        self.secret_entry = ttk.Entry(lookup_box, textvariable=self.client_secret, show="*")
        self.secret_entry.grid(row=2, column=1, sticky="ew", pady=4)
        self.show_check = ttk.Checkbutton(lookup_box, text="Show", variable=self.show_secret,
                                          command=self.toggle_secret)
        self.show_check.grid(row=2, column=2, padx=(8, 0))

        btns = ttk.Frame(lookup_box)
        btns.grid(row=3, column=1, columnspan=2, sticky="w", pady=(6, 0))
        self.save_button = ttk.Button(btns, text="Save to config.ini", command=self.save_credentials)
        self.save_button.pack(side="left")

        ttk.Label(lookup_box, textvariable=self.creds_status, foreground="gray",
                  wraplength=600).grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

        # ---- 3. Run -----------------------------------------------------------
        run_row = ttk.Frame(report_box)
        run_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.run_button = ttk.Button(run_row, text="Run report", command=self.run)
        self.run_button.pack(side="left")
        self.open_button = ttk.Button(run_row, text="Open report folder",
                                      command=self.open_report, state="disabled")
        self.open_button.pack(side="left", padx=(8, 0))
        self.progress = ttk.Progressbar(run_row, mode="indeterminate", length=180)
        self.progress.pack(side="left", padx=(12, 0))

        # ---- Log --------------------------------------------------------------
        # ---- 3. Compare two channels ------------------------------------------
        ttk.Separator(outer).grid(row=1, column=0, sticky="ew", pady=12)
        compare_box = ttk.LabelFrame(outer, text="Extra: compare two channels (accounts following both)", padding=10)
        compare_box.grid(row=2, column=0, sticky="ew")
        compare_box.columnconfigure(1, weight=1)
        ttk.Label(compare_box, text="Channel 1 CSV").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(compare_box, textvariable=self.file_a, state="readonly").grid(
            row=0, column=1, sticky="ew", padx=8, pady=3)
        ttk.Button(compare_box, text="Browse...", command=lambda: self.browse_file(self.file_a)).grid(
            row=0, column=2)
        ttk.Label(compare_box, text="Channel 2 CSV").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(compare_box, textvariable=self.file_b, state="readonly").grid(
            row=1, column=1, sticky="ew", padx=8, pady=3)
        ttk.Button(compare_box, text="Browse...", command=lambda: self.browse_file(self.file_b)).grid(
            row=1, column=2)
        self.compare_button = ttk.Button(compare_box, text="Find accounts following both", command=self.compare)
        self.compare_button.grid(row=2, column=1, sticky="w", pady=(8, 0))

        ttk.Label(outer, text="Log").grid(row=3, column=0, sticky="w", pady=(10, 2))
        log_frame = ttk.Frame(outer)
        log_frame.grid(row=4, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, wrap="word", height=12, state="disabled")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        self.load_saved()
        self.toggle_lookup()

    # ---- Folder ---------------------------------------------------------------
    def browse(self):
        start = self.folder.get() or os.path.expanduser("~")
        chosen = filedialog.askdirectory(title="Choose the folder with your follower CSV files",
                                         initialdir=start)
        if chosen:
            self.folder.set(chosen)
            self.refresh_count()

    def csv_files(self):
        folder = self.folder.get()
        if not folder or not os.path.isdir(folder):
            return []
        return fr.collect_files([folder])

    def refresh_count(self):
        if not self.folder.get():
            self.found_text.set("No folder chosen.")
            return
        n = len(self.csv_files())
        if n == 0:
            self.found_text.set("No CSV files in that folder.")
        else:
            self.found_text.set(f"{n} CSV file{'s' if n != 1 else ''} found.")

    # ---- Lookup settings --------------------------------------------------------
    def toggle_lookup(self):
        state = "normal" if self.use_lookup.get() else "disabled"
        for widget in (self.id_entry, self.secret_entry, self.show_check, self.save_button):
            widget.configure(state=state)

    def toggle_secret(self):
        self.secret_entry.configure(show="" if self.show_secret.get() else "*")

    def load_saved(self):
        path = fr.config_path()
        try:
            cid, secret = fr.read_saved_credentials()
        except Exception:
            cid, secret = "", ""
        if cid and not fr.is_placeholder(cid):
            self.client_id.set(cid)
        if secret and not fr.is_placeholder(secret):
            self.client_secret.set(secret)
        if os.path.exists(path):
            self.creds_status.set(f"Credentials file: {path}")
        else:
            self.creds_status.set(f"No config.ini yet. Saving will create it at: {path}")

    def save_credentials(self):
        cid = self.client_id.get().strip()
        secret = self.client_secret.get().strip()
        if not cid or not secret:
            messagebox.showerror("Missing details", "Enter both the Client ID and the Client Secret.")
            return
        try:
            path = fr.save_config(cid, secret)
        except OSError as e:
            messagebox.showerror("Could not save", str(e))
            return
        self.creds_status.set(f"Saved to {path}")

    # ---- Run ---------------------------------------------------------------------
    def run(self):
        if self.busy:
            return
        files = self.csv_files()
        if not files:
            messagebox.showwarning("No CSV files", "Browse to a folder that contains follower CSV files first.")
            return

        lookup = self.use_lookup.get()
        client = None
        if lookup:
            cid = self.client_id.get().strip()
            secret = self.client_secret.get().strip()
            if not cid or not secret:
                messagebox.showerror("Missing details",
                                     "Enter the Client ID and Client Secret, or untick the Twitch lookup box.")
                return
            if fr.TwitchClient is None:
                messagebox.showerror("Missing file", "twitch_lookup.py is missing from the program folder.")
                return
            client = fr.TwitchClient(cid, secret)

        self.busy = True
        self.run_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.progress.start(12)
        self.clear_log()
        threading.Thread(target=self._worker, args=(files, lookup, client), daemon=True).start()

    def _worker(self, files, lookup, client):
        try:
            out_dir = fr.generate(files, lookup, log=self.log, given_client=client)
        except Exception as e:
            self.log(f"Error: {e}")
            out_dir = None
        self.root.after(0, self._finish, out_dir)

    def _finish(self, out_dir):
        self.busy = False
        self.progress.stop()
        self.run_button.configure(state="normal")
        self.compare_button.configure(state="normal")
        if out_dir:
            self.report_dir = out_dir
            self.open_button.configure(state="normal")

    def open_report(self):
        if self.report_dir and os.path.isdir(self.report_dir) and hasattr(os, "startfile"):
            os.startfile(self.report_dir)

    # ---- Compare two channels ------------------------------------------------
    def browse_file(self, var):
        start = os.path.dirname(var.get()) if var.get() else os.path.expanduser("~")
        chosen = filedialog.askopenfilename(
            title="Choose a follower CSV",
            initialdir=start,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if chosen:
            var.set(chosen)

    def compare(self):
        if self.busy:
            return
        a, b = self.file_a.get(), self.file_b.get()
        if not a or not b:
            messagebox.showwarning("Pick two files", "Browse to a CSV for Channel 1 and one for Channel 2.")
            return
        if os.path.abspath(a) == os.path.abspath(b):
            messagebox.showwarning("Same file", "Pick two different CSV files.")
            return
        self.busy = True
        self.run_button.configure(state="disabled")
        self.compare_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.progress.start(12)
        self.clear_log()
        threading.Thread(target=self._compare_worker, args=(a, b), daemon=True).start()

    def _compare_worker(self, a, b):
        try:
            out_dir = fr.compare_channels(a, b, log=self.log)
        except Exception as e:
            self.log(f"Error: {e}")
            out_dir = None
        self.root.after(0, self._finish, out_dir)

    # ---- Log box ---------------------------------------------------------------
    def log(self, message):
        text = str(message)
        if not text.endswith("\n"):
            text += "\n"
        self.root.after(0, self._append, text)

    def _append(self, text):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
