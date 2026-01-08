import os
import subprocess
import laspy
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from colorama import Fore, Style
import pickle
import sys
import shutil
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")

# Version of the executable
version = '3.1'

# --- Helper for resource loading (works for PyInstaller) ---
def resource_path(relative_path):
    """Get absolute path to resource (dev and PyInstaller)."""
    try:
        # PyInstaller places files in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Development mode: use the directory of THIS script
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)

# Path to the pickle file (bundled with PyInstaller)
pickle_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "urban_tiles.pkl")

# --- Rainbow dashes ---
def print_rainbow_dashes(line_length=120):
    rainbow_colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]
    for i in range(line_length):
        print(rainbow_colors[i % len(rainbow_colors)] + "-" + Style.RESET_ALL, end="")
    print()

# --- Convert LAZ to LAS ---
def convert_laz_to_las(directory, num_cores):
    laz_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".laz")]
    las_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".las")]

    output_directory = os.path.join(directory, "LAS")
    os.makedirs(output_directory, exist_ok=True)

    # Move existing LAS files
    for las_file in las_files:
        new_path = os.path.join(output_directory, os.path.basename(las_file))
        os.replace(las_file, new_path)

    if not laz_files:
        print("No .laz files found. Only .las files moved to the LAS folder.")
        return output_directory

    command = [
        "las2las64",
        "-i", "*.laz",
        "-olas",
        "-cores", str(num_cores),
        "-odir", output_directory
    ]

    try:
        print(f"Converting .laz files to .las in {output_directory} using {num_cores} cores...")
        subprocess.run(command, cwd=directory, check=True)
        print_rainbow_dashes()
        print("Conversion completed successfully.")
        print_rainbow_dashes()
    except subprocess.CalledProcessError as e:
        print_rainbow_dashes()
        print(f"Error during .laz to .las conversion: {e}")
        return None

    return output_directory

# --- Get unique Point Source IDs ---
def get_point_source_ids(file_path):
    point_source_ids = set()
    with laspy.open(file_path) as las_file:
        for points in las_file.chunk_iterator(points_per_iteration=100000):
            point_source_ids.update(points.point_source_id)
    return point_source_ids

# --- List unique Point Source IDs from a folder ---
def list_point_source_ids(directory):
    point_source_ids = set()
    las_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".las")]

    with ThreadPoolExecutor(max_workers=4) as executor:
        with tqdm(total=len(las_files), desc=f"Gathering Point Source IDs in {os.path.basename(directory)}") as pbar:
            futures = {executor.submit(get_point_source_ids, file): file for file in las_files}
            for future in futures:
                ids = future.result()
                point_source_ids.update(ids)
                pbar.update(1)

    return sorted(point_source_ids)

# --- Create Macro and PRJ files for Regular tiles ---
def create_macro_and_prj(directory, unique_point_source_ids):
    macro_content = [
        "[TerraScan macro]",
        "Version=020.001",
        "Description=",
        "Author=Spencer Floyd",
        "ByLine=0",
        "ByScanner=0",
        "SlaveCanRun=0",
        "AnotherComputerCanRun=0",
        "CanBeDistributed=0",
        "",
        "FnScanClassifyClass(\"Any\",0,0)",
        "FnScanThinPoints(\"Any\",9997,2,0,0.001,0.001,0)",
        "FnScanClassifyIsolated(\"0\",7,5,\"0\",3.00,0)"
    ]

    for point_id in unique_point_source_ids:
        macro_content.append("Keyin: scan display view=1/lineoff=all")
        macro_content.append(f"Keyin: scan display view=1/lineon={point_id}")
        macro_content.extend([
            "FnScanClassifyClass(\"0\",6,1)",
            "FnScanClassifyCloseby(\"6\",\"0-65535\",\"0-255\",0,3,1.500,0,0,1,\"0\",0,\"0-65535\",0,\"0-255\",0)",
            "FnScanClassifyClass(\"6\",7,0)"
        ])

    macro_content.extend([
        "FnScanClassifyAngle(\"Any\",12,0,-29.00,-99.99,0)",
        "FnScanClassifyAngle(\"Any\",12,0,29.00,99.99,0)",
        "FnScanClassifyClass(\"6\",7,0)",
        "FnScanClassifyClass(\"13\",7,0)",
        "FnScanClassifyGround(\"0\",2,\"2\",1,40.0,89.00,10.00,1.50,1,5.0,0,2.0,0,0,0)",
        "FnScanClassifyBelow(\"2\",7,0,1.00,0.10,0)",
        "FnScanClassifyIsolated(\"2\",7,4,\"2\",4.00,0)",
        "FnScanClassifyLow(\"2\",7,6,0.50,5.00,0)",
        "FnScanClassifyHgtGrd(2,100.0,9999,7,-100.000,-0.100,0)",
        "FnScanClassifyHgtGrd(2,100.0,0,13,15.000,100000.000,0)",
        "FnScanClassifyIsolated(\"13\",7,15,\"0,13\",5.00,0)",
        "FnScanClassifyClass(\"13\",0,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,3,0.000,0.100,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,4,0.100,1.000,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,5,1.000,1000000.000,0)",
        "FnScanClassifyHgtGrd(2,500.0,9999,7,400.000,1000000.000,0)",
        "FnScanClassifyClass(\"0\",1,0)"
    ])

    macro_dir = os.path.join(directory, f"Custom_Classification_Macro_v{version}")
    os.makedirs(macro_dir, exist_ok=True)
    macro_file_path = os.path.join(macro_dir, f"Custom_Closeby_Classification_v{version}.mac")

    with open(macro_file_path, 'w') as file:
        file.write("\n".join(macro_content))

    # PRJ content
    prj_content = [
        "[TerraScan project]",
        "Scanner=AirborneLidar",
        "Storage=LAS1.4",
        "StoreTime=2",
        "StoreColor=0",
        "StoreEchoLen=0",
        "StoreParam=0",
        "StoreReflectance=0",
        "StoreDeviation=0",
        "StoreReliability=0",
        "StoreDistance=0",
        "StoreGroup=0",
        "StoreNormal=0",
        "RequireLock=0",
        "Description=",
        "FirstPointId=1",
        "BlockRounded=1",
        "BlockSize=1000",
        "BlockGroupCount=1000000",
        "BlockNaming=0",
        "BlockPrefix=pt"
    ]

    prj_file_path = os.path.join(directory, "PRJ.prj")
    with open(prj_file_path, 'w') as file:
        file.write("\n".join(prj_content))

# --- Create Macro and PRJ files for Urban tiles ---
def create_macro_and_prj_urban(directory, unique_point_source_ids):
    macro_content = [
        "[TerraScan macro]",
        "Version=020.001",
        "Description=",
        "Author=Spencer Floyd",
        "ByLine=0",
        "ByScanner=0",
        "SlaveCanRun=0",
        "AnotherComputerCanRun=0",
        "CanBeDistributed=0",
        "",
        "FnScanClassifyClass(\"Any\",0,0)",
        "FnScanThinPoints(\"Any\",9997,2,0,0.001,0.001,0)",
        "FnScanClassifyIsolated(\"0\",7,5,\"0\",3.00,0)"
    ]

    for point_id in unique_point_source_ids:
        macro_content.append("Keyin: scan display view=1/lineoff=all")
        macro_content.append(f"Keyin: scan display view=1/lineon={point_id}")
        macro_content.extend([
            "FnScanClassifyClass(\"0\",6,1)",
            "FnScanClassifyCloseby(\"6\",\"0-65535\",\"0-255\",0,3,2,0,0,1,\"0\",0,\"0-65535\",0,\"0-255\",0)",
            "FnScanClassifyClass(\"6\",7,0)"
        ])

    macro_content.extend([
        "FnScanClassifyAngle(\"Any\",12,0,-29.00,-99.99,0)",
        "FnScanClassifyAngle(\"Any\",12,0,29.00,99.99,0)",
        "FnScanClassifyClass(\"6\",7,0)",
        "FnScanClassifyClass(\"13\",7,0)",
        "FnScanClassifyGround(\"0\",2,\"2\",1,150,89.00,7,1.5,1,5.0,0,2.0,0,0,0)",
        "FnScanClassifyBelow(\"2\",7,0,1.00,0.10,0)",
        "FnScanClassifyIsolated(\"2\",7,4,\"2\",4.00,0)",
        "FnScanClassifyLow(\"2\",7,6,0.50,5.00,0)",
        "FnScanClassifyHgtGrd(2,100.0,9999,7,-100.000,-0.100,0)",
        "FnScanClassifyHgtGrd(2,100.0,0,13,15.000,100000.000,0)",
        "FnScanClassifyIsolated(\"13\",7,15,\"0,13\",5.00,0)",
        "FnScanClassifyClass(\"13\",0,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,3,0.000,0.100,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,4,0.100,1.000,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,5,1.000,1000000.000,0)",
        "FnScanClassifyHgtGrd(2,500.0,9999,7,400.000,1000000.000,0)",
        "FnScanClassifyClass(\"0\",1,0)"
    ])

    macro_dir = os.path.join(directory, f"Custom_Classification_Macro_v{version}_urban")
    os.makedirs(macro_dir, exist_ok=True)
    macro_file_path = os.path.join(macro_dir, f"Custom_Closeby_Classification_v{version}_urban.mac")

    with open(macro_file_path, 'w') as file:
        file.write("\n".join(macro_content))

    # PRJ content for Urban
    prj_content = [
        "[TerraScan project]",
        "Scanner=AirborneLidar",
        "Storage=LAS1.4",
        "StoreTime=2",
        "StoreColor=0",
        "StoreEchoLen=0",
        "StoreParam=0",
        "StoreReflectance=0",
        "StoreDeviation=0",
        "StoreReliability=0",
        "StoreDistance=0",
        "StoreGroup=0",
        "StoreNormal=0",
        "RequireLock=0",
        "Description=",
        "FirstPointId=1",
        "BlockRounded=1",
        "BlockSize=1000",
        "BlockGroupCount=1000000",
        "BlockNaming=0",
        "BlockPrefix=pt"
    ]

    prj_file_path = os.path.join(directory, "PRJ.prj")
    with open(prj_file_path, 'w') as file:
        file.write("\n".join(prj_content))

# --- Organize LAS files using pickle ---
def organize_las_files(las_directory):
    if not os.path.exists(pickle_path):
        print("⚠️ No pickle file found — skipping Urban/Regular sort.")
        return [las_directory]

    with open(pickle_path, "rb") as f:
        urban_tiles = pickle.load(f)

    las_files = [os.path.join(las_directory, f) for f in os.listdir(las_directory) if f.endswith(".las")]

    urban_files = []
    regular_files = []

    # Separate files
    for las_file in las_files:
        filename = os.path.basename(las_file)
        if any(tile.lower() in filename.lower() for tile in urban_tiles):
            urban_files.append(las_file)
        else:
            regular_files.append(las_file)

    subfolders = []

    # Move urban files only if there are any
    if urban_files:
        urban_dir = os.path.join(las_directory, "Urban")
        os.makedirs(urban_dir, exist_ok=True)
        for f in urban_files:
            shutil.move(f, os.path.join(urban_dir, os.path.basename(f)))
        subfolders.append(urban_dir)

    # Move regular files only if there are any
    if regular_files:
        regular_dir = os.path.join(las_directory, "Regular")
        os.makedirs(regular_dir, exist_ok=True)
        for f in regular_files:
            shutil.move(f, os.path.join(regular_dir, os.path.basename(f)))
        subfolders.append(regular_dir)

    return subfolders

# --- Main processing logic ---
def create_macro_file(directory, num_cores):
    start_time = time.time()
    las_directory = convert_laz_to_las(directory, num_cores)
    if not las_directory:
        messagebox.showerror("Error", "Failed to convert .laz files to .las.")
        return

    subdirs = organize_las_files(las_directory)

    for subdir in subdirs:
        unique_point_source_ids = list_point_source_ids(subdir)
        subdir_name = os.path.basename(subdir)
        
        if subdir_name == "Urban":
            create_macro_and_prj_urban(subdir, unique_point_source_ids)
        elif subdir_name == "Regular":
            create_macro_and_prj(subdir, unique_point_source_ids)
        else:
            # fallback if only one folder (no urban found)
            create_macro_and_prj(subdir, unique_point_source_ids)

    elapsed_time = time.time() - start_time
    print_rainbow_dashes()
    print(f"Processing took {elapsed_time:.2f} seconds.")
    messagebox.showinfo("Success", f"Macro and PRJ files created in:\n{', '.join(subdirs)}")

# --- GUI setup ---
def select_directory():
    directory = filedialog.askdirectory()
    if directory:
        directory_path.set(directory)

def on_create_macro_file():
    directory = directory_path.get()
    if not directory:
        messagebox.showerror("Error", "Please select a directory.")
        return
    try:
        num_cores = int(cores_var.get())
    except ValueError:
        messagebox.showerror("Error", "Invalid number of cores selected.")
        return
    create_macro_file(directory, num_cores)

# Path to your ICO
icon_path = resource_path("Macro_Generator.ico")

root = tk.Tk()
root.title(f"Classification Macro Generator v{version}")
root.geometry("420x200")
root.iconbitmap(icon_path)  # sets the window and taskbar icon

directory_path = tk.StringVar()
cores_var = tk.StringVar(value="4")

tk.Entry(root, textvariable=directory_path, width=50).pack(padx=10, pady=5)
tk.Button(root, text="Select Directory", command=select_directory).pack(pady=5)
tk.Label(root, text="Number of Cores:").pack()
tk.OptionMenu(root, cores_var, *[str(i) for i in range(1, 33)]).pack()
tk.Button(root, text="Create Macro File", command=on_create_macro_file).pack(pady=20)

root.mainloop()
