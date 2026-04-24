# Last Return Density Checker — Release Guide

How to update the app and ship a new installer. Covers everything from pulling the code to dropping the compiled installer on the NAS.

Source repo: https://github.com/bcgov/BC_LiDAR_Production — folder `Scripts/Density_Checks/`

---

## First time only — set up your machine

1. **Clone the repo**
   ```
   git clone https://github.com/bcgov/BC_LiDAR_Production.git
   ```

2. **Install Inno Setup** — free download from https://jrsoftware.org/isdl.php

3. **Create the conda env** — one command:
   ```
   conda create -n geo_env python=3.11 -c conda-forge rasterio fiona shapely pyproj numpy certifi colorama pyinstaller
   ```

4. **Map the `V:` drive** to the Production NAS. Ask your sysadmin if it's not already mapped.

---

## Every release — the six steps

### 1. Pull the latest code
```
cd BC_LiDAR_Production\Scripts\Density_Checks
git pull
```

### 2. Edit the app
Open `Last_Return_Density_Analysis.py` in your editor, make your changes, save.

### 3. Bump the version
In `installer.iss`, change this line to the new version:
```
#define MyAppVersion "1.5.0"
```

### 4. Build the EXE
From inside `Scripts\Density_Checks\`:
```
build.bat
```
This will automatically:
- Activate the `geo_env` conda environment
- Robocopy `Tiles_by_UTM` and `Water_by_UTM` from V: into the local `data/` folder
- Run `sync_proj_data.py` to bundle the correct PROJ/GDAL data
- Run PyInstaller using `LastReturnDensityChecker.spec`

Output: `dist\LastReturnDensityChecker\LastReturnDensityChecker.exe`

### 5. Compile the installer
Open `installer.iss` in Inno Setup Compiler and press `F9` (or click the green Compile button).

Output: `installer_output\LastReturnDensityChecker_Setup_<version>.exe`

### 6. Distribute and commit
**Copy the new installer** to the NAS:
```
V:\Production_NAS\Supporting_Production_Files\Top_common\Software\GeoBC\Last_Return_Density_Checker\
```
Move the previous installer into the `Superceded\` subfolder at that same location.

**Push your source changes:**
```
git add Scripts/Density_Checks/
git commit -m "feat: Last Return Density Checker vX.Y.Z — <what changed>"
git push
```

---

## Troubleshooting

| Error | Cause / Fix |
|---|---|
| `build.bat` — "Cannot access network data source" | `V:` drive isn't mapped. Map it and retry. |
| `build.bat` — "PROJ/GDAL SYNC FAILED" | Conda env is out of sync. Recreate it using the command in setup step 3. |
| PyInstaller — "module not found" | Add the missing module to `hiddenimports` in `LastReturnDensityChecker.spec`. |
| App crashes on startup | Check `%APPDATA%\GeoBC\LastReturnDensityChecker\app_debug.log` and `boot_*.log`. |

---

Maintainers: Spencer Floyd (spencer.floyd@gov.bc.ca), Nikolay Senilov
