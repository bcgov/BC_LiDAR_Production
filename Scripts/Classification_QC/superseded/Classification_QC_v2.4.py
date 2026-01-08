import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tempfile
import shutil
import os
import sys
from colorama import Fore, Style
import rasterio
import numpy as np
from rasterio.crs import CRS
from rasterio.merge import merge
from scipy.ndimage import binary_erosion
from shapely.geometry import box

if getattr(sys, "frozen", False):
    base_path = sys._MEIPASS
    os.environ["GDAL_DATA"] = os.path.join(base_path, "gdal_data")
    os.environ["PROJ_LIB"] = os.path.join(base_path, "proj_data")

class ClassificationQC:
    def __init__(self, root):
        self.root = root
        self.root.title("Classification_QC_v2.4")
        self.root.geometry("600x425")

        # -----------------------
        # Setup the ICO for Tkinter
        # -----------------------
        icon_name = r"Class_QC_icon.ico"

        if getattr(sys, 'frozen', False):
            # Running as PyInstaller bundle
            base_path = sys._MEIPASS
            bundled_icon_path = os.path.join(base_path, icon_name)

            # Copy ICO to temp file so Tkinter can read it
            temp_icon_path = os.path.join(tempfile.gettempdir(), icon_name)
            try:
                shutil.copy(bundled_icon_path, temp_icon_path)
                icon_path = temp_icon_path
            except Exception as e:
                print(f"Failed to copy ICO to temp file: {e}")
                icon_path = bundled_icon_path
        else:
            # Running as script
            icon_path = r"Z:\SPENCER_FLOYD\.ico\Class_QC_icon.ico"

        # Set Tkinter window icon
        try:
            root.iconbitmap(icon_path)
        except Exception as e:
            print(f"Failed to set window icon: {e}")

        self.input_dir_button = tk.Button(root, text="Select Input Directory", command=self.choose_directory)
        self.input_dir_button.pack(pady=10)

        self.input_dir_label = tk.Label(root, text="")
        self.input_dir_label.pack()

        self.input_dir_path = None

        self.num_cores_label = tk.Label(root, text="Number of Cores:")
        self.num_cores_label.pack()

        self.cores_var = tk.StringVar(root)
        self.cores_var.set("7")
        self.num_cores_combobox = ttk.Combobox(root, textvariable=self.cores_var, values=["1", "2", "3", "4", "5", "6", "7", "8"], width=2)
        self.num_cores_combobox.pack()

        self.main_qc_rasters_label = tk.Label(root, text="Main QC Rasters")
        self.main_qc_rasters_label.pack(pady=10)

        self.class_7_var = tk.IntVar(value=1)
        self.class_7_checkbox = tk.Checkbutton(root, text="Outlier Denisty Rasters", variable=self.class_7_var)
        self.class_7_checkbox.pack()

        self.default_density_var = tk.IntVar(value=1)
        self.default_density_checkbox = tk.Checkbutton(root, text="Default Density Rasters", variable=self.default_density_var)
        self.default_density_checkbox.pack()

        self.hillshade_var = tk.IntVar(value=1)
        self.hillshade_checkbox = tk.Checkbutton(root, text="Hillshade Raster", variable=self.hillshade_var)
        self.hillshade_checkbox.pack()

        self.optional_QC_label = tk.Label(root, text="Optional QC Rasters")
        self.optional_QC_label.pack(pady=10)

        self.ground_density_var = tk.IntVar(value=0)
        self.ground_density_checkbox = tk.Checkbutton(root, text="Ground Density Rasters", variable=self.ground_density_var)
        self.ground_density_checkbox.pack()

        self.high_noise_range_var = tk.IntVar(value=0)
        self.high_noise_range_checkbox = tk.Checkbutton(root, text="High Point Range Rasters", variable=self.high_noise_range_var)
        self.high_noise_range_checkbox.pack()

        self.start_button = tk.Button(root, text="Start Processing", command=self.start_processing)
        self.start_button.pack(pady=30)

        if not self.check_lastools_license():
            return

    def print_rainbow_dashes(self, line_length=120):
        rainbow_colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]
        for i in range(line_length):
            print(rainbow_colors[i % len(rainbow_colors)] + "-" + Style.RESET_ALL, end="")
        print()

    def check_lastools_license(self):
        lastools_license_path = r"C:\LAStools\bin\lastoolslicense.txt"
        if not os.path.exists(lastools_license_path):
            messagebox.showerror("Error", "No LASTools license file found. Please ensure that either LASTools is properly installed, or ensure you have the latest LASTools license file.")
            self.root.destroy()
            return False
        return True

    def choose_directory(self):
        self.input_dir_path = filedialog.askdirectory()
        if self.input_dir_path:
            lidar_files = [file for file in os.listdir(self.input_dir_path) if file.endswith(('.las', '.laz'))]
            if not lidar_files:
                messagebox.showinfo("Error", "No LiDAR files found in the directory chosen. Choose a directory with .las or .laz files to continue.")
                self.input_dir_path = None
            else:
                self.input_dir_label.config(text=self.input_dir_path)

    def erode_valid_data(self, src, nodata_value, erosion_pixels=25):
        array = src.read()
        if nodata_value is None:
            nodata_value = src.nodata if src.nodata is not None else np.min(array)
        valid_mask = array != nodata_value
        if len(array.shape) == 2:
            eroded_mask = binary_erosion(valid_mask, iterations=erosion_pixels)
            array[~eroded_mask] = nodata_value
        else:
            for i in range(array.shape[0]):
                eroded_mask = binary_erosion(valid_mask[i], iterations=erosion_pixels)
                array[i, ~eroded_mask] = nodata_value
        return array

    def merge_geotiffs_by_island(self, input_dir, output_base, nodata_value=0):
        import re
        # Step 1: Get all GeoTIFF files
        tif_files = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.lower().endswith('.tif')]
        if not tif_files:
            print("No GeoTIFFs found.")
            return

        # Step 2: Determine EPSG code from first filename
        first_filename = os.path.basename(tif_files[0])
        utm_epsg_mapping = {
            "7": 3154,
            "8": 3155,
            "9": 3156,
            "10": 3157,
            "11": 2955
        }

        # Extract the number right after "utm"
        match = re.search(r'utm(7|8|9|10|11)', first_filename, re.IGNORECASE)
        if match:
            utm_zone = match.group(1)
            epsg_code = utm_epsg_mapping[utm_zone]
        else:
            print(f"Warning: Could not determine UTM zone from filename {first_filename}. Using default EPSG 3156.")
            epsg_code = 3156

        print(f"Using EPSG:{epsg_code} for merged island GeoTIFFs.")

        # Step 3: Create bounding boxes
        geometries = []
        file_indices = {}  # use index of geometry as key

        for idx, f in enumerate(tif_files):
            with rasterio.open(f) as src:
                geom = box(*src.bounds)
                geometries.append(geom)
                file_indices[idx] = f  # store filename by index

        # Step 4: Group into islands of overlapping rasters
        islands = []
        used = set()

        for i, geom in enumerate(geometries):
            if i in used:
                continue
            island = [i]
            queue = [i]
            used.add(i)

            while queue:
                current_idx = queue.pop()
                current_geom = geometries[current_idx]
                for j, other_geom in enumerate(geometries):
                    if j in used:
                        continue
                    if current_geom.intersects(other_geom):
                        island.append(j)
                        queue.append(j)
                        used.add(j)
            islands.append(island)

        # Step 5: Merge each island using rasterio
        for idx, island in enumerate(islands, start=1):
            files_to_merge = [file_indices[i] for i in island]
            output_file = os.path.join(input_dir, f"{output_base}_Island_{idx}.tif")
            print(f"Merging island {idx} with {len(files_to_merge)} files...")

            src_files_to_mosaic = [rasterio.open(fp) for fp in files_to_merge]
            mosaic, out_trans = merge(src_files_to_mosaic, nodata=nodata_value)
            out_meta = src_files_to_mosaic[0].meta.copy()
            out_meta.update({
                "driver": "GTiff",
                "height": mosaic.shape[1],
                "width": mosaic.shape[2],
                "transform": out_trans,
                "nodata": nodata_value,
                "crs": CRS.from_epsg(epsg_code)
            })

            with rasterio.open(output_file, "w", **out_meta) as dest:
                dest.write(mosaic)

            for src in src_files_to_mosaic:
                src.close()

    def start_processing(self):
        if not self.input_dir_path:
            messagebox.showinfo("Error", "No input directory has been selected. Please choose a directory containing .las files.")
            return
        
        if not self.hillshade_var.get() and not self.high_noise_range_var.get() and not self.ground_density_var.get() and not self.class_7_var.get() and not self.default_density_var.get():
            messagebox.showinfo("Error", "No QC tests selected")
            return

        qc_rasters_dir = os.path.join(self.input_dir_path, "Classification_QC_Rasters")
        os.makedirs(qc_rasters_dir, exist_ok=True)

        if self.high_noise_range_var.get():
            high_noise_range_dir = os.path.join(qc_rasters_dir, "High_Point_Range_Rasters")
            os.makedirs(high_noise_range_dir, exist_ok=True)
            print("Creating High Point Range Rasters...")
            os.system(f'lasgrid64 -i "{self.input_dir_path}\\*.las" -nodata 0 -no_world_file -no_kml -range -cores {self.cores_var.get()} -false -nodata 0 -quiet -keep_class 1 3 4 5 -otif -odir "{high_noise_range_dir}" -step 8')
            output_tiff = os.path.join(high_noise_range_dir, '_High_Poise_Range_Raster_Merged')
            self.merge_geotiffs_by_island(high_noise_range_dir, output_tiff, nodata_value=0)
            self.print_rainbow_dashes()

        if self.class_7_var.get():
            class_7_dir = os.path.join(qc_rasters_dir, "Outlier_Density")
            os.makedirs(class_7_dir, exist_ok=True)
            print("Creating Outlier Rasters...")
            os.system(f'lasgrid64 -i "{self.input_dir_path}\\*.las" -cores {self.cores_var.get()} -step 6 -false -quiet -no_world_file -no_kml -nodata 0 -quiet -keep_class 7 -point_density -otif -odir "{class_7_dir}"')
            output_tiff = os.path.join(class_7_dir, '_Outlier_Density_Merged')
            self.merge_geotiffs_by_island(class_7_dir, output_tiff, nodata_value=0)
            self.print_rainbow_dashes()

        if self.ground_density_var.get():
            ground_density_dir = os.path.join(qc_rasters_dir, "Ground Density")
            os.makedirs(ground_density_dir, exist_ok=True)
            print("Creating Ground Density Rasters...")
            os.system(f'lasgrid64 -i "{self.input_dir_path}\\*.las" -no_world_file -no_kml -cores {self.cores_var.get()} -point_density -false -nodata 0 -quiet -keep_class 2 -otif -odir "{ground_density_dir}" -step 6')
            output_tiff = os.path.join(ground_density_dir, '_Ground_Density_Merged')
            self.merge_geotiffs_by_island(ground_density_dir, output_tiff, nodata_value=0)
            self.print_rainbow_dashes()

        if self.default_density_var.get():
            default_density_dir = os.path.join(qc_rasters_dir, "Default Density")
            os.makedirs(default_density_dir, exist_ok=True)
            print("Creating Default Density Rasters...")
            os.system(f'lasgrid64 -i "{self.input_dir_path}\\*.las" -no_world_file -no_kml -cores {self.cores_var.get()} -point_density -false -nodata 0 -quiet -keep_class 1 -otif -odir "{default_density_dir}" -step 6')
            output_tiff = os.path.join(default_density_dir, '_Default_Density_Merged')
            self.merge_geotiffs_by_island(default_density_dir, output_tiff, nodata_value=0)
            self.print_rainbow_dashes()

        if self.hillshade_var.get():
            hillshade_dir = os.path.join(qc_rasters_dir, "Hillshade_Raster")
            os.makedirs(hillshade_dir, exist_ok=True)
            print("Creating Hillshade Raster...")
            os.system(f'blast2dem64 -i "{self.input_dir_path}\\*.las" -cores {self.cores_var.get()} -hillshade -no_kml -no_world_file -nodata 0 -keep_class 2 -otif -kill 100 -odir "{hillshade_dir}" -step 2 >nul 2>&1')
            output_tiff = os.path.join(hillshade_dir, '_Hillshade_Merged')
            self.merge_geotiffs_by_island(hillshade_dir, output_tiff, nodata_value=0)
            self.print_rainbow_dashes()


        # Print COMPLETE when everything is complete
        print(f"""{Fore.LIGHTGREEN_EX}
        ( C | O | M | P | L | E | T | E )
        {Style.RESET_ALL}                                                                                                    
        """)
        # Pop up for completion
        result = messagebox.askquestion("Complete", "Classification QC Rasters Complete. Would you like to open the output directory?", icon="question", parent=self.root)

        if result == "yes":
            os.startfile(qc_rasters_dir)


if __name__ == "__main__":
    root = tk.Tk()
    app = ClassificationQC(root)
    root.mainloop()