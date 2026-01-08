import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
from colorama import Fore, Style

class ClassificationQC:
    def __init__(self, root):
        self.root = root
        self.root.title("Classification_QC_v1.3")
        self.root.geometry("500x480")
        root.iconbitmap(r"Z:\SPENCER_FLOYD\.ico\Classification_QC.ico")

        self.input_dir_button = tk.Button(root, text="Select Input Directory", command=self.choose_directory)
        self.input_dir_button.pack(pady=10)

        self.input_dir_label = tk.Label(root, text="")
        self.input_dir_label.pack()

        self.input_dir_path = None

        self.num_cores_label = tk.Label(root, text="Number of Cores:")
        self.num_cores_label.pack()

        self.cores_var = tk.StringVar(root)
        self.cores_var.set("4")
        self.num_cores_combobox = ttk.Combobox(root, textvariable=self.cores_var, values=["1", "2", "3", "4", "5", "6", "7", "8"], width=2)
        self.num_cores_combobox.pack()

        self.spatial_resolution_label = tk.Label(root, text="Spatial Resolution (m):")
        self.spatial_resolution_label.pack()

        self.spatial_resolution_var = tk.StringVar(root)
        self.spatial_resolution_var.set("1")
        self.spatial_resolution_combobox = ttk.Combobox(root, textvariable=self.spatial_resolution_var, values=["0.5", "1", "2", "3", "4", "5"], width=4)
        self.spatial_resolution_combobox.pack()

        self.spatial_resolution_label = tk.Label(root, text="Initial QC Rasters")
        self.spatial_resolution_label.pack(pady=10)

        self.high_noise_var = tk.IntVar(value=1)
        self.high_noise_checkbox = tk.Checkbutton(root, text="Create High Point Rasters", variable=self.high_noise_var)
        self.high_noise_checkbox.pack()

        self.high_noise_range_var = tk.IntVar(value=1)
        self.high_noise_range_checkbox = tk.Checkbutton(root, text="Create High Point Range Rasters", variable=self.high_noise_range_var)
        self.high_noise_range_checkbox.pack()

        self.low_noise_var = tk.IntVar(value=1)
        self.low_noise_checkbox = tk.Checkbutton(root, text="Create Low Point Rasters", variable=self.low_noise_var)
        self.low_noise_checkbox.pack()

        self.low_noise_range_var = tk.IntVar(value=1)
        self.low_noise_range_checkbox = tk.Checkbutton(root, text="Create Low Point Range Rasters", variable=self.low_noise_range_var)
        self.low_noise_range_checkbox.pack()

        self.class_7_var = tk.IntVar(value=1)
        self.class_7_checkbox = tk.Checkbutton(root, text="Create Outlier Rasters", variable=self.class_7_var)
        self.class_7_checkbox.pack()

        self.spatial_resolution_label = tk.Label(root, text="Final QC Rasters")
        self.spatial_resolution_label.pack(pady=10)
        
        self.hillshade_var = tk.IntVar(value=1)
        self.hillshade_checkbox = tk.Checkbutton(root, text="Create Hillshade Raster", variable=self.hillshade_var)
        self.hillshade_checkbox.pack()

        self.DSM_var = tk.IntVar(value=1)
        self.DSM_checkbox = tk.Checkbutton(root, text="Create Digital Surface Model", variable=self.DSM_var)
        self.DSM_checkbox.pack()

        self.start_button = tk.Button(root, text="Start Processing", command=self.start_processing)
        self.start_button.pack(pady=10)

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

    def start_processing(self):
        if not self.hillshade_var.get() and not self.high_noise_var.get() and not self.high_noise_range_var.get() and not self.class_7_var.get() and not self.DSM_var.get() and not self.low_noise_var.get() and not self.low_noise_range_var.get():
            messagebox.showinfo("Error", "No QC tests selected")
            return

        qc_rasters_dir = os.path.join(self.input_dir_path, "Classification_QC_Rasters")
        os.makedirs(qc_rasters_dir, exist_ok=True)

        if self.high_noise_var.get():
            high_noise_dir = os.path.join(qc_rasters_dir, "High_Point_Rasters")
            os.makedirs(high_noise_dir, exist_ok=True)
            print("Creating High Point Rasters...")
            os.system(f'lasgrid -i "{self.input_dir_path}\\*.las" -nodata 0 -no_world_file -no_kml -cpu64 -max -cores {self.cores_var.get()} -grey -fail -fill 1000 -quiet -keep_class 1 3 4 5 -otif -odir "{high_noise_dir}" -step {self.spatial_resolution_var.get()}')
            self.print_rainbow_dashes()

        if self.high_noise_range_var.get():
            high_noise_range_dir = os.path.join(qc_rasters_dir, "High_Point_Range_Rasters")
            os.makedirs(high_noise_range_dir, exist_ok=True)
            print("Creating High Point Range Rasters...")
            os.system(f'lasgrid -i "{self.input_dir_path}\\*.las" -nodata 0 -no_world_file -no_kml -cpu64 -range -cores {self.cores_var.get()} -false -fail -fill 1000 -quiet -keep_class 5 -otif -odir "{high_noise_range_dir}" -step {self.spatial_resolution_var.get()}')
            self.print_rainbow_dashes()

        if self.low_noise_var.get():
            low_noise_dir = os.path.join(qc_rasters_dir, "Low_Point_Rasters")
            os.makedirs(low_noise_dir, exist_ok=True)
            print("Creating Low Point Rasters...")
            os.system(f'lasgrid -i "{self.input_dir_path}\\*.las" -nodata 0 -no_world_file -no_kml -cpu64 -min -cores {self.cores_var.get()} -grey -fail -fill 1000 -quiet -keep_class 2 -otif -odir "{low_noise_dir}" -step {self.spatial_resolution_var.get()}')
            self.print_rainbow_dashes()

        if self.low_noise_range_var.get():
            low_noise_range_dir = os.path.join(qc_rasters_dir, "Low_Point_Range_Rasters")
            os.makedirs(low_noise_range_dir, exist_ok=True)
            print("Creating Low Point Range Rasters...")
            os.system(f'lasgrid -i "{self.input_dir_path}\\*.las" -nodata 0 -no_world_file -no_kml -cpu64 -min -cores {self.cores_var.get()} -false -fail -fill 1000 -quiet -keep_class 2 -otif -odir "{low_noise_range_dir}" -step {self.spatial_resolution_var.get()}')
            self.print_rainbow_dashes()

        if self.class_7_var.get():
            class_7_dir = os.path.join(qc_rasters_dir, "Outlier_Rasters")
            os.makedirs(class_7_dir, exist_ok=True)
            print("Creating Outlier Rasters...")
            os.system(f'lasgrid -i "{self.input_dir_path}\\*.las" -cpu64 -cores {self.cores_var.get()} -step {self.spatial_resolution_var.get()} -false -fail -quiet -no_world_file -no_kml -nodata 0 -quiet -keep_class 7 31 32 -point_density -otif -odir "{class_7_dir}"')
            self.print_rainbow_dashes()
        
        if self.hillshade_var.get():
            hillshade_dir = os.path.join(qc_rasters_dir, "Hillshade_Raster")
            os.makedirs(hillshade_dir, exist_ok=True)
            print("Creating Hillshade Raster...")
            os.system(f'blast2dem -i "{self.input_dir_path}\\*.las" -merged -hillshade -o Hillshade.tif -no_kml -no_world_file -nodata 0 -fail -keep_class 2 -kill 500 -odir "{hillshade_dir}" -step {self.spatial_resolution_var.get()}')
            self.print_rainbow_dashes()

        if self.DSM_var.get():
            DSM_dir = os.path.join(qc_rasters_dir, "Digital_Surface_Model_Raster")
            os.makedirs(DSM_dir, exist_ok=True)
            print("Creating DSM Raster...")
            os.system(f'blast2dem -i "{self.input_dir_path}\\*.las" -merged -o DSM.tif -no_kml -no_world_file -false -nodata 0 -fail -first_only -kill 500 -odir "{DSM_dir}" -step {self.spatial_resolution_var.get()}')
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