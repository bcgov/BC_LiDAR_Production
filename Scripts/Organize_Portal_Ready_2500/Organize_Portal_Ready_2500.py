import os
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font
import subprocess

class OrganizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("4_Portal_Ready Organizer")
        self.input_directory = tk.StringVar()

        self.select_button = tk.Button(root, text="Select Input Directory", command=self.select_directory)
        self.select_button.pack(pady=10)

        self.organize_button = tk.Button(root, text="Organize", command=self.organize_files)
        self.organize_button.pack(pady=10)

    def select_directory(self):
        selected_dir = filedialog.askdirectory()
        if not selected_dir.endswith("4_Portal_Ready"):
            messagebox.showerror("Error", "4_Portal_Ready folder not selected. Please select the 4_Portal_Ready folder.")
            self.input_directory.set("")
        else:
            self.input_directory.set(selected_dir)
            print(f"Selected directory: {selected_dir}")

    def count_files(self, path, ext):
        if not os.path.isdir(path):
            return 0
        return sum(1 for f in os.listdir(path) if f.lower().endswith(ext.lower()))

    def run_robocopy_move(self, src, dst, file_ext):
        before_count = self.count_files(src, file_ext)
        if before_count == 0:
            return 0
        cmd = [
            "robocopy",
            src,
            dst,
            "/MOV",
            "/NJH",  # No Job Header
            "/NJS",  # No Job Summary
            "/NP",    # No Progress
            "/XO"   #Exclude older files in source (only move newer or non-existing in dest)
        ]
        # Run robocopy without capturing logs to file
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        after_count = self.count_files(src, file_ext)
        moved = before_count - after_count
        return moved

    def organize_files(self):
        base_dir = self.input_directory.get()
        if not base_dir:
            messagebox.showerror("Error", "No input directory selected.")
            return

        monthly_dir = os.path.join(base_dir, "_Monthly_Deliveries")
        if not os.path.isdir(monthly_dir):
            messagebox.showerror("Error", "_Monthly_Deliveries folder does not exist. Please create this directory within 4_Portal_Ready before continuing.")
            return

        current_ym = datetime.now().strftime("%Y_%m")
        target_dir = os.path.join(monthly_dir, current_ym)
        print(f"Creating monthly folder: {target_dir}")
        os.makedirs(target_dir, exist_ok=True)

        for sub in ["DEM", "DSM", "LAZ"]:
            os.makedirs(os.path.join(target_dir, sub), exist_ok=True)

        discrepancies = []

        # STEP 1: Scan and check for discrepancies first
        print("Checking for file consistency...")
        folders_to_process = []
        for folder in os.listdir(base_dir):
            folder_path = os.path.join(base_dir, folder)
            if os.path.isdir(folder_path) and len(folder) == 2:
                folders_to_process.append((folder, folder_path))
                dem_path = os.path.join(folder_path, "DEM")
                dsm_path = os.path.join(folder_path, "DSM")
                laz_path = os.path.join(folder_path, "LAZ")

                def get_names(path):
                    names = set()
                    if os.path.isdir(path):
                        for f in os.listdir(path):
                            if os.path.isfile(os.path.join(path, f)):
                                parts = f.split('_')
                                if len(parts) >= 5:
                                    name = '_'.join(parts[:5])
                                    names.add(name)
                    return names

                dem_names = get_names(dem_path)
                dsm_names = get_names(dsm_path)
                laz_names = get_names(laz_path)

                all_names = dem_names.union(dsm_names).union(laz_names)
                for name in all_names:
                    if name not in dem_names:
                        discrepancies.append(f"{name} missing from DEM in {folder}")
                    if name not in dsm_names:
                        discrepancies.append(f"{name} missing from DSM in {folder}")
                    if name not in laz_names:
                        discrepancies.append(f"{name} missing from LAZ in {folder}")

        # STEP 2: Abort if discrepancies found
        if discrepancies:
            discrepancy_file = os.path.join(base_dir, "File_Discrepancies.txt")
            with open(discrepancy_file, "w") as f:
                for d in discrepancies:
                    f.write(d + "\n")
            messagebox.showerror("Discrepancies Found", f"{len(discrepancies)} discrepancies found. See File_Discrepancies.txt for details.")
            return

        # STEP 3: Proceed with moving files after clean check
        print("All files verified. Proceeding with file move...")

        # Track stats for Excel summary
        tile_stats = {}
        # Track counts for move report summary
        product_original = {"DEM":0, "DSM":0, "LAZ":0}
        product_moved = {"DEM":0, "DSM":0, "LAZ":0}

        for folder, folder_path in folders_to_process:
            print(f"Moving files from: {folder}")
            dem_path = os.path.join(folder_path, "DEM")
            dsm_path = os.path.join(folder_path, "DSM")
            laz_path = os.path.join(folder_path, "LAZ")

            # Tally LAZ stats for Excel summary
            laz_count = 0
            laz_size_bytes = 0
            if os.path.isdir(laz_path):
                for f in os.listdir(laz_path):
                    file_path = os.path.join(laz_path, f)
                    if os.path.isfile(file_path) and f.lower().endswith(".laz"):
                        laz_count += 1
                        laz_size_bytes += os.path.getsize(file_path)
            tile_stats[folder] = {
                "count": laz_count,
                "size_gb": round(laz_size_bytes / (1024 ** 3), 2)
            }

            # Move files for each product type and count original and moved
            for subfolder, ext in [("DEM", ".tif"), ("DSM", ".tif"), ("LAZ", ".laz")]:
                source = os.path.join(folder_path, subfolder)
                dest = os.path.join(target_dir, subfolder)

                original_count = self.count_files(source, ext)
                moved_count = self.run_robocopy_move(source, dest, ext)

                product_original[subfolder] += original_count
                product_moved[subfolder] += moved_count

        # STEP 4: Write summary Excel (as before)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = current_ym

        sheet["B1"] = "Total Tiles"
        sheet["C1"] = "Total LAZ (GB)"
        sheet["E1"] = "Total Month Tiles"
        sheet["F1"] = "Total Month LAZ (GB)"
        bold_font = Font(bold=True)
        for col in ["B1", "C1", "E1", "F1"]:
            sheet[col].font = bold_font

        row = 2
        total_tiles = 0
        total_gb = 0.0
        for folder_name, stats in sorted(tile_stats.items()):
            sheet[f"A{row}"] = folder_name
            sheet[f"B{row}"] = stats["count"]
            sheet[f"C{row}"] = stats["size_gb"]
            total_tiles += stats["count"]
            total_gb += stats["size_gb"]
            row += 1

        sheet["E2"] = total_tiles
        sheet["F2"] = round(total_gb, 2)

        excel_path = os.path.join(target_dir, f"Delivery_Summary_{current_ym}.xlsx")
        workbook.save(excel_path)

        # STEP 5: Write move report with corrected counts
        report_path = os.path.join(target_dir, "Move_Report.txt")
        with open(report_path, "w") as f:
            f.write("Move Report Summary:\n\n")
            for product in ["DEM", "DSM", "LAZ"]:
                f.write(f"{product} - Original: {product_original[product]}\n")
                f.write(f"{product} - Moved:    {product_moved[product]}\n\n")

        messagebox.showinfo("Success", "All files moved and summary generated.")

if __name__ == "__main__":
    print("Launching 4_Portal_Ready Organizer...")
    root = tk.Tk()
    app = OrganizerApp(root)
    root.mainloop()
