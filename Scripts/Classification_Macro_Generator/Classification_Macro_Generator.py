import os
import subprocess
import laspy
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import time
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox
from colorama import Fore, Style
import pickle
import sys
import shutil
import warnings
import threading

# --- Subprocess helpers (hide LAStools windows on Windows) ---
def _subprocess_hide_window_kwargs():
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {
            "startupinfo": si,
            "creationflags": subprocess.CREATE_NO_WINDOW,
        }
    return {}

def _run_lastools(command, cwd=None):
    r = subprocess.run(
        command,
        text=True,
        capture_output=True,
        cwd=cwd,
        **_subprocess_hide_window_kwargs()
    )
    if r.stdout:
        print("LAStools stdout:\n" + r.stdout)
    if r.stderr:
        print("LAStools stderr:\n" + r.stderr)
    return r

# --- PyInstaller windowed app can have stdout/stderr = None ---
def _ensure_streams():
    import sys, os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

_ensure_streams()

warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")

# Version of the executable
version = '4.1.2'

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
def copy_large_file_safe(
    src_path,
    dest_path,
    buffer_size=16 * 1024 * 1024,
    progress_cb=None,          # progress_cb(bytes_done, total_bytes, elapsed_s)
    status_cb=None,            # status_cb(text)
    update_interval=0.25
):
    start_time = time.time()
    bytes_copied = 0
    dest_dir = os.path.dirname(dest_path)
    os.makedirs(dest_dir, exist_ok=True)
    temp_path = dest_path + ".part"

    try:
        total_bytes = None
        try:
            total_bytes = os.path.getsize(src_path)
        except Exception:
            total_bytes = None

        if status_cb:
            status_cb(f"Copying {os.path.basename(src_path)}...")

        last_ui = 0.0
        with open(src_path, "rb") as src_file, open(temp_path, "wb") as dest_file:
            while True:
                chunk = src_file.read(buffer_size)
                if not chunk:
                    break
                dest_file.write(chunk)
                bytes_copied += len(chunk)

                if progress_cb:
                    now = time.time()
                    if (now - last_ui) >= update_interval:
                        elapsed = max(1e-6, now - start_time)
                        progress_cb(bytes_copied, total_bytes, elapsed)
                        last_ui = now

        os.replace(temp_path, dest_path)

        elapsed_time = time.time() - start_time
        if progress_cb:
            progress_cb(bytes_copied, total_bytes, max(1e-6, elapsed_time))

        return bytes_copied, elapsed_time

    except Exception as e:
        print(f"Error during copy: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return None, None

# --- Copy + convert pipeline (background thread) ---
def run_copy_convert_pipeline(source_dir, dest_dir, max_conversions, num_cores,
                              skip_existing, status_var, copied_count_var, converted_count_var,
                              start_button, copy_progress_var, copy_speed_var, copy_file_var):
    copied_count = 0
    converted_count = 0
    total_tiles = 0
    error_flag = False
    las_root = os.path.join(dest_dir, "LAS")
    os.makedirs(las_root, exist_ok=True)

    def update_status(text):
        root.after(0, lambda: status_var.set(text))

    def reset_copy_ui(total):
        def _reset():
            copy_progress_var.set(f"Downloaded: 0/{total} ({total} left)")
            copy_speed_var.set("Speed: -- MiB/s")
            copy_file_var.set("")
        root.after(0, _reset)

    def update_counts(copied_delta=0, converted_delta=0):
        nonlocal copied_count, converted_count
        copied_count += copied_delta
        converted_count += converted_delta
        left = max(total_tiles - copied_count, 0)

        def _update():
            copied_count_var.set(str(copied_count))
            converted_count_var.set(str(converted_count))
            copy_progress_var.set(f"Downloaded: {copied_count}/{total_tiles} ({left} left)")
        root.after(0, _update)

    def update_copy_file(text):
        root.after(0, lambda: copy_file_var.set(text))

    def update_copy_progress(bytes_done, total_bytes, elapsed_s, name):
        speed_mib = (bytes_done / 1024 / 1024) / max(elapsed_s, 1e-6)
        if total_bytes:
            percent = (bytes_done / total_bytes) * 100.0
            file_text = f"{name} {percent:.1f}%"
        else:
            file_text = name

        def _update():
            copy_file_var.set(file_text)
            copy_speed_var.set(f"Speed: {speed_mib:.2f} MiB/s")
        root.after(0, _update)

    def make_progress_cb(name):
        def _progress(bytes_done, total_bytes, elapsed_s):
            update_copy_progress(bytes_done, total_bytes, elapsed_s, name)
        return _progress

    def make_status_cb():
        def _status(text):
            update_copy_file(text)
        return _status

    def enable_start_button():
        root.after(0, lambda: start_button.config(state=tk.NORMAL))

    def show_success(subdirs, elapsed_time):
        def _show():
            paths_text = "\n".join(subdirs)
            messagebox.showinfo("Success", f"Macro and PRJ files created in:\n{paths_text}")
        root.after(0, _show)

    def show_error(title, message):
        nonlocal error_flag

        # If we've already shown an error, don't spam more popups.
        if error_flag:
            print(message)
            return

        error_flag = True
        print(message)
        root.after(0, lambda: (status_var.set("Error"), messagebox.showerror(title, message)))

    update_status("Copying tiles...")

    try:
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=max_conversions) as executor:
            conversion_started = False
            laz_files = sorted(f for f in os.listdir(source_dir) if f.lower().endswith(".laz"))
            total_tiles = len(laz_files)
            reset_copy_ui(total_tiles)
            if not laz_files:
                update_status("No .laz files found in source.")
                root.after(0, lambda: messagebox.showinfo(
                    "No tiles",
                    "No .laz files found in the source folder."
                ))
                return
            for filename in laz_files:
                src_path = os.path.join(source_dir, filename)
                dest_path = os.path.join(dest_dir, filename)
                las_output_path = os.path.join(las_root, f"{os.path.splitext(filename)[0]}.las")

                if skip_existing and os.path.exists(dest_path):
                    print(f"Skipping copy (exists): {dest_path}")
                    update_copy_file(f"Skipping {filename}")
                    update_counts(copied_delta=1)
                else:
                    bytes_copied, _ = copy_large_file_safe(
                        src_path,
                        dest_path,
                        progress_cb=make_progress_cb(filename),
                        status_cb=make_status_cb(),
                        update_interval=0.25
                    )
                    if bytes_copied is None:
                        show_error("Copy Error", f"Failed to copy: {src_path}")
                        continue
                    update_counts(copied_delta=1)

                if skip_existing and os.path.exists(las_output_path):
                    print(f"Skipping conversion (exists): {las_output_path}")
                    continue

                if not conversion_started:
                    update_status("Converting tiles...")
                    conversion_started = True
                future = executor.submit(convert_one_laz_to_las, dest_path, las_root, num_cores)

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
        r = _run_lastools(command, cwd=directory)
        if r.returncode != 0:
            raise subprocess.CalledProcessError(r.returncode, command, r.stdout, r.stderr)
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

    r = _run_lastools(command)

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
    no_console = (sys.stdout is None) or (sys.stderr is None)

    with ThreadPoolExecutor(max_workers=4) as executor:
        with tqdm(total=len(las_files), desc=f"Gathering Point Source IDs in {os.path.basename(directory)}", disable=no_console) as pbar:
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
    """
    Sort root-level LAS files into Urban/Regular (if pickle exists),
    using STEM matching (so .laz vs .las doesn't break),
    and ALWAYS return BOTH Urban and Regular folder paths.
    """
    las_directory = os.path.normpath(las_directory)

    regular_dir = os.path.join(las_directory, "Regular")
    urban_dir = os.path.join(las_directory, "Urban")
    os.makedirs(regular_dir, exist_ok=True)

    # Helper: file stem (no extension)
    def stem(name: str) -> str:
        return os.path.splitext(str(name))[0].lower()

    # If no pickle, we can't sort — put everything in Regular
    if not os.path.exists(pickle_path):
        print("⚠️ No pickle file found — skipping Urban/Regular sort.")
        return [regular_dir]

    # Load and normalize urban tile identifiers
    with open(pickle_path, "rb") as f:
        urban_tiles = pickle.load(f)

    urban_stems = {stem(t) for t in urban_tiles}

    # Only sort LAS files currently sitting in the root LAS dir
    root_las_files = [
        f for f in os.listdir(las_directory)
        if f.lower().endswith(".las") and os.path.isfile(os.path.join(las_directory, f))
    ]

    moved_urban = 0
    moved_regular = 0

    for filename in root_las_files:
        file_stem = stem(filename)

        # Primary: exact stem match
        is_urban = (file_stem in urban_stems)

        # Secondary fallback: substring match (keeps old behavior if your pickle contains partial IDs)
        if not is_urban:
            is_urban = any(u in file_stem for u in urban_stems)

        if is_urban:
            os.makedirs(urban_dir, exist_ok=True)
            dest_folder = urban_dir
            moved_urban += 1
        else:
            dest_folder = regular_dir
            moved_regular += 1

        shutil.move(os.path.join(las_directory, filename), os.path.join(dest_folder, filename))

    print(f"[SORT] Moved Urban: {moved_urban} | Regular: {moved_regular}")
    print(f"[SORT] Regular dir: {regular_dir}")

    result = [regular_dir]
    if moved_urban > 0:
        print(f"[SORT] Urban dir: {urban_dir}")
        result.append(urban_dir)

    return result

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
    paths_text = "\n".join(subdirs)
    messagebox.showinfo("Success", f"Macro and PRJ files created in:\n{paths_text}")

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
    root.after(0, lambda: (
        copy_progress_var.set("Downloaded: 0/0 (0 left)"),
        copy_speed_var.set("Speed: -- MiB/s"),
        copy_file_var.set("")
    ))

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
            max_conversions,
            num_cores,
            skip_existing,
            status_var,
            copied_count_var,
            converted_count_var,
            start_copy_convert_button,
            copy_progress_var,
            copy_speed_var,
            copy_file_var
        ),
        daemon=True
    )
    worker.start()

# --- GUI setup (ttk + 2-column layout) ---

# Path to your ICO
icon_path = resource_path("Macro_Generator.ico")

root = tk.Tk()
root.title(f"Classification Macro Generator v{version}")
root.iconbitmap(icon_path)
root.resizable(True, True)

# A nicer default size for the new 2-column layout
root.geometry("920x430")
root.minsize(840, 400)

# Use a native-ish theme if available
style = ttk.Style()
try:
    style.theme_use("vista")   # best on Windows if available
except tk.TclError:
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

# Slightly nicer padding on buttons/frames
style.configure("TButton", padding=(10, 6))
style.configure("TLabelframe", padding=(10, 8))
style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))

# Variables
directory_path = tk.StringVar()
cores_var = tk.StringVar(value="4")

source_directory_path = tk.StringVar()
dest_directory_path   = tk.StringVar()

max_conversions_var   = tk.StringVar(value="2")

status_var            = tk.StringVar(value="Idle")
copied_count_var      = tk.StringVar(value="0")
converted_count_var   = tk.StringVar(value="0")
copy_progress_var     = tk.StringVar(value="0/0 (0 left)")
copy_speed_var        = tk.StringVar(value="Speed: -- MiB/s")
copy_file_var         = tk.StringVar(value="")

# Root grid config
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

# Main container
main = ttk.Frame(root, padding=12)
main.grid(row=0, column=0, sticky="nsew")
main.columnconfigure(0, weight=1, uniform="maincols")
main.columnconfigure(1, weight=1, uniform="maincols")
main.rowconfigure(0, weight=1)

# ---------- LEFT: Convert existing folder ----------
left = ttk.LabelFrame(main, text="Workflow A — Convert Local Folder → Generate Macro")
left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
left.columnconfigure(0, weight=0)
left.columnconfigure(1, weight=1)
left.columnconfigure(2, weight=0)

ttk.Label(left, text="Input folder (Local):").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

# --- Path row (A) ---
a_path_row = ttk.Frame(left)
a_path_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))
a_path_row.columnconfigure(0, weight=1)

dir_entry = ttk.Entry(a_path_row, textvariable=directory_path)
dir_entry.grid(row=0, column=0, sticky="ew")

ttk.Button(a_path_row, text="Browse…", command=select_directory).grid(row=0, column=1, padx=(8, 0))

ttk.Label(left, text="Cores (LAStools):").grid(row=2, column=0, sticky="w")
cores_combo = ttk.Combobox(left, textvariable=cores_var, values=[str(i) for i in range(1, 9)], state="readonly", width=6)
cores_combo.grid(row=2, column=1, sticky="w", pady=(2, 10))
ttk.Label(left, text="(batch convert; ID scan uses same value)").grid(row=2, column=2, sticky="w", padx=(8, 0), pady=(2, 10))

ttk.Button(left, text="Create Macro File", command=on_create_macro_file).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 0))

# ---------- RIGHT: Copy + convert pipeline ----------
right = ttk.LabelFrame(main, text="Workflow B — Copy From Network → Convert → Generate Macro")
right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
right.columnconfigure(0, weight=0)
right.columnconfigure(1, weight=1)
right.columnconfigure(2, weight=0)

ttk.Label(right, text="Source folder (Network):").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
b_src_row = ttk.Frame(right)
b_src_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))
b_src_row.columnconfigure(0, weight=1)

src_entry = ttk.Entry(b_src_row, textvariable=source_directory_path)
src_entry.grid(row=0, column=0, sticky="ew")

ttk.Button(b_src_row, text="Browse…", command=select_source_directory).grid(row=0, column=1, padx=(8, 0))

ttk.Label(right, text="Destination folder (Local):").grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 4))
b_dst_row = ttk.Frame(right)
b_dst_row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 8))
b_dst_row.columnconfigure(0, weight=1)

dst_entry = ttk.Entry(b_dst_row, textvariable=dest_directory_path)
dst_entry.grid(row=0, column=0, sticky="ew")

ttk.Button(b_dst_row, text="Browse…", command=select_dest_directory).grid(row=0, column=1, padx=(8, 0))

ttk.Label(right, text="Cores (Parallel tiles):").grid(row=4, column=0, sticky="w")
max_combo = ttk.Combobox(right, textvariable=max_conversions_var, values=[str(i) for i in range(1, 9)], state="readonly", width=6)
max_combo.grid(row=4, column=1, sticky="w", pady=(2, 10))
ttk.Label(right, text="(tiles convert in parallel; ID scan uses same value)").grid(row=4, column=2, sticky="w", padx=(8, 0), pady=(2, 10))

start_copy_convert_button = ttk.Button(right, text="Start Copy + Convert", command=on_start_copy_convert)
start_copy_convert_button.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(6, 0))

ttk.Label(right, textvariable=copy_progress_var).grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
ttk.Label(right, textvariable=copy_file_var).grid(row=7, column=0, columnspan=3, sticky="w")
ttk.Label(right, textvariable=copy_speed_var).grid(row=8, column=0, columnspan=3, sticky="w", pady=(0, 4))

# ---------- Bottom status bar (spans both columns) ----------
status_bar = ttk.Frame(main, padding=(8, 10))
status_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
status_bar.columnconfigure(0, weight=1)

ttk.Separator(main).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 6))

status_line = ttk.Frame(main)
status_line.grid(row=3, column=0, columnspan=2, sticky="ew")
status_line.columnconfigure(1, weight=1)

ttk.Label(status_line, text="Status:").grid(row=0, column=0, sticky="w")
ttk.Label(status_line, textvariable=status_var).grid(row=0, column=1, sticky="w")

ttk.Label(status_line, text="Copied:").grid(row=0, column=2, sticky="e", padx=(20, 4))
ttk.Label(status_line, textvariable=copied_count_var, width=6).grid(row=0, column=3, sticky="w")

ttk.Label(status_line, text="Converted:").grid(row=0, column=4, sticky="e", padx=(20, 4))
ttk.Label(status_line, textvariable=converted_count_var, width=6).grid(row=0, column=5, sticky="w")

# Let layout settle, then clamp min size to content
root.update_idletasks()

root.mainloop()
