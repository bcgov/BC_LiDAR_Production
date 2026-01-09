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

class _TeeToFile:
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

    tee = _TeeToFile(log_file)

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
from_bounds = None
RioCRS = None
Affine = None

def _import_heavy():
    global np, fiona, rasterio, rasterize, geom_bounds, reproject, Resampling
    global from_bounds, RioCRS, Affine  # <-- ADD THIS

    if np is not None and RioCRS is not None and Affine is not None:
        return


    import numpy as _np
    import fiona as _fiona
    import rasterio as _rasterio
    from rasterio.features import rasterize as _rasterize, bounds as _geom_bounds
    from rasterio.warp import reproject as _reproject, Resampling as _Resampling
    from rasterio.transform import from_bounds as _from_bounds, Affine as _Affine
    from rasterio.crs import CRS as _RioCRS

    np = _np
    fiona = _fiona
    rasterio = _rasterio
    rasterize = _rasterize
    geom_bounds = _geom_bounds
    reproject = _reproject
    Resampling = _Resampling
    from_bounds = _from_bounds
    RioCRS = _RioCRS
    Affine = _Affine

# -----------------------------------------------------------------------------
# UI colors
# -----------------------------------------------------------------------------
BG_MAIN = "#f0f0f0"
BG_BAR  = "#d9d9d9"

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
WATER_GPKG_TEMPLATE = "Water_UTM{zone:02d}_buf50m_tilebbox.gpkg"
WATER_LAYER_TEMPLATE = "water_utm{zone:02d}_buf50m"
NODATA_VALUE = -9999

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
# Output naming
# -----------------------------------------------------------------------------
def utm_folder_name(zone: int, kind: str) -> str:
    if kind.lower() == "clipped":
        return f"UTM{zone:02d}_Clipped"
    return f"UTM{zone:02d}_Unclipped"

# -----------------------------------------------------------------------------
# Sorting raw lasgrid TIFFs -> Unclipped/UTMxx_Unclipped
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
        dest_folder = os.path.join(unclipped_root, utm_folder_name(zone, "Unclipped"))
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
_WORKER_ZONE = None
_TILING_ROOT = None
_PREP_WATER_DIR = None
_CURRENT_ZONE = None

_INPUT_FILE_MAP = None  # stem(lower) -> full path to .laz/.las
_FAIL_LAZ_ROOT = None   # e.g. C:\...\input\LAZ_Density_Fail


def _match_input_pointcloud_for_tif(tif_filename: str):
    """
    Best-effort match from a lasgrid-produced tif name back to the original .laz/.las.
    Uses _INPUT_FILE_MAP (stem -> path).
    """
    global _INPUT_FILE_MAP
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

def _init_pool(tiling_root: str, prep_water_dir: str, input_file_map: dict, fail_laz_root: str):
    _import_heavy()  # each worker loads numpy/fiona/rasterio + assigns module globals

    global _TILING_ROOT, _PREP_WATER_DIR, _INPUT_FILE_MAP, _FAIL_LAZ_ROOT
    _TILING_ROOT = tiling_root
    _PREP_WATER_DIR = prep_water_dir
    _INPUT_FILE_MAP = input_file_map or {}
    _FAIL_LAZ_ROOT = fail_laz_root

    atexit.register(_close_worker_sources)

def _ensure_zone_loaded(zone: int):
    """Lazy-load per-zone resources inside each worker process."""
    global _CURRENT_ZONE, _WATER_SRC, _TILE_DICT, _WORKER_ZONE

    if _CURRENT_ZONE == zone and _WATER_SRC is not None and _TILE_DICT is not None:
        _WORKER_ZONE = zone
        return

    _close_worker_sources()

    gpkg_path, layer_name = _get_water_gpkg_and_layer_for_zone(_PREP_WATER_DIR, zone)
    _WATER_SRC = fiona.open(gpkg_path, layer=layer_name)
    _TILE_DICT = _load_tile_dict_for_zone(_TILING_ROOT, zone)

    _CURRENT_ZONE = zone
    _WORKER_ZONE = zone

def process_raster_task(args):
    if np is None:
        _import_heavy()
    raster_path, zone, clipped_utm_folder, unclipped_utm_folder = args
    _ensure_zone_loaded(zone)
    return process_raster(raster_path, clipped_utm_folder, unclipped_utm_folder)

def _rasterize_water_mask(tile_bounds, out_shape, transform):
    global _WATER_SRC
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
def process_raster(raster_path: str, clipped_utm_folder: str, unclipped_utm_folder: str):
    """
    Writes clipped raster into:
      - clipped_utm_folder (PASS)
      - clipped_utm_folder/FAIL (FAIL)
    Moves original unclipped raster into:
      - unclipped_utm_folder/FAIL (only if FAIL)

    Returns (Filename, Result, Info) for CSV.
    """
    global _TILE_DICT

    filename = os.path.basename(raster_path)

    if RioCRS is None or Affine is None or rasterio is None or fiona is None:
        try:
            _import_heavy()
        except Exception:
            pass
        if RioCRS is None or Affine is None or rasterio is None or fiona is None:
            return (filename, "ERROR", f"heavy not ready after import: RioCRS={RioCRS} Affine={Affine} rasterio={rasterio} fiona={fiona}")

    try:
        if os.path.getsize(raster_path) < 1024:
            return (filename, "SKIP", "File is < 1 KB")

        match = UTM_RE.search(filename)
        if not match:
            return (filename, "SKIP", "Could not find UTM zone in filename")

        utm_number = int(match.group(1))
        utm_tag = f"utm{utm_number}"
        if utm_tag not in EPSG_BY_UTM:
            return (filename, "SKIP", f"Unsupported UTM zone: {utm_number}")

        # tile name key (expecting something like: <prefix>_<a>_<b>_<c>_<d>_... .tif)
        parts = filename.split("_")
        if len(parts) < 5:
            return (filename, "SKIP", "Filename does not match expected tile pattern (needs >= 5 underscore parts)")

        tile_key = "".join(parts[1:5]).lower()

        tile_entry = _TILE_DICT.get(tile_key) if _TILE_DICT else None
        if tile_entry is None:
            return (filename, "SKIP", "No matching tile geometry")
        
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


        # We've normalized away nodata; do NOT tell reproject() to treat any value as nodata now.
        src_nodata = None

        if src_crs is None:
            src_crs = RioCRS.from_epsg(EPSG_BY_UTM[utm_tag])

        tile_geom, (minx, miny, maxx, maxy) = tile_entry
        res_x = src_transform.a
        res_y = -src_transform.e if src_transform.e < 0 else src_transform.e
        if res_x == 0 or res_y == 0:
            return (filename, "ERROR", "Invalid source resolution")

        out_width = int(np.ceil((maxx - minx) / res_x))
        out_height = int(np.ceil((maxy - miny) / res_y))
        if out_width <= 0 or out_height <= 0:
            return (filename, "ERROR", "Computed non-positive output dimensions")

        # Snap to the SAME pixel size as the source raster.
        # Using ceil() means this grid may extend slightly past the tile bounds, which is fine
        # because you mask outside the tile to NODATA_VALUE afterward.
        tile_transform = Affine(res_x, 0, minx, 0, -res_y, maxy)


        full_tile_data = np.zeros((out_height, out_width), dtype=np.int32)
        reproject(
            source=data,
            destination=full_tile_data,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=tile_transform,
            dst_crs=src_crs,
            resampling=Resampling.nearest,
            src_nodata=src_nodata,
            dst_nodata=0
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
        final_data = full_tile_data

        # NODATA_VALUE is -9999, so it will never be >= 8.
        total_valid = np.count_nonzero(final_data != NODATA_VALUE)
        count_ge_8 = np.count_nonzero(final_data >= 8)
        percent_above_8 = (count_ge_8 / total_valid) * 100 if total_valid > 0 else 0.0

        result = "PASS" if percent_above_8 >= 95 else "FAIL"
        info = f"{percent_above_8:.2f} >=8"

        # Output folder selection (create FAIL folder only if needed)
        clipped_out_dir = clipped_utm_folder if result == "PASS" else os.path.join(clipped_utm_folder, "FAIL")
        os.makedirs(clipped_out_dir, exist_ok=True)
        clipped_path = os.path.join(clipped_out_dir, filename)

        profile = {
            "driver": "GTiff",
            "height": out_height,
            "width": out_width,
            "count": 1,
            "dtype": "int32",
            "crs": src_crs,
            "transform": tile_transform,
            "nodata": NODATA_VALUE,
        }
        if GTIFF_COMPRESS:
            profile["compress"] = GTIFF_COMPRESS

        with rasterio.open(clipped_path, "w", **profile) as dst:
            dst.write(final_data, 1)

        if result == "FAIL":
            # Move unclipped TIFF into Unclipped/.../FAIL
            fail_dir = os.path.join(unclipped_utm_folder, "FAIL")
            os.makedirs(fail_dir, exist_ok=True)
            dest = unique_dest_path(os.path.join(fail_dir, filename))
            try:
                shutil.move(raster_path, dest)
            except Exception as move_err:
                info = info + f" | TIFF_MOVE_FAILED: {move_err}"

            # Move source LAZ/LAS into INPUT_DIR\LAZ_Density_Fail\UTMxx\
            try:
                src_pc = _match_input_pointcloud_for_tif(filename)
                if src_pc and os.path.isfile(src_pc) and _FAIL_LAZ_ROOT:
                    utm_subdir = os.path.join(_FAIL_LAZ_ROOT, f"UTM{_WORKER_ZONE:02d}_LAZ")
                    os.makedirs(utm_subdir, exist_ok=True)  # creates LAZ_Density_Fail only if a FAIL happens
                    pc_dest = unique_dest_path(os.path.join(utm_subdir, os.path.basename(src_pc)))
                    shutil.move(src_pc, pc_dest)
                else:
                    info = info + " | PC_NOT_FOUND"
            except Exception as pc_err:
                info = info + f" | PC_MOVE_FAILED: {pc_err}"


        return (filename, result, info)

    except Exception as e:
        _boot_write("=== ERROR in process_raster ===")
        traceback.print_exc(file=_BOOT_FH)  # logs to boot_<pid>.log for that worker
        return (filename, "ERROR", f"{type(e).__name__}: {e}")

# -----------------------------------------------------------------------------
# Clipping driver per UTM folder
# -----------------------------------------------------------------------------
def clip_density_grids_parallel(
    cfg: dict,
    unclipped_utm_folder: str,
    clipped_utm_folder: str,
    input_file_map: dict,
    fail_laz_root: str,
    workers=DEFAULT_WORKERS,
    executor=None
):
    if executor is None:
        raise ValueError("clip_density_grids_parallel() requires an executor when using the shared pool.")

    # Always define counts FIRST so early-returns can safely return ([], counts)
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, "ERROR": 0}

    m = UTM_RE.search(os.path.basename(unclipped_utm_folder))
    if not m:
        print(f"Error: Cannot detect UTM zone from folder: {unclipped_utm_folder}")
        return [], counts

    zone = int(m.group(1))  # <-- you need this (you use zone below)

    raster_files = sorted(glob.glob(os.path.join(unclipped_utm_folder, "*.tif")))
    if not raster_files:
        print(f"No TIFFs found in {unclipped_utm_folder}, skipping.")
        return [], counts

    os.makedirs(clipped_utm_folder, exist_ok=True)

    requested_workers = clamp_workers(workers)
    effective_workers = min(requested_workers, len(raster_files))

    print(f"[UTM{zone:02d}] Clipping {len(raster_files)} rasters (pool={requested_workers}, needed={effective_workers})")

    tasks = [(p, zone, clipped_utm_folder, unclipped_utm_folder) for p in raster_files]

    if len(tasks) >= 256:
        chunksize = 16
    elif len(tasks) >= 64:
        chunksize = 8
    else:
        chunksize = 4

    fail_only = []
    log_path = os.path.join(clipped_utm_folder, "density_check_log.csv")

    with open(log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Filename", "Result", "Info"])

        for row in executor.map(process_raster_task, tasks, chunksize=chunksize):
            result = row[1]
            counts[result] = counts.get(result, 0) + 1

            if result != "PASS":
                print(",".join(row))

            w.writerow(row)

            if result == "FAIL":
                fail_only.append((zone, row[0], row[2]))

    return fail_only, counts

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
    output_root = os.path.join(base_out, "Last_Return_Density_Rasters")
    os.makedirs(output_root, exist_ok=True)

    unclipped_root = os.path.join(output_root, "Unclipped")
    clipped_root   = os.path.join(output_root, "Water_Clipped")
    os.makedirs(unclipped_root, exist_ok=True)
    os.makedirs(clipped_root, exist_ok=True)

    # lasgrid writes here, then we sort into Unclipped/UTMxx_Unclipped
    lasgrid_out = os.path.join(output_root, "_lasgrid_out")
    os.makedirs(lasgrid_out, exist_ok=True)

    input_files = sorted(
        glob.glob(os.path.join(input_dir, "*.laz")) +
        glob.glob(os.path.join(input_dir, "*.las"))
    )
    if not input_files:
        messagebox.showerror("Error", "No .las or .laz files found in the input directory.")
        return
    
    # Map: input stem -> full path (prefer .laz over .las if both exist)
    input_file_map = {}
    for p in input_files:
        stem = Path(p).stem.lower()
        if stem not in input_file_map:
            input_file_map[stem] = p
        else:
            # prefer .laz
            if p.lower().endswith(".laz") and not input_file_map[stem].lower().endswith(".laz"):
                input_file_map[stem] = p

    # Failed LAZs folder goes next to the input LAZs (but not inside TIFF output)
    fail_laz_root = os.path.join(input_dir, "LAZ_Density_Fail")

    # We'll accumulate all FAIL rows across all zones here
    all_failed = []


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


        print("Sorting TIFFs into Unclipped/UTMxx_Unclipped...")
        unclipped_utm_folders = sort_tifs_by_utm(lasgrid_out, unclipped_root)
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

        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_pool,
            initargs=(cfg["tiling_scheme_root"], cfg["prep_water_gpkg_dir"], input_file_map, fail_laz_root),
        ) as executor:
            t5 = time.perf_counter()
            print(f"[TIMING] pool_startup: {t5 - t4:.2f}s")

            for unclipped_utm in unclipped_utm_folders:
                m = UTM_RE.search(os.path.basename(unclipped_utm))
                if not m:
                    continue
                zone = int(m.group(1))
                clipped_utm = os.path.join(clipped_root, utm_folder_name(zone, "Clipped"))

                failed_rows, zone_counts = clip_density_grids_parallel(
                    cfg, unclipped_utm, clipped_utm,
                    input_file_map, fail_laz_root,
                    workers=workers,
                    executor=executor
                )

                # accumulate fails
                if failed_rows:
                    all_failed.extend(failed_rows)

                # accumulate counts (we’ll define totals just before the executor loop)
                for k, v in zone_counts.items():
                    totals[k] = totals.get(k, 0) + v

            t6 = time.perf_counter()
            print(f"[TIMING] clipping_total: {t6 - t5:.2f}s")

        t7 = time.perf_counter()
        print(f"[TIMING] total: {t7 - t0:.2f}s")


        # ---- after ALL zones ----
        pass_n = totals.get("PASS", 0)
        fail_n = totals.get("FAIL", 0)
        skip_n = totals.get("SKIP", 0)
        err_n  = totals.get("ERROR", 0)

        # Write failed_tiles.csv if there were FAIL tiles
        if fail_n > 0:
            os.makedirs(fail_laz_root, exist_ok=True)
            failed_csv = os.path.join(fail_laz_root, "failed_tiles.csv")
            with open(failed_csv, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["UTM_Zone", "TIFF_Filename", "Info"])
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
            self.configure(bg=BG_BAR)

            self.cfg = cfg
            self.on_save_callback = on_save_callback
            self.protocol("WM_DELETE_WINDOW", self.cancel)

            self.lasgrid_var = tk.StringVar(value=self.cfg.get("lasgrid_exe", ORG_LASGRID_DEFAULT))
            self.tiling_var  = tk.StringVar(value=self.cfg.get("tiling_scheme_root", PACKAGED_TILING_DEFAULT))
            self.water_var   = tk.StringVar(value=self.cfg.get("prep_water_gpkg_dir", PACKAGED_WATER_DEFAULT))

            def lbl(text, r, pady=(10, 4)):
                tk.Label(self, text=text, bg=BG_BAR).grid(row=r, column=0, sticky="w", padx=10, pady=pady, columnspan=3)

            def entry(var, r):
                tk.Entry(self, textvariable=var, width=78).grid(row=r, column=0, padx=10, pady=4, columnspan=3)

            row = 0
            lbl("LAStools lasgrid64.exe path:", row); row += 1
            entry(self.lasgrid_var, row); row += 1
            tk.Button(self, text="Browse…", command=self.browse_lasgrid).grid(row=row, column=0, padx=10, pady=6, sticky="w")
            tk.Button(self, text="Reset", command=self.reset_lasgrid).grid(row=row, column=1, padx=10, pady=6, sticky="w")
            row += 1

            lbl("Tiling scheme folder (Tiles_by_UTM):", row); row += 1
            entry(self.tiling_var, row); row += 1
            tk.Button(self, text="Browse…", command=self.browse_tiling).grid(row=row, column=0, padx=10, pady=6, sticky="w")
            tk.Button(self, text="Reset", command=self.reset_tiling).grid(row=row, column=1, padx=10, pady=6, sticky="w")
            row += 1

            lbl("Water folder (Water_by_UTM):", row); row += 1
            entry(self.water_var, row); row += 1
            tk.Button(self, text="Browse…", command=self.browse_water).grid(row=row, column=0, padx=10, pady=6, sticky="w")
            tk.Button(self, text="Reset", command=self.reset_water).grid(row=row, column=1, padx=10, pady=6, sticky="w")
            row += 1

            btns = tk.Frame(self, bg=BG_BAR)
            btns.grid(row=row, column=0, padx=10, pady=12, sticky="e", columnspan=3)
            tk.Button(btns, text="Cancel", command=self.cancel).pack(side="right", padx=(8, 0))
            tk.Button(btns, text="Save", command=self.save).pack(side="right")

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
                messagebox.showerror("Invalid", f"lasgrid64.exe not found:\n{las}")
                return
            if not til or not Path(til).is_dir():
                messagebox.showerror("Invalid", f"Tiling folder not found:\n{til}")
                return
            if not wat or not Path(wat).is_dir():
                messagebox.showerror("Invalid", f"Prepared water folder not found:\n{wat}")
                return

            self.cfg["lasgrid_exe"] = las
            self.cfg["tiling_scheme_root"] = til
            self.cfg["prep_water_gpkg_dir"] = wat

            try:
                save_config(self.cfg)
            except Exception as e:
                messagebox.showerror("Save failed", str(e))
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
            self.master.configure(bg=BG_MAIN)

            self.cfg = load_config()

            menubar = tk.Menu(master)
            settings_menu = tk.Menu(menubar, tearoff=0)
            settings_menu.add_command(label="Settings…", command=self.open_settings)
            menubar.add_cascade(label="Settings", menu=settings_menu)
            master.config(menu=menubar)

            body = tk.Frame(master, bg=BG_MAIN)
            body.pack(fill="both", expand=True)

            self.input_dir = tk.StringVar()
            self.output_dir = tk.StringVar()
            self.use_custom_output = tk.BooleanVar()

            tk.Label(body, text="Input Directory:", bg=BG_MAIN).pack(pady=(12, 5))
            tk.Entry(body, textvariable=self.input_dir, width=70).pack(padx=10)
            tk.Button(body, text="Browse", command=self.browse_input_directory).pack(pady=6)

            tk.Checkbutton(
                body,
                text="Use custom output directory",
                variable=self.use_custom_output,
                command=self.toggle_output_dir,
                bg=BG_MAIN
            ).pack(pady=6)

            self.output_entry = tk.Entry(body, textvariable=self.output_dir, width=70, state="disabled")
            self.output_entry.pack(padx=10)
            self.output_browse_btn = tk.Button(body, text="Browse Output", command=self.browse_output_directory, state="disabled")
            self.output_browse_btn.pack(pady=6)

            self.workers = tk.IntVar(value=DEFAULT_WORKERS)
            tk.Label(body, text=f"Number of cores: 1–{WORKERS_CAP}", bg=BG_MAIN).pack(pady=(12, 5))
            tk.Spinbox(body, from_=1, to=WORKERS_CAP, textvariable=self.workers, width=6).pack()

            self.run_btn = tk.Button(
                body,
                text="Density Check",
                command=self.start_density_check,
                bg="green",
                fg="white",
                height=2,
                width=20
            )
            self.run_btn.pack(pady=22)



        def open_settings(self):
            SettingsWindow(self.master, dict(self.cfg), self._on_settings_saved)

        def _on_settings_saved(self, new_cfg: dict):
            self.cfg = new_cfg

        def browse_input_directory(self):
            folder = filedialog.askdirectory()
            if folder:
                self.input_dir.set(folder)

        def toggle_output_dir(self):
            if self.use_custom_output.get():
                self.output_entry.config(state="normal")
                self.output_browse_btn.config(state="normal")
            else:
                self.output_entry.config(state="disabled")
                self.output_browse_btn.config(state="disabled")

        def browse_output_directory(self):
            folder = filedialog.askdirectory()
            if folder:
                self.output_dir.set(folder)

        def start_density_check(self):
            self.run_btn.config(state="disabled")
            try:
                input_path = self.input_dir.get().strip()
                output_path = self.output_dir.get().strip() if self.use_custom_output.get() else None
                workers = int(self.workers.get())

                print(f"[RUN] exe={getattr(sys, 'frozen', False)}")
                print(f"[RUN] sys.executable={sys.executable}")
                print(f"[RUN] sys.version={sys.version}")
                print(f"[RUN] workers={workers}")
                print(f"[RUN] input={input_path}")
                print(f"[RUN] output={(output_path or input_path)}")

                run_density_check(
                    cfg=self.cfg,
                    input_dir=input_path,
                    custom_output_dir=output_path,
                    workers=workers
                )
            finally:
                self.run_btn.config(state="normal")

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

        # Boot log no longer needed once app_debug.log is live
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