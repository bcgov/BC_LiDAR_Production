LAS/LAZ Corruption Checker
A GUI-based Python application for detecting and managing corrupted LiDAR point cloud files. This tool performs parallel integrity checks on LAS and LAZ files using LAStools' lasinfo utility, identifies potentially corrupt files, and provides options to quarantine problematic data for government LiDAR quality control workflows.
Features

Automated Corruption Detection: Scans LAS/LAZ files for errors, warnings, truncation, and missing data chunks
Parallel Processing: Utilizes multi-core processing (up to 8 workers) for fast validation of large datasets
GUI Interface: Simple tkinter-based interface for directory selection and operation control
Corruption Reports: Generates text reports listing all potentially corrupt files
File Quarantine: Optional automatic movement of corrupt files to a separate folder
Batch Processing: Processes entire directories of point cloud files in a single operation

Usage

Launch the application
Click "Browse" to select the directory containing your LAS/LAZ files
Click "Check Files" to begin the corruption scan
Review the results:

If corrupt files are found, you'll be prompted to move them to a Corrupted_Files folder
A report (corrupt_laz_report.txt) is generated in the input directory listing all problematic files



What Gets Flagged as Corrupt
The tool checks lasinfo64 output for the following indicators:

Error messages
Warnings
Chunk issues
Truncated files
Missing data

Requirements
Software Dependencies

Python 3.x
LAStools (lasinfo64 executable must be in system PATH)

Python Libraries

tkinter (standard library)
subprocess (standard library)
concurrent.futures (standard library)
shutil (standard library)
multiprocessing (standard library)

System Requirements

Multi-core processor recommended for optimal performance
Sufficient disk space for moving corrupt files (if using quarantine feature)

Installation

Clone or download this repository
Install LAStools:

Download LAStools from rapidlasso.com
Add LAStools/bin directory to your system PATH
Ensure lasinfo64 is accessible from command line


Verify Python installation:

bash   python --version
(Python 3.x required; tkinter is included in standard Python distributions)

Run the application:

bash   python las_corruption_checker.py
Project Status
This tool is actively used for quality control in BC government LiDAR processing workflows. It has been tested with various LAS format versions and LAZ compressed files from multiple sensor platforms.
Goals/Roadmap

 Add progress bar with real-time file count
 Support for custom corruption criteria/keywords
 Detailed corruption classification (errors vs warnings vs truncation)
 Export reports in CSV format for integration with QC databases
 Add option to attempt automatic repair of minor issues
 Generate summary statistics (corruption rate, file sizes, etc.)
 Command-line interface option for scripted workflows
 Support for recursive directory scanning

Getting Help or Reporting an Issue
To report bugs, suggest features, or ask questions:

Check existing issues in the GitHub repository
Create a new issue with:

Detailed description of the problem
LAS/LAZ format version and file specifications
LAStools version being used
Error messages or unexpected behavior
System environment (OS, Python version)



For urgent data integrity issues, contact your LiDAR QC team immediately.
How to Contribute
We welcome contributions from the LiDAR and geospatial data processing community:

Fork the repository and create a feature branch
Make your changes with clear, documented code
Test thoroughly with various LAS/LAZ file types and corruption scenarios
Submit a pull request with:

Description of changes
Problem solved or feature added
Testing performed
Any new dependencies



Contribution Guidelines

Follow PEP 8 Python style guidelines
Add docstrings to new functions
Update README if adding features or changing behavior
Ensure compatibility with LAStools lasinfo64 output format
Test with both LAS and LAZ formats across different versions (1.2, 1.4)
Consider performance implications for large file collections

Suggested Areas for Contribution

Enhanced error parsing for specific LAS format issues
Integration with other LAS validation tools
Automated logging for audit trails
Network/shared drive optimization


License: [Specify your government open source license]
Maintainer: [Your contact information or team]
