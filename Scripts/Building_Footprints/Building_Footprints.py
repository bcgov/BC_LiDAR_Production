import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, BooleanVar
import glob
import shutil
import laspy
import time
from datetime import datetime

class LiDARRoofDelineationTool:
    def __init__(self, root):
        self.root = root
        self.root.title("LiDAR Roof Delineation Tool")
        self.input_dir = tk.StringVar()
        self.num_cores = tk.IntVar(value=4)
        self.use_merged = BooleanVar(value=True)

        self.create_widgets()

    def create_widgets(self):
        tk.Button(self.root, text="Input", command=self.select_input_dir).grid(row=0, column=0, padx=10, pady=10)

        self.input_label = tk.Label(self.root, text="No directory selected", width=50, anchor="w")
        self.input_label.grid(row=0, column=1, padx=10, pady=10)

        tk.Label(self.root, text="Cores:").grid(row=1, column=0, padx=10, sticky="w")
        core_dropdown = ttk.Combobox(self.root, textvariable=self.num_cores, values=list(range(1, 9)), width=5)
        core_dropdown.grid(row=1, column=1, sticky="w")

        self.merged_check = tk.Checkbutton(self.root, text="Merged", variable=self.use_merged)
        self.merged_check.grid(row=2, column=0, padx=10, pady=5, sticky="w")

        tk.Button(self.root, text="Execute", command=self.run_process).grid(row=3, column=0, columnspan=2, pady=20)

    def select_input_dir(self):
        selected_dir = filedialog.askdirectory()
        if selected_dir:
            self.input_dir.set(selected_dir)
            self.input_label.config(text=selected_dir)

    def run_command(self, command):
        print(f"Running command:\n{command}\n")
        try:
            subprocess.run(command, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"Command failed:\n{e}")
            raise

    def contains_class6_points(self, las_file):
        try:
            las = laspy.read(las_file)
            return 6 in las.classification
        except Exception as e:
            print(f"Error reading {las_file}: {e}")
            return False

    def run_process(self):
        if not self.input_dir.get():
            messagebox.showwarning("No Directory", "Please select an input directory.")
            return

        start_time = time.time()
        date_str = datetime.now().strftime("%Y%m%d")
        base_dir = self.input_dir.get()
        height_norm_dir = os.path.join(base_dir, "Roof_Detection", "Height_Normalized")
        classified_dir = os.path.join(base_dir, "Roof_Detection", "Classified")
        boundaries_dir = os.path.join(base_dir, "Roof_Detection", "Roof_Boundaries")
        yes_class6_dir = os.path.join(classified_dir, "yes_class_6")
        no_class6_dir = os.path.join(classified_dir, "no_class_6")
        report_path = os.path.join(base_dir, f"Processing_Report{date_str}.txt")

        for d in [height_norm_dir, classified_dir, boundaries_dir, yes_class6_dir, no_class6_dir]:
            os.makedirs(d, exist_ok=True)

        # Count input files
        input_files = glob.glob(os.path.join(base_dir, "*.las")) + glob.glob(os.path.join(base_dir, "*.laz"))
        print(f"Found {len(input_files)} input .las/.laz files.")

        print(f"Running LASHeight on {len(input_files)} files...")
        cmd1 = (
            f'lasheight64 -i "{base_dir}/*.la?" -class 2 '
            f'-odir "{height_norm_dir}" -olas -cores {self.num_cores.get()} -odix _normalized'
        )
        self.run_command(cmd1)

        height_files = glob.glob(os.path.join(height_norm_dir, "*.las"))
        print(f"Running LASClassify on {len(height_files)} files...")
        cmd2 = (
            f'lasclassify64 -i "{height_norm_dir}/*.las" '
            f'-odir "{classified_dir}" -odix _classified -ignore_class 7 12 '
            f'-cores {self.num_cores.get()}'
        )
        self.run_command(cmd2)

        classified_files = glob.glob(os.path.join(classified_dir, "*.las"))
        print(f"Sorting {len(classified_files)} files based on presence of class 6...")

        has_class6 = []
        for f in classified_files:
            if os.path.getsize(f) < 500:
                continue  # skip empty files
            if self.contains_class6_points(f):
                shutil.move(f, os.path.join(yes_class6_dir, os.path.basename(f)))
                has_class6.append(os.path.join(yes_class6_dir, os.path.basename(f)))
            else:
                shutil.move(f, os.path.join(no_class6_dir, os.path.basename(f)))

        print(f"{len(has_class6)} files contain class 6 points.")
        if not has_class6:
            messagebox.showwarning(
                "No Class 6 Found",
                "No tiles contain class 6.\n"
                "This indicates no points met the criteria of a building roof."
            )
            return

        print(f"Running LASBoundary on {len(has_class6)} files...")
        input_pattern = " ".join(f'"{f}"' for f in has_class6)
        cmd3 = (
            f'lasboundary64 -i {input_pattern} '
            f'-odir "{boundaries_dir}" -oshp -keep_class 6 -concavity 1 -disjoint -labels'
        )
        if self.use_merged.get():
            cmd3 += " -merged"
        else:
            cmd3 += f" -cores {self.num_cores.get()}"

        self.run_command(cmd3)

        end_time = time.time()
        total_time = round(end_time - start_time, 2)

        print(f"\nProcess complete. Total time: {total_time} seconds.")
        messagebox.showinfo("Complete", "Process Complete!")

        # Write report
        with open(report_path, "w") as report:
            report.write("LiDAR Roof Delineation - Processing Report\n")
            report.write(f"Date: {date_str}\n")
            report.write(f"Input Directory: {base_dir}\n")
            report.write(f"Number of cores used: {self.num_cores.get()}\n")
            report.write(f"Total input files: {len(input_files)}\n")
            report.write(f"Files with class 6: {len(has_class6)}\n")
            report.write(f"Processing time (s): {total_time}\n")

        print(f"Report written to: {report_path}")

# Run the GUI
if __name__ == "__main__":
    root = tk.Tk()
    app = LiDARRoofDelineationTool(root)
    root.mainloop()
