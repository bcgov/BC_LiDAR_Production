import subprocess
import os
import tkinter as tk
from tkinter import messagebox
from colorama import Fore, Style

# Check if LAStools directory exists
lastools_dir = "C:\\LAStools\\bin"
if not os.path.exists(lastools_dir):
    root = tk.Tk()
    root.withdraw()  # Hide the main window

    messagebox.showerror("Error", "C:\\LAStools\\bin not found!")

    exit()

# Prompt user for input directory
print("")
input_dir = input("Enter the input directory of .laz or .las files: ")

# Check if input directory contains .laz or .las files
lidar_files = [f for f in os.listdir(input_dir) if f.endswith(('.laz', '.las'))]
if not lidar_files:
    root = tk.Tk()
    root.withdraw()  # Hide the main window

    messagebox.showerror("Error", "No LiDAR files found in the specified input directory.")

    exit()

# Prompt user for output directory
print("")
output_dir = input("Enter the output directory: ")

# Determine lidar file type
lidar_type = lidar_files[0].split('.')[-1]

# Run LAStools command
command = [
    lastools_dir + "\\lasoverlap.exe",
    "-i", f"{input_dir}\\*.{lidar_type}",
    '-cpu64', '-min_diff', '-0.16', '-max_diff', '0.16', '-step', '1', '-elevation_lowest', '-keep_single', '-fail', '-faf', '-o', 'Overlap.tif', '-odir', output_dir
]
print("")
print("...Creating Overlap Accuracy Grids...")

try:
    subprocess.run(command, check=True)
    print("")
    print("Overlap Grids COMPLETE")
    print(f"Results: {output_dir}")
    print("")
    input("Press Enter to exit...")
except subprocess.CalledProcessError as e:
    root = tk.Tk()
    root.withdraw()  # Hide the main window

    messagebox.showerror("Error", f"LASTools license either expired or does not exist")
    input("Press Enter to exit...")
