#!/usr/bin/env python3
"""
Download ONLY the REFC (composite reflectivity) fields from RRFS GRIB2 files.

Uses HTTP byte-range requests to download only the REFC data portion,
reducing download size from ~5GB to ~7MB per file (99% reduction).
"""

import os
import sys
import time
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import argparse
import json

# Configuration
S3_BUCKET = "https://noaa-rrfs-pds.s3.amazonaws.com"
PREFIX_ROOT = "rrfs_a"
DATA_DIR = Path("rrfs_data")
CYCLES_TO_CHECK = 12  # Check last 12 cycles (12 hours back)


def setup_data_directory():
    """Create data directory if it doesn't exist."""
    DATA_DIR.mkdir(exist_ok=True)
    print(f"Data directory: {DATA_DIR.absolute()}")


def list_bucket(prefix: str):
    """Query S3 bucket with given prefix."""
    params = {"delimiter": "/", "prefix": prefix}
    r = requests.get(S3_BUCKET + "/", params=params, timeout=20)
    r.raise_for_status()
    return ET.fromstring(r.text)


def find_latest_cycle(day_ymd: str) -> str | None:
    """Find the latest available cycle hour for a given date."""
    try:
        root = list_bucket(f"{PREFIX_ROOT}/rrfs.{day_ymd}/")
        hours = []
        for cp in root.findall("{http://s3.amazonaws.com/doc/2006-03-01/}CommonPrefixes"):
            pref = cp.find("{http://s3.amazonaws.com/doc/2006-03-01/}Prefix").text
            parts = pref.strip("/").split("/")
            if len(parts) >= 3:
                hh = parts[2]
                if hh.isdigit() and len(hh) == 2:
                    hours.append(hh)
        return max(hours) if hours else None
    except Exception as e:
        print(f"Error finding cycles for {day_ymd}: {e}")
        return None


def get_latest_available_cycle():
    """Determine the latest available RRFS cycle."""
    current_utc = datetime.now(timezone.utc)

    for hours_back in range(CYCLES_TO_CHECK):
        check_time = current_utc - timedelta(hours=hours_back + 2)
        day_ymd = check_time.strftime("%Y%m%d")

        latest_hour = find_latest_cycle(day_ymd)
        if latest_hour:
            print(f"Found available cycle: {day_ymd}/{latest_hour}z")
            return day_ymd, latest_hour

    print("No recent RRFS cycles found in the last 12 hours")
    return None, None


def list_prslev_keys(day_ymd: str, hh: str, domain: str = "na") -> list[dict]:
    """List pressure level GRIB2 files for a given cycle and domain."""
    try:
        root = list_bucket(f"{PREFIX_ROOT}/rrfs.{day_ymd}/{hh}/")
        files = []
        for ct in root.findall("{http://s3.amazonaws.com/doc/2006-03-01/}Contents"):
            key_elem = ct.find("{http://s3.amazonaws.com/doc/2006-03-01/}Key")
            size_elem = ct.find("{http://s3.amazonaws.com/doc/2006-03-01/}Size")

            if key_elem is not None and key_elem.text:
                key = key_elem.text
                size = int(size_elem.text) if size_elem is not None else 0

                # Look for pressure level files for specified domain
                if "/rrfs.t" in key and ".prslev" in key and f".{domain}.grib2" in key:
                    files.append({'key': key, 'size': size})

        return files
    except Exception as e:
        print(f"Error listing files: {e}")
        return []


def get_refc_byte_range(idx_url: str) -> tuple[int, int] | None:
    """
    Parse .idx file to find byte range for REFC field.

    Returns:
        Tuple of (start_byte, end_byte) or None if REFC not found
    """
    try:
        r = requests.get(idx_url, timeout=20)
        if r.status_code != 200:
            return None

        lines = r.text.strip().split('\n')
        refc_line_num = None

        # Find the line with REFC
        for i, line in enumerate(lines):
            if ':REFC:' in line:
                refc_line_num = i
                break

        if refc_line_num is None:
            return None

        # Parse byte offset from REFC line
        refc_parts = lines[refc_line_num].split(':')
        start_byte = int(refc_parts[1])

        # Get end byte from next line (or file size if last field)
        if refc_line_num + 1 < len(lines):
            next_parts = lines[refc_line_num + 1].split(':')
            end_byte = int(next_parts[1]) - 1
        else:
            # If REFC is the last field, we'll need to download to end
            end_byte = None

        return (start_byte, end_byte)

    except Exception as e:
        print(f"  Error parsing .idx file: {e}")
        return None


def download_refc_only(grib_url: str, idx_url: str, out_path: Path) -> bool:
    """
    Download only the REFC field from a GRIB2 file using byte-range request.

    Args:
        grib_url: URL to the full GRIB2 file
        idx_url: URL to the .idx index file
        out_path: Local path to save REFC data

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"Downloading REFC from: {out_path.name}")

        # Get byte range for REFC field
        byte_range = get_refc_byte_range(idx_url)
        if byte_range is None:
            print(f"  Error: Could not find REFC field in index")
            return False

        start_byte, end_byte = byte_range

        # Download only the REFC portion using byte-range request
        headers = {}
        if end_byte:
            headers['Range'] = f'bytes={start_byte}-{end_byte}'
            size_mb = (end_byte - start_byte) / (1024 * 1024)
        else:
            headers['Range'] = f'bytes={start_byte}-'
            size_mb = "unknown"

        print(f"  Downloading bytes {start_byte:,} to {end_byte:,} ({size_mb:.1f} MB)" if isinstance(size_mb, float) else f"  Downloading from byte {start_byte:,}")

        t0 = time.time()
        r = requests.get(grib_url, headers=headers, timeout=300)
        r.raise_for_status()

        # Save to file
        with open(out_path, 'wb') as f:
            f.write(r.content)

        dt = time.time() - t0
        actual_size_mb = len(r.content) / (1024 * 1024)
        print(f"  Downloaded: {actual_size_mb:.1f} MB in {dt:.1f}s ({actual_size_mb/dt:.1f} MB/s)")

        # Also save a copy of the idx file for reference
        idx_path = out_path.with_suffix('.grib2.idx')
        try:
            idx_r = requests.get(idx_url, timeout=20)
            idx_r.raise_for_status()
            with open(idx_path, 'wb') as f:
                f.write(idx_r.content)
        except Exception as e:
            print(f"  Warning: Could not download .idx file: {e}")

        return True

    except Exception as e:
        print(f"  Error downloading: {e}")
        if out_path.exists():
            out_path.unlink()
        return False


def choose_forecast_files(files: list[dict], num_forecasts: int = None) -> list[dict]:
    """
    Choose forecast hours to download, sorted by forecast hour.
    If num_forecasts is None, downloads ALL available forecast hours.

    Args:
        files: List of file dicts
        num_forecasts: Number of forecast hours to select (None = all)

    Returns:
        Filtered list of file dicts
    """
    def sort_key(f):
        key = f['key']
        # Extract forecast hour
        fhour = 999
        if ".f" in key:
            try:
                fhour_str = key.split(".f")[1].split(".")[0]
                fhour = int(fhour_str)
            except (IndexError, ValueError):
                pass

        # Skip subhourly files
        is_subh = ".subh." in key

        return (is_subh, fhour, key)

    sorted_files = sorted(files, key=sort_key)

    # If num_forecasts is None, return all files
    if num_forecasts is None:
        return sorted_files

    return sorted_files[:num_forecasts]


def detect_forecast_length(files: list[dict]) -> tuple[int, str]:
    """
    Detect the maximum forecast hour available and classify as short/long range.

    Returns:
        Tuple of (max_forecast_hour, range_type) where range_type is 'short' or 'long'
    """
    max_hour = 0
    for f in files:
        key = f['key']
        if ".f" in key and ".subh." not in key:
            try:
                fhour_str = key.split(".f")[1].split(".")[0]
                fhour = int(fhour_str)
                max_hour = max(max_hour, fhour)
            except (IndexError, ValueError):
                pass

    # Classify: short-range (≤24 hrs), long-range (>24 hrs)
    range_type = 'long' if max_hour > 24 else 'short'
    return max_hour, range_type


def clean_old_files(current_cycle_date: str, current_cycle_hour: str):
    """
    Remove old GRIB files from previous cycles, keeping only the current cycle.

    Args:
        current_cycle_date: Date of current cycle (YYYYMMDD)
        current_cycle_hour: Hour of current cycle (HH)
    """
    grib_files = list(DATA_DIR.glob("*.grib2"))

    if not grib_files:
        return

    current_cycle_prefix = f"rrfs.t{current_cycle_hour}z"
    files_to_remove = []

    for grib_file in grib_files:
        # Keep files from current cycle, remove everything else
        if not grib_file.name.startswith(current_cycle_prefix):
            files_to_remove.append(grib_file)

    if files_to_remove:
        print(f"\nCleaning old data from previous cycles ({len(files_to_remove)} files)...")
        for old_file in files_to_remove:
            print(f"  Removing: {old_file.name}")
            old_file.unlink()
            # Also remove associated .idx file
            idx_file = old_file.with_suffix('.grib2.idx')
            if idx_file.exists():
                idx_file.unlink()


def save_metadata(cycle_date: str, cycle_hour: str, downloaded_files: list[str],
                  max_forecast_hour: int, range_type: str):
    """Save metadata about the download."""
    metadata = {
        'last_update': datetime.now(timezone.utc).isoformat(),
        'cycle_date': cycle_date,
        'cycle_hour': cycle_hour,
        'forecast_range_type': range_type,
        'max_forecast_hour': max_forecast_hour,
        'files_downloaded': len(downloaded_files),
        'file_list': downloaded_files,
        'note': 'Files contain REFC field only (extracted via byte-range request)'
    }

    metadata_file = DATA_DIR / 'metadata.json'
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\nMetadata saved to: {metadata_file}")


def main():
    """Main download routine."""
    parser = argparse.ArgumentParser(description='Download RRFS REFC (composite reflectivity) data only')
    parser.add_argument('--date', type=str, help='Specific date to download (YYYYMMDD)')
    parser.add_argument('--hour', type=str, help='Specific cycle hour (HH)')
    parser.add_argument('--num-forecasts', type=int, default=None,
                        help='Number of forecast hours to download (default: None = download all available)')
    parser.add_argument('--domain', type=str, default='na',
                        choices=['na', 'conus', 'ak', 'hi', 'pr'],
                        help='Domain to download (default: na for North America)')
    parser.add_argument('--download-all-hours', action='store_true',
                        help='Download ALL available forecast hours (overrides --num-forecasts)')
    args = parser.parse_args()

    # If --download-all-hours is set, override num_forecasts to None
    if args.download_all_hours:
        args.num_forecasts = None

    print("=" * 60)
    print("RRFS REFC-Only Downloader (Byte-Range Optimized)")
    print("=" * 60)

    setup_data_directory()

    # Determine which cycle to download
    if args.date and args.hour:
        cycle_date, cycle_hour = args.date, args.hour
        print(f"Using specified cycle: {cycle_date}/{cycle_hour}z")
    else:
        cycle_date, cycle_hour = get_latest_available_cycle()
        if cycle_date is None:
            print("\nNo files available for download.")
            return 1

    # List available files
    print(f"\nListing files at: {PREFIX_ROOT}/rrfs.{cycle_date}/{cycle_hour}/")
    available_files = list_prslev_keys(cycle_date, cycle_hour, args.domain)

    if not available_files:
        print(f"\nNo GRIB2 files found for {args.domain.upper()} domain.")
        return 1

    # Detect forecast length
    max_forecast_hour, range_type = detect_forecast_length(available_files)
    print(f"Found {len(available_files)} {args.domain.upper()} domain files")
    print(f"Forecast range: {range_type.upper()}-RANGE (extends to f{max_forecast_hour:03d})")

    # Choose which files to download
    files_to_download = choose_forecast_files(available_files, args.num_forecasts)

    if args.num_forecasts is None:
        print(f"Downloading ALL forecast hours: f000-f{max_forecast_hour:03d}")
    else:
        print(f"Downloading {len(files_to_download)} forecast hours (f000-f{args.num_forecasts-1:03d})")

    # Download REFC fields only
    downloaded_files = []
    for file_info in files_to_download:
        s3_key = file_info['key']
        filename = Path(s3_key).name
        local_path = DATA_DIR / filename

        # Skip if already exists
        if local_path.exists():
            print(f"\nSkipping (already exists): {filename}")
            downloaded_files.append(filename)
            continue

        grib_url = f"{S3_BUCKET}/{s3_key}"
        idx_url = grib_url + ".idx"

        if download_refc_only(grib_url, idx_url, local_path):
            downloaded_files.append(filename)

    # Clean old data AFTER successful download
    if downloaded_files:
        clean_old_files(cycle_date, cycle_hour)

    # Save metadata
    if downloaded_files:
        save_metadata(cycle_date, cycle_hour, downloaded_files, max_forecast_hour, range_type)

    print("\n" + "=" * 60)
    print(f"Download complete: {len(downloaded_files)} files")
    print(f"Cycle type: {range_type.upper()}-RANGE (f000-f{max_forecast_hour:03d})")
    print(f"Data directory: {DATA_DIR.absolute()}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
