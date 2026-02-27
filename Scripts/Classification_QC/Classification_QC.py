import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import ttkbootstrap as ttkb
import tempfile
import shutil
import os
import random

# ------------------------------------------------------------------
# Silence GDAL DXF warning + set GDAL paths early
# ------------------------------------------------------------------
os.environ["CPL_LOG"] = "ERROR"   # suppress harmless GDAL warnings

import rasterio

# ------------------------------------------------------------------
# Set GDAL / PROJ paths ONLY if discoverable
# ------------------------------------------------------------------
gdal_data = rasterio.env.GDALDataFinder().search()
proj_data = rasterio.env.PROJDataFinder().search()

if gdal_data:
    os.environ["GDAL_DATA"] = gdal_data

if proj_data:
    os.environ["PROJ_LIB"] = proj_data

import sys
from colorama import Fore, Style
import numpy as np
from rasterio.crs import CRS
from rasterio.transform import from_bounds
import re

# ------------------------------------------------------------------
# Version
# ------------------------------------------------------------------
VERSION = "2.7"

# ------------------------------------------------------------------
# Hardcoded WKT for BC UTM zones — no PROJ database lookup needed.
# Update central_meridian / AUTHORITY if adding new zones.
# ------------------------------------------------------------------
_UTM_WKT = {
    3154: 'PROJCS["NAD83(CSRS) / UTM zone 7N",GEOGCS["NAD83(CSRS)",DATUM["NAD83_Canadian_Spatial_Reference_System",SPHEROID["GRS 1980",6378137,298.257222101]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-141],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG","3154"]]',
    3155: 'PROJCS["NAD83(CSRS) / UTM zone 8N",GEOGCS["NAD83(CSRS)",DATUM["NAD83_Canadian_Spatial_Reference_System",SPHEROID["GRS 1980",6378137,298.257222101]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-135],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG","3155"]]',
    3156: 'PROJCS["NAD83(CSRS) / UTM zone 9N",GEOGCS["NAD83(CSRS)",DATUM["NAD83_Canadian_Spatial_Reference_System",SPHEROID["GRS 1980",6378137,298.257222101]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-129],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG","3156"]]',
    3157: 'PROJCS["NAD83(CSRS) / UTM zone 10N",GEOGCS["NAD83(CSRS)",DATUM["NAD83_Canadian_Spatial_Reference_System",SPHEROID["GRS 1980",6378137,298.257222101]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-123],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG","3157"]]',
    2955: 'PROJCS["NAD83(CSRS) / UTM zone 11N",GEOGCS["NAD83(CSRS)",DATUM["NAD83_Canadian_Spatial_Reference_System",SPHEROID["GRS 1980",6378137,298.257222101]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-117],PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],PARAMETER["false_northing",0],UNIT["metre",1],AUTHORITY["EPSG","2955"]]',
}

# ------------------------------------------------------------------
# Controls
# ------------------------------------------------------------------
# Tile adjacency: how big a gap between tiles is still "same island"
ADJACENCY_TILE_GAP_FACTOR = 0.01   # 1% of tile width

# Island-level bbox merge: how much to expand island bboxes
# 0.0 = strict, >0 expands boxes a bit before overlap test
ISLAND_BBOX_GAP_FACTOR = 0.0

# ------------------------------------------------------------------
# PyInstaller GDAL/PROJ setup
# ------------------------------------------------------------------
if getattr(sys, "frozen", False):
    base_path = sys._MEIPASS
    os.environ["GDAL_DATA"] = os.path.join(base_path, "gdal_data")
    os.environ["PROJ_LIB"] = os.path.join(base_path, "proj_data")


def _bbox_intersects(a, b):
    """Return True if two (minx, miny, maxx, maxy) bboxes overlap."""
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


class ClassificationQC:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Classification QC  v{VERSION}")
        self.root.resizable(False, False)

        # -----------------------
        # Window icon
        # -----------------------
        icon_name = r"QC_icon.ico"

        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
            bundled_icon_path = os.path.join(base_path, icon_name)
            temp_icon_path = os.path.join(tempfile.gettempdir(), icon_name)
            try:
                shutil.copy(bundled_icon_path, temp_icon_path)
                icon_path = temp_icon_path
            except Exception as e:
                print(f"Failed to copy ICO to temp file: {e}")
                icon_path = bundled_icon_path
        else:
            icon_path = r"C:\Users\NSENILOV\BC_LiDAR_Production\Scripts\Classification_QC\ico\QC_icon.ico"

        self.icon_path = icon_path
        try:
            root.iconbitmap(icon_path)
        except Exception as e:
            print(f"Failed to set window icon: {e}")

        # -----------------------
        # Variables
        # -----------------------
        self.input_dir_path = None
        self.cores_var            = tk.StringVar(value="4")
        self.class_7_var          = tk.IntVar(value=1)
        self.default_density_var  = tk.IntVar(value=1)
        self.hillshade_var        = tk.IntVar(value=1)
        self.hill_step_var        = tk.StringVar(value="2")
        self.ground_density_var   = tk.IntVar(value=0)
        self.high_noise_range_var = tk.IntVar(value=0)
        self.hp_step_var          = tk.StringVar(value="2")

        # -----------------------
        # Layout
        # -----------------------
        outer = ttk.Frame(root, padding=(16, 12, 16, 8))
        outer.pack(fill="both", expand=True)

        # ── Top row: directory button + cores ────────────────────────
        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 4))

        ttkb.Button(
            top, text="Select Input Directory",
            bootstyle="secondary-outline",
            command=self.choose_directory,
            width=26,
        ).pack(side="left")

        ttk.Combobox(
            top, textvariable=self.cores_var,
            values=[str(i) for i in range(1, 17)],
            width=3, state="readonly",
        ).pack(side="right")
        ttk.Label(top, text="Cores:").pack(side="right", padx=(0, 4))

        self.input_dir_label = ttk.Label(
            outer, text="No directory selected",
            foreground="gray", wraplength=678,
        )
        self.input_dir_label.pack(fill="x", pady=(0, 8))

        ttk.Separator(outer).pack(fill="x", pady=(0, 10))

        # ── Two-column panels ─────────────────────────────────────────
        panels = ttk.Frame(outer)
        panels.pack(fill="both", expand=False)
        panels.columnconfigure(0, weight=1, uniform="panel")
        panels.columnconfigure(1, weight=1, uniform="panel")

        # Left — Main QC Rasters
        main_lf = ttk.LabelFrame(
            panels, text="  Main QC Rasters  ",
            padding=(12, 8),
        )
        main_lf.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ttkb.Checkbutton(
            main_lf, text="Outlier Density",
            variable=self.class_7_var,
            bootstyle="success-round-toggle",
        ).pack(anchor="w", pady=2)
        ttkb.Checkbutton(
            main_lf, text="Default Density",
            variable=self.default_density_var,
            bootstyle="success-round-toggle",
        ).pack(anchor="w", pady=2)

        hill_frame = ttk.Frame(main_lf)
        hill_frame.pack(fill="x", pady=2)
        ttkb.Checkbutton(
            hill_frame, text="Hillshade",
            variable=self.hillshade_var,
            bootstyle="success-round-toggle",
        ).pack(side="left")
        ttk.Combobox(
            hill_frame, textvariable=self.hill_step_var,
            values=["0.5", "1", "2"], width=4, state="readonly",
        ).pack(side="right")
        ttk.Label(hill_frame, text="(m):", foreground="gray").pack(side="right", padx=(0, 4))

        # Right — Optional QC Rasters
        opt_lf = ttk.LabelFrame(
            panels, text="  Optional QC Rasters  ",
            padding=(12, 8),
        )
        opt_lf.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        ttkb.Checkbutton(
            opt_lf, text="Ground Density",
            variable=self.ground_density_var,
            bootstyle="secondary-round-toggle",
        ).pack(anchor="w", pady=2)


        hp_frame = ttk.Frame(opt_lf)
        hp_frame.pack(fill="x", pady=2)
        ttkb.Checkbutton(
            hp_frame, text="High Point Range",
            variable=self.high_noise_range_var,
            bootstyle="secondary-round-toggle",
        ).pack(side="left")
        ttk.Combobox(
            hp_frame, textvariable=self.hp_step_var,
            values=["0.5", "1", "2", "3", "4", "5"], width=4, state="readonly",
        ).pack(side="right")
        ttk.Label(hp_frame, text="(m):", foreground="gray").pack(side="right", padx=(0, 4))

        # ── Start button ──────────────────────────────────────────────
        ttk.Separator(outer).pack(fill="x", pady=(10, 10))

        btn_row = ttk.Frame(outer)
        btn_row.pack(fill="x")
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(2, weight=1)

        ttkb.Button(
            btn_row, text="Start Processing",
            bootstyle="primary",
            command=self._start_processing_impl,
            width=26,
        ).grid(row=0, column=1)

        ttk.Label(
            btn_row, text=f"v{VERSION}",
            foreground="gray", font=("TkDefaultFont", 8),
        ).grid(row=0, column=2, sticky="se")

        # Fit window height to content, keep fixed width
        self.root.update_idletasks()
        self.root.geometry(f"710x{self.root.winfo_reqheight()}")

        if not self.check_lastools_license():
            return

    # -------------------------------------------------------------------------
    # Utility / license
    # -------------------------------------------------------------------------
    def print_rainbow_dashes(self, line_length=120):
        rainbow_colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]
        for i in range(line_length):
            print(rainbow_colors[i % len(rainbow_colors)] + "-" + Style.RESET_ALL, end="")
        print()

    def check_lastools_license(self):
        lastools_license_path = r"C:\LAStools\bin\lastoolslicense.txt"
        if not os.path.exists(lastools_license_path):
            messagebox.showerror(
                "Error",
                "No LASTools license file found. Please ensure that LASTools is properly installed, "
                "and that the lastoolslicense.txt file is present in C:\\LAStools\\bin."
            )
            self.root.destroy()
            return False
        return True

    def choose_directory(self):
        self.input_dir_path = filedialog.askdirectory()
        if self.input_dir_path:
            lidar_files = [file for file in os.listdir(self.input_dir_path)
                           if file.lower().endswith('.las')]
            if not lidar_files:
                messagebox.showinfo(
                    "Error",
                    "No .las files found in the selected directory. "
                    "Choose a directory containing .las files to continue."
                )
                self.input_dir_path = None
            else:
                self.input_dir_label.config(text=self.input_dir_path)

    # -------------------------------------------------------------------------
    # Island-based merge with ISLAND-LEVEL BBOX MERGING
    # -------------------------------------------------------------------------
    def merge_geotiffs_by_island(self, input_dir, output_base, label, nodata_value=0):
        """
        1) Identify tile-level islands by adjacency.
        2) Build bounding boxes for each island.
        3) Merge islands whose bounding boxes intersect.
        4) Merge all tiles in each final group into one GeoTIFF.
        5) Only AFTER islands are defined, move the original tile TIFFs
        (i.e., LAStools-created per-tile output) into input_dir/Original.
        """

        # -------------------------------------------------
        # 1) Collect ONLY raw LAStools-created GeoTIFFs
        # -------------------------------------------------
        tif_files = []
        for f in os.listdir(input_dir):
            fl = f.lower()
            if not fl.endswith(".tif"):
                continue
            # Ignore previously created outputs
            if fl.startswith("_") or "merged" in fl or "island" in fl:
                continue
            tif_files.append(os.path.join(input_dir, f))

        if not tif_files:
            print(f"No GeoTIFFs found for merging in: {input_dir}")
            return

        print(f"Creating islands of connected tiles ({label})...")

        # -------------------------------------------------
        # 2) Detect EPSG from filename (best-effort)
        # -------------------------------------------------
        first_filename = os.path.basename(tif_files[0])
        utm_epsg_mapping = {"7": 3154, "8": 3155, "9": 3156, "10": 3157, "11": 2955}
        match = re.search(r'utm(7|8|9|10|11)', first_filename, re.IGNORECASE)
        if match:
            utm_zone = match.group(1)
            epsg_code = utm_epsg_mapping[utm_zone]
        else:
            raise ValueError(
                f"Cannot determine UTM zone from filename: {first_filename!r}\n\n"
                f"Filenames must include the UTM zone number (e.g. 'utm9', 'utm10', 'utm11').\n"
                f"Supported BC zones: UTM 7–11 (EPSG 3154, 3155, 3156, 3157, 2955)."
            )

        print(f"Using EPSG:{epsg_code} for merged GeoTIFF(s).")

        # -------------------------------------------------
        # 3) Read bounds and estimate tile size (uses original files)
        # -------------------------------------------------
        geometries = []
        widths = []
        with rasterio.Env():
            for fp in tif_files:
                with rasterio.open(fp) as src:
                    b = src.bounds
                    geometries.append((b.left, b.bottom, b.right, b.top))
                    widths.append(b.right - b.left)

        if not geometries:
            print("No geometries extracted from GeoTIFFs.")
            return

        tile_width = float(np.median(widths))
        tile_gap = tile_width * ADJACENCY_TILE_GAP_FACTOR

        # Buffered geometries for adjacency
        buffered_tiles = [(g[0]-tile_gap, g[1]-tile_gap, g[2]+tile_gap, g[3]+tile_gap) for g in geometries]

        # -------------------------------------------------
        # 4) Build tile-level islands (connectivity)
        # -------------------------------------------------
        n = len(geometries)
        used = set()
        tile_islands = []  # list of lists of tile indices

        for i in range(n):
            if i in used:
                continue
            isl = [i]
            used.add(i)
            q = [i]
            while q:
                cur = q.pop()
                gcur_buff = buffered_tiles[cur]
                for j in range(n):
                    if j in used:
                        continue
                    if _bbox_intersects(gcur_buff, geometries[j]):
                        used.add(j)
                        q.append(j)
                        isl.append(j)
            tile_islands.append(isl)

        print(f"Initial tile-based islands: {len(tile_islands)}")

        # -------------------------------------------------
        # 5) Build and expand bounding boxes for islands
        # -------------------------------------------------
        island_boxes = []
        for isl in tile_islands:
            xs_min, ys_min, xs_max, ys_max = [], [], [], []
            for idx in isl:
                minx, miny, maxx, maxy = geometries[idx]
                xs_min.append(minx); ys_min.append(miny); xs_max.append(maxx); ys_max.append(maxy)

            expand_x = tile_width * ISLAND_BBOX_GAP_FACTOR
            expand_y = tile_width * ISLAND_BBOX_GAP_FACTOR

            island_boxes.append(
                (min(xs_min) - expand_x, min(ys_min) - expand_y,
                 max(xs_max) + expand_x, max(ys_max) + expand_y)
            )

        # -------------------------------------------------
        # 6) Merge islands whose bboxes intersect -> final_groups
        # -------------------------------------------------
        m = len(island_boxes)
        used_islands = set()
        final_groups = []

        for i in range(m):
            if i in used_islands:
                continue
            grp = [i]
            used_islands.add(i)
            q = [i]
            while q:
                cur = q.pop()
                cur_box = island_boxes[cur]
                for j in range(m):
                    if j in used_islands:
                        continue
                    if _bbox_intersects(cur_box, island_boxes[j]):
                        used_islands.add(j)
                        q.append(j)
                        grp.append(j)
            final_groups.append(grp)

        print(f"After bbox-based island merge: {len(final_groups)} final island group(s).")

        # -------------------------------------------------
        # 7) Merge tiles for each final island group (do NOT move files yet)
        # -------------------------------------------------
        final_groups.sort(key=lambda g: len(g), reverse=True)

        merge_success = True
        merge_errors = []

        for group_idx, group in enumerate(final_groups, start=1):
            # build list of tile indices and file paths to merge
            tile_indices = sorted({i for isl in group for i in tile_islands[isl]})
            files_to_merge = [tif_files[i] for i in tile_indices]

            out_path = f"{output_base}_Island_{group_idx}.tif"
            print(f"  • Final Island {group_idx}: {len(files_to_merge)} tiles → {os.path.basename(out_path)}")

            # open sources
            srcs = []
            try:
                srcs = [rasterio.open(fp) for fp in files_to_merge]
            except Exception as e:
                merge_success = False
                merge_errors.append(f"Failed to open sources for island {group_idx}: {e}")
                # close any that did open
                for s in srcs:
                    try:
                        s.close()
                    except Exception:
                        pass
                # skip this island and continue (do not move originals)
                continue

            try:
                # Manual numpy mosaic — avoids rasterio.merge() which causes
                # a native GDAL crash with certain LAStools GeoTIFF outputs.
                all_bounds = [s.bounds for s in srcs]
                out_left   = min(b.left   for b in all_bounds)
                out_bottom = min(b.bottom for b in all_bounds)
                out_right  = max(b.right  for b in all_bounds)
                out_top    = max(b.top    for b in all_bounds)
                res_x, res_y = srcs[0].res
                out_width  = max(1, round((out_right - out_left)   / res_x))
                out_height = max(1, round((out_top   - out_bottom) / res_y))
                out_transform = from_bounds(out_left, out_bottom, out_right, out_top,
                                            out_width, out_height)
                out_count = srcs[0].count
                out_dtype = srcs[0].dtypes[0]
                mosaic = np.full((out_count, out_height, out_width),
                                 nodata_value, dtype=out_dtype)
                for src in srcs:
                    col_off = max(0, round((src.bounds.left - out_left)  / res_x))
                    row_off = max(0, round((out_top - src.bounds.top)    / res_y))
                    data = src.read()
                    h = min(data.shape[1], out_height - row_off)
                    w = min(data.shape[2], out_width  - col_off)
                    if h <= 0 or w <= 0:
                        continue
                    patch = data[:, :h, :w]
                    valid = patch != nodata_value
                    mosaic[:, row_off:row_off+h, col_off:col_off+w] = np.where(
                        valid, patch,
                        mosaic[:, row_off:row_off+h, col_off:col_off+w]
                    )

                # Hardcoded WKT — no PROJ database lookup.
                src_crs = CRS.from_wkt(_UTM_WKT[epsg_code])

                meta = srcs[0].meta.copy()
                meta.update({
                    "driver": "GTiff",
                    "height": mosaic.shape[1],
                    "width": mosaic.shape[2],
                    "transform": out_transform,
                    "nodata": nodata_value,
                    "count": mosaic.shape[0],
                    "crs": src_crs,
                    "compress": "LZW",
                    "tiled": True,
                    "blockxsize": 256,
                    "blockysize": 256
                })

                with rasterio.open(out_path, "w", **meta) as dst:
                    dst.write(mosaic)

            except Exception as e:
                merge_success = False
                merge_errors.append(f"Failed to merge/write island {group_idx}: {e}")

            finally:
                for s in srcs:
                    try:
                        s.close()
                    except Exception:
                        pass

        # -------------------------------------------------
        # 8) ONLY IF we successfully at least attempted merges, move the original LAStools-created tiles
        #    (we move the tif_files list which we collected earlier)
        # -------------------------------------------------
        # NOTE: We choose to move regardless of merge_success, but you can change to only move when merge_success==True.
        # We'll move if at least one merge succeeded or if user prefers unconditional move; here we'll move only if there
        # was no catastrophic failure opening files (i.e., tif_files existed and we opened them above successfully at least).
        if not tif_files:
            # nothing to move
            return

        # If every island failed to open, avoid moving (safer)
        if len(merge_errors) == len(final_groups) and len(final_groups) > 0:
            print("All island merges failed to open/merge. Aborting move of original tiles. Errors:")
            for e in merge_errors:
                print("  -", e)
            return

        original_dir = os.path.join(input_dir, "Original")
        os.makedirs(original_dir, exist_ok=True)

        moved = []
        failed_moves = []
        for fp in tif_files:
            dst = os.path.join(original_dir, os.path.basename(fp))
            try:
                # ensure destination doesn't already exist (avoid overwrite)
                if os.path.exists(dst):
                    # if same file already present, remove source
                    # but be conservative: if sizes differ, rename instead
                    try:
                        if os.path.getsize(dst) == os.path.getsize(fp):
                            os.remove(fp)
                            moved.append(fp)
                        else:
                            # make unique name
                            base, ext = os.path.splitext(os.path.basename(fp))
                            newname = f"{base}_orig{ext}"
                            dst2 = os.path.join(original_dir, newname)
                            shutil.move(fp, dst2)
                            moved.append(fp)
                    except Exception as e:
                        failed_moves.append((fp, str(e)))
                else:
                    shutil.move(fp, dst)
                    moved.append(fp)
            except Exception as e:
                failed_moves.append((fp, str(e)))

        print(f"Moved {len(moved)} original tile(s) to: {original_dir}")
        if failed_moves:
            print(f"Failed to move {len(failed_moves)} file(s):")
            for fp, err in failed_moves:
                print(f"  - {fp}: {err}")

        if merge_errors:
            print("Merge completed with some errors:")
            for e in merge_errors:
                print("  -", e)

    # -------------------------------------------------------------------------
    # Main processing
    # -------------------------------------------------------------------------
    def _start_processing_impl(self):
        try:
            if not self.input_dir_path:
                messagebox.showinfo(
                    "Error",
                    "No input directory has been selected. Please choose a directory containing .las files."
                )
                return

            if (not self.hillshade_var.get()
                and not self.high_noise_range_var.get()
                and not self.ground_density_var.get()
                and not self.class_7_var.get()
                and not self.default_density_var.get()):
                messagebox.showinfo("Error", "No QC tests selected")
                return

            qc_rasters_dir = os.path.join(self.input_dir_path, "Classification_QC_Rasters")
            os.makedirs(qc_rasters_dir, exist_ok=True)

            cores = self.cores_var.get()
            hp_step = self.hp_step_var.get()
            hill_step = self.hill_step_var.get()

            # High Point Range
            if self.high_noise_range_var.get():
                high_noise_range_dir = os.path.join(qc_rasters_dir, "High_Point_Range_Rasters")
                os.makedirs(high_noise_range_dir, exist_ok=True)
                print("Creating High Point Range Rasters...")
                ret = os.system(
                    f'lasgrid64 -i "{self.input_dir_path}\\*.las" '
                    f'-nodata 0 -no_world_file -no_kml -range -cores {cores} '
                    f'-false -nodata 0 -quiet -keep_class 1 2 3 4 5 '
                    f'-otif -odir "{high_noise_range_dir}" -step {hp_step}'
                )
                if ret != 0:
                    raise RuntimeError(f"lasgrid64 failed (exit code {ret}). Check that LASTools is installed correctly.")
                out_base = os.path.join(high_noise_range_dir, "_High_Point_Range_Merged")
                self.merge_geotiffs_by_island(high_noise_range_dir, out_base, "High Point Range", nodata_value=0)
                self.print_rainbow_dashes()

            # Outlier Density (Class 7)
            if self.class_7_var.get():
                class_7_dir = os.path.join(qc_rasters_dir, "Outlier_Density")
                os.makedirs(class_7_dir, exist_ok=True)
                print("Creating Outlier Density tiles...")
                ret = os.system(
                    f'lasgrid64 -i "{self.input_dir_path}\\*.las" '
                    f'-cores {cores} -step 6 -false -quiet '
                    f'-no_world_file -no_kml -nodata 0 -keep_class 7 '
                    f'-point_density -otif -odir "{class_7_dir}"'
                )
                if ret != 0:
                    raise RuntimeError(f"lasgrid64 failed (exit code {ret}). Check that LASTools is installed correctly.")
                out_base = os.path.join(class_7_dir, "_Outlier_Density_Merged")
                self.merge_geotiffs_by_island(class_7_dir, out_base, "Outlier Density", nodata_value=0)
                self.print_rainbow_dashes()

            # Default Density (Class 1)
            if self.default_density_var.get():
                default_density_dir = os.path.join(qc_rasters_dir, "Default_Density")
                os.makedirs(default_density_dir, exist_ok=True)
                print("Creating Default Density tiles...")
                ret = os.system(
                    f'lasgrid64 -i "{self.input_dir_path}\\*.las" '
                    f'-no_world_file -no_kml -cores {cores} '
                    f'-point_density -false -nodata 0 -quiet -keep_class 1 '
                    f'-otif -odir "{default_density_dir}" -step 6'
                )
                if ret != 0:
                    raise RuntimeError(f"lasgrid64 failed (exit code {ret}). Check that LASTools is installed correctly.")
                out_base = os.path.join(default_density_dir, "_Default_Density_Merged")
                self.merge_geotiffs_by_island(default_density_dir, out_base, "Default Density", nodata_value=0)
                self.print_rainbow_dashes()

            # Ground Density (Class 2)
            if self.ground_density_var.get():
                ground_density_dir = os.path.join(qc_rasters_dir, "Ground_Density")
                os.makedirs(ground_density_dir, exist_ok=True)
                print("Creating Ground Density tiles...")
                ret = os.system(
                    f'lasgrid64 -i "{self.input_dir_path}\\*.las" '
                    f'-no_world_file -no_kml -cores {cores} '
                    f'-point_density -false -nodata 0 -quiet -keep_class 2 '
                    f'-otif -odir "{ground_density_dir}" -step 6'
                )
                if ret != 0:
                    raise RuntimeError(f"lasgrid64 failed (exit code {ret}). Check that LASTools is installed correctly.")
                out_base = os.path.join(ground_density_dir, "_Ground_Density_Merged")
                self.merge_geotiffs_by_island(ground_density_dir, out_base, "Ground Density", nodata_value=0)
                self.print_rainbow_dashes()

            # Hillshade (Class 2 → blast2dem64)
            if self.hillshade_var.get():
                hillshade_dir = os.path.join(qc_rasters_dir, "Hillshade_Raster")
                os.makedirs(hillshade_dir, exist_ok=True)
                print("Creating Hillshade tiles...")
                ret = os.system(
                    f'blast2dem64 -i "{self.input_dir_path}\\*.las" '
                    f'-cores {cores} -hillshade -no_kml -no_world_file '
                    f'-nodata 0 -keep_class 2 -otif -kill 100 '
                    f'-odir "{hillshade_dir}" -step {hill_step} >nul 2>&1'
                )
                if ret != 0:
                    raise RuntimeError(f"blast2dem64 failed (exit code {ret}). Check that LASTools is installed correctly.")
                out_base = os.path.join(hillshade_dir, "_Hillshade_Merged")
                self.merge_geotiffs_by_island(hillshade_dir, out_base, "Hillshade", nodata_value=0)
                self.print_rainbow_dashes()

            # COMPLETE
            print(f"""{Fore.LIGHTGREEN_EX}
        ( C | O | M | P | L | E | T | E )
        {Style.RESET_ALL}
        """)

            self._show_celebration(qc_rasters_dir)

        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Error", str(e))


    def _show_celebration(self, output_dir):
        BG = "#1e1e1e"

        win = tk.Toplevel(self.root)
        win.title("Complete!")
        win.geometry("480x270")
        win.resizable(False, False)
        win.grab_set()
        win.after(50, lambda: win.iconbitmap(self.icon_path))

        canvas = tk.Canvas(win, highlightthickness=0, bd=0, width=480, height=270)
        canvas.pack(fill="both", expand=True)

        # Full dark background drawn as a rectangle (immune to theme overrides)
        canvas.create_rectangle(0, 0, 480, 270, fill=BG, outline="")

        canvas.create_text(240, 100, text="Classification QC Complete!",
                           font=("TkDefaultFont", 13, "bold"), fill="white")
        canvas.create_text(240, 126, text="All rasters processed successfully.",
                           font=("TkDefaultFont", 10), fill="#666666")

        colors = ["#FF6B6B", "#FFE66D", "#4ECDC4", "#45B7D1", "#96CEB4",
                  "#FF9FF3", "#54A0FF", "#FFA07A", "#98FB98", "#DDA0DD"]
        pieces = []
        for _ in range(55):
            x = random.randint(0, 480)
            y = random.randint(-250, 0)
            w = random.randint(8, 16)
            h = random.randint(4, 9)
            color = random.choice(colors)
            dx = random.uniform(-1.5, 1.5)
            dy = random.uniform(2.5, 6.0)
            if random.random() < 0.5:
                item = canvas.create_rectangle(x, y, x + w, y + h, fill=color, outline="")
            else:
                item = canvas.create_oval(x, y, x + w, y + w, fill=color, outline="")
            pieces.append({"id": item, "x": x, "y": y, "w": w, "h": h, "dx": dx, "dy": dy})

        running = [True]

        def animate():
            if not running[0]:
                return
            for p in pieces:
                p["x"] += p["dx"]
                p["y"] += p["dy"]
                p["dy"] = min(p["dy"] + 0.07, 10)
                if p["y"] > 270:
                    p["y"] = random.randint(-30, -5)
                    p["x"] = random.randint(0, 480)
                    p["dy"] = random.uniform(2.5, 5.5)
                canvas.coords(p["id"], p["x"], p["y"], p["x"] + p["w"], p["y"] + p["h"])
            win.after(20, animate)

        animate()

        def close():
            running[0] = False
            win.destroy()

        def open_folder():
            running[0] = False
            win.destroy()
            os.startfile(output_dir)

        # Place buttons directly in canvas (no frame bg gap between them)
        btn_open = ttkb.Button(canvas, text="Open Output Folder",
                               bootstyle="success", command=open_folder, width=20)
        btn_done = ttkb.Button(canvas, text="Done",
                               bootstyle="success", command=close, width=10)
        canvas.create_window(160, 210, window=btn_open)
        canvas.create_window(365, 210, window=btn_done)

        win.protocol("WM_DELETE_WINDOW", close)


if __name__ == "__main__":
    root = ttkb.Window(themename="cosmo")
    app = ClassificationQC(root)
    root.mainloop()
