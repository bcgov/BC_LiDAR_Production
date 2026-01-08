import os
import laspy
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import time
import tkinter as tk
from tkinter import filedialog, messagebox

# version of executable
version = '1.5'

def get_point_source_ids(file_path):
    point_source_ids = set()
    with laspy.open(file_path) as las_file:
        for points in las_file.chunk_iterator(points_per_iteration=100000):
            point_source_ids.update(points.point_source_id)
    return point_source_ids

def list_point_source_ids(directory):
    point_source_ids = set()
    las_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".las")]
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        with tqdm(total=len(las_files), desc="Processing Files") as pbar:
            futures = {executor.submit(get_point_source_ids, file): file for file in las_files}
            for future in futures:
                ids = future.result()
                point_source_ids.update(ids)
                pbar.update(1)
    
    return sorted(point_source_ids)

def create_macro_file(directory):
    start_time = time.time()
    
    unique_point_source_ids = list_point_source_ids(directory)
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
        "FnScanClassifyIntensity(\"Any\",7,0,2100,10000,0)",
        "FnScanThinPoints(\"Any\",7,2,0,0.001,0.001,0)"
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
        "FnScanClassifyHgtGrd(2,20.0,0,3,0.000,0.100,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,4,0.100,1.000,0)",
        "FnScanClassifyHgtGrd(2,20.0,0,5,1.000,1000000.000,0)",
        "FnScanClassifyClass(\"0\",1,0)"
    ])
    
    # Ensure Custom_Classification_Macro folder exists
    macro_dir = os.path.join(directory, f"Custom_Classification_Macro_v{version}")
    os.makedirs(macro_dir, exist_ok=True)
    
    # Write to .mac file in the new folder
    macro_file_path = os.path.join(macro_dir, "Custom_Closeby_Classification_v1.5.mac")
    with open(macro_file_path, 'w') as file:
        file.write("\n".join(macro_content))
    
    elapsed_time = time.time() - start_time
    print(f"Processing took {elapsed_time:.2f} seconds.")
    messagebox.showinfo("Success", f"Macro file created in: {macro_file_path}")

def select_directory():
    directory = filedialog.askdirectory()
    if directory:
        directory_path.set(directory)

def on_create_macro_file():
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
tk.Button(root, text="Select Directory", command=select_directory).pack(pady=5)
tk.Button(root, text="Create Macro File", command=on_create_macro_file).pack(pady=20)


# Run the GUI
root.mainloop()
