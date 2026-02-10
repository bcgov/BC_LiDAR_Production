LiDAR Tile Header QC Tool
A GUI-based Python application for automated validation of LiDAR tile header metadata against BC government specifications for final deliverable products. This tool uses LAStools' lasinfo utility to extract header information from tiled LAS/LAZ files, validates critical metadata fields against provincial standards, and generates color-coded Excel reports highlighting compliance issues for final product QC workflows.
Features

Automated Header Extraction: Uses LAStools lasinfo to extract header metadata from all tiled LAS/LAZ files in a directory
Multi-Core Processing: Utilizes 8 cores for fast processing of large tile collections
Comprehensive Metadata Validation: Checks 10 critical header fields against BC LiDAR tile specifications:

BC tile filename convention compliance
Global encoding settings
Project GUID format
LAS version (1.4)
System identifier (Riegl-VQ1560II)
Point data format (format 6)
Scale factors (0.01m precision)
LiDAR BC VLR presence
Processing software verification
WKT coordinate system string validation per UTM zone


Tile Filename Validation: Enforces BC tile naming convention: bc_[mapsheet]_[channel]_[session]_[priority]_xyes_[density]_utm[zone]_[startdate]_[enddate].laz
UTM-Specific CRS Validation: Validates complete WKT strings for UTM zones 7-11 with CGVD2013 vertical datum
Color-Coded Excel Reports: Generates formatted spreadsheets with:

Green cells for compliant fields
Red cells for non-compliant fields
Auto-fitted column widths
Bold headers


File Organization: Moves lasinfo text files to organized subfolder after processing
GUI Interface: Simple tkinter interface with directory selection and help documentation
Automatic Folder Opening: Opens results folder upon completion

Usage
Running the Tool

Launch the application
Click "Select Directory" and choose the folder containing tiled LAZ files (final deliverables)
Click "Run" to begin processing
Review the generated Excel report: LiDAR Header QC Summary.xlsx
Results folder opens automatically upon completion

Reading the Report
Each row represents one tile file. Columns show validation results for each metadata field:

Green cells: Metadata is correct ✓
Red cells: Metadata needs correction ✗

Focus on red cells to identify tiles requiring header fixes before final delivery.
Output Structure
Input_Directory/
├── LiDAR Header QC/
│   ├── LiDAR Header QC Summary.xlsx
│   └── LASInfo Text Files/
│       └── [individual lasinfo output .txt files]
Requirements
Software Dependencies

Python 3.x
LAStools (lasinfo.exe) installed at C:\LAStools\bin\
LAStools license (optional for header reading)

Python Libraries
openpyxl
colorama
tkinter (standard library)
subprocess (standard library)
os (standard library)
shutil (standard library)
re (standard library)
Data Requirements

LAZ (or LAS) tiles from BC LiDAR final deliverables
Files must follow BC tile naming convention (enforced by tool)
Expected metadata based on Riegl VQ-1560II sensor and BC processing standards

Installation

Clone or download this repository
Install Python dependencies:

bash   pip install openpyxl colorama

Install LAStools:

Download LAStools from rapidlasso.com
Install to default location: C:\LAStools\
Ensure lasinfo.exe is present: C:\LAStools\bin\lasinfo.exe


(Optional) Set custom icon path:

Edit line with root.iconbitmap(...) to point to your icon file
Or remove this line to use default window icon


Run the application:

bash   python lidar_tile_header_qc.py
```

## Project Status

This tool is actively maintained for BC government LiDAR final product QC. Current version: **1.1**

The tool has been tested with:
- BC provincial tile schema (2500m x 2500m tiles)
- Riegl VQ-1560II dual-channel sensor data
- Final tiled deliverable products
- Various project sizes (100s to 1000s of tiles)

## Goals/Roadmap

- [ ] Support for additional sensor systems beyond Riegl VQ-1560II
- [ ] Configurable metadata validation rules (external config file)
- [ ] Summary statistics in Excel report (% compliance, failure counts by field)
- [ ] Support for LAS 1.2 and other versions
- [ ] Batch processing across multiple project directories
- [ ] Export of non-compliant tiles list for bulk fixing
- [ ] Integration with header repair tools
- [ ] Command-line interface option
- [ ] Progress bar for large datasets (1000+ tiles)
- [ ] Detailed logging of validation process
- [ ] Support for custom tile naming patterns
- [ ] Validation of point counts and density metadata

## Getting Help or Reporting an Issue

To report bugs, suggest features, or ask questions:

**Contact**: Spencer Floyd at spencer.floyd@gov.bc.ca

For GitHub issues:
1. Check existing issues in the repository
2. Create a new issue with:
   - Detailed description of the problem
   - LAStools version
   - Sample tile filenames (if naming convention issue)
   - System environment (OS, Python version)
   - Error messages or unexpected validation results
   - Excel report screenshot (if formatting issue)

For urgent QC issues affecting deliverables, contact your LiDAR processing team lead.

## How to Contribute

We welcome contributions from the LiDAR processing and QC community:

1. **Fork the repository** and create a feature branch
2. **Make your changes** with clear, documented code
3. **Test thoroughly** with various tile collections and metadata scenarios
4. **Submit a pull request** with:
   - Description of changes
   - Validation rules added/modified
   - Testing performed with different sensor data and tile schemas
   - Any new dependencies or configuration requirements

### Contribution Guidelines
- Follow PEP 8 Python style guidelines
- Add docstrings to new functions
- Update version number and README for feature additions
- Ensure compatibility with LAStools lasinfo output format
- Test with both LAS and LAZ formats
- Validate Excel formatting and color coding
- Test with various metadata error scenarios
- Consider backward compatibility with existing tile deliverables

### Technical Notes

**BC Tile Filename Convention:**
```
Format: bc_[mapsheet]_[ch]_[sess]_[pri]_xyes_[dens]_utm[zone]_[start]_[end].laz
Example: bc_092L001_1_1_1_xyes_8_utm9_20240501_20240515.laz
Components:
  - Prefix: "bc" or "BC" (case insensitive)
  - Mapsheet: 3 digits + 1 letter + 3 digits (e.g., 092L001)
  - Channel: single digit
  - Session: single digit
  - Priority: single digit
  - Fixed: "xyes"
  - Density: 1-2 digits (points per m²)
  - UTM Zone: "utm8", "utm9", "utm10", "utm11" (case insensitive)
  - Start Date: YYYYMMDD
  - End Date: YYYYMMDD
  - Extension: .laz

Regex: ^(B|b)(C|c)_\d\d\d[A-Za-z]\d\d\d_\d_\d_\d_xyes_(\d|\d\d)_(utm08|UTM08|utm8|UTM8|utm09|UTM09|utm9|UTM9|utm10|UTM10|utm11|UTM11)_\d\d\d\d\d\d\d\d_\d\d\d\d\d\d\d\d.laz$
Expected Metadata Values:

Global Encoding: 17 (GPS time type + WKT flag)
Project GUID: All zeros (00000000-0000-0000-0000-000000000000)
LAS Version: 1.4
System ID: "Riegl-VQ1560II"
Point Format: 6 (LAS 1.4 format with GPS time, RGB, NIR)
Scale Factors: 0.01 0.01 0.01 (1cm precision)
VLR Markers: Presence of "OP24BMRS001" and "province_BC" strings
Software: "RiPROCESS" or starts with "STRIPALIGN"

WKT Validation:

Complete compound coordinate system strings validated
Includes NAD83(CSRS) / UTM projection + CGVD2013 vertical datum
Specific EPSG codes per zone:

UTM 7 → EPSG 3154 + 6647
UTM 8 → EPSG 3155 + 6647
UTM 9 → EPSG 3156 + 6647
UTM 10 → EPSG 3157 + 6647
UTM 11 → EPSG 2955 + 6647



LiDAR BC VLR:
The tool checks for presence of BC-specific Variable Length Record containing:

User ID: "OP24BMRS001"
Description containing: "province_BC"

This VLR must be present in all final tile deliverables.
Processing Software Validation:

RiPROCESS: Direct output from Riegl processing software
STRIPALIGN: Strip adjustment software (any version starting with "STRIPALIGN")

Both are acceptable for final tiles, as headers should remain compliant through the tiling workflow.
Difference from Flight Line QC Tool:
This tool is specifically for tiled final products, not raw flight lines. Key differences:

Different filename convention (BC tile schema vs. flight line identifiers)
Applied to deliverable tiles after tiling process
Same metadata requirements but different file organization


License: [Specify your government open source license]
Maintainer: Spencer Floyd (spencer.floyd@gov.bc.ca)
Version: 1.1
Sensor Compatibility: Optimized for Riegl VQ-1560II dual-channel sensor
