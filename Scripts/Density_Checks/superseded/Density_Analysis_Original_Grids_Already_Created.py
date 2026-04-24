import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import geopandas as gpd
import rasterio
from rasterio.mask import mask
from rasterio.features import rasterize
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds
from shapely.geometry import mapping
import glob
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing
import time
import numpy as np
import re

# === Constants root folders ===
TILING_SCHEME_ROOT = r"C:\Vector_Data\UTM_Zones"
WATER_GPKG_ROOT = r"C:\Vector_Data\50m_Buffered_Geopackage_UTM"
LASGRID_EXE = r"C:\LAStools\bin\lasgrid64.exe"

NODATA_VALUE = -9999
MAX_WORKERS = 8

EPSG_BY_UTM = {
    "utm11": 2955,
    "utm10": 3157,
    "utm9": 3156,
    "utm8": 3155,
    "utm7": 3154
}

# === Helper Functions ===

def replace_nodata_with_zero(tif_path):
    """Replace masked nodata in a TIFF with zeros (writes back in place)."""
    with rasterio.open(tif_path) as src:
        data = src.read(1, masked=True)
        meta = src.meta.copy()
    masked_data = np.where(data.mask | (data.data == src.nodata), 0, data.data)
    # Remove nodata from meta (we'll write raw data)
    if "nodata" in meta:
        meta.pop("nodata")
    with rasterio.open(tif_path, "w", **meta) as dst:
        dst.write(masked_data, 1)

def replace_nodata_parallel(tif_files):
    if not tif_files:
        return
    with ThreadPoolExecutor() as executor:
        executor.map(replace_nodata_with_zero, tif_files)

def load_tile_geometries(utm_zone):
    """
    Load the tile shapefile for the specified UTM zone.
    NOTE: uses folder names UTM07, UTM08, etc. (zero-padded).
    This function DOES NOT reproject — it simply reads the shapefile.
    """
    utm_folder = f"UTM{utm_zone:02d}"  # zero-pad single-digit zones for tile folder name
    shapefile_dir = os.path.join(TILING_SCHEME_ROOT, utm_folder)

    if not os.path.isdir(shapefile_dir):
        raise FileNotFoundError(f"Tile folder not found: {shapefile_dir}")

    # Find the shapefile inside shapefile_dir (assume first .shp if multiple)
    shapefiles = [f for f in os.listdir(shapefile_dir) if f.lower().endswith('.shp')]
    if not shapefiles:
        raise FileNotFoundError(f"No shapefile found in {shapefile_dir}")
    shapefile_path = os.path.join(shapefile_dir, shapefiles[0])

    tile_gdf = gpd.read_file(shapefile_path)

    # prepare lookup using lowercased MAP_TILE (same approach as before)
    if "MAP_TILE" not in tile_gdf.columns:
        # try MAPSHEET fallback if your attribute is named differently
        if "MAPSHEET" in tile_gdf.columns:
            tile_gdf["MAP_TILE"] = tile_gdf["MAPSHEET"]
        else:
            raise KeyError("Tile shapefile missing 'MAP_TILE' (or 'MAPSHEET') attribute")

    tile_gdf["MAP_TILE_LOWER"] = tile_gdf["MAP_TILE"].astype(str).str.lower()
    tile_dict = dict(zip(tile_gdf["MAP_TILE_LOWER"], tile_gdf.geometry))

    # We still return crs attribute (no reprojection will be done)
    crs = tile_gdf.crs

    return tile_dict, crs

def load_and_prepare_water(utm_zone, _crs_hint=None):
    """
    Load the water geopackage for the specified UTM zone.
    This function DOES NOT reproject the water layer; it only reads it.
    _crs_hint is accepted only to allow informational warnings (not used to reproject).
    """
    # water gpkg name: UTM[zone]_Water_50m_Buffer.gpkg (note: no zero-pad for gpkg name per your description)
    water_gpkg = os.path.join(WATER_GPKG_ROOT, f"Water_UTM{utm_zone}.gpkg")
    water_layer = f"{utm_zone}_water"

    if not os.path.isfile(water_gpkg):
        raise FileNotFoundError(f"Water geopackage not found: {water_gpkg}")

    water_gdf = gpd.read_file(water_gpkg, layer=water_layer)
    water_sindex = water_gdf.sindex

    return water_gdf, water_sindex

def process_raster(raster_path, tile_dict, water_gdf, water_sindex, clipped_dir):
    """
    Clip raster by tile polygon and mask out water polygons (rasterize).
    This updated function expands the raster to the full tile extent and fills missing areas with 0,
    but then masks OUTSIDE the tile polygon to NODATA (-9999), and also masks water to NODATA.
    It assumes inputs are already aligned (same CRS), otherwise the intersection/rasterize steps may yield empty results.
    """
    filename = os.path.basename(raster_path)
    if os.path.getsize(raster_path) < 1024:
        return f"{filename},SKIP,File is 0 KB"

    # Determine UTM from filename (for checks)
    match = re.search(r'utm(\d{1,2})', filename.lower())
    if not match:
        return f"{filename},SKIP,Could not find UTM zone in filename"

    utm_number = int(match.group(1))
    utm_tag = f"utm{utm_number}"
    if utm_tag not in EPSG_BY_UTM:
        return f"{filename},SKIP,Unsupported UTM zone: {utm_number}"

    # extract tile name from filename (same logic you had)
    tile_name_parts = filename.split("_")[1:5]
    tile_name = "".join(tile_name_parts).lower()
    tile_geom = tile_dict.get(tile_name)
    if tile_geom is None:
        return f"{filename},SKIP,No matching tile geometry"

    try:
        with rasterio.open(raster_path) as src:
            data = src.read(1)
            src_transform = src.transform
            src_crs = src.crs
            src_nodata = src.nodata
            out_meta = src.meta.copy()

        # Determine full tile bounds and intended output grid using source resolution
        minx, miny, maxx, maxy = tile_geom.bounds

        # resolution from source transform (assumes north-up/Cartesian affine)
        res_x = src_transform.a
        res_y = -src_transform.e if src_transform.e < 0 else src_transform.e
        # guard against zero or invalid res
        if res_x == 0 or res_y == 0:
            return f"{filename},ERROR,Invalid source resolution"

        out_width = int(np.ceil((maxx - minx) / res_x))
        out_height = int(np.ceil((maxy - miny) / res_y))

        if out_width <= 0 or out_height <= 0:
            return f"{filename},ERROR,Computed non-positive output dimensions"

        tile_transform = from_bounds(minx, miny, maxx, maxy, out_width, out_height)

        # Prepare destination array (full tile grid) filled with zeros
        # Cast to int32 to safely hold NODATA_VALUE (-9999) even if source dtype was unsigned
        dtype_for_writing = np.int32
        full_tile_data = np.zeros((out_height, out_width), dtype=dtype_for_writing)

        # Reproject existing raster data into the full tile grid, filling missing areas with 0
        # Use nearest resampling to preserve integer density counts
        reproject(
            source=data,
            destination=full_tile_data,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=tile_transform,
            dst_crs=src_crs,
            resampling=Resampling.nearest,
            src_nodata=src_nodata,
            dst_nodata=0
        )

        # find water polygons whose bounds intersect the tile geometry bounds (spatial index)
        bounds = tile_geom.bounds
        water_idxs = list(water_sindex.intersection(bounds)) if water_sindex is not None else []
        water_subset = water_gdf.iloc[water_idxs] if len(water_idxs) else gpd.GeoDataFrame(columns=water_gdf.columns)

        # further filter by intersection (safe even if CRS mismatch — may return empty)
        try:
            water_subset = water_subset[water_subset.intersects(tile_geom)]
        except Exception:
            # if intersects fails due to CRS mismatch types, keep the subset as-is (it may be empty)
            pass

        # Rasterize water geometry into same raster grid (full tile)
        water_mask = np.zeros((out_height, out_width), dtype=bool)
        if not water_subset.empty:
            try:
                water_raster = rasterize(
                    ((geom, 1) for geom in water_subset.geometry),
                    out_shape=(out_height, out_width),
                    transform=tile_transform,
                    fill=0,
                    dtype='uint8'
                )
                water_mask = water_raster.astype(bool)
            except Exception as e:
                print(f"WARNING: rasterize failed for water in {filename}: {e}")
                water_mask = np.zeros((out_height, out_width), dtype=bool)

        # Step 1: apply water mask -> set water pixels to NODATA
        data_after_water = np.where(water_mask, NODATA_VALUE, full_tile_data)

        # Step 2: rasterize the tile boundary EXACTLY to get tile mask
        try:
            tile_mask = rasterize(
                [(tile_geom, 1)],
                out_shape=(out_height, out_width),
                transform=tile_transform,
                fill=0,
                dtype='uint8'
            ).astype(bool)
        except Exception as e:
            # If rasterization of the tile fails for some reason, skip this raster
            return f"{filename},ERROR,Tile rasterize failed: {e}"

        # Step 3: mask out bounding-box slivers (outside tile -> NODATA)
        final_data = np.where(tile_mask, data_after_water, NODATA_VALUE)

        # write clipped raster
        clipped_path = os.path.join(clipped_dir, filename)
        # update metadata to match new grid. Force dtype to int32 to safely store -9999 nodata
        out_meta.update({
            "height": out_height,
            "width": out_width,
            "transform": tile_transform,
            "nodata": NODATA_VALUE,
            "dtype": 'int32'
        })

        # If original had multiple bands, we only consider first band here (same as original behavior)
        with rasterio.open(clipped_path, "w", **out_meta) as dst:
            dst.write(final_data.astype(np.int32)[np.newaxis, :, :])

        # Density check
        valid_pixels = final_data != NODATA_VALUE
        total_valid = np.count_nonzero(valid_pixels)
        count_ge_8 = np.count_nonzero((final_data >= 8) & valid_pixels)
        percent_above_8 = (count_ge_8 / total_valid) * 100 if total_valid > 0 else 0

        result = "PASS" if percent_above_8 >= 95 else "FAIL"
        info = f"{percent_above_8:.2f} >=8"

        return f"{filename},{result},{info}"

    except Exception as e:
        return f"{filename},ERROR,{str(e)}"

def wait_for_all_tifs(directory, min_size_kb=10, timeout=120):
    print("Waiting for all GeoTIFFs to finish writing...")
    start = time.time()
    while True:
        all_tifs = glob.glob(os.path.join(directory, "*.tif"))
        if not all_tifs:
            time.sleep(1)
            continue

        small_files = [f for f in all_tifs if os.path.getsize(f) < min_size_kb * 1024]
        if not small_files:
            print("All GeoTIFFs written.")
            break

        if time.time() - start > timeout:
            print("Warning: Timeout waiting for GeoTIFFs to finish.")
            break

        time.sleep(1)

def sort_tifs_by_utm(output_dir):
    """
    Move TIFFs into utmNN subfolders (e.g. utm7, utm10). Returns list of folder paths created.
    """
    tif_files = glob.glob(os.path.join(output_dir, "*.tif"))
    utm_folders_created = []
    for tif in tif_files:
        filename = os.path.basename(tif)
        match = re.search(r'utm(\d{1,2})', filename.lower())
        if not match:
            print(f"Warning: Could not detect UTM zone in {filename}, skipping sorting.")
            continue
        utm_zone = int(match.group(1))
        utm_folder = f"utm{utm_zone}"
        utm_folder_path = os.path.join(output_dir, utm_folder)
        if not os.path.isdir(utm_folder_path):
            os.makedirs(utm_folder_path, exist_ok=True)
            utm_folders_created.append(utm_folder_path)
        dest_path = os.path.join(utm_folder_path, filename)
        shutil.move(tif, dest_path)
    return utm_folders_created

def clip_density_grids_parallel(utm_folder_path):
    """
    Process all TIFFs within a single utm folder (e.g. .../Last_Return_Density_Rasters/utm10).
    Dynamically loads tile shapefile folder UTMxx (zero-padded) and water gpkg UTM[zone]_Water_50m_Buffer.gpkg.
    """
    utm_match = re.search(r'utm(\d+)', os.path.basename(utm_folder_path).lower())
    if not utm_match:
        print(f"Error: Cannot detect UTM zone from folder: {utm_folder_path}")
        return
    utm_zone = int(utm_match.group(1))

    # load tile geometries and water (no reprojection)
    try:
        tile_dict, tile_crs = load_tile_geometries(utm_zone)
    except Exception as e:
        print(f"ERROR loading tile geometries for UTM{utm_zone}: {e}")
        return

    try:
        water_gdf, water_sindex = load_and_prepare_water(utm_zone, _crs_hint=tile_crs)
    except Exception as e:
        print(f"ERROR loading water for UTM{utm_zone}: {e}")
        # create an empty water_gdf so processing can continue without water masking
        water_gdf = gpd.GeoDataFrame(columns=['geometry'])
        water_sindex = None

    clipped_dir = os.path.join(os.path.dirname(utm_folder_path), "Clipped_Last_Return_Density_Grids", os.path.basename(utm_folder_path))
    os.makedirs(clipped_dir, exist_ok=True)

    raster_files = glob.glob(os.path.join(utm_folder_path, "*.tif"))
    if not raster_files:
        print(f"No TIFFs found in {utm_folder_path}, skipping.")
        return

    log_lines = []
    args = [(path, tile_dict, water_gdf, water_sindex, clipped_dir) for path in raster_files]

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_raster, *arg) for arg in args]
        for future in as_completed(futures):
            result = future.result()
            print(result)
            log_lines.append(result)

    log_path = os.path.join(clipped_dir, "density_check_log.csv")
    with open(log_path, "w") as log_file:
        log_file.write("Filename,Result,Info\n")
        log_file.write("\n".join(log_lines))

def run_density_check(input_dir, custom_output_dir=None):
    if not input_dir:
        messagebox.showwarning("Missing Input", "Please select an input directory.")
        return

    # Input directory already contains density GeoTIFFs
    output_dir = input_dir

    tif_files = glob.glob(os.path.join(input_dir, "*.tif"))
    if not tif_files:
        messagebox.showerror(
            "Error",
            "No GeoTIFFs found in the input directory.\n"
            "This tool now expects pre-generated last return density grids."
        )
        return

    try:
        print("Replacing nodata values in input TIFFs...")
        replace_nodata_parallel(tif_files)

        print("Sorting TIFFs into UTM subfolders...")
        utm_folders = sort_tifs_by_utm(output_dir)
        print(f"Found UTM folders: {utm_folders}")

        for utm_folder in utm_folders:
            print(f"Processing UTM folder: {utm_folder}")
            clip_density_grids_parallel(utm_folder)

        messagebox.showinfo("Done", "Density Checks Complete.")

    except Exception as e:
        messagebox.showerror("Error", str(e))


# === GUI ===
class DensityCheckApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Last Return Density Checker")

        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.use_custom_output = tk.BooleanVar()

        # Input Directory
        tk.Label(master, text="Input Directory:").pack(pady=5)
        tk.Entry(master, textvariable=self.input_dir, width=60).pack(padx=10)
        tk.Button(master, text="Browse", command=self.browse_input_directory).pack(pady=5)

        # Custom Output Toggle
        tk.Checkbutton(master, text="Use custom output directory",
                       variable=self.use_custom_output,
                       command=self.toggle_output_dir).pack(pady=5)

        # Output Directory
        self.output_entry = tk.Entry(master, textvariable=self.output_dir, width=60, state='disabled')
        self.output_entry.pack(padx=10)
        self.output_browse_btn = tk.Button(master, text="Browse Output", command=self.browse_output_directory, state='disabled')
        self.output_browse_btn.pack(pady=5)

        # Run Button
        tk.Button(master, text="Density Check", command=self.start_density_check,
                  bg="green", fg="white", height=2).pack(pady=20)

    def browse_input_directory(self):
        folder = filedialog.askdirectory()
        if folder:
            self.input_dir.set(folder)

    def toggle_output_dir(self):
        if self.use_custom_output.get():
            self.output_entry.config(state='normal')
            self.output_browse_btn.config(state='normal')
        else:
            self.output_entry.config(state='disabled')
            self.output_browse_btn.config(state='disabled')

    def browse_output_directory(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_dir.set(folder)

    def start_density_check(self):
        input_path = self.input_dir.get()
        output_path = self.output_dir.get() if self.use_custom_output.get() else None
        run_density_check(input_path, output_path)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    root = tk.Tk()
    app = DensityCheckApp(root)
    root.mainloop()