import os
import subprocess
import laspy
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from colorama import Fore, Style

# Version of the executable
version = '2.1'

    # Function to create rainbow dashes
def print_rainbow_dashes(line_length=120):
    # Define a list of rainbow colors
    rainbow_colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]

    # Print dashed lines with rainbow colors
    for i in range(line_length):
        print(rainbow_colors[i % len(rainbow_colors)] + "-" + Style.RESET_ALL, end="")
    print()  # Move to the next line after the dashes

def convert_laz_to_las(directory):
    """Convert all .laz files in the directory to .las using las2las64 or move existing .las files."""
    laz_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".laz")]
    las_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".las")]

    # Create the LAS folder
    output_directory = os.path.join(directory, "LAS")
    os.makedirs(output_directory, exist_ok=True)

    # Move existing LAS files to the LAS folder
    for las_file in las_files:
        new_path = os.path.join(output_directory, os.path.basename(las_file))
        os.replace(las_file, new_path)

    # If no .laz files, return the LAS directory (all .las files already moved)
    if not laz_files:
        print("No .laz files found. Only .las files moved to the LAS folder.")
        return output_directory

    # Construct the las2las64 command
    command = [
        "las2las",
        "-i",
        "*.laz",
        "-cpu64",
        "-olas",
        "-cores", "7",
        "-odir", output_directory
    ]

    try:
        # Run the las2las64 command
        print(f"Converting .laz files to .las in {output_directory}...")
        subprocess.run(command, cwd=directory, check=True)
        print_rainbow_dashes()
        print("Conversion completed successfully.")
        print_rainbow_dashes()
    except subprocess.CalledProcessError as e:
        print_rainbow_dashes()
        print(f"Error during .laz to .las conversion: {e}")
        return None

    return output_directory

def get_point_source_ids(file_path):
    """Extract unique point source IDs from a LAS file."""
    point_source_ids = set()
    with laspy.open(file_path) as las_file:
        for points in las_file.chunk_iterator(points_per_iteration=100000):
            point_source_ids.update(points.point_source_id)
    return point_source_ids

def list_point_source_ids(directory):
    """List all unique point source IDs from LAS files in the directory."""
    point_source_ids = set()
    las_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".las")]

    with ThreadPoolExecutor(max_workers=7) as executor:
        with tqdm(total=len(las_files), desc="Gathering Unique Point Source IDs") as pbar:
            futures = {executor.submit(get_point_source_ids, file): file for file in las_files}
            for future in futures:
                ids = future.result()
                point_source_ids.update(ids)
                pbar.update(1)

    return sorted(point_source_ids)

def create_macro_file(directory):
    """Generate the TerraScan macro file based on point source IDs."""
    start_time = time.time()

    # Convert .laz files to .las and get the LAS directory
    las_directory = convert_laz_to_las(directory)
    if not las_directory:
        messagebox.showerror("Error", "Failed to convert .laz files to .las.")
        return

    # Process the LAS files
    unique_point_source_ids = list_point_source_ids(las_directory)
    macro_content = [
        "[TerraScan macro]",
        "Version=020.001",
        "Description=",
        "Author=",
        "ByLine=0",
        "ByScanner=0",
        "SlaveCanRun=0",
        "AnotherComputerCanRun=0",
        "CanBeDistributed=0",
        "",
        "FnScanClassifyClass(\"Any\",0,0)",
        "FnScanClassifyIntensity(\"Any\",7,0,2400,10000,0)",
        "FnScanThinPoints(\"Any\",9997,2,0,0.001,0.001,0)"
    ]

    # Add custom lines with point source IDs
    for point_id in unique_point_source_ids:
        macro_content.append(f"Keyin: scan display view=1/lineoff=all")
        macro_content.append(f"Keyin: scan display view=1/lineon={point_id}")
        macro_content.extend([
            "FnScanClassifyClass(\"0\",6,1)",
            "FnScanClassifyCloseby(\"6\",\"0-65535\",\"0-255\",0,3,1.500,0,0,1,\"0\",0,\"0-65535\",0,\"0-255\",0)",
            "FnScanClassifyClass(\"6\",7,0)"
        ])

    # Append remaining static lines
    macro_content.extend([
        "FnScanClassifyAngle(\"Any\",12,0,-29.00,-99.99,0)",
        "FnScanClassifyAngle(\"Any\",12,0,29.00,99.99,0)",
        "FnScanClassifyClass(\"6\",7,0)",
        "FnScanClassifyClass(\"13\",7,0)",
        "FnScanClassifyIsolated(\"0\",7,5,\"0\",3.00,0)",
        "FnScanClassifyGround(\"0\",2,\"2\",1,40.0,89.00,10.00,1.50,1,5.0,0,2.0,0,0,0)",
        "FnScanClassifyBelow(\"2\",7,0,4.00,0.10,0)",
        "FnScanClassifyLow(\"2\",7,6,0.50,5.00,0)",
        "FnScanClassifyHgtGrd(2,100.0,0,13,15.000,100000.000,0)",
        "FnScanClassifyIsolated(\"13\",7,15,\"0,13\",5.00,0)",
        "FnScanClassifyClass(\"13\",0,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,3,0.000,0.100,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,4,0.100,1.000,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,5,1.000,1000000.000,0)",
        "FnScanClassifyClass(\"0\",1,0)"
    ])

    # Ensure Custom_Classification_Macro folder exists
    output_directory = os.path.join(directory, "LAS")
    macro_dir = os.path.join(output_directory, f"Custom_Classification_Macro_v{version}")
    
    os.makedirs(macro_dir, exist_ok=True)

    # Write to .mac file in the new folder
    macro_file_path = os.path.join(macro_dir, f"Custom_Closeby_Classification_v{version}.mac")
    with open(macro_file_path, 'w') as file:
        file.write("\n".join(macro_content))

    # Create the .prj file
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
    output_directory = os.path.join(directory, "LAS")
    prj_file_path = os.path.join(output_directory, f"PRJ.prj")
    with open(prj_file_path, 'w') as file:
        file.write("\n".join(prj_content))

    elapsed_time = time.time() - start_time
    print_rainbow_dashes()
    print(f"Processing took {elapsed_time:.2f} seconds.")
    messagebox.showinfo("Success", f"Macro and PRJ files created in: {macro_dir}")

def select_directory():
    """Open a directory selection dialog."""
    directory = filedialog.askdirectory()
    if directory:
        directory_path.set(directory)

def on_create_macro_file():
    """Handle Create Macro File button click."""
    directory = directory_path.get()
    if not directory:
        messagebox.showerror("Error", "Please select a directory.")
        return
    create_macro_file(directory)

# Tkinter GUI setup
root = tk.Tk()
root.title(f"Classification Macro Generator_v{version}")
root.geometry("400x130")

# Directory path
directory_path = tk.StringVar()

# GUI elements
tk.Entry(root, textvariable=directory_path, width=50).pack(padx=10)
root.iconbitmap(r"Z:\SPENCER_FLOYD\.ico\Macro.ico")
tk.Button(root, text="Select Directory", command=select_directory).pack(pady=5)
tk.Button(root, text="Create Macro File", command=on_create_macro_file).pack(pady=20)

# Run the GUI
root.mainloop()
