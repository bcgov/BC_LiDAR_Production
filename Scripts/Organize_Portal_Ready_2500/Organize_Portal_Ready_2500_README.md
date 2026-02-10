4_Portal_Ready Organizer
A GUI-based Python application for automated organization and validation of monthly LiDAR deliverables. This tool moves tiled LiDAR products (LAZ, DEM, DSM) from staging folders into monthly delivery directories, validates file completeness across product types, generates delivery summaries, and creates move reports for BC government LiDAR data management workflows.
Features

Automated Monthly Organization: Creates timestamped monthly delivery folders (YYYY_MM format)
Multi-Product Support: Organizes three product types simultaneously:

LAZ point cloud tiles
DEM (Digital Elevation Model) raster tiles
DSM (Digital Surface Model) raster tiles


File Completeness Validation: Pre-move verification ensures each tile exists in all three product folders
Discrepancy Detection: Identifies and reports missing files before any moves occur
Robocopy Integration: Uses Windows robocopy for reliable file moving with exclusion of older files
Delivery Summary Generation: Creates Excel spreadsheets with:

Tile counts per staging folder
Total LAZ file sizes (GB) per folder
Overall monthly totals
Bold headers and formatted columns


Move Report Generation: Text reports documenting original and moved file counts per product type
Safe Operation: Aborts entire operation if any discrepancies detected (all-or-nothing approach)
GUI Interface: Simple tkinter interface with directory selection validation

Usage
Prerequisites
The tool expects a specific directory structure in your 4_Portal_Ready folder:
4_Portal_Ready/
├── _Monthly_Deliveries/
├── [Two-digit folder 1]/
│   ├── DEM/
│   ├── DSM/
│   └── LAZ/
├── [Two-digit folder 2]/
│   ├── DEM/
│   ├── DSM/
│   └── LAZ/
└── ...
Important:

Create the _Monthly_Deliveries folder before running
Two-digit folders (e.g., "01", "02") contain staged tiles ready for delivery
Each two-digit folder must have DEM, DSM, and LAZ subfolders

Running the Tool

Launch the application
Click "Select Input Directory"
Navigate to and select your 4_Portal_Ready folder
Click "Organize" to begin processing

Workflow
The tool performs these steps in order:

Validation Phase: Scans all two-digit folders and checks that each tile exists in DEM, DSM, and LAZ
Abort if Issues: If any discrepancies found, writes File_Discrepancies.txt and stops
Move Phase: If validation passes, creates monthly folder and moves all files
Summary Generation: Creates Excel delivery summary and move report

Output Structure
4_Portal_Ready/
├── _Monthly_Deliveries/
│   └── 2026_02/  (current year_month)
│       ├── DEM/
│       │   └── [all DEM tiles from staging folders]
│       ├── DSM/
│       │   └── [all DSM tiles from staging folders]
│       ├── LAZ/
│       │   └── [all LAZ tiles from staging folders]
│       ├── Delivery_Summary_2026_02.xlsx
│       └── Move_Report.txt
Tile Naming Convention
The tool extracts tile identifiers from the first 5 underscore-separated parts of filenames:
Example: bc_092L001_1_1_1_xyes_8_utm9_20240501_20240515.laz
Identifier: bc_092L001_1_1_1

This identifier must match across DEM, DSM, and LAZ files.
Requirements
Software Dependencies

Python 3.x
Windows OS (uses robocopy)

Python Libraries
openpyxl
tkinter (standard library)
subprocess (standard library)
os (standard library)
datetime (standard library)
System Requirements

Windows operating system (robocopy utility)
Sufficient disk space for file moves
Write permissions in 4_Portal_Ready directory

Installation

Clone or download this repository
Install Python dependencies:

bash   pip install openpyxl

Prepare directory structure:

Create 4_Portal_Ready folder
Create _Monthly_Deliveries subfolder inside it
Organize tiles into two-digit staging folders with DEM/DSM/LAZ subfolders


Run the application:

bash   python portal_ready_organizer.py
Project Status
This tool is actively maintained for BC government LiDAR delivery management. The tool has been tested with:

BC provincial tile deliverables
Multiple product types (LAZ, DEM, DSM)
Various staging folder configurations
Monthly delivery cycles

Goals/Roadmap

 Progress bar for large file moves
 Support for additional product types (intensity, classification rasters)
 Configurable delivery folder naming patterns
 Automatic cleanup of empty staging folders after successful moves
 Integration with metadata validation tools
 Summary statistics in Excel (total area covered, density ranges)
 Email notification option upon completion
 Undo/rollback functionality for accidental moves
 Command-line interface for automated workflows
 Support for custom tile naming conventions
 Duplicate file detection and handling
 Compression statistics in summary reports

Getting Help or Reporting an Issue
To report bugs, suggest features, or ask questions:

Check existing issues in the GitHub repository
Create a new issue with:

Detailed description of the problem
Directory structure screenshot
File_Discrepancies.txt contents (if applicable)
Move_Report.txt contents
System environment (OS version, Python version)
Error messages or unexpected behavior



For urgent delivery organization issues, contact your LiDAR data management team lead.
How to Contribute
We welcome contributions from the LiDAR data management community:

Fork the repository and create a feature branch
Make your changes with clear, documented code
Test thoroughly with various folder structures and file counts
Submit a pull request with:

Description of changes
Problem solved or feature added
Testing performed with different scenarios
Any new dependencies or requirements



Contribution Guidelines

Follow PEP 8 Python style guidelines
Add docstrings to new functions
Update README for feature additions
Ensure robocopy commands are safe (no data loss risk)
Test with various file counts and sizes
Validate Excel formatting and summary calculations
Consider edge cases (empty folders, partial deliveries)
Maintain all-or-nothing transaction safety

Technical Notes
Robocopy Parameters:

/MOV: Move files (delete from source after successful copy)
/NJH: No Job Header (suppress header output)
/NJS: No Job Summary (suppress summary output)
/NP: No Progress (suppress per-file progress)
/XO: Exclude Older (only move newer or non-existing files in destination)

File Counting Logic:

Counts files before and after robocopy operation
Moved count = Original count - Remaining count
Handles case-insensitive file extensions

Tile Identifier Extraction:
python# From filename: bc_092L001_1_1_1_xyes_8_utm9_20240501_20240515.laz
parts = filename.split('_')
if len(parts) >= 5:
    identifier = '_'.join(parts[:5])  # "bc_092L001_1_1_1"
Discrepancy Detection:

Extracts identifiers from all files in DEM, DSM, LAZ folders
Creates union of all identifiers found
Checks each identifier exists in all three product folders
Reports missing combinations before any moves occur

Monthly Folder Naming:
python# Example: 2026_02 for February 2026
current_ym = datetime.now().strftime("%Y_%m")
Two-Digit Folder Detection:

Only processes folders with exactly 2-character names
Allows flexible staging organization (e.g., "01", "02", "AB", etc.)
Ignores _Monthly_Deliveries and other non-staging folders

Safety Features:

Validates 4_Portal_Ready folder selection
Requires _Monthly_Deliveries folder existence
Aborts if any discrepancies detected
Uses robocopy's /XO flag to prevent overwriting newer files


License: [Specify your government open source license]
Maintainer: [Your contact information or team]
