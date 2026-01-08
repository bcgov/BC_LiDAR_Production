import os
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
import tkinter as tk
from tkinter import filedialog, messagebox
import shutil

def check_file(file_path):
    try:
        result = subprocess.run(
            ['lasinfo64', '-i', file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        output = result.stdout.lower()
        if any(error in output for error in ['error', 'warning', 'chunk', 'truncated', 'missing']):
            return os.path.basename(file_path)
    except Exception:
        return os.path.basename(file_path)
    return None

def check_laz_files_gui(directory, max_workers=8):
    laz_files = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.lower().endswith(('.laz', '.las'))
    ]
    corrupted = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_file, f): f for f in laz_files}
        for future in as_completed(futures):
            result = future.result()
            if result:
                corrupted.append(result)

    report_path = os.path.join(directory, "corrupt_laz_report.txt")
    with open(report_path, "w") as report:
        for filename in corrupted:
            report.write(f"{filename}\n")

    if corrupted:
        msg = f"{len(corrupted)} potentially corrupt files found.\nDo you want to move them to a 'Corrupted_Files' folder?"
        if messagebox.askyesno("Corrupt Files Found", msg):
            corrupted_dir = os.path.join(directory, "Corrupted_Files")
            os.makedirs(corrupted_dir, exist_ok=True)
            for filename in corrupted:
                src = os.path.join(directory, filename)
                dst = os.path.join(corrupted_dir, filename)
                if os.path.exists(src):
                    shutil.move(src, dst)
            messagebox.showinfo("Files Moved", f"{len(corrupted)} files moved to 'Corrupted_Files'.")
        else:
            messagebox.showinfo("Report Only", f"Corrupt files listed in:\n{report_path}")
    else:
        messagebox.showinfo("Check Complete", "No corruption detected.")

class LASCheckerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("LAS/LAZ Corruption Checker")

        self.input_dir = tk.StringVar()

        tk.Label(master, text="Input Directory:").pack(pady=5)
        tk.Entry(master, textvariable=self.input_dir, width=60).pack(padx=10)
        tk.Button(master, text="Browse", command=self.browse_directory).pack(pady=5)
        tk.Button(master, text="Check Files", command=self.start_check,
                  bg="darkred", fg="white", height=2, width=20).pack(pady=20)

    def browse_directory(self):
        folder = filedialog.askdirectory()
        if folder:
            self.input_dir.set(folder)

    def start_check(self):
        directory = self.input_dir.get()
        if not os.path.isdir(directory):
            messagebox.showwarning("Invalid Input", "Please select a valid input directory.")
            return
        check_laz_files_gui(directory)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    root = tk.Tk()
    app = LASCheckerApp(root)
    root.mainloop()
