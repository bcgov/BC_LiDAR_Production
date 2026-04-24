"""
Build helper: sync PROJ and GDAL data from the EXACT libraries rasterio uses.

Run this from the build conda environment BEFORE PyInstaller:
    python sync_proj_data.py

It imports rasterio, asks PROJ/GDAL where their data lives, copies it into
data/proj/ and data/gdal/, then VERIFIES the copied data actually works by
creating a test CRS. If verification fails, the script exits with code 1
so build.bat can abort.
"""
import os
import sys
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_PROJ = SCRIPT_DIR / "data" / "proj"
LOCAL_GDAL = SCRIPT_DIR / "data" / "gdal"


def find_proj_data() -> Path:
    """Find the PROJ data directory that rasterio's PROJ library actually uses."""
    import rasterio  # noqa — triggers PROJ/GDAL env setup

    # 1) Check env vars rasterio may have set
    for var in ("PROJ_LIB", "PROJ_DATA"):
        val = os.environ.get(var)
        if val and Path(val).is_dir() and (Path(val) / "proj.db").is_file():
            return Path(val)

    # 2) Rasterio wheel bundles proj_data inside the package
    rio_proj = Path(rasterio.__file__).parent / "proj_data"
    if rio_proj.is_dir() and (rio_proj / "proj.db").is_file():
        return rio_proj

    # 3) Conda env: Library/share/proj
    prefix = Path(sys.prefix)
    conda_proj = prefix / "Library" / "share" / "proj"
    if conda_proj.is_dir() and (conda_proj / "proj.db").is_file():
        return conda_proj

    raise FileNotFoundError(
        "Could not find proj.db anywhere.\n"
        "Checked: PROJ_LIB, PROJ_DATA, rasterio/proj_data, conda Library/share/proj"
    )


def find_gdal_data() -> Path:
    """Find the GDAL data directory."""
    import rasterio  # noqa

    val = os.environ.get("GDAL_DATA")
    if val and Path(val).is_dir():
        return Path(val)

    rio_gdal = Path(rasterio.__file__).parent / "gdal_data"
    if rio_gdal.is_dir():
        return rio_gdal

    prefix = Path(sys.prefix)
    conda_gdal = prefix / "Library" / "share" / "gdal"
    if conda_gdal.is_dir():
        return conda_gdal

    return None  # GDAL data is less critical


def copy_dir(src: Path, dst: Path, label: str):
    """Copy all files from src into dst, overwriting existing."""
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in src.iterdir():
        if f.is_file():
            shutil.copy2(f, dst / f.name)
            count += 1
    print(f"  Copied {count} files from {src}")


def verify_proj(proj_dir: Path):
    """Verify the copied proj.db works by creating CRS objects."""
    # Point PROJ at our local copy
    os.environ["PROJ_LIB"] = str(proj_dir)
    os.environ["PROJ_DATA"] = str(proj_dir)

    # Force rasterio to reload with new env
    # We do a fresh CRS creation which exercises proj.db
    from rasterio.crs import CRS

    test_codes = {
        2955: "NAD83(CSRS) / UTM zone 11N",
        3157: "NAD83(CSRS) / UTM zone 10N",
        3156: "NAD83(CSRS) / UTM zone 9N",
        3155: "NAD83(CSRS) / UTM zone 8N",
        3154: "NAD83(CSRS) / UTM zone 7N",
    }

    for epsg, name in test_codes.items():
        try:
            crs = CRS.from_epsg(epsg)
            if crs is None:
                raise RuntimeError(f"CRS.from_epsg({epsg}) returned None")
        except Exception as e:
            print(f"  VERIFY FAILED: EPSG:{epsg} ({name}): {e}")
            return False
        print(f"  EPSG:{epsg} ({name}) OK")

    return True


def main():
    print("=" * 60)
    print("Syncing PROJ/GDAL data from rasterio environment")
    print("=" * 60)

    # --- PROJ ---
    print("\n[PROJ]")
    try:
        proj_src = find_proj_data()
        print(f"  Source: {proj_src}")

        # Show the version of the source proj.db
        import sqlite3
        db_path = proj_src / "proj.db"
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT key, value FROM metadata "
            "WHERE key LIKE 'DATABASE.LAYOUT.VERSION%'"
        ).fetchall()
        conn.close()
        for k, v in rows:
            print(f"  {k} = {v}")

        copy_dir(proj_src, LOCAL_PROJ, "PROJ")

    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # --- GDAL ---
    print("\n[GDAL]")
    try:
        gdal_src = find_gdal_data()
        if gdal_src:
            print(f"  Source: {gdal_src}")
            copy_dir(gdal_src, LOCAL_GDAL, "GDAL")
        else:
            print("  WARNING: GDAL data directory not found (non-fatal)")
    except Exception as e:
        print(f"  WARNING: {e}")

    # --- VERIFY ---
    print("\n[VERIFY]")
    print(f"  Testing proj.db at: {LOCAL_PROJ / 'proj.db'}")

    # Show the version of the COPIED proj.db
    import sqlite3
    db_path = LOCAL_PROJ / "proj.db"
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT key, value FROM metadata "
        "WHERE key LIKE 'DATABASE.LAYOUT.VERSION%'"
    ).fetchall()
    conn.close()
    for k, v in rows:
        print(f"  Copied: {k} = {v}")

    if verify_proj(LOCAL_PROJ):
        print("\n  ALL CRS TESTS PASSED — proj.db is correct!")
    else:
        print("\n  PROJ VERIFICATION FAILED!")
        print("  The copied proj.db does not match the PROJ library.")
        print("  DO NOT proceed with the build.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("PROJ/GDAL sync complete — ready for PyInstaller")
    print("=" * 60)


if __name__ == "__main__":
    main()
