import time
from pathlib import Path
import sys
import os
from datetime import datetime
import traceback
import faulthandler

os.environ.setdefault("MPLBACKEND", "Agg")
_TBOOT = time.perf_counter()

def _boot_log_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    d = Path(appdata) / "GeoBC" / "LastReturnDensityChecker"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"boot_{os.getpid()}.log"

_BOOT_LOG = _boot_log_path()
try:
    _BOOT_FH = open(_BOOT_LOG, "a", encoding="utf-8", buffering=1)
except Exception:
    # Absolute fallback: never let boot logging kill startup
    _BOOT_FH = open(os.devnull, "w", encoding="utf-8")

def _boot_write(msg: str):
    fh = _BOOT_FH
    if fh is None or getattr(fh, "closed", False):
        return
    try:
        fh.write(msg + "\n")
        fh.flush()
    except Exception:
        pass

def _t(msg: str):
    _boot_write(f"[BOOT_TIMING] {msg}: {time.perf_counter() - _TBOOT:.2f}s")

_boot_write("\n" + "=" * 80)
_boot_write(f"BOOT {datetime.now().isoformat(timespec='seconds')}")
_boot_write(f"sys.executable={sys.executable}")
_boot_write(f"sys.prefix={sys.prefix}")
_boot_write(f"frozen={getattr(sys, 'frozen', False)}")

faulthandler.enable(_BOOT_FH)

def _boot_excepthook(exctype, value, tb):
    _boot_write("=== UNCAUGHT EXCEPTION (BOOT) ===")
    traceback.print_exception(exctype, value, tb, file=_BOOT_FH)
    try:
        _BOOT_FH.flush()
    except Exception:
        pass

sys.excepthook = _boot_excepthook

# Make sure print() can't crash windowed builds
if sys.stdout is None:
    sys.stdout = _BOOT_FH
if sys.stderr is None:
    sys.stderr = _BOOT_FH

_t("top-of-file (boot logger ready)")
# -------------------------------------------------------------------------------

# -------------------- stdlib imports (needed by the rest of the file) --------------------
import json
import csv
import shutil
import glob
import re
UTM_RE = re.compile(r"utm(\d{1,2})", re.IGNORECASE)
import subprocess
import multiprocessing
import threading
import atexit
from concurrent.futures import ProcessPoolExecutor
# -------------------- stdlib imports --------------------
_t("after stdlib imports")


# Prevent oversubscription (good with numpy + multiprocessing)
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

def get_app_root() -> Path:
    # Normal python run: folder containing this .py
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent

    # Frozen: prefer folder containing the exe (installer will place data next to it)
    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / "data").is_dir():
        return exe_dir

    # Fallback: PyInstaller temp dir (mostly for onefile)
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)

    return exe_dir

APP_ROOT = get_app_root()
DATA_ROOT = APP_ROOT / "data"
ASSETS_ROOT = APP_ROOT / "assets"

def apply_window_icon(win):
    """
    Set the window titlebar icon (Windows).
    Requires an .ico file.
    """
    ico = ASSETS_ROOT / "LastReturnDensityChecker_Icon.ico"
    try:
        if ico.is_file():
            win.iconbitmap(str(ico))
    except Exception:
        pass

PACKAGED_TILING_DEFAULT = str(DATA_ROOT / "Tiles_By_UTM")
PACKAGED_WATER_DEFAULT  = str(DATA_ROOT / "Water_by_UTM")

# Keep a handle so faulthandler isn't using a leaked anonymous open()
_FAULT_FH = None
_DEVNULL_FH = None

class _SafeFileWriter:
    def __init__(self, file_path: Path):
        self._f = open(file_path, "a", encoding="utf-8", buffering=8192)

    def write(self, s):
        if s is None:
            return 0
        if isinstance(s, bytes):
            try:
                s = s.decode("utf-8", errors="replace")
            except Exception:
                s = str(s)

        self._f.write(s)
        return len(s)

    def flush(self):
        try:
            self._f.flush()
        except Exception:
            pass

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass

def setup_logging():
    global _FAULT_FH, _DEVNULL_FH

    log_dir = _config_dir()
    log_file = log_dir / "app_debug.log"

    _FAULT_FH = open(log_file, "a", encoding="utf-8", buffering=8192)
    faulthandler.enable(_FAULT_FH)

    tee = _SafeFileWriter(log_file)

    def _cleanup():
        global _FAULT_FH, _DEVNULL_FH  # <-- IMPORTANT

        try:
            tee.close()
        except Exception:
            pass
        try:
            if _FAULT_FH:
                _FAULT_FH.close()
        except Exception:
            pass
        _FAULT_FH = None
        try:
            if _DEVNULL_FH:
                _DEVNULL_FH.close()
        except Exception:
            pass
        _DEVNULL_FH = None  # now actually resets the module global

    atexit.register(_cleanup)

    def excepthook(exctype, value, tb):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("\n\n=== UNCAUGHT EXCEPTION ===\n")
            traceback.print_exception(exctype, value, tb, file=f)
        try:
            from tkinter import messagebox as _mb
            _mb.showerror("Crash", f"See log:\n{log_file}\n\n{value}")
        except Exception:
            pass

    sys.excepthook = excepthook
    sys.stdout = tee
    sys.stderr = tee
    return str(log_file)

def _safe_log_fh():
    """
    Return a file-like object that is safe to write to at any time.
    Prefers app_debug.log handle if setup_logging() has run.
    Falls back to boot log if it's still open.
    Final fallback: sys.__stderr__ / sys.stderr / devnull.
    """
    global _FAULT_FH, _BOOT_FH, _DEVNULL_FH

    try:
        if _FAULT_FH is not None and not getattr(_FAULT_FH, "closed", False):
            return _FAULT_FH
    except Exception:
        pass

    try:
        if _BOOT_FH is not None and not getattr(_BOOT_FH, "closed", False):
            return _BOOT_FH
    except Exception:
        pass

    if sys.__stderr__:
        return sys.__stderr__
    if sys.stderr:
        return sys.stderr

    # Final fallback: open devnull ONCE and reuse it
    if _DEVNULL_FH is None or getattr(_DEVNULL_FH, "closed", False):
        try:
            _DEVNULL_FH = open(os.devnull, "w", encoding="utf-8")
        except Exception:
            # absolute last resort: give back something writable-ish
            return sys.stdout or _BOOT_FH

    return _DEVNULL_FH

def _log_exception(prefix: str = ""):
    """
    Log the current exception traceback safely to whichever log is available.
    Call inside an except: block.
    """
    fh = _safe_log_fh()
    try:
        if prefix:
            fh.write(prefix + "\n")
        traceback.print_exc(file=fh)
        try:
            fh.flush()
        except Exception:
            pass
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Org defaults + config storage
# -----------------------------------------------------------------------------
ORG_LASGRID_DEFAULT = r"C:\LAStools\bin\lasgrid64.exe"
ORG_DEFAULT_WORKERS = 8

def _config_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    d = base / "GeoBC" / "LastReturnDensityChecker"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _config_path() -> Path:
    return _config_dir() / "config.json"

def _first_existing_dir(candidates):
    for p in candidates:
        if p and Path(p).is_dir():
            return str(Path(p))
    return ""

def load_config() -> dict:
    cfg = {
        "lasgrid_exe": ORG_LASGRID_DEFAULT,
        "tiling_scheme_root": _first_existing_dir([PACKAGED_TILING_DEFAULT]),
        "prep_water_gpkg_dir": _first_existing_dir([PACKAGED_WATER_DEFAULT]),
    }
    try:
        cfg_path = _config_path()
        if cfg_path.is_file():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg.update(data)
    except Exception:
        pass

    # sanitize
    if not isinstance(cfg.get("lasgrid_exe"), str) or not cfg["lasgrid_exe"].strip():
        cfg["lasgrid_exe"] = ORG_LASGRID_DEFAULT

    if not (isinstance(cfg.get("tiling_scheme_root"), str) and Path(cfg["tiling_scheme_root"]).is_dir()):
        cfg["tiling_scheme_root"] = _first_existing_dir([PACKAGED_TILING_DEFAULT])

    if not (isinstance(cfg.get("prep_water_gpkg_dir"), str) and Path(cfg["prep_water_gpkg_dir"]).is_dir()):
        cfg["prep_water_gpkg_dir"] = _first_existing_dir([PACKAGED_WATER_DEFAULT])

    return cfg

def save_config(cfg: dict) -> None:
    out = {
        "lasgrid_exe": cfg.get("lasgrid_exe", ORG_LASGRID_DEFAULT),
        "tiling_scheme_root": cfg.get("tiling_scheme_root", PACKAGED_TILING_DEFAULT),
        "prep_water_gpkg_dir": cfg.get("prep_water_gpkg_dir", PACKAGED_WATER_DEFAULT),
    }
    _config_path().write_text(json.dumps(out, indent=2), encoding="utf-8")


# -----------------------------------------------------------------------------
# GDAL/PROJ env setup (must happen BEFORE importing rasterio/fiona/geopandas)
# -----------------------------------------------------------------------------
def _set_env_dir(varname: str, candidates):
    cur = os.environ.get(varname)
    if cur and Path(cur).is_dir():
        return cur
    for p in candidates:
        p = Path(p)
        if p.is_dir():
            os.environ[varname] = str(p)
            return str(p)
    return None

# When frozen, always force bundled data paths first — PyInstaller hooks
# (e.g. pyproj) may pre-set PROJ_LIB/PROJ_DATA to Library/share/proj before
# our code runs, bypassing the bundled data/proj directory.
if getattr(sys, "frozen", False):
    _bundled_gdal = DATA_ROOT / "gdal"
    _bundled_proj = DATA_ROOT / "proj"
    if _bundled_gdal.is_dir():
        os.environ["GDAL_DATA"] = str(_bundled_gdal)
    if _bundled_proj.is_dir():
        os.environ["PROJ_LIB"] = str(_bundled_proj)
        os.environ["PROJ_DATA"] = str(_bundled_proj)

    # Prevent conflicting PROJ/GDAL DLLs from OSGeo4W, QGIS, or other GIS
    # installations on the system PATH from being loaded instead of the
    # bundled ones. Put the exe directory first and filter out known conflicts.
    _exe_dir = str(Path(sys.executable).resolve().parent)
    # Check individual folder names, not substrings of the whole path,
    # to avoid stripping paths like "C:\Users\me\Projects\..." where
    # "proj" is a substring of "Projects".
    _conflict_dirs = {"osgeo4w", "osgeo4w64", "qgis", "saga-gis"}
    _clean_path = [_exe_dir]
    for _p in os.environ.get("PATH", "").split(os.pathsep):
        if not _p:
            continue
        _parts = _p.lower().replace("/", "\\").split("\\")
        if any(part in _conflict_dirs for part in _parts):
            _boot_write(f"PATH_STRIPPED: {_p}")
            continue
        if os.path.normcase(_p) != os.path.normcase(_exe_dir):
            _clean_path.append(_p)
    os.environ["PATH"] = os.pathsep.join(_clean_path)

    # Python 3.8+: explicitly add exe directory as DLL search path
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(_exe_dir)
        except OSError:
            pass

env_prefix = Path(sys.prefix)
exe = Path(sys.executable)
conda_root = exe.parents[2] if len(exe.parents) >= 3 else env_prefix

gdal_candidates = [
    DATA_ROOT / "gdal",
    env_prefix / "Library" / "share" / "gdal",
    conda_root / "Library" / "share" / "gdal",
    env_prefix / "share" / "gdal",
    conda_root / "share" / "gdal",
]
proj_candidates = [
    DATA_ROOT / "proj",
    env_prefix / "Library" / "share" / "proj",
    conda_root / "Library" / "share" / "proj",
    env_prefix / "share" / "proj",
    conda_root / "share" / "proj",
]

_set_env_dir("GDAL_DATA", gdal_candidates)
proj_dir = _set_env_dir("PROJ_LIB", proj_candidates)
if proj_dir and not os.environ.get("PROJ_DATA"):
    os.environ["PROJ_DATA"] = proj_dir
_boot_write(f"GDAL_DATA={os.environ.get('GDAL_DATA')}")
_boot_write(f"PROJ_LIB={os.environ.get('PROJ_LIB')}")
_boot_write(f"PROJ_DATA={os.environ.get('PROJ_DATA')}")


# -----------------------------------------------------------------------------
# Heavy imports (AFTER GDAL/PROJ env is set!)
# -----------------------------------------------------------------------------
# Lazily imported in main run + in worker initializer (reduces GUI + worker spawn overhead)
np = None
fiona = None
rasterio = None
rasterize = None
geom_bounds = None
reproject = None
Resampling = None
RioCRS = None
Affine = None

def _import_heavy():
    global np, fiona, rasterio, rasterize, geom_bounds, reproject, Resampling
    global RioCRS, Affine

    if np is not None and RioCRS is not None and Affine is not None:
        return

    import numpy as _np
    import fiona as _fiona
    import rasterio as _rasterio
    from rasterio.features import rasterize as _rasterize, bounds as _geom_bounds
    from rasterio.warp import reproject as _reproject, Resampling as _Resampling
    from rasterio.transform import Affine as _Affine
    from rasterio.crs import CRS as _RioCRS

    np = _np
    fiona = _fiona
    rasterio = _rasterio
    rasterize = _rasterize
    geom_bounds = _geom_bounds
    reproject = _reproject
    Resampling = _Resampling
    RioCRS = _RioCRS
    Affine = _Affine

# -----------------------------------------------------------------------------
# UI colors
# -----------------------------------------------------------------------------
BG_MAIN = "#f0f0f0"

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
APP_VERSION = "1.4.0"

WATER_GPKG_TEMPLATE = "Water_UTM{zone:02d}_buf50m_tilebbox.gpkg"
WATER_LAYER_TEMPLATE = "water_utm{zone:02d}_buf50m"
NODATA_VALUE = -9999
DENSITY_THRESHOLD = 8       # pts/m² — tiles must meet this density
PASS_PERCENT = 95           # % of valid pixels that must meet DENSITY_THRESHOLD

WORKERS_CAP = 32
DEFAULT_WORKERS = min(ORG_DEFAULT_WORKERS, WORKERS_CAP)

# Speed vs file size:
# - None = fastest (no compression)
# - "LZW" = smaller files, slower writes
GTIFF_COMPRESS = None

EPSG_BY_UTM = {
    "utm11": 2955,
    "utm10": 3157,
    "utm9": 3156,
    "utm8": 3155,
    "utm7": 3154
}

# Hardcoded WKT for BC UTM zones (NAD83(CSRS)).
# Avoids CRS.from_epsg() which requires a matching proj.db version.
# AUTHORITY tags are required so QGIS can identify the CRS automatically.
_UTM_ZONE_INFO = {
    7:  (-141, 3154),
    8:  (-135, 3155),
    9:  (-129, 3156),
    10: (-123, 3157),
    11: (-117, 2955),
}

def _wkt_for_utm(zone: int) -> str:
    cm, epsg = _UTM_ZONE_INFO[zone]
    return (
        f'PROJCS["NAD83(CSRS) / UTM zone {zone}N",'
        'GEOGCS["NAD83(CSRS)",'
        'DATUM["NAD83_Canadian_Spatial_Reference_System",'
        'SPHEROID["GRS 1980",6378137,298.257222101,'
        'AUTHORITY["EPSG","7019"]]],'
        'PRIMEM["Greenwich",0,'
        'AUTHORITY["EPSG","8901"]],'
        'UNIT["degree",0.0174532925199433,'
        'AUTHORITY["EPSG","9122"]],'
        'AUTHORITY["EPSG","4617"]],'
        'PROJECTION["Transverse_Mercator"],'
        'PARAMETER["latitude_of_origin",0],'
        f'PARAMETER["central_meridian",{cm}],'
        'PARAMETER["scale_factor",0.9996],'
        'PARAMETER["false_easting",500000],'
        'PARAMETER["false_northing",0],'
        'UNIT["metre",1,'
        'AUTHORITY["EPSG","9001"]],'
        f'AUTHORITY["EPSG","{epsg}"]]'
    )

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def clamp_workers(workers: int) -> int:
    workers = int(workers)
    return max(1, min(workers, WORKERS_CAP))

def unique_dest_path(dest_path: str) -> str:
    p = Path(dest_path)
    if not p.exists():
        return str(p)
    i = 2
    while True:
        candidate = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not candidate.exists():
            return str(candidate)
        i += 1

def assert_required_assets(cfg: dict):
    missing = []
    tiling = cfg.get("tiling_scheme_root", "")
    water  = cfg.get("prep_water_gpkg_dir", "")
    if not tiling or not Path(tiling).is_dir():
        missing.append(f"Tiling scheme folder not found:\n{tiling}")
    if not water or not Path(water).is_dir():
        missing.append(f"Water folder not found:\n{water}")
    if missing:
        raise FileNotFoundError("\n\n".join(missing))

# -----------------------------------------------------------------------------
# QML sidecar generation for QGIS auto-styling (SINGLE MASTER FILE APPROACH)
# -----------------------------------------------------------------------------
def _generate_qml_content(
    threshold: float = 8.0,
    nodata_value: float = -9999.0,
    classification_min: float = 0.0,
    classification_max: float = 20.0
) -> bytes:
    """
    Generate QML XML content (not written to file yet).

    Returns:
        QML XML content as bytes (UTF-8 encoded)
    """
    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    # Use a cutoff slightly below threshold to ensure proper binning
    cutoff = threshold - 0.0001

    # Build QML XML structure
    qgis = ET.Element('qgis', {
        'version': '3.28.0',
        'styleCategories': 'AllStyleCategories'
    })

    # Pipe element (rendering settings)
    pipe = ET.SubElement(qgis, 'pipe')
    pipe_properties = ET.SubElement(pipe, 'pipe-properties')
    ET.SubElement(pipe_properties, 'Option', {'type': 'Map'})

    # Raster renderer (pseudocolor)
    rasterrenderer = ET.SubElement(pipe, 'rasterrenderer', {
        'type': 'singlebandpseudocolor',
        'opacity': '1',
        'alphaBand': '-1',
        'band': '1',
        'nodataColor': '',
        'classificationMin': str(classification_min),
        'classificationMax': str(classification_max)
    })

    # Raster transparency (handle nodata)
    rastertransparency = ET.SubElement(rasterrenderer, 'rasterTransparency')
    singleValuePixelList = ET.SubElement(rastertransparency, 'singleValuePixelList')
    ET.SubElement(singleValuePixelList, 'pixelListEntry', {
        'min': str(nodata_value),
        'max': str(nodata_value),
        'percentTransparent': '100'
    })

    # Min/Max origin
    minmaxorigin = ET.SubElement(rasterrenderer, 'minMaxOrigin')
    ET.SubElement(minmaxorigin, 'limits').text = 'None'
    ET.SubElement(minmaxorigin, 'extent').text = 'WholeRaster'
    ET.SubElement(minmaxorigin, 'statAccuracy').text = 'Estimated'
    ET.SubElement(minmaxorigin, 'cumulativeCutLower').text = '0.02'
    ET.SubElement(minmaxorigin, 'cumulativeCutUpper').text = '0.98'
    ET.SubElement(minmaxorigin, 'stdDevFactor').text = '2'

    # Color ramp shader (DISCRETE mode with graduated colors)
    rastershader = ET.SubElement(rasterrenderer, 'rastershader')
    colorrampshader = ET.SubElement(rastershader, 'colorrampshader', {
        'colorRampType': 'DISCRETE',
        'classificationMode': '1',
        'clip': '0',
        'minimumValue': str(classification_min),
        'maximumValue': str(classification_max)
    })

    # Graduated color ramp showing density quality
    # RED GRADIENT (< 8.0) - darker = worse failure
    ET.SubElement(colorrampshader, 'item', {
        'alpha': '255',
        'value': '2.0',
        'label': '0-2 (Critical)',
        'color': '#8B0000'  # Dark red
    })

    ET.SubElement(colorrampshader, 'item', {
        'alpha': '255',
        'value': '4.0',
        'label': '2-4 (Very Low)',
        'color': '#CD0000'  # Medium-dark red
    })

    ET.SubElement(colorrampshader, 'item', {
        'alpha': '255',
        'value': '6.0',
        'label': '4-6 (Low)',
        'color': '#FF0000'  # Bright red
    })

    ET.SubElement(colorrampshader, 'item', {
        'alpha': '255',
        'value': str(cutoff),  # 7.9999
        'label': '6-8 (Near Threshold)',
        'color': '#FF6B6B'  # Light red
    })

    # GREEN GRADIENT (>= 8.0) - darker = better quality
    ET.SubElement(colorrampshader, 'item', {
        'alpha': '255',
        'value': '10.0',
        'label': '8-10 (Pass)',
        'color': '#90EE90'  # Light green
    })

    ET.SubElement(colorrampshader, 'item', {
        'alpha': '255',
        'value': '12.0',
        'label': '10-12 (Good)',
        'color': '#00FF00'  # Bright green
    })

    ET.SubElement(colorrampshader, 'item', {
        'alpha': '255',
        'value': '15.0',
        'label': '12-15 (Very Good)',
        'color': '#00CD00'  # Medium-dark green
    })

    ET.SubElement(colorrampshader, 'item', {
        'alpha': '255',
        'value': str(classification_max),  # Now 100.0 to catch all realistic density values
        'label': f'15+ (Excellent)',
        'color': '#008B00'  # Dark green
    })

    # Brightness/Contrast/Saturation
    ET.SubElement(pipe, 'brightnesscontrast', {
        'brightness': '0',
        'contrast': '0',
        'gamma': '1'
    })

    # Hue/Saturation
    ET.SubElement(pipe, 'huesaturation', {
        'colorizeGreen': '128',
        'colorizeOn': '0',
        'colorizeRed': '255',
        'colorizeBlue': '128',
        'colorizeStrength': '100',
        'saturation': '0',
        'grayscaleMode': '0'
    })

    # Raster resampler
    ET.SubElement(pipe, 'rasterresampler', {
        'maxOversampling': '2'
    })

    # Resample filter
    ET.SubElement(pipe, 'resamplingStage', {
        'resamplingFilter': 'bilinear'
    })

    # Blend mode
    ET.SubElement(qgis, 'blendMode').text = '0'

    # Pretty-print XML
    rough_string = ET.tostring(qgis, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent='  ', encoding='utf-8')


def create_master_qml(output_root: str, threshold: float = 8.0, nodata_value: float = -9999.0) -> str:
    """
    Create ONE master QML file in _internal/_styles subdirectory.

    The master file is the single source of truth. All per-raster .qml files
    are hard-linked to this master, so editing the master updates all styles.

    Returns:
        Path to the master QML file
    """
    # Store master in _internal/_styles folder (misc files users don't need to see)
    internal_dir = Path(output_root) / "_internal"
    internal_dir.mkdir(exist_ok=True)
    styles_dir = internal_dir / "_styles"
    styles_dir.mkdir(exist_ok=True)
    master_qml_path = styles_dir / "density_raster_style_MASTER.qml"

    qml_content = _generate_qml_content(
        threshold=threshold,
        nodata_value=nodata_value,
        classification_min=0.0,
        classification_max=100.0  # High enough to catch all realistic density values
    )

    # Write master file
    master_qml_path.write_bytes(qml_content)

    # Create a README to explain the setup
    readme_path = styles_dir / "README.txt"
    readme_content = f"""QGIS Style Configuration
=========================

This folder contains the MASTER style file for all density rasters.

Master Style File:
  {master_qml_path.name}

How It Works:
- Each .tif file in PASS/, FAIL/, and Unclipped_Rasters/ has a matching .qml file next to it
- All those .qml files are HARD LINKS to this master file (not copies)
- They share the same disk space (~5KB total, not 5KB per raster)
- Editing the master file updates ALL raster styles automatically

Current Style (Graduated Colors):
RED GRADIENT (< {threshold:.1f} - FAIL):
  - 0-2:   Dark Red     (Critical - very poor density)
  - 2-4:   Medium Red   (Very Low)
  - 4-6:   Bright Red   (Low)
  - 6-8:   Light Red    (Near Threshold)

GREEN GRADIENT (>= {threshold:.1f} - PASS):
  - 8-10:  Light Green  (Pass)
  - 10-12: Bright Green (Good)
  - 12-15: Medium Green (Very Good)
  - 15+:   Dark Green   (Excellent)

NODATA: Transparent ({nodata_value}) for water bodies

To Change Colors:
1. Open {master_qml_path.name} in a text editor
2. Find <item> elements with color='#xxxxxx' attributes
3. Change hex colors (e.g., #8B0000 to #990000)
4. Adjust value='x.x' thresholds if needed
5. Save the file
6. All linked .qml files update instantly
7. Reload rasters in QGIS to see new colors

Note: The per-raster .qml files MUST stay next to their .tif files
      for QGIS auto-styling to work on drag-and-drop.
"""
    readme_path.write_text(readme_content, encoding='utf-8')

    return str(master_qml_path)


def link_qml_to_raster(tif_path: str, master_qml_path: str) -> tuple:
    """
    Create a hard link (or copy as fallback) from master QML to raster-specific QML.

    Hard links appear as separate files but share the same disk space.
    Editing the master updates all linked files.

    Args:
        tif_path: Path to the raster .tif file
        master_qml_path: Path to the master QML file

    Returns:
        (success: bool, message: str)
    """
    try:
        tif_path = Path(tif_path)
        master_qml_path = Path(master_qml_path)

        if not tif_path.exists():
            return False, f"Raster not found: {tif_path}"
        if not master_qml_path.exists():
            return False, f"Master QML not found: {master_qml_path}"

        qml_path = tif_path.with_suffix('.qml')

        # Remove existing QML if present
        if qml_path.exists():
            try:
                qml_path.unlink()
            except Exception:
                pass

        # Try hard link first (Windows: no admin required, shares disk space)
        try:
            os.link(master_qml_path, qml_path)
            return True, "QML_LINKED"
        except (OSError, NotImplementedError):
            # Fallback: copy the file (small overhead ~5KB per file)
            try:
                shutil.copy2(master_qml_path, qml_path)
                return True, "QML_COPIED"
            except Exception as copy_err:
                return False, f"QML_LINK_FAILED: {copy_err}"

    except Exception as e:
        return False, f"QML_ERROR: {type(e).__name__}: {e}"


def link_qml_to_directory(directory: str, master_qml_path: str) -> tuple:
    """
    Link master QML to all .tif files in a directory (including subdirectories).

    Args:
        directory: Directory containing .tif files
        master_qml_path: Path to the master QML file

    Returns:
        (success_count: int, fail_count: int)
    """
    success_count = 0
    fail_count = 0

    tif_files = glob.glob(os.path.join(directory, "**", "*.tif"), recursive=True)

    for tif_path in tif_files:
        qml_ok, qml_msg = link_qml_to_raster(tif_path, master_qml_path)
        if qml_ok:
            success_count += 1
        else:
            fail_count += 1

    return success_count, fail_count

# -----------------------------------------------------------------------------
# Output naming
# -----------------------------------------------------------------------------
def utm_folder_name(zone: int) -> str:
    """Return the per-zone subfolder name, e.g. 'UTM07'."""
    return f"UTM{zone:02d}"

# -----------------------------------------------------------------------------
# Sorting raw lasgrid TIFFs -> Unclipped_Rasters/UTMxx
# -----------------------------------------------------------------------------
def sort_tifs_by_utm(lasgrid_out_dir: str, unclipped_root: str):
    tif_files = glob.glob(os.path.join(lasgrid_out_dir, "*.tif"))
    utm_folders_used = set()

    for tif in tif_files:
        filename = os.path.basename(tif)
        match = UTM_RE.search(filename)
        if not match:
            print(f"Warning: Could not detect UTM zone in {filename}, skipping.")
            continue

        zone = int(match.group(1))
        dest_folder = os.path.join(unclipped_root, utm_folder_name(zone))
        os.makedirs(dest_folder, exist_ok=True)
        utm_folders_used.add(dest_folder)

        dest_path = unique_dest_path(os.path.join(dest_folder, filename))
        shutil.move(tif, dest_path)

    return sorted(utm_folders_used)

# -----------------------------------------------------------------------------
# Worker globals (IMPORTANT: avoids pickling tile_dict every task)
# -----------------------------------------------------------------------------
_WATER_SRC = None
_TILE_DICT = None
_TILING_ROOT = None
_PREP_WATER_DIR = None
_CURRENT_ZONE = None

_INPUT_FILE_MAP = None  # stem(lower) -> full path to .laz
_FAIL_LAZ_ROOT = None   # e.g. C:\...\Density_Results\FAIL
_UNCLIPPED_ROOT = None  # e.g. C:\...\Density_Results\Unclipped_Rasters
_MASTER_QML_PATH = None  # Path to the master QML file for linking


def _match_input_pointcloud_for_tif(tif_filename: str):
    """
    Best-effort match from a lasgrid-produced tif name back to the original .laz file.
    Uses _INPUT_FILE_MAP (stem -> path).
    """
    if not _INPUT_FILE_MAP:
        return None

    stem = Path(tif_filename).stem.lower()

    # 1) direct match
    if stem in _INPUT_FILE_MAP:
        return _INPUT_FILE_MAP[stem]

    # 2) strip common suffixes
    suffixes = [
        "_density", "_point_density", "_pt_density",
        "_grid", "_lasgrid",
        "_last", "_lastreturn", "_last_return", "_last_only",
    ]
    for s in suffixes:
        if stem.endswith(s):
            base = stem[:-len(s)]
            if base in _INPUT_FILE_MAP:
                return _INPUT_FILE_MAP[base]

    # 3) progressively shorten by underscore chunks
    parts = stem.split("_")
    for i in range(len(parts) - 1, 0, -1):
        cand = "_".join(parts[:i])
        if cand in _INPUT_FILE_MAP:
            return _INPUT_FILE_MAP[cand]

    return None

def _close_worker_sources():
    global _WATER_SRC, _TILE_DICT, _CURRENT_ZONE
    try:
        if _WATER_SRC is not None:
            _WATER_SRC.close()
    except Exception:
        pass
    _WATER_SRC = None
    _TILE_DICT = None
    _CURRENT_ZONE = None

def _get_water_gpkg_and_layer_for_zone(prep_water_dir: str, utm_zone: int):
    gpkg_path = os.path.join(prep_water_dir, WATER_GPKG_TEMPLATE.format(zone=utm_zone))
    layer_name = WATER_LAYER_TEMPLATE.format(zone=utm_zone)

    if not os.path.isfile(gpkg_path):
        raise FileNotFoundError(f"Prepared water GPKG not found for UTM{utm_zone}:\n{gpkg_path}")

    layers = fiona.listlayers(gpkg_path)
    if layer_name not in layers:
        if not layers:
            raise RuntimeError(f"No layers found inside:\n{gpkg_path}")
        layer_name = layers[0]

    return gpkg_path, layer_name

def _load_tile_dict_for_zone(tiling_root: str, utm_zone: int) -> dict:
    """
    Returns:
      { tile_key_lower : (geom_geojson, (minx, miny, maxx, maxy)) }
    """
    root = Path(tiling_root)

    gpkg_path = root / f"2500_Tiles_UTM{utm_zone:02d}.gpkg"
    if gpkg_path.is_file():
        expected_layer = f"tiles_utm{utm_zone:02d}"
        layers = fiona.listlayers(str(gpkg_path))
        layer = expected_layer if expected_layer in layers else (layers[0] if layers else None)
        if not layer:
            raise RuntimeError(f"No layers found inside:\n{gpkg_path}")

        src_path = str(gpkg_path)
        src_layer = layer
    else:
        shp_dir = root / f"UTM{utm_zone:02d}"
        if not shp_dir.is_dir():
            raise FileNotFoundError(
                f"Tile data not found for UTM{utm_zone:02d}.\n"
                f"Expected either:\n  {gpkg_path}\nOR\n  {shp_dir}\\*.shp"
            )
        shapefiles = [p for p in shp_dir.iterdir() if p.suffix.lower() == ".shp"]
        if not shapefiles:
            raise FileNotFoundError(f"No shapefile found in:\n{shp_dir}")

        src_path = str(shapefiles[0])
        src_layer = None  # shapefile

    out = {}
    with fiona.open(src_path, layer=src_layer) as src:
        for feat in src:
            props = feat.get("properties") or {}
            tile = props.get("MAP_TILE") or props.get("MAPSHEET")
            if tile is None:
                continue

            key = str(tile).lower()
            geom = feat.get("geometry")
            if not geom:
                continue

            out[key] = (geom, geom_bounds(geom))

    if not out:
        raise RuntimeError(f"No tile features loaded for UTM{utm_zone:02d} from:\n{src_path}")

    return out

def _init_pool(tiling_root: str, prep_water_dir: str, input_file_map: dict, fail_root: str, unclipped_root: str, master_qml_path: str):
    try:
        _import_heavy()  # each worker loads numpy/fiona/rasterio + assigns module globals
    except Exception as e:
        _boot_write(f"=== _init_pool IMPORT FAILED (pid={os.getpid()}): {type(e).__name__}: {e} ===")
        _boot_write(f"  GDAL_DATA={os.environ.get('GDAL_DATA', 'NOT SET')}")
        _boot_write(f"  PROJ_LIB={os.environ.get('PROJ_LIB', 'NOT SET')}")
        traceback.print_exc(file=_safe_log_fh())
        raise

    global _TILING_ROOT, _PREP_WATER_DIR, _INPUT_FILE_MAP, _FAIL_LAZ_ROOT, _UNCLIPPED_ROOT, _MASTER_QML_PATH
    _TILING_ROOT = tiling_root
    _PREP_WATER_DIR = prep_water_dir
    _INPUT_FILE_MAP = input_file_map or {}
    _FAIL_LAZ_ROOT = fail_root
    _UNCLIPPED_ROOT = unclipped_root
    _MASTER_QML_PATH = master_qml_path

    atexit.register(_close_worker_sources)

def _ensure_zone_loaded(zone: int):
    """Lazy-load per-zone resources inside each worker process."""
    global _CURRENT_ZONE, _WATER_SRC, _TILE_DICT

    if _CURRENT_ZONE == zone and _WATER_SRC is not None and _TILE_DICT is not None:
        return

    _close_worker_sources()

    gpkg_path, layer_name = _get_water_gpkg_and_layer_for_zone(_PREP_WATER_DIR, zone)
    _WATER_SRC = fiona.open(gpkg_path, layer=layer_name)
    _TILE_DICT = _load_tile_dict_for_zone(_TILING_ROOT, zone)

    _CURRENT_ZONE = zone

def process_raster_task(args):
    if np is None:
        _import_heavy()
    raster_path, zone, pass_utm_folder, fail_rasters_utm_folder = args
    _ensure_zone_loaded(zone)
    return process_raster(raster_path, pass_utm_folder, fail_rasters_utm_folder)

def _rasterize_water_mask(tile_bounds, out_shape, transform):
    if _WATER_SRC is None:
        return np.zeros(out_shape, dtype=bool)

    shapes = (
        (feat["geometry"], 1)
        for feat in _WATER_SRC.filter(bbox=tile_bounds)
        if feat and feat.get("geometry")
    )

    try:
        water_raster = rasterize(
            shapes,
            out_shape=out_shape,
            transform=transform,
            fill=0,
            dtype="uint8",
        )
        return water_raster.astype(bool)
    except Exception:
        return np.zeros(out_shape, dtype=bool)

# -----------------------------------------------------------------------------
# Core processing (worker)
# -----------------------------------------------------------------------------
def process_raster(raster_path: str, pass_utm_folder: str, fail_rasters_utm_folder: str):
    """
    Writes clipped raster into:
      - pass_utm_folder         (if PASS)
      - fail_rasters_utm_folder (if FAIL)
    Unclipped rasters remain in place (not moved on failure).

    Returns (Filename, Result, Info, Time) for log file.
    """
    t_start = time.perf_counter()
    filename = os.path.basename(raster_path)

    try:
        if os.path.getsize(raster_path) < 1024:
            elapsed = time.perf_counter() - t_start
            return (filename, "SKIP", "File is < 1 KB", f"{elapsed:.2f}s")

        match = UTM_RE.search(filename)
        if not match:
            elapsed = time.perf_counter() - t_start
            return (filename, "SKIP", "Could not find UTM zone in filename", f"{elapsed:.2f}s")

        utm_number = int(match.group(1))
        utm_tag = f"utm{utm_number}"
        if utm_tag not in EPSG_BY_UTM:
            elapsed = time.perf_counter() - t_start
            return (filename, "SKIP", f"Unsupported UTM zone: {utm_number}", f"{elapsed:.2f}s")

        # tile name key (expecting something like: <prefix>_<a>_<b>_<c>_<d>_... .tif)
        parts = filename.split("_")
        if len(parts) < 5:
            elapsed = time.perf_counter() - t_start
            return (filename, "SKIP", "Filename does not match expected tile pattern (needs >= 5 underscore parts)", f"{elapsed:.2f}s")

        tile_key = "".join(parts[1:5]).lower()

        tile_entry = _TILE_DICT.get(tile_key) if _TILE_DICT else None
        if tile_entry is None:
            elapsed = time.perf_counter() - t_start
            return (filename, "SKIP", "No matching tile geometry", f"{elapsed:.2f}s")
        
        with rasterio.open(raster_path) as src:
            data = src.read(1)
            src_transform = src.transform
            src_crs = src.crs
            src_nodata = src.nodata

        # IMPORTANT: density should never be negative.
        if src_nodata is not None:
            data[data == src_nodata] = 0

        # clamp negatives to 0 in-place (no extra array)
        np.maximum(data, 0, out=data)

        # Always assign the known horizontal-only CRS for this UTM zone.
        # Lasgrid sometimes embeds a compound CRS (horizontal + vertical datum)
        # which QGIS can't transform. Density rasters don't need a vertical datum.
        try:
            src_crs = RioCRS.from_epsg(EPSG_BY_UTM[utm_tag])
        except Exception:
            src_crs = RioCRS.from_wkt(_wkt_for_utm(utm_number))

        tile_geom, (minx, miny, maxx, maxy) = tile_entry
        res_x = src_transform.a
        res_y = -src_transform.e if src_transform.e < 0 else src_transform.e
        if res_x == 0 or res_y == 0:
            elapsed = time.perf_counter() - t_start
            return (filename, "ERROR", "Invalid source resolution", f"{elapsed:.2f}s")

        out_width = int(np.ceil((maxx - minx) / res_x))
        out_height = int(np.ceil((maxy - miny) / res_y))
        if out_width <= 0 or out_height <= 0:
            elapsed = time.perf_counter() - t_start
            return (filename, "ERROR", "Computed non-positive output dimensions", f"{elapsed:.2f}s")

        # Snap to the SAME pixel size as the source raster.
        # Using ceil() means this grid may extend slightly past the tile bounds, which is fine
        # because you mask outside the tile to NODATA_VALUE afterward.
        tile_transform = Affine(res_x, 0, minx, 0, -res_y, maxy)


        full_tile_data = np.full((out_height, out_width), NODATA_VALUE, dtype=np.float32)
        reproject(
            source=data,
            destination=full_tile_data,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=tile_transform,
            dst_crs=src_crs,
            resampling=Resampling.nearest,
            dst_nodata=NODATA_VALUE
        )


        tile_bounds = (minx, miny, maxx, maxy)

        water_mask = _rasterize_water_mask(tile_bounds, (out_height, out_width), tile_transform)
        full_tile_data[water_mask] = NODATA_VALUE

        tile_mask = rasterize(
            [(tile_geom, 1)],
            out_shape=(out_height, out_width),
            transform=tile_transform,
            fill=0,
            dtype="uint8"
        ).astype(bool)

        full_tile_data[~tile_mask] = NODATA_VALUE

        # Pixels inside the tile that had no lasgrid coverage are gaps in point
        # cloud data, not "no data".  Treat them as zero density so they count
        # against the pass threshold (e.g. half a tile deleted → FAIL).
        coverage_gap = (full_tile_data == NODATA_VALUE) & tile_mask & ~water_mask
        full_tile_data[coverage_gap] = 0

        final_data = full_tile_data

        total_valid = np.count_nonzero(final_data != NODATA_VALUE)
        count_above = np.count_nonzero(final_data >= DENSITY_THRESHOLD)

        if total_valid == 0:
            # Entire tile is water/NODATA — nothing to evaluate, auto-pass
            pct_above = 0.0
            result = "PASS"
            info = f"0.00 >={DENSITY_THRESHOLD}"
            note = "All water/nodata - auto-pass"
        else:
            pct_above = (count_above / total_valid) * 100
            result = "PASS" if pct_above >= PASS_PERCENT else "FAIL"
            info = f"{pct_above:.2f} >={DENSITY_THRESHOLD}"
            note = ""

        # Output folder selection
        clipped_out_dir = pass_utm_folder if result == "PASS" else fail_rasters_utm_folder
        os.makedirs(clipped_out_dir, exist_ok=True)
        clipped_path = os.path.join(clipped_out_dir, filename)

        profile = {
            "driver": "GTiff",
            "height": out_height,
            "width": out_width,
            "count": 1,
            "dtype": "float32",
            "crs": src_crs,
            "transform": tile_transform,
            "nodata": NODATA_VALUE,
        }
        if GTIFF_COMPRESS:
            profile["compress"] = GTIFF_COMPRESS

        with rasterio.open(clipped_path, "w", **profile) as dst:
            dst.write(final_data, 1)

        # Link QML sidecar for QGIS auto-styling (red < 8.0, green >= 8.0)
        # Uses single master QML file via hard link (or copy fallback)
        try:
            if _MASTER_QML_PATH and os.path.isfile(_MASTER_QML_PATH):
                qml_ok, qml_msg = link_qml_to_raster(
                    tif_path=clipped_path,
                    master_qml_path=_MASTER_QML_PATH
                )
                if not qml_ok:
                    info = info + f" | {qml_msg}"
        except Exception as qml_err:
            info = info + f" | QML_EXCEPTION: {qml_err}"

        if result == "FAIL":
            # Move source LAZ/LAS into FAIL/LAZ_Failed_UTMxx/
            try:
                src_pc = _match_input_pointcloud_for_tif(filename)
                if src_pc and os.path.isfile(src_pc) and _FAIL_LAZ_ROOT:
                    utm_subdir = os.path.join(_FAIL_LAZ_ROOT, f"LAZ_Failed_UTM{_CURRENT_ZONE:02d}")
                    os.makedirs(utm_subdir, exist_ok=True)
                    pc_dest = unique_dest_path(os.path.join(utm_subdir, os.path.basename(src_pc)))
                    shutil.move(src_pc, pc_dest)
                else:
                    info = info + " | PC_NOT_FOUND"
            except Exception as pc_err:
                info = info + f" | PC_MOVE_FAILED: {pc_err}"

        # Move unclipped raster to Unclipped_Pass_UTMxx/ or Unclipped_Fail_UTMxx/
        if _UNCLIPPED_ROOT and os.path.isfile(raster_path):
            try:
                status_tag = "Pass" if result == "PASS" else "Fail"
                unc_dest_dir = os.path.join(_UNCLIPPED_ROOT, f"Unclipped_{status_tag}_UTM{_CURRENT_ZONE:02d}")
                os.makedirs(unc_dest_dir, exist_ok=True)
                unc_dest = unique_dest_path(os.path.join(unc_dest_dir, filename))
                shutil.move(raster_path, unc_dest)
            except Exception as unc_err:
                info = info + f" | UNC_MOVE_FAILED: {unc_err}"

        elapsed = time.perf_counter() - t_start
        return (filename, result, info, f"{elapsed:.2f}s", note)

    except Exception as e:
        elapsed = time.perf_counter() - t_start
        _boot_write("=== ERROR in process_raster ===")
        traceback.print_exc(file=_BOOT_FH)  # logs to boot_<pid>.log for that worker
        return (filename, "ERROR", f"{type(e).__name__}: {e}", f"{elapsed:.2f}s", "")

# -----------------------------------------------------------------------------
# Clipping driver per UTM folder
# -----------------------------------------------------------------------------
def clip_density_grids_parallel(
    cfg: dict,
    unclipped_utm_folder: str,
    pass_utm_folder: str,
    fail_rasters_utm_folder: str,
    input_file_map: dict,
    fail_laz_root: str,
    workers=DEFAULT_WORKERS,
    executor=None
):
    if executor is None:
        raise ValueError("clip_density_grids_parallel() requires an executor when using the shared pool.")

    # Always define counts FIRST so early-returns can safely return ([], counts, [])
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, "ERROR": 0}

    m = UTM_RE.search(os.path.basename(unclipped_utm_folder))
    if not m:
        print(f"Error: Cannot detect UTM zone from folder: {unclipped_utm_folder}")
        return [], counts, []

    zone = int(m.group(1))

    raster_files = sorted(glob.glob(os.path.join(unclipped_utm_folder, "*.tif")))
    if not raster_files:
        print(f"No TIFFs found in {unclipped_utm_folder}, skipping.")
        return [], counts, []

    os.makedirs(pass_utm_folder, exist_ok=True)

    requested_workers = clamp_workers(workers)

    print(f"[UTM{zone:02d}] Clipping {len(raster_files)} rasters (pool={requested_workers}, needed={min(requested_workers, len(raster_files))})")

    tasks = [(p, zone, pass_utm_folder, fail_rasters_utm_folder) for p in raster_files]

    if len(tasks) >= 256:
        chunksize = 16
    elif len(tasks) >= 64:
        chunksize = 8
    else:
        chunksize = 4

    fail_only = []
    all_results = []

    for row in executor.map(process_raster_task, tasks, chunksize=chunksize):
        filename, result, info, elapsed, note = row
        counts[result] = counts.get(result, 0) + 1

        all_results.append((zone, filename, result, info, elapsed, note))

        if result != "PASS":
            print(f"{filename} | {result} | {elapsed} | {info}")

        if result == "FAIL":
            pct = info.split()[0] if info else ""
            fail_only.append((f"UTM{zone:02d}", filename, result, pct, elapsed, note))

    return fail_only, counts, all_results

# -----------------------------------------------------------------------------
# Run density check (main pipeline)
# -----------------------------------------------------------------------------
def run_density_check(cfg: dict, input_dir, custom_output_dir=None, workers=DEFAULT_WORKERS):
    from tkinter import messagebox

    try:
        _import_heavy()
    except Exception as e:
        _boot_write("=== HEAVY IMPORT FAILED (main) ===")
        _log_exception("=== HEAVY IMPORT FAILED (main) ===")
        messagebox.showerror(
            "Startup Error",
            "Failed to load required GIS libraries (numpy/rasterio/fiona).\n\n"
            f"Details: {type(e).__name__}: {e}\n\n"
            "See app_debug.log / boot_*.log in:\n"
            f"{_config_dir()}"
        )
        return
    # --- validate packaged assets + inputs BEFORE running anything ---
    try:
        assert_required_assets(cfg)
    except Exception as e:
        messagebox.showerror("Missing Data", str(e))
        return

    if not input_dir or not Path(input_dir).is_dir():
        messagebox.showwarning("Missing Input", "Please select an input directory.")
        return

    lasgrid_exe = cfg.get("lasgrid_exe", ORG_LASGRID_DEFAULT)
    if not os.path.isfile(lasgrid_exe):
        messagebox.showerror(
            "Missing LAStools",
            f"lasgrid64.exe not found:\n{lasgrid_exe}\n\n"
            "Open Settings and set the correct path, or Reset it."
        )
        return

    workers = clamp_workers(workers)
    t0 = time.perf_counter()

    base_out = custom_output_dir if custom_output_dir else input_dir
    output_root = os.path.join(base_out, "Density_Results")
    os.makedirs(output_root, exist_ok=True)

    unclipped_root = os.path.join(output_root, "Unclipped_Rasters")
    pass_root = os.path.join(output_root, "PASS")
    fail_root = os.path.join(output_root, "FAIL")
    # Zone-specific folders created on-demand: Raster_Failed_UTMxx, LAZ_Failed_UTMxx
    os.makedirs(unclipped_root, exist_ok=True)
    os.makedirs(pass_root, exist_ok=True)
    # fail_root subdirs created on-demand by workers

    # Misc files go into _internal (users don't need to see these)
    internal_root = os.path.join(output_root, "_internal")
    lasgrid_out = os.path.join(internal_root, "_lasgrid_out")
    os.makedirs(lasgrid_out, exist_ok=True)

    input_files = sorted(glob.glob(os.path.join(input_dir, "*.laz")))
    if not input_files:
        messagebox.showerror("Error", "No .laz files found in the input directory.")
        return

    # Map: input stem -> full path
    input_file_map = {}
    for p in input_files:
        stem = Path(p).stem.lower()
        input_file_map[stem] = p

    # We'll accumulate all FAIL rows across all zones here
    all_failed = []
    # Accumulate ALL results across zones for combined CSV
    all_zone_results = []


    try:
        file_list_path = os.path.join(lasgrid_out, "lasgrid_input_files.txt")
        with open(file_list_path, "w", encoding="utf-8") as f:
            f.write("\n".join(input_files))

        command = [
            lasgrid_exe,
            "-point_density",
            "-cores", str(workers),
            "-last_only",
            "-step", "5",
            "-no_kml",
            "-no_world_file",
            "-otif",
            "-odir", lasgrid_out,
            "-lof", file_list_path
        ]

        print(f"Running lasgrid64 on {len(input_files)} files with {workers} cores...")
        log_path = os.path.join(lasgrid_out, "lasgrid64_log.txt")
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
            log_file.write("COMMAND:\n" + " ".join(command) + "\n\n")
            proc = subprocess.run(
                command,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        if proc.returncode != 0:
            raise RuntimeError(f"lasgrid64 failed (returncode {proc.returncode}). See:\n{log_path}")

        t1 = time.perf_counter()
        print(f"[TIMING] lasgrid: {t1 - t0:.2f}s")

        tifs_now = glob.glob(os.path.join(lasgrid_out, "*.tif"))
        if not tifs_now:
            raise RuntimeError(f"lasgrid produced no .tif files in:\n{lasgrid_out}\nSee:\n{log_path}")


        # Record old TIFs BEFORE sorting, so we can safely clean them up AFTER
        old_tifs = set()
        for old_utm_dir in glob.glob(os.path.join(unclipped_root, "*UTM*")):
            for old_tif in glob.glob(os.path.join(old_utm_dir, "*.tif")):
                old_tifs.add(old_tif)

        # Sort into temp UTMxx folders first (workers will move to Pass/Fail folders)
        print("Sorting TIFFs into temp folders for processing...")
        unclipped_utm_folders = sort_tifs_by_utm(lasgrid_out, unclipped_root)

        # Clean only the old TIFs from previous runs (new ones are safely in place)
        for old_tif in old_tifs:
            try:
                os.remove(old_tif)
            except Exception:
                pass
        t3 = time.perf_counter()
        print(f"[TIMING] sort_tifs: {t3 - t1:.2f}s")

        # optional cleanup: leave the log + input list, but remove leftover .tifs from _lasgrid_out
        for f in glob.glob(os.path.join(lasgrid_out, "*.tif")):
            try:
                os.remove(f)
            except Exception:
                pass

        # ---- clipping pool timing ----
        t4 = time.perf_counter()

        totals = {"PASS": 0, "FAIL": 0, "SKIP": 0, "ERROR": 0}
        errors_encountered = []

        # Create ONE master QML file for all rasters (workers will link to it)
        print("Creating master QML style file...")
        try:
            master_qml_path = create_master_qml(
                output_root=output_root,
                threshold=float(DENSITY_THRESHOLD),
                nodata_value=NODATA_VALUE
            )
            print(f"Master QML: {master_qml_path}")
        except Exception as e:
            error_msg = f"Failed to create master QML: {type(e).__name__}: {e}"
            errors_encountered.append(error_msg)
            print(f"ERROR: {error_msg}")
            master_qml_path = None

        # Determine if single zone (no subfolders needed for PASS)
        single_zone = len(unclipped_utm_folders) == 1

        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_pool,
            initargs=(cfg["tiling_scheme_root"], cfg["prep_water_gpkg_dir"], input_file_map, fail_root, unclipped_root, master_qml_path),
        ) as executor:
            t5 = time.perf_counter()
            print(f"[TIMING] pool_startup: {t5 - t4:.2f}s")

            for unclipped_utm in unclipped_utm_folders:
                m = UTM_RE.search(os.path.basename(unclipped_utm))
                if not m:
                    continue
                zone = int(m.group(1))
                # PASS: files directly in PASS/ if single zone, else PASS_UTMxx/
                pass_utm = pass_root if single_zone else os.path.join(pass_root, f"PASS_UTM{zone:02d}")
                # FAIL: Raster_Failed_UTMxx/ directly in FAIL/
                fail_rasters_utm = os.path.join(fail_root, f"Raster_Failed_UTM{zone:02d}")

                try:
                    failed_rows, zone_counts, zone_results = clip_density_grids_parallel(
                        cfg, unclipped_utm, pass_utm, fail_rasters_utm,
                        input_file_map, fail_root,
                        workers=workers,
                        executor=executor
                    )

                    # accumulate fails
                    if failed_rows:
                        all_failed.extend(failed_rows)

                    # accumulate ALL results for combined CSV
                    if zone_results:
                        all_zone_results.extend(zone_results)

                    # accumulate counts
                    for k, v in zone_counts.items():
                        totals[k] = totals.get(k, 0) + v

                except Exception as e:
                    error_msg = f"UTM{zone:02d} clipping failed: {type(e).__name__}: {e}"
                    errors_encountered.append(error_msg)
                    print(f"ERROR: {error_msg}")

            t6 = time.perf_counter()
            print(f"[TIMING] clipping_total: {t6 - t5:.2f}s")

        # Clean up empty temp UTMxx folders (files were moved to Pass/Fail folders)
        for temp_utm_dir in unclipped_utm_folders:
            try:
                if os.path.isdir(temp_utm_dir) and not os.listdir(temp_utm_dir):
                    os.rmdir(temp_utm_dir)
            except Exception:
                pass

        # ---- Write combined density_results.csv ----
        if all_zone_results:
            combined_csv_path = os.path.join(output_root, "density_results.csv")
            try:
                with open(combined_csv_path, "w", newline="", encoding="utf-8") as cf:
                    cw = csv.writer(cf)
                    cw.writerow(["UTM_Zone", "Filename", "Result", "Pct_Above_8", "Time", "Notes"])
                    for z, fn, res, info, elapsed, note in all_zone_results:
                        pct = info.split()[0] if info else ""
                        cw.writerow([f"UTM{z:02d}", fn, res, pct, elapsed, note])
                print(f"Combined results CSV: {combined_csv_path}")
            except Exception as csv_err:
                print(f"Warning: Failed to write combined results CSV: {csv_err}")

        # ---- Link QML to all output directories ----
        if master_qml_path:
            print("Linking QML styles to output rasters...")
            try:
                unc_ok, unc_fail = link_qml_to_directory(unclipped_root, master_qml_path)
                pass_ok, pass_fail_qml = link_qml_to_directory(pass_root, master_qml_path)
                fail_ok, fail_fail_qml = link_qml_to_directory(fail_root, master_qml_path)
                total_ok = unc_ok + pass_ok + fail_ok
                total_fail_qml = unc_fail + pass_fail_qml + fail_fail_qml
                if total_ok > 0:
                    print(f"Linked QML to {total_ok} rasters (unclipped={unc_ok}, pass={pass_ok}, fail={fail_ok})")
                if total_fail_qml > 0:
                    warn_msg = f"Failed to link QML to {total_fail_qml} rasters"
                    errors_encountered.append(warn_msg)
                    print(f"Warning: {warn_msg}")
            except Exception as e:
                error_msg = f"QML linking failed: {type(e).__name__}: {e}"
                errors_encountered.append(error_msg)
                print(f"ERROR: {error_msg}")

        t7 = time.perf_counter()
        print(f"[TIMING] total: {t7 - t0:.2f}s")

        # ---- Write pipeline summary log ----
        log_path = os.path.join(output_root, "density_check_log.txt")
        try:
            with open(log_path, "w", encoding="utf-8") as log_file:
                log_file.write("=" * 80 + "\n")
                log_file.write("DENSITY CHECK PIPELINE LOG\n")
                log_file.write("=" * 80 + "\n\n")

                log_file.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                log_file.write(f"Input Directory: {input_dir}\n")
                log_file.write(f"Output Directory: {output_root}\n")
                log_file.write(f"Workers: {workers}\n")
                log_file.write(f"Input Files: {len(input_files)} .laz files\n\n")

                log_file.write("=" * 80 + "\n")
                log_file.write("CONFIGURATION\n")
                log_file.write("=" * 80 + "\n\n")
                log_file.write(f"Executable: {sys.executable}\n")
                log_file.write(f"Frozen: {getattr(sys, 'frozen', False)}\n")
                _gdal = os.environ.get('GDAL_DATA', 'NOT SET')
                _proj = os.environ.get('PROJ_LIB', 'NOT SET')
                _projd = os.environ.get('PROJ_DATA', 'NOT SET')
                log_file.write(f"GDAL_DATA: {_gdal}\n")
                log_file.write(f"PROJ_LIB: {_proj}\n")
                log_file.write(f"PROJ_DATA: {_projd}\n")
                _tiling = cfg.get("tiling_scheme_root", "")
                _water = cfg.get("prep_water_gpkg_dir", "")
                log_file.write(f"Tiling Scheme: {_tiling} (exists={Path(_tiling).is_dir() if _tiling else False})\n")
                log_file.write(f"Water Data: {_water} (exists={Path(_water).is_dir() if _water else False})\n")
                log_file.write(f"App Version: {APP_VERSION}\n\n")

                # PROJ diagnostics
                log_file.write("=" * 80 + "\n")
                log_file.write("PROJ / GDAL DIAGNOSTICS\n")
                log_file.write("=" * 80 + "\n\n")
                try:
                    _proj_db = Path(os.environ.get('PROJ_LIB', '')) / 'proj.db'
                    log_file.write(f"proj.db path: {_proj_db}\n")
                    log_file.write(f"proj.db exists: {_proj_db.is_file()}\n")
                    if _proj_db.is_file():
                        import sqlite3 as _sq
                        _conn = _sq.connect(str(_proj_db))
                        for _k, _v in _conn.execute(
                            "SELECT key, value FROM metadata "
                            "WHERE key LIKE 'DATABASE.LAYOUT.VERSION%'"
                        ).fetchall():
                            log_file.write(f"proj.db {_k} = {_v}\n")
                        _conn.close()
                    # Test CRS creation for all BC zones
                    for _epsg, _name in [(2955, "UTM11"), (3157, "UTM10"),
                                         (3156, "UTM9"), (3155, "UTM8"), (3154, "UTM7")]:
                        try:
                            RioCRS.from_epsg(_epsg)
                            log_file.write(f"EPSG:{_epsg} ({_name}): OK\n")
                        except Exception as _crs_err:
                            log_file.write(f"EPSG:{_epsg} ({_name}): FAILED — {_crs_err}\n")
                            log_file.write(f"  WKT fallback available: {_epsg in [2955,3157,3156,3155,3154]}\n")
                    log_file.write(f"rasterio version: {rasterio.__version__}\n")
                except Exception as _diag_err:
                    log_file.write(f"Diagnostics error: {_diag_err}\n")
                log_file.write("\n")

                log_file.write("=" * 80 + "\n")
                log_file.write("PIPELINE STAGES\n")
                log_file.write("=" * 80 + "\n\n")

                log_file.write(f"1. lasgrid (density grid generation):\n")
                log_file.write(f"   Duration: {t1 - t0:.2f}s\n")
                log_file.write(f"   Output: {len(tifs_now)} .tif files generated\n\n")

                log_file.write(f"2. Sorting TIFFs by UTM zone:\n")
                log_file.write(f"   Duration: {t3 - t1:.2f}s\n")
                log_file.write(f"   UTM folders: {len(unclipped_utm_folders)}\n\n")

                log_file.write(f"3. QML master file creation:\n")
                log_file.write(f"   Duration: {t5 - t4:.2f}s\n")
                log_file.write(f"   Master QML: {master_qml_path if master_qml_path else 'FAILED'}\n\n")

                log_file.write(f"4. Water clipping and QA:\n")
                log_file.write(f"   Duration: {t6 - t5:.2f}s\n")
                log_file.write(f"   PASS: {totals.get('PASS', 0)}\n")
                log_file.write(f"   FAIL: {totals.get('FAIL', 0)}\n")
                log_file.write(f"   SKIP: {totals.get('SKIP', 0)}\n")
                log_file.write(f"   ERROR: {totals.get('ERROR', 0)}\n\n")

                log_file.write(f"5. QML linking to unclipped tiles:\n")
                log_file.write(f"   Duration: {t7 - t6:.2f}s\n\n")

                log_file.write("=" * 80 + "\n")
                log_file.write("SUMMARY\n")
                log_file.write("=" * 80 + "\n\n")

                log_file.write(f"Total Duration: {t7 - t0:.2f}s\n")
                log_file.write(f"Total Tiles Processed: {sum(totals.values())}\n")
                log_file.write(f"Pass Rate: {totals.get('PASS', 0) / max(1, sum(totals.values())) * 100:.1f}%\n\n")

                if errors_encountered:
                    log_file.write("=" * 80 + "\n")
                    log_file.write("ERRORS ENCOUNTERED\n")
                    log_file.write("=" * 80 + "\n\n")
                    for i, error in enumerate(errors_encountered, 1):
                        log_file.write(f"{i}. {error}\n")
                    log_file.write("\n")

                log_file.write("=" * 80 + "\n")
                log_file.write("OUTPUT LOCATIONS\n")
                log_file.write("=" * 80 + "\n\n")
                log_file.write(f"Unclipped rasters: {unclipped_root}\n")
                log_file.write(f"  (Unclipped_Pass_UTMxx/ and Unclipped_Fail_UTMxx/ subfolders)\n")
                log_file.write(f"Clipped passing rasters: {pass_root}\n")
                log_file.write(f"Combined results CSV: {os.path.join(output_root, 'density_results.csv')}\n")
                if totals.get('FAIL', 0) > 0:
                    log_file.write(f"Failed folder: {fail_root}\n")
                    log_file.write(f"  (Raster_Failed_UTMxx/ and LAZ_Failed_UTMxx/ subfolders)\n")
                    log_file.write(f"Failed tiles CSV: {os.path.join(fail_root, 'failed_tiles.csv')}\n")
                log_file.write(f"Master QML style: {master_qml_path if master_qml_path else 'N/A'}\n")
                log_file.write("\n")

            print(f"Pipeline log written to: {log_path}")
        except Exception as e:
            print(f"Warning: Failed to write pipeline log: {e}")

        # ---- after ALL zones ----
        pass_n = totals.get("PASS", 0)
        fail_n = totals.get("FAIL", 0)
        skip_n = totals.get("SKIP", 0)
        err_n  = totals.get("ERROR", 0)

        # Write failed_tiles.csv if there were FAIL tiles
        if fail_n > 0:
            os.makedirs(fail_root, exist_ok=True)
            failed_csv = os.path.join(fail_root, "failed_tiles.csv")
            with open(failed_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["UTM_Zone", "Filename", "Result", "Pct_Above_8", "Time", "Notes"])
                w.writerows(all_failed)

        # Build a cleaner summary: only show non-zero categories (always show PASS)
        lines = [f"PASS: {pass_n}"]
        if fail_n:
            lines.append(f"FAIL: {fail_n}")
        if skip_n:
            lines.append(f"SKIP: {skip_n}")
        if err_n:
            lines.append(f"ERROR: {err_n}")
        summary = "\n".join(lines)

        # Only show the SKIP / ERROR dialogs if those actually happened
        # Precedence: ERRORs > FAILs > SKIPs > All Passed
        if err_n > 0:
            messagebox.showwarning("Done (with errors)", "Some rasters errored.\n\n" + summary)
        elif fail_n > 0:
            messagebox.showwarning("Done (with fails)", "Some tiles failed :( \n\n" + summary)
        elif skip_n > 0:
            messagebox.showwarning("Done (with skips)", "Some rasters were skipped.\n\n" + summary)
        else:
            messagebox.showinfo("Done", "All Passed\n\n" + summary)

    except Exception as e:
        _log_exception("=== ERROR (main) ===")
        messagebox.showerror("Error", str(e))


def launch_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    # -----------------------------------------------------------------------------
    # Settings UI
    # -----------------------------------------------------------------------------
    class SettingsWindow(tk.Toplevel):
        def __init__(self, master, cfg: dict, on_save_callback):
            super().__init__(master)
            apply_window_icon(self)
            self.title("Settings")
            self.resizable(False, False)
            self.configure(bg=BG_MAIN, padx=15, pady=15)

            self.cfg = cfg
            self.on_save_callback = on_save_callback
            self.protocol("WM_DELETE_WINDOW", self.cancel)

            self.lasgrid_var = tk.StringVar(value=self.cfg.get("lasgrid_exe", ORG_LASGRID_DEFAULT))
            self.tiling_var  = tk.StringVar(value=self.cfg.get("tiling_scheme_root", PACKAGED_TILING_DEFAULT))
            self.water_var   = tk.StringVar(value=self.cfg.get("prep_water_gpkg_dir", PACKAGED_WATER_DEFAULT))

            row = 0

            # LAStools
            tk.Label(self, text="LAStools lasgrid64.exe:", bg=BG_MAIN, anchor='w').grid(
                row=row, column=0, sticky='w', pady=(0, 3))
            row += 1
            tk.Entry(self, textvariable=self.lasgrid_var, width=70).grid(
                row=row, column=0, pady=(0, 3), sticky='ew')
            row += 1
            btn_frame = tk.Frame(self, bg=BG_MAIN)
            btn_frame.grid(row=row, column=0, sticky='ew', pady=(0, 15))
            tk.Button(btn_frame, text="Browse", command=self.browse_lasgrid, width=10).pack(side='left')
            tk.Button(btn_frame, text="Reset", command=self.reset_lasgrid, width=10).pack(side='right')
            row += 1

            # Tiling
            tk.Label(self, text="Tiling Scheme (Tiles_by_UTM):", bg=BG_MAIN, anchor='w').grid(
                row=row, column=0, sticky='w', pady=(0, 3))
            row += 1
            tk.Entry(self, textvariable=self.tiling_var, width=70).grid(
                row=row, column=0, pady=(0, 3), sticky='ew')
            row += 1
            btn_frame = tk.Frame(self, bg=BG_MAIN)
            btn_frame.grid(row=row, column=0, sticky='ew', pady=(0, 15))
            tk.Button(btn_frame, text="Browse", command=self.browse_tiling, width=10).pack(side='left')
            tk.Button(btn_frame, text="Reset", command=self.reset_tiling, width=10).pack(side='right')
            row += 1

            # Water
            tk.Label(self, text="Water Folder (Water_by_UTM):", bg=BG_MAIN, anchor='w').grid(
                row=row, column=0, sticky='w', pady=(0, 3))
            row += 1
            tk.Entry(self, textvariable=self.water_var, width=70).grid(
                row=row, column=0, pady=(0, 3), sticky='ew')
            row += 1
            btn_frame = tk.Frame(self, bg=BG_MAIN)
            btn_frame.grid(row=row, column=0, sticky='ew', pady=(0, 20))
            tk.Button(btn_frame, text="Browse", command=self.browse_water, width=10).pack(side='left')
            tk.Button(btn_frame, text="Reset", command=self.reset_water, width=10).pack(side='right')
            row += 1

            # Buttons
            btn_frame2 = tk.Frame(self, bg=BG_MAIN)
            btn_frame2.grid(row=row, column=0)
            tk.Button(btn_frame2, text="Save", command=self.save, width=12, bg='#2E7D32', fg='white').pack(side='left', padx=(0, 5))
            tk.Button(btn_frame2, text="Cancel", command=self.cancel, width=12).pack(side='left')

        def browse_lasgrid(self):
            path = filedialog.askopenfilename(
                title="Select lasgrid64.exe",
                filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
            )
            if path:
                self.lasgrid_var.set(path)

        def browse_tiling(self):
            folder = filedialog.askdirectory(title="Select Tiles_By_UTM folder")
            if folder:
                self.tiling_var.set(folder)

        def browse_water(self):
            folder = filedialog.askdirectory(title="Select Water_by_UTM folder")
            if folder:
                self.water_var.set(folder)

        def reset_lasgrid(self):
            self.lasgrid_var.set(ORG_LASGRID_DEFAULT)

        def reset_tiling(self):
            self.tiling_var.set(PACKAGED_TILING_DEFAULT)

        def reset_water(self):
            self.water_var.set(PACKAGED_WATER_DEFAULT)

        def cancel(self):
            self.destroy()

        def save(self):
            las = self.lasgrid_var.get().strip()
            til = self.tiling_var.get().strip()
            wat = self.water_var.get().strip()

            if not las or not os.path.isfile(las):
                messagebox.showerror("Invalid Path", f"lasgrid64.exe not found:\n{las}")
                return
            if not til or not Path(til).is_dir():
                messagebox.showerror("Invalid Path", f"Tiling folder not found:\n{til}")
                return
            if not wat or not Path(wat).is_dir():
                messagebox.showerror("Invalid Path", f"Prepared water folder not found:\n{wat}")
                return

            self.cfg["lasgrid_exe"] = las
            self.cfg["tiling_scheme_root"] = til
            self.cfg["prep_water_gpkg_dir"] = wat

            try:
                save_config(self.cfg)
                messagebox.showinfo("Success", "Settings saved successfully!")
            except Exception as e:
                messagebox.showerror("Save Failed", str(e))
                return

            if self.on_save_callback:
                self.on_save_callback(self.cfg)

            self.destroy()

    # -----------------------------------------------------------------------------
    # Main GUI
    # -----------------------------------------------------------------------------
    class DensityCheckApp:
        def __init__(self, master):
            self.master = master
            self.master.title("Last Return Density Checker")
            self.master.configure(bg=BG_MAIN, padx=15, pady=15)

            self.cfg = load_config()

            # Menu bar
            menubar = tk.Menu(master)
            settings_menu = tk.Menu(menubar, tearoff=0)
            settings_menu.add_command(label="Settings", command=self.open_settings)
            menubar.add_cascade(label="Settings", menu=settings_menu)
            master.config(menu=menubar)

            self.input_dir = tk.StringVar()
            self.output_dir = tk.StringVar()
            self.use_custom_output = tk.BooleanVar()

            # Input
            tk.Label(master, text="Input Directory:", bg=BG_MAIN).pack(anchor='w', pady=(0, 3))

            input_frame = tk.Frame(master, bg=BG_MAIN)
            input_frame.pack(fill='x', pady=(0, 10))
            tk.Entry(input_frame, textvariable=self.input_dir, width=55).pack(side='left', fill='x', expand=True)
            tk.Button(input_frame, text="Browse", command=self.browse_input_directory, width=10).pack(side='left', padx=(5, 0))

            # Custom output checkbox
            tk.Checkbutton(master, text="Use custom output directory", variable=self.use_custom_output,
                          command=self.toggle_output_dir, bg=BG_MAIN).pack(anchor='w', pady=(0, 3))

            # Output
            output_frame = tk.Frame(master, bg=BG_MAIN)
            output_frame.pack(fill='x', pady=(0, 15))
            self.output_entry = tk.Entry(output_frame, textvariable=self.output_dir, width=55, state='disabled')
            self.output_entry.pack(side='left', fill='x', expand=True)
            self.output_browse_btn = tk.Button(output_frame, text="Browse", command=self.browse_output_directory,
                                              width=10, state='disabled')
            self.output_browse_btn.pack(side='left', padx=(5, 0))

            # Workers
            workers_frame = tk.Frame(master, bg=BG_MAIN)
            workers_frame.pack(anchor='w', pady=(0, 15))
            tk.Label(workers_frame, text="CPU Cores:", bg=BG_MAIN).pack(side='left', padx=(0, 5))
            self.workers = tk.IntVar(value=DEFAULT_WORKERS)
            tk.Spinbox(workers_frame, from_=1, to=WORKERS_CAP, textvariable=self.workers, width=8).pack(side='left', padx=(0, 10))
            tk.Label(workers_frame, text=f"(1-{WORKERS_CAP})", bg=BG_MAIN, fg='#666').pack(side='left')

            # Run button + version label on same row
            run_frame = tk.Frame(master, bg=BG_MAIN)
            run_frame.pack(fill='x', pady=(5, 0))
            self.run_btn = tk.Button(run_frame, text="Run Density Check", command=self.start_density_check,
                                    bg='#2E7D32', fg='white', width=25, height=2)
            self.run_btn.pack(side='left', expand=True)
            tk.Label(run_frame, text=f"v{APP_VERSION}", bg=BG_MAIN, fg='#999',
                     font=("Segoe UI", 7)).pack(side='right', anchor='s')

        def open_settings(self):
            SettingsWindow(self.master, dict(self.cfg), self._on_settings_saved)

        def _on_settings_saved(self, new_cfg: dict):
            self.cfg = new_cfg

        def browse_input_directory(self):
            folder = filedialog.askdirectory(title="Select Input Directory with .laz files")
            if folder:
                self.input_dir.set(folder)

        def toggle_output_dir(self):
            if self.use_custom_output.get():
                self.output_entry.config(state='normal')
                self.output_browse_btn.config(state='normal')
            else:
                self.output_entry.config(state='disabled')
                self.output_browse_btn.config(state='disabled')

        def browse_output_directory(self):
            folder = filedialog.askdirectory(title="Select Output Directory")
            if folder:
                self.output_dir.set(folder)

        def start_density_check(self):
            self.run_btn.config(state='disabled', text='Processing...')
            self.master.update()

            input_path = self.input_dir.get().strip()
            output_path = self.output_dir.get().strip() if self.use_custom_output.get() else None
            workers = int(self.workers.get())

            print(f"[RUN] exe={getattr(sys, 'frozen', False)}")
            print(f"[RUN] sys.executable={sys.executable}")
            print(f"[RUN] sys.version={sys.version}")
            print(f"[RUN] workers={workers}")
            print(f"[RUN] input={input_path}")
            print(f"[RUN] output={(output_path or input_path)}")

            def _run():
                try:
                    run_density_check(
                        cfg=self.cfg,
                        input_dir=input_path,
                        custom_output_dir=output_path,
                        workers=workers
                    )
                finally:
                    self.master.after(0, lambda: self.run_btn.config(state='normal', text='Run Density Check'))

            threading.Thread(target=_run, daemon=True).start()

    root = tk.Tk()
    apply_window_icon(root)
    app = DensityCheckApp(root)
    root.mainloop()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    _t("__main__ entered")

    try:
        log_path = setup_logging()
        _t("after setup_logging")
        print(f"[LOG] {log_path}")
        try:
            if _BOOT_FH is not None and not getattr(_BOOT_FH, "closed", False):
                _BOOT_FH.flush()
                _BOOT_FH.close()
        except Exception:
            pass
        _BOOT_FH = None

    except Exception:
        _t("setup_logging FAILED")
        pass
    launch_gui()