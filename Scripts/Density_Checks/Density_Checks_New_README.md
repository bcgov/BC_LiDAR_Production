Last Return Density Checker
A comprehensive GUI-based Python application for automated validation of LiDAR last-return point density across tiled datasets. This tool generates density rasters, clips them to standard BC tile boundaries, masks water bodies, and identifies tiles failing to meet the 8 points/m² density threshold for government LiDAR QC workflows.
Features

Automated Density Raster Generation: Uses LAStools lasgrid64 to create 5m resolution point density grids from last-return points
Multi-Core Processing: Configurable parallel processing (1-32 cores) for both raster generation and clipping operations
Intelligent Tile Clipping: Clips density rasters to exact BC tiling scheme boundaries with precise pixel alignment
Water Body Masking: Automatically masks water areas using pre-prepared 50m-buffered water GeoPackages per UTM zone
Pass/Fail Classification: Validates tiles against 95% threshold for ≥8 pts/m² density requirement
Automatic File Organization:

Sorts outputs by UTM zone (7-11)
Separates PASS and FAIL tiles into distinct folders
Moves failed source LAZ/LAS files to quarantine directory


Comprehensive Logging: Generates CSV reports with per-tile density statistics and failure reasons
Configurable Data Paths: Settings interface for customizing LAStools location and data folder paths
Custom Output Directory: Optional specification of output location separate from input data
Robust Error Handling: Detailed logging with boot diagnostics and crash reporting

Usage
Basic Workflow

Launch the application
Click "Browse" to select the input directory containing LAZ/LAS files
(Optional) Enable "Use custom output directory" and select output location
Configure number of cores (default: 8, max: 32)
Click "Density Check" to begin processing

Settings Configuration
Access via Settings → Settings… menu:

LAStools lasgrid64.exe path: Location of lasgrid64 executable
Tiling scheme folder: Path to Tiles_By_UTM directory containing tile boundary data
Water folder: Path to Water_by_UTM directory containing water mask GeoPackages

Each setting has Browse and Reset buttons for easy configuration.
Output Structure
Input_Directory/ (or Custom Output Directory)
├── Last_Return_Density_Rasters/
│   ├── Unclipped/
│   │   ├── UTM07_Unclipped/
│   │   │   ├── [original density TIFFs]
│   │   │   └── FAIL/
│   │   │       └── [failed original TIFFs]
│   │   ├── UTM08_Unclipped/
│   │   └── ...
│   ├── Water_Clipped/
│   │   ├── UTM07_Clipped/
│   │   │   ├── [clipped PASS TIFFs]
│   │   │   ├── FAIL/
│   │   │   │   └── [clipped FAIL TIFFs]
│   │   │   └── density_check_log.csv
│   │   ├── UTM08_Clipped/
│   │   └── ...
│   └── _lasgrid_out/
│       ├── lasgrid64_log.txt
│       └── lasgrid_input_files.txt
└── LAZ_Density_Fail/  (created only if failures occur)
    ├── UTM07_LAZ/
    │   └── [failed source LAZ/LAS files]
    ├── UTM08_LAZ/
    └── failed_tiles.csv
Requirements
Software Dependencies

Python 3.7+
LAStools (lasgrid64.exe) - commercial license required
GDAL/PROJ libraries (typically bundled with Python geospatial packages)

Python Libraries
numpy
fiona
rasterio
geopandas (implicit via fiona/rasterio)
colorama
tkinter (standard library)
Data Requirements
Required Data Assets (typically packaged with application):

Tiling Scheme Data (Tiles_By_UTM/):

Per-zone GeoPackages: 2500_Tiles_UTM{zone:02d}.gpkg
OR per-zone shapefiles: UTM{zone:02d}/*.shp
Must contain MAP_TILE or MAPSHEET attribute with tile identifiers


Water Mask Data (Water_by_UTM/):

Per-zone GeoPackages: Water_UTM{zone:02d}_buf50m_tilebbox.gpkg
Layer name: water_utm{zone:02d}_buf50m
Polygons representing water bodies with 50m buffer


Input LiDAR Data:

LAZ or LAS files with UTM zone identifier in filename (e.g., "utm09", "utm10")
Files must contain last-return classification
Recommended: pre-classified point clouds



EPSG/UTM Zone Support (BC)

UTM 7 → EPSG 3154
UTM 8 → EPSG 3155
UTM 9 → EPSG 3156
UTM 10 → EPSG 3157
UTM 11 → EPSG 2955

Installation
Standard Python Installation

Clone or download this repository
Install Python dependencies:

bash   pip install numpy fiona rasterio colorama

Install LAStools:

Obtain commercial license from rapidlasso.com
Install to default location: C:\LAStools\
Or specify custom path in Settings


Prepare data assets:

Place Tiles_By_UTM/ and Water_by_UTM/ folders in data/ subdirectory next to script
Or configure custom paths via Settings menu


Run the application:

bash   python last_return_density_checker.py
Building Standalone Executable
For distribution without Python installation:
bashpip install pyinstaller

# Create onefile executable with bundled data
pyinstaller --onefile --windowed ^
    --add-data "data;data" ^
    --add-data "assets;assets" ^
    --icon=assets/LastReturnDensityChecker_Icon.ico ^
    --name "LastReturnDensityChecker" ^
    last_return_density_checker.py
Note: Ensure GDAL/PROJ data files are included in the data/ folder for standalone builds.
Project Status
This tool is actively maintained for BC government LiDAR QC workflows. The application has been tested with:

Large-scale provincial LiDAR datasets
Multiple UTM zones simultaneously
Various point cloud formats and densities
Dual-channel Riegl VQ-1560 LiDAR data

Goals/Roadmap

 Support for configurable density thresholds (currently hardcoded at 8 pts/m²)
 Progress bars in GUI for long-running operations
 Support for first-return and all-return density checks
 Integration with additional LiDAR QC metrics
 Batch processing across multiple project directories
 Export of summary statistics and visualizations
 Support for custom water mask sources
 Configurable raster resolution (currently fixed at 5m)
 Command-line interface for automated workflows
 Integration with project metadata databases

Getting Help or Reporting an Issue
To report bugs, suggest features, or ask questions:

Check existing issues in the GitHub repository
Create a new issue with:

Detailed description of the problem
System environment (OS, Python version, LAStools version)
Input data specifications (file count, UTM zones, formats)
Log files from application directory:

Windows: %APPDATA%\GeoBC\LastReturnDensityChecker\
Includes: app_debug.log, boot_*.log


Error messages or unexpected behavior
Steps to reproduce



For urgent processing issues affecting deliverables, contact your LiDAR QC team lead immediately.
How to Contribute
We welcome contributions from the LiDAR processing and geospatial analysis community:

Fork the repository and create a feature branch
Make your changes with clear, documented code
Test thoroughly with representative datasets across multiple UTM zones
Submit a pull request with:

Description of changes
Problem solved or feature added
Performance benchmarks for large datasets
Testing performed with different point cloud types
Any new dependencies or data requirements



Contribution Guidelines

Follow PEP 8 Python style guidelines
Add comprehensive docstrings to functions
Update version tracking and README for features
Ensure compatibility with LAStools command-line interface
Test with both LAZ and LAS formats
Consider memory usage for large tile collections (1000+ tiles)
Validate georeferencing and spatial accuracy of outputs
Test with various point densities and terrain types

Technical Notes
Density Calculation:

Uses lasgrid64 -last_only flag for last-return filtering
5m cell size for consistent provincial standards
Point density = points per square meter

Pass/Fail Criteria:

Tile PASSES if ≥95% of non-water pixels have density ≥8 pts/m²
Water pixels (NoData = -9999) excluded from percentage calculation
Negative density values clamped to 0 before analysis

Tile Matching Logic:

Extracts tile identifier from filename pattern: <prefix>_<a>_<b>_<c>_<d>_*.tif
Concatenates parts 2-5 (positions 1-4 in zero-indexed split)
Matches case-insensitively against MAP_TILE or MAPSHEET attributes

Processing Optimization:

Lazy import of heavy libraries (numpy, rasterio, fiona) to speed startup
Per-zone resource loading in worker processes
Chunked task distribution for balanced workload
Resampling uses nearest-neighbor to preserve density values


Maintainer: Spencer Floyd (spencer.floyd@gov.bc.ca)
