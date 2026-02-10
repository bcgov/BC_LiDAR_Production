LiDAR Flight Line Header QC Tool
A GUI-based Python application for automated validation of LiDAR flight line header metadata against BC government specifications. This tool uses LAStools' lasinfo utility to extract header information from LAS/LAZ files, validates critical metadata fields, and generates color-coded Excel reports highlighting compliance issues for post-processing QC workflows.
Features

Automated Header Extraction: Uses LAStools lasinfo to extract header metadata from all LAS/LAZ files in a directory
Multi-Core Processing: Utilizes 8 cores for fast processing of large flight line collections
Comprehensive Metadata Validation: Checks 10 critical header fields against BC LiDAR specifications:

Filename convention compliance
Global encoding settings
Project GUID format
LAS version (1.4)
System identifier (Riegl-VQ1560II)
Point data format (format 6)
Scale factors (0.01m precision)
LiDAR BC VLR presence
Processing software verification
WKT coordinate system string validation per UTM zone


Filename Validation: Enforces BC naming convention: [FSID]_[Session]_[GPSDay]_[Year]_[Serial]_[TailNumber]_utm[Zone].[ext]
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
Click "Select Directory" and choose the folder containing LAS/LAZ flight line files
Click "Run" to begin processing
Review the generated Excel report: LiDAR Header QC Summary.xlsx
Results folder opens automatically upon completion

Reading the Report
Each row represents one flight line file. Columns show validation results for each metadata field:

Green cells: Metadata is correct ✓
Red cells: Metadata needs correction ✗

Focus on red cells to identify files requiring header fixes.
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

LAS or LAZ files from BC LiDAR acquisitions
Files should follow BC naming convention (enforced by tool)
Expected metadata based on Riegl VQ-1560II sensor processing

Installation

Clone or download this repository
Install Python dependencies:

bash   pip install openpyxl colorama

Install LAStools:

Download LAStools from rapidlasso.com
Install to default location: C:\LAStools\
Ensure lasinfo.exe is present: C:\LAStools\bin\lasinfo.exe


Run the application:

bash   python lidar_header_qc.py
```

## Project Status

This tool is actively maintained for BC government LiDAR post-processing QC. Current version: **1.2**

The tool has been tested with:
- Riegl VQ-1560II dual-channel sensor data
- RFQC processed flight lines
- StripAlign adjusted flight lines
- Various project sizes (10s to 100s of flight lines)

## Goals/Roadmap

- [ ] Support for additional sensor systems beyond Riegl VQ-1560II
- [ ] Configurable metadata validation rules (external config file)
- [ ] Summary statistics in Excel report (% compliance, failure counts)
- [ ] Support for LAS 1.2 and other versions
- [ ] Batch processing across multiple project directories
- [ ] Export of non-compliant files list for bulk fixing
- [ ] Integration with header repair tools
- [ ] Command-line interface option
- [ ] Progress bar for large datasets
- [ ] Detailed logging of validation process
- [ ] Support for custom filename patterns

## Getting Help or Reporting an Issue

To report bugs, suggest features, or ask questions:

**Contact**: Spencer Floyd at spencer.floyd@gov.bc.ca

For GitHub issues:
1. Check existing issues in the repository
2. Create a new issue with:
   - Detailed description of the problem
   - LAStools version
   - Sample filenames (if naming convention issue)
   - System environment (OS, Python version)
   - Error messages or unexpected validation results
   - Excel report screenshot (if formatting issue)

For urgent QC issues affecting deliverables, contact your LiDAR processing team lead.

## How to Contribute

We welcome contributions from the LiDAR processing and QC community:

1. **Fork the repository** and create a feature branch
2. **Make your changes** with clear, documented code
3. **Test thoroughly** with various flight line collections and metadata scenarios
4. **Submit a pull request** with:
   - Description of changes
   - Validation rules added/modified
   - Testing performed with different sensor data
   - Any new dependencies or configuration requirements

### Contribution Guidelines
- Follow PEP 8 Python style guidelines
- Add docstrings to new functions
- Update version number and README for feature additions
- Ensure compatibility with LAStools lasinfo output format
- Test with both LAS and LAZ formats
- Validate Excel formatting and color coding
- Test with various metadata error scenarios
- Consider backward compatibility with existing projects

### Technical Notes

**BC Filename Convention:**
```
Format: [FSID]_[Session]_[GPSDay]_[Year]_[Serial]_C-[Tail]_utm[Zone].[ext]
Example: 12345_1_123_2024_1234_C-ABCD_utm9.laz
Regex: ^[1-2]\d{4}_\d_[0-9]{3}_20\d\d_\d{4}_C-[A-Za-z]{4}_utm(7|8|9|10|11)\.(las|laz)$
Expected Metadata Values:

Global Encoding: 17 (GPS time type + WKT flag)
Project GUID: All zeros (00000000-0000-0000-0000-000000000000)
LAS Version: 1.4
System ID: "Riegl-VQ1560II"
Point Format: 6 (LAS 1.4 format with GPS time, RGB, NIR)
Scale Factors: 0.01 0.01 0.01 (1cm precision)
VLR Markers: Presence of "OP24BMRS001" and "province_bc" strings
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
Description containing: "province_bc"

This VLR is added during RFQC processing and should persist through StripAlign adjustments.
Processing Software Validation:

RiPROCESS: Direct output from Riegl processing software
STRIPALIGN: Strip adjustment software (any version starting with "STRIPALIGN")

Both are acceptable, as headers should remain compliant through the adjustment workflow.

License: [Specify your government open source license]
Maintainer: Spencer Floyd (spencer.floyd@gov.bc.ca)
Version: 1.2
Sensor Compatibility: Optimized for Riegl VQ-1560II dual-channel sensor
