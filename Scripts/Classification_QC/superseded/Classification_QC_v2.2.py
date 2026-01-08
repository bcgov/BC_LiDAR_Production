import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import sys
if getattr(sys, 'frozen', False):
    os.environ['GDAL_DATA'] = os.path.join(sys._MEIPASS, 'gdal_data')
from colorama import Fore, Style
import glob
import rasterio
import numpy as np
from rasterio.merge import merge
from scipy.ndimage import binary_erosion
from rasterio.io import MemoryFile

os.environ['GDAL_DATA'] = r'C:\Users\SFLOYD\AppData\Local\anaconda3\envs\spatial_env\Library\share\gdal'

class ClassificationQC:
    def __init__(self, root):
        self.root = root
        self.root.title("Classification_QC_v2.2")
        self.root.geometry("600x450")
        root.iconbitmap(r"Z:\SPENCER_FLOYD\.ico\Classification_QC.ico")

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

        self.high_noise_rasters_label = tk.Label(root, text="High Noise Raster")
        self.high_noise_rasters_label.pack(pady=10)

        self.high_noise_range_var = tk.IntVar(value=0)
        self.high_noise_range_checkbox = tk.Checkbutton(root, text="Create High Point Range Rasters", variable=self.high_noise_range_var)
        self.high_noise_range_checkbox.pack()

        self.density_rasters_label = tk.Label(root, text="Density Rasters")
        self.density_rasters_label.pack(pady=10)

        self.class_7_var = tk.IntVar(value=0)
        self.class_7_checkbox = tk.Checkbutton(root, text="Create Outlier Denisty Rasters", variable=self.class_7_var)
        self.class_7_checkbox.pack()

        self.ground_density_var = tk.IntVar(value=0)
        self.ground_density_checkbox = tk.Checkbutton(root, text="Create Ground Density Rasters", variable=self.ground_density_var)
        self.ground_density_checkbox.pack()

        self.geowizard_density_var = tk.IntVar(value=0)
        self.geowizard_density_checkbox = tk.Checkbutton(root, text="Create Geowizard (Class 18) Density Rasters", variable=self.geowizard_density_var)
        self.geowizard_density_checkbox.pack()

        self.default_density_var = tk.IntVar(value=0)
        self.default_density_checkbox = tk.Checkbutton(root, text="Create Default Density Rasters", variable=self.default_density_var)
        self.default_density_checkbox.pack()

        self.final_QC_label = tk.Label(root, text="Final QC Rasters")
        self.final_QC_label.pack(pady=10)
        
        self.hillshade_var = tk.IntVar(value=0)
        self.hillshade_checkbox = tk.Checkbutton(root, text="Create Hillshade Raster", variable=self.hillshade_var)
        self.hillshade_checkbox.pack()

        self.start_button = tk.Button(root, text="Start Processing", command=self.start_processing)
        self.start_button.pack(pady=20)

        # Check for LASTools license file existence
        if not self.check_lastools_license():
            return

    def print_rainbow_dashes(self, line_length=120):
        # Define a list of rainbow colors
        rainbow_colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]

        # Print dashed lines with rainbow colors
        for i in range(line_length):
            print(rainbow_colors[i % len(rainbow_colors)] + "-" + Style.RESET_ALL, end="")
        print()  # Move to the next line after the dashes

    def check_lastools_license(self):
        lastools_license_path = r"C:\LAStools\bin\lastoolslicense.txt"
        if not os.path.exists(lastools_license_path):
            messagebox.showerror("Error", "No LASTools license file found. Please ensure that either LASTools is properly installed, or ensure you have the latest LASTools license file.")
            self.root.destroy()  # Close the entire program
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
        """Erodes valid (non-nodata) pixels inward by a given number of pixels."""
        array = src.read()  # Read all bands (this could be 1 band or multiple bands)
        
        if nodata_value is None:
            nodata_value = src.nodata if src.nodata is not None else np.min(array)

        # Create a binary mask: 1 for valid data, 0 for nodata
        valid_mask = array != nodata_value  

        # Check if it's a single-band raster or multi-band raster
        if len(array.shape) == 2:  # Single band raster (2D array)
            # Erode the mask for single-band raster
            eroded_mask = binary_erosion(valid_mask, iterations=erosion_pixels)
            array[~eroded_mask] = nodata_value  # Set newly eroded pixels to nodata
        else:  # Multi-band raster (3D array)
            # Erode the mask for each band separately
            for i in range(array.shape[0]):  # Loop through each band
                eroded_mask = binary_erosion(valid_mask[i], iterations=erosion_pixels)
                array[i, ~eroded_mask] = nodata_value  # Set newly eroded pixels to nodata

        return array

    def merge_geotiffs(self, input_dir, output_file, nodata_value=None):
        search_pattern = os.path.join(input_dir, "*.tif")
        tiff_files = glob.glob(search_pattern)

        if not tiff_files:
            print("No GeoTIFF files found in the directory.")
            return

        src_files_to_mosaic = []
        mem_files = []  # Store MemoryFile objects to prevent premature closing

        for f in tiff_files:
            with rasterio.open(f) as src:
                # Check the number of bands in the GeoTIFF
                num_bands = src.count

                # If it's a 3-band raster, skip the erosion step
                if num_bands == 3:
                    processed_array = src.read()  # Read the raster as it is
                else:
                    # If not 3-band, apply erosion
                    processed_array = self.erode_valid_data(src, nodata_value, erosion_pixels=10)

                # Copy metadata and update nodata value
                profile = src.profile
                profile.update(nodata=nodata_value)

                # Keep MemoryFile open
                memfile = MemoryFile()
                mem_files.append(memfile)  # Store MemoryFile so it doesn't close

                mem_dst = memfile.open(**profile)
                mem_dst.write(processed_array)  # Write all bands (or the single band)
                src_files_to_mosaic.append(mem_dst)  # Store open dataset

        # Merge the rasters: merge will work with both single-band and multi-band rasters
        mosaic, out_transform = merge(src_files_to_mosaic, nodata=nodata_value)

        # Copy metadata from the first raster
        out_meta = src_files_to_mosaic[0].profile
        out_meta.update({
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": out_transform,
            "nodata": nodata_value
        })

        # Write merged GeoTIFF: all bands will be written to the output
        with rasterio.open(output_file, "w", **out_meta) as dest:
            dest.write(mosaic)

        print(f"Merged GeoTIFF saved to {output_file}")

        # Close all MemoryFile objects
        for memfile in mem_files:
            memfile.close()

    def start_processing(self):
        if not self.input_dir_path:
            messagebox.showinfo("Error", "No input directory has been selected. Please choose a directory containing .las files.")
            return
        
        if not self.hillshade_var.get() and not self.high_noise_range_var.get() and not self.ground_density_var.get() and not self.class_7_var.get() and not self.geowizard_density_var.get() and not self.default_density_var.get():
            messagebox.showinfo("Error", "No QC tests selected")
            return

        qc_rasters_dir = os.path.join(self.input_dir_path, "Classification_QC_Rasters")
        os.makedirs(qc_rasters_dir, exist_ok=True)

        if self.high_noise_range_var.get():
            high_noise_range_dir = os.path.join(qc_rasters_dir, "High_Point_Range_Rasters")
            os.makedirs(high_noise_range_dir, exist_ok=True)
            print("Creating High Point Range Rasters...")
            os.system(f'lasgrid -i "{self.input_dir_path}\\*.las" -nodata 0 -no_world_file -no_kml -cpu64 -range -cores {self.cores_var.get()} -false -nodata 0 -quiet -keep_class 1 3 4 5 -otif -odir "{high_noise_range_dir}" -step 6')
            output_tiff = os.path.join(high_noise_range_dir, '_High_Poise_Range_Raster_Merged.tif')
            self.merge_geotiffs(high_noise_range_dir, output_tiff, nodata_value=0)
            self.print_rainbow_dashes()

        if self.class_7_var.get():
            class_7_dir = os.path.join(qc_rasters_dir, "Outlier_Density")
            os.makedirs(class_7_dir, exist_ok=True)
            print("Creating Outlier Rasters...")
            os.system(f'lasgrid -i "{self.input_dir_path}\\*.las" -cpu64 -cores {self.cores_var.get()} -step 4 -false -quiet -no_world_file -no_kml -nodata 0 -quiet -keep_class 7 -point_density -otif -odir "{class_7_dir}"')
            output_tiff = os.path.join(class_7_dir, '_Outlier_Density_Merged.tif')
            self.merge_geotiffs(class_7_dir, output_tiff, nodata_value=0)
            self.print_rainbow_dashes()

        if self.ground_density_var.get():
            ground_density_dir = os.path.join(qc_rasters_dir, "Ground Density")
            os.makedirs(ground_density_dir, exist_ok=True)
            print("Creating Ground Density Rasters...")
            os.system(f'lasgrid -i "{self.input_dir_path}\\*.las" -no_world_file -no_kml -cpu64 -cores {self.cores_var.get()} -point_density -false -nodata 0 -quiet -keep_class 2 -otif -odir "{ground_density_dir}" -step 4')
            output_tiff = os.path.join(ground_density_dir, '_Ground_Density_Merged.tif')
            self.merge_geotiffs(ground_density_dir, output_tiff, nodata_value=0)
            self.print_rainbow_dashes()

        if self.default_density_var.get():
            default_density_dir = os.path.join(qc_rasters_dir, "Default Density")
            os.makedirs(default_density_dir, exist_ok=True)
            print("Creating Default Density Rasters...")
            os.system(f'lasgrid -i "{self.input_dir_path}\\*.las" -no_world_file -no_kml -cpu64 -cores {self.cores_var.get()} -point_density -false -nodata 0 -quiet -keep_class 1 -otif -odir "{default_density_dir}" -step 4')
            output_tiff = os.path.join(default_density_dir, '_Default_Density_Merged.tif')
            self.merge_geotiffs(default_density_dir, output_tiff, nodata_value=0)
            self.print_rainbow_dashes()

        if self.geowizard_density_var.get():
            geowizard_density_dir = os.path.join(qc_rasters_dir, "Geowizard Density (Class 18)")
            os.makedirs(geowizard_density_dir, exist_ok=True)
            print("Creating Geowizard (Class 18) Density Rasters...")
            os.system(f'lasgrid -i "{self.input_dir_path}\\*.las" -no_world_file -no_kml -cpu64 -cores {self.cores_var.get()} -point_density -nodata 0 -false -quiet -keep_class 18 -otif -odir "{geowizard_density_dir}" -step 5')
            output_tiff = os.path.join(geowizard_density_dir, '_Geowizard_Density_Merged.tif')
            self.merge_geotiffs(geowizard_density_dir, output_tiff, nodata_value=0)
            self.print_rainbow_dashes()
        
        if self.hillshade_var.get():
            hillshade_dir = os.path.join(qc_rasters_dir, "Hillshade_Raster")
            os.makedirs(hillshade_dir, exist_ok=True)
            print("Creating Hillshade Raster...")
            os.system(f'blast2dem -i "{self.input_dir_path}\\*.las" -cores {self.cores_var.get()} -hillshade -no_kml -no_world_file -nodata 0 -keep_class 2 -otif -kill 100 -odir "{hillshade_dir}" -step 2')
            output_tiff = os.path.join(hillshade_dir, '_Hillshade_Merged.tif')
            self.merge_geotiffs(hillshade_dir, output_tiff, nodata_value=0)
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