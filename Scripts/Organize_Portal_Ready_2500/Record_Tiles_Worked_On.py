import os
import tkinter as tk
from tkinter import filedialog, messagebox

# --------------------------
# Hardcoded output directory
# --------------------------
OUTPUT_DIR = r"V:\Production_NAS\Supporting_Production_Files\Tile_Processing_Tracking"  # <-- change this to your desired output path

# --------------------------
# Functions
# --------------------------
def validate_input_folder(path):
    folder_name = os.path.basename(os.path.normpath(path))
    return folder_name == "4_Portal_Ready"

def process_folders(input_dir):
    for item in os.listdir(input_dir):
        item_path = os.path.join(input_dir, item)
        
        # Skip non-folders and the _Monthly_Deliveries folder
        if not os.path.isdir(item_path) or item == "_Monthly_Deliveries":
            continue
        
        initials = item  # folder name is assumed to be initials
        person_folder = os.path.join(OUTPUT_DIR, initials)
        os.makedirs(person_folder, exist_ok=True)  # create folder if it doesn't exist
        
        laz_folder = os.path.join(item_path, "LAZ")
        if os.path.exists(laz_folder) and os.path.isdir(laz_folder):
            filenames = os.listdir(laz_folder)
            txt_file_path = os.path.join(person_folder, f"{initials}.txt")
            
            with open(txt_file_path, "a") as f:  # append mode
                for name in filenames:
                    f.write(name + "\n")
    
    messagebox.showinfo("Done", "Processing complete!")

# --------------------------
# Tkinter GUI
# --------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Portal Ready LAZ List Creator")
        
        # Input folder selection
        self.input_label = tk.Label(root, text="Select 4_Portal_Ready folder:")
        self.input_label.pack(pady=5)
        
        self.input_button = tk.Button(root, text="Browse", command=self.browse_folder)
        self.input_button.pack(pady=5)
        
        self.go_button = tk.Button(root, text="Go", command=self.run, state="disabled")
        self.go_button.pack(pady=20)
        
        self.selected_path = ""
    
    def browse_folder(self):
        folder = filedialog.askdirectory(title="Select 4_Portal_Ready folder")
        if folder:
            if validate_input_folder(folder):
                self.selected_path = folder
                messagebox.showinfo("Folder Selected", f"Selected folder: {folder}")
                self.go_button.config(state="normal")
            else:
                messagebox.showerror("Wrong Folder", "Please select a folder named '4_Portal_Ready'.")
                self.go_button.config(state="disabled")
    
    def run(self):
        if self.selected_path:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            process_folders(self.selected_path)

# --------------------------
# Run GUI
# --------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
