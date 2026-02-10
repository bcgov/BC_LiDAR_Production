LiDAR Classification QC Raster Generator
A GUI-based Python application for automated generation of quality control raster products from classified LiDAR point clouds. This tool creates density, range, and hillshade rasters for visual inspection of classification accuracy, with intelligent tile merging that preserves spatial relationships for government LiDAR QC workflows.
Features

Multi-Core Processing: Configurable parallel processing (1-8 cores) for efficient raster generation
Intelligent Island-Based Merging: Automatically detects and merges spatially connected tiles while preserving distinct project areas
Comprehensive QC Raster Suite:

Outlier Density Rasters: Visualize classification 7 (noise) point distribution
Default Density Rasters: Analyze classification 1 (unclassified) point density
Ground Density Rasters: Assess classification 2 (ground) point coverage
High Point Range Rasters: Identify elevation anomalies in classified points
Hillshade Rasters: Generate terrain visualization from ground points


Customizable Resolution: Adjustable raster cell size for hillshade (0.5-2m) and high point range (0.5-5m)
Automatic EPSG Detection: Intelligently determines UTM zone from BC filenames
Original Tile Preservation: Moves individual tiles to "Original" subfolder after successful merging
GUI Interface: User-friendly tkinter interface for parameter selection and processing control

Usage

Launch the application
Click "Select Input Directory" to choose the folder containing classified LAS/LAZ files
Configure processing options:

Number of Cores: Select CPU cores to use (1-8)
Main QC Rasters: Check desired outputs (Outlier Density, Default Density, Hillshade)
Hillshade Resolution: Choose cell size (0.5m, 1m, or 2m)
Optional QC Rasters: Enable Ground Density and/or High Point Range
High Point Range Resolution: Choose cell size (0.5-5m)


Click "Start Processing" to begin raster generation

Output Structure
Input_Directory/
├── Classification_QC_Rasters/
│   ├── Outlier_Density/
│   │   ├── _Outlier_Density_Merged_Island_1.tif
│   │   └── Original/
│   │       └── [individual tile GeoTIFFs]
│   ├── Default_Density/
│   │   ├── _Default_Density_Merged_Island_1.tif
│   │   └── Original/
│   ├── Ground_Density/
│   │   └── [similar structure]
│   ├── High_Point_Range_Rasters/
│   │   └── [similar structure]
│   └── Hillshade_Raster/
│       ├── _Hillshade_Merged_Island_1.tif
│       └── Original/
Requirements
Software Dependencies

Python 3.x
LAStools (lasgrid64, blast2dem64 executables must be in system PATH)
LAStools license file at C:\LAStools\bin\lastoolslicense.txt

Python Libraries
rasterio
shapely
numpy
colorama
tkinter (standard library)
Data Requirements

Classified LAS or LAZ files
Files should follow BC naming convention with UTM zone identifier (e.g., "utm9", "utm10")
Recommended classifications present: 1 (unclassified), 2 (ground), 7 (noise)

Installation

Clone or download this repository
Install Python dependencies:

bash   pip install rasterio shapely numpy colorama

Install LAStools:

Download LAStools from rapidlasso.com
Install to C:\LAStools\ (or adjust license check path in code)
Ensure license file exists: C:\LAStools\bin\lastoolslicense.txt
Add LAStools/bin directory to system PATH
Verify lasgrid64 and blast2dem64 are accessible


Verify GDAL/PROJ installation:

Rasterio requires GDAL (usually installed automatically with rasterio)
For PyInstaller builds, bundle gdal_data and proj_data folders


Run the application:

bash   python classification_qc_rasters.py
Building Standalone Executable (Optional)
bashpip install pyinstaller
pyinstaller --onefile --windowed --add-data "gdal_data;gdal_data" --add-data "proj_data;proj_data" --icon=Class_QC_icon.ico classification_qc_rasters.py
Project Status
This tool is actively maintained for BC government LiDAR QC workflows. Current version: 2.6
The tool has been tested with:

Various LAS classification schemes
BC UTM zones 7-11 (EPSG 3154-3157, 2955)
Multiple project areas with spatial gaps
Large datasets spanning hundreds of tiles

Goals/Roadmap

 Add custom classification filtering (user-defined class combinations)
 Progress bars for long-running operations
 Support for additional EPSG codes and coordinate systems
 Automated QC metric calculation (coverage percentages, density statistics)
 Export QC summary reports
 Integration with LiDAR metadata extraction tools
 Support for custom color ramps in output rasters
 Batch processing across multiple project directories
 Command-line interface option for automated workflows
 Comparison mode for before/after classification analysis

Getting Help or Reporting an Issue
To report bugs, suggest features, or ask questions:

Check existing issues in the GitHub repository
Create a new issue with:

Detailed description of the problem
LAS file specifications (version, point format, classification scheme)
LAStools version and license status
Python and library versions (pip list)
System environment (OS, available RAM)
Error messages or unexpected behavior
Sample data characteristics (tile count, file sizes, spatial extent)



For urgent QC processing issues, contact your LiDAR data processing team lead.
How to Contribute
We welcome contributions from the LiDAR QC and geospatial analysis community:

Fork the repository and create a feature branch
Make your changes with clear, documented code
Test thoroughly with various LAS classification schemes and spatial configurations
Submit a pull request with:

Description of changes
QC workflow improvements or new features
Testing performed with different datasets
Any new dependencies added
Performance benchmarks for large datasets



Contribution Guidelines

Follow PEP 8 Python style guidelines
Add docstrings to new functions
Update version number and README for feature additions
Ensure compatibility with LAStools command-line interface
Test with both LAS and LAZ formats
Consider memory usage for large tile collections
Validate output raster integrity and georeferencing
Test island detection algorithm with various tile configurations

Technical Notes
Island Detection Algorithm:

Tiles are grouped by spatial adjacency (1% tile width gap tolerance)
Island bounding boxes can be expanded for merge detection (configurable)
Prevents inappropriate merging of spatially distinct project areas
Preserves individual merged GeoTIFFs for each spatial island

EPSG/UTM Zone Mapping (BC):

UTM 7 → EPSG 3154
UTM 8 → EPSG 3155
UTM 9 → EPSG 3156
UTM 10 → EPSG 3157
UTM 11 → EPSG 2955

Output Optimization:

LZW compression for reduced file sizes
Tiled GeoTIFF structure (256x256 blocks) for efficient reading
NoData value set to 0 for all outputs


License: [Specify your government open source license]
Maintainer: [Your contact information or team]
Version: 2.6
