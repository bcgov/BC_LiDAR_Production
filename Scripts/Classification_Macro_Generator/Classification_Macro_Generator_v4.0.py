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
import threading

warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")

# Version of the executable
version = '3.2'

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

# Path to the pickle file (bundled with PyInstaller if present)
pickle_path = resource_path("urban_tiles.pkl")

# --- Rainbow dashes ---
def print_rainbow_dashes(line_length=120):
    rainbow_colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]
    for i in range(line_length):
        print(rainbow_colors[i % len(rainbow_colors)] + "-" + Style.RESET_ALL, end="")
    print()

# --- Copy large LAZ files safely to local destination ---
def copy_large_file_safe(src_path, dest_path, buffer_size=16 * 1024 * 1024):
    start_time = time.time()
    bytes_copied = 0
    dest_dir = os.path.dirname(dest_path)
    os.makedirs(dest_dir, exist_ok=True)
    temp_path = dest_path + ".part"

    try:
        print(f"Copying file to temp path: {src_path} -> {temp_path}")
        with open(src_path, "rb") as src_file, open(temp_path, "wb") as dest_file:
            while True:
                chunk = src_file.read(buffer_size)
                if not chunk:
                    break
                dest_file.write(chunk)
                bytes_copied += len(chunk)
        os.replace(temp_path, dest_path)
        elapsed_time = time.time() - start_time
        print(f"Copy completed: {dest_path} ({bytes_copied} bytes in {elapsed_time:.2f}s)")
        return bytes_copied, elapsed_time
    except Exception as e:
        print(f"Error during copy: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return None, None

# --- Copy + convert pipeline (background thread) ---
def run_copy_convert_pipeline(source_dir, dest_dir, copy_as_arrive, max_conversions, num_cores,
                              skip_existing, status_var, copied_count_var, converted_count_var, start_button):
    processed = set()
    copied_count = 0
    converted_count = 0
    futures = set()
    error_flag = False
    poll_interval_sec = 2
    idle_timeout_sec = 120
    last_activity_time = time.time()
    las_root = os.path.join(dest_dir, "LAS")
    os.makedirs(las_root, exist_ok=True)

    def update_status(text):
        root.after(0, lambda: status_var.set(text))

    def update_counts(copied_delta=0, converted_delta=0):
        nonlocal copied_count, converted_count
        copied_count += copied_delta
        converted_count += converted_delta
        root.after(0, lambda: (copied_count_var.set(str(copied_count)),
                               converted_count_var.set(str(converted_count))))

    def enable_start_button():
        root.after(0, lambda: start_button.config(state=tk.NORMAL))

    def show_success(subdirs, elapsed_time):
        def _show():
            messagebox.showinfo("Success", f"Macro and PRJ files created in:\n{', '.join(subdirs)}")
        root.after(0, _show)

    def show_error(title, message):
        nonlocal error_flag
        error_flag = True
        print(message)
        root.after(0, lambda: (status_var.set("Error"), messagebox.showerror(title, message)))

    update_status("Copying tiles...")

    try:
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=max_conversions) as executor:
            conversion_started = False
            while True:
                laz_files = [f for f in os.listdir(source_dir) if f.lower().endswith(".laz")]
                processed_any = False
                for filename in laz_files:
                    if filename in processed:
                        continue
                    src_path = os.path.join(source_dir, filename)
                    dest_path = os.path.join(dest_dir, filename)
                    las_output_path = os.path.join(las_root, f"{os.path.splitext(filename)[0]}.las")

                    if skip_existing and os.path.exists(dest_path):
                        print(f"Skipping copy (exists): {dest_path}")
                        processed.add(filename)
                        processed_any = True
                        update_counts(copied_delta=1)
                        last_activity_time = time.time()
                    else:
                        bytes_copied, _ = copy_large_file_safe(src_path, dest_path)
                        if bytes_copied is None:
                            show_error("Copy Error", f"Failed to copy: {src_path}")
                            continue
                        processed.add(filename)
                        processed_any = True
                        update_counts(copied_delta=1)
                        last_activity_time = time.time()

                    if skip_existing and os.path.exists(las_output_path):
                        print(f"Skipping conversion (exists): {las_output_path}")
                        continue

                    if not conversion_started:
                        update_status("Converting tiles...")
                        conversion_started = True
                    future = executor.submit(convert_one_laz_to_las, dest_path, las_root, num_cores)
                    futures.add(future)
                    last_activity_time = time.time()

                    def _conversion_done(f):
                        try:
                            result = f.result()
                            if result:
                                update_counts(converted_delta=1)
                            else:
                                show_error("Conversion Error", "Conversion failed. See console for details.")
                        except Exception as e:
                            show_error("Conversion Error", f"Conversion error: {e}")

                    future.add_done_callback(_conversion_done)

                done = {f for f in futures if f.done()}
                futures.difference_update(done)

                if not copy_as_arrive and not futures:
                    break

                if copy_as_arrive and not processed_any and not futures:
                    if time.time() - last_activity_time >= idle_timeout_sec:
                        break
                time.sleep(poll_interval_sec)
        if error_flag:
            return
        if futures:
            for future in list(futures):
                try:
                    result = future.result()
                    if not result:
                        show_error("Conversion Error", "Conversion failed. See console for details.")
                except Exception as e:
                    show_error("Conversion Error", f"Conversion error: {e}")
            futures.clear()
        if error_flag:
            return
        update_status("Generating macros...")
        subdirs = organize_las_files(las_root)
        for subdir in subdirs:
            unique_point_source_ids = list_point_source_ids(subdir)
            subdir_name = os.path.basename(subdir)

            if subdir_name == "Urban":
                create_macro_and_prj_urban(subdir, unique_point_source_ids)
            elif subdir_name == "Regular":
                create_macro_and_prj(subdir, unique_point_source_ids)
            else:
                create_macro_and_prj(subdir, unique_point_source_ids)
        elapsed_time = time.time() - start_time
        print_rainbow_dashes()
        print(f"Processing took {elapsed_time:.2f} seconds.")
        show_success(subdirs, elapsed_time)
        update_status("Done.")
    except Exception as e:
        show_error("Error", f"Pipeline error: {e}")
    finally:
        if error_flag:
            update_status("Error")
        enable_start_button()

# --- Convert LAZ to LAS ---
def convert_laz_to_las(directory, num_cores):
    laz_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith(".laz")]
    las_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith(".las")]

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

# --- Convert a single LAZ to LAS ---
def convert_one_laz_to_las(laz_path, out_dir, num_cores):
    # Normalize paths (prevents D:/foo\bar mixed separators)
    laz_path = os.path.normpath(laz_path)
    out_dir = os.path.normpath(out_dir)

    if not os.path.isfile(laz_path):
        print(f"Input .laz file not found: {laz_path}")
        return None

    os.makedirs(out_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(laz_path))[0]
    las_path = os.path.normpath(os.path.join(out_dir, f"{base_name}.las"))

    # Remove existing output so we don't hit overwrite behavior
    try:
        if os.path.exists(las_path):
            os.remove(las_path)
    except Exception as e:
        print(f"Could not remove existing LAS: {las_path}\n{e}")
        return None

    # IMPORTANT: do not pass -cores for single file (LAStools ignores and may return nonzero)
    command = [
        "las2las64",
        "-i", laz_path,
        "-olas",
        "-o", las_path
    ]

    print(f"Converting: {laz_path} -> {las_path}")

    r = subprocess.run(command, capture_output=True, text=True)

    # If tool wrote anything, show it (helps future debugging)
    if r.stdout:
        print("stdout:\n" + r.stdout)
    if r.stderr:
        print("stderr:\n" + r.stderr)

    # Treat success as: returncode==0 OR output file exists and is non-trivial size
    if r.returncode != 0:
        if os.path.exists(las_path) and os.path.getsize(las_path) > 1024 * 1024:
            print(f"WARNING: las2las64 returned {r.returncode} but output exists; treating as success: {las_path}")
            return las_path

        print(f"ERROR: las2las64 failed with code {r.returncode}")
        print(f"Command: {' '.join(command)}")
        return None

    if not os.path.exists(las_path) or os.path.getsize(las_path) == 0:
        print("ERROR: las2las64 returned success but output LAS missing/empty.")
        return None

    print("Single-file conversion completed successfully.")
    return las_path

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
    las_files = [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith(".las")]

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
        "FnScanClassifyLow(\"0\",7,6,0.30,5.00,0)",
        "FnScanClassifyLow(\"0\",7,6,0.30,5.00,0)",
        "FnScanClassifyLow(\"0\",7,6,0.30,5.00,0)",
        "FnScanClassifyIsolated(\"0\",7,30,\"0\",15.00,0)",
        "FnScanClassifyIsolated(\"0\",7,15,\"0\",5.00,0)",
        "FnScanClassifyGround(\"0\",2,\"2\",1,40.0,89.00,10.00,1.50,1,5.0,0,2.0,0,0,0)",
        "FnScanClassifyHgtGrd(2,100.0,0,13,15.000,100000.000,0)",
        "FnScanClassifyIsolated(\"13\",7,15,\"0,13\",5.00,0)",
        "FnScanClassifyClass(\"13\",0,0)",
        "FnScanClassifyHgtGrd(2,15.0,0,3,0.000,0.100,0)",
        "FnScanClassifyHgtGrd(2,15.0,0,4,0.100,1.000,0)",
        "FnScanClassifyHgtGrd(2,15.0,0,5,1.000,1000000.000,0)",
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
            "FnScanClassifyCloseby(\"6\",\"0-65535\",\"0-255\",0,3,1.500,0,0,1,\"0\",0,\"0-65535\",0,\"0-255\",0)",
            "FnScanClassifyClass(\"6\",7,0)"
        ])

    macro_content.extend([
        "FnScanClassifyAngle(\"Any\",12,0,-29.00,-99.99,0)",
        "FnScanClassifyAngle(\"Any\",12,0,29.00,99.99,0)",
        "FnScanClassifyLow(\"0\",7,6,0.30,5.00,0)",
        "FnScanClassifyLow(\"0\",7,6,0.30,5.00,0)",
        "FnScanClassifyLow(\"0\",7,6,0.30,5.00,0)",
        "FnScanClassifyIsolated(\"0\",7,30,\"0\",15.00,0)",
        "FnScanClassifyIsolated(\"0\",7,15,\"0\",5.00,0)",
        "FnScanClassifyGround(\"0\",2,\"2\",1,200,89.00,7,1.5,1,5.0,0,2.0,0,0,0)",
        "FnScanClassifyHgtGrd(2,100.0,0,13,15.000,100000.000,0)",
        "FnScanClassifyIsolated(\"13\",7,15,\"0,13\",5.00,0)",
        "FnScanClassifyClass(\"13\",0,0)",
        "FnScanClassifyHgtGrd(2,15.0,0,3,0.000,0.100,0)",
        "FnScanClassifyHgtGrd(2,15.0,0,4,0.100,1.000,0)",
        "FnScanClassifyHgtGrd(2,15.0,0,5,1.000,1000000.000,0)",
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

    las_files = [os.path.join(las_directory, f) for f in os.listdir(las_directory) if f.lower().endswith(".las")]

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

def _check_directory_access(path, require_write=False):
    if not os.path.isdir(path):
        return False, f"Folder not found: {path}"
    if not os.access(path, os.R_OK):
        return False, f"Folder is not readable: {path}"
    if require_write and not os.access(path, os.W_OK):
        return False, f"Folder is not writable: {path}"
    return True, ""

def select_source_directory():
    directory = filedialog.askdirectory()
    if directory:
        source_directory_path.set(directory)

def select_dest_directory():
    directory = filedialog.askdirectory()
    if directory:
        dest_directory_path.set(directory)

def on_start_copy_convert():
    source_dir = source_directory_path.get()
    dest_dir = dest_directory_path.get()
    source_dir = os.path.normpath(source_directory_path.get())
    dest_dir   = os.path.normpath(dest_directory_path.get())
    if not source_dir or not dest_dir:
        messagebox.showerror("Error", "Please select both source and destination folders.")
        return
    if os.path.abspath(source_dir) == os.path.abspath(dest_dir):
        messagebox.showerror("Error", "Source and destination folders must be different.")
        return
    ok, msg = _check_directory_access(source_dir, require_write=False)
    if not ok:
        print(msg)
        messagebox.showerror("Error", msg)
        return
    ok, msg = _check_directory_access(dest_dir, require_write=True)
    if not ok:
        print(msg)
        messagebox.showerror("Error", msg)
        return
    try:
        max_conversions = int(max_conversions_var.get())
    except ValueError:
        messagebox.showerror("Error", "Invalid max concurrent conversions.")
        return
    try:
        num_cores = int(cores_var.get())
    except ValueError:
        messagebox.showerror("Error", "Invalid number of cores selected.")
        return

    copied_count_var.set("0")
    converted_count_var.set("0")
    status_var.set("Starting copy + convert...")
    start_copy_convert_button.config(state=tk.DISABLED)

    las_root = os.path.join(dest_dir, "LAS")
    existing_files = [f for f in os.listdir(dest_dir) if f.lower().endswith(".laz")]
    existing_las = []
    if os.path.isdir(las_root):
        existing_las = [f for f in os.listdir(las_root) if f.lower().endswith(".las")]
    skip_existing = False
    if existing_files or existing_las:
        overwrite = messagebox.askyesno(
            "Existing Files Found",
            "Destination folder contains .laz/.las files.\n\n"
            "Yes = overwrite existing\n"
            "No = skip existing"
        )
        skip_existing = not overwrite

    worker = threading.Thread(
        target=run_copy_convert_pipeline,
        args=(
            source_dir,
            dest_dir,
            copy_as_arrive_var.get(),
            max_conversions,
            num_cores,
            skip_existing,
            status_var,
            copied_count_var,
            converted_count_var,
            start_copy_convert_button
        ),
        daemon=True
    )
    worker.start()

# Path to your ICO
icon_path = resource_path("Macro_Generator.ico")

root = tk.Tk()
root.title(f"Classification Macro Generator v{version}")
root.geometry("520x420")
root.iconbitmap(icon_path)  # sets the window and taskbar icon

directory_path = tk.StringVar()
cores_var = tk.StringVar(value="4")
source_directory_path = tk.StringVar()
dest_directory_path = tk.StringVar()
copy_as_arrive_var = tk.BooleanVar(value=True)
max_conversions_var = tk.StringVar(value="2")
status_var = tk.StringVar(value="Idle")
copied_count_var = tk.StringVar(value="0")
converted_count_var = tk.StringVar(value="0")

tk.Entry(root, textvariable=directory_path, width=50).pack(padx=10, pady=5)
tk.Button(root, text="Select Directory", command=select_directory).pack(pady=5)
tk.Label(root, text="Number of Cores:").pack()
tk.OptionMenu(root, cores_var, *[str(i) for i in range(1, 33)]).pack()
tk.Button(root, text="Create Macro File", command=on_create_macro_file).pack(pady=20)

tk.Label(root, text="Source Folder (Network/UNC):").pack()
tk.Entry(root, textvariable=source_directory_path, width=50).pack(padx=10, pady=5)
tk.Button(root, text="Select Source Folder", command=select_source_directory).pack(pady=5)

tk.Label(root, text="Destination Folder (Local):").pack()
tk.Entry(root, textvariable=dest_directory_path, width=50).pack(padx=10, pady=5)
tk.Button(root, text="Select Destination Folder", command=select_dest_directory).pack(pady=5)

tk.Checkbutton(root, text="Copy from source and process as files arrive",
               variable=copy_as_arrive_var).pack(pady=5)

tk.Label(root, text="Max Concurrent Conversions:").pack()
tk.OptionMenu(root, max_conversions_var, *[str(i) for i in range(1, 5)]).pack()

start_copy_convert_button = tk.Button(root, text="Start Copy + Convert", command=on_start_copy_convert)
start_copy_convert_button.pack(pady=10)

tk.Label(root, textvariable=status_var).pack()
tk.Label(root, text="Copied:").pack()
tk.Label(root, textvariable=copied_count_var).pack()
tk.Label(root, text="Converted:").pack()
tk.Label(root, textvariable=converted_count_var).pack()

root.mainloop()
