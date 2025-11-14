#!/usr/bin/env python3
"""
Download RRFS Composite Reflectivity (REFC) GRIB2 files from NOAA S3 bucket.

This script downloads the latest RRFS forecast data containing composite
reflectivity information and manages storage on a rolling basis.
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
MAX_FILES = 50  # Maximum number of GRIB files to keep (rolling basis)
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
    """
    Find the latest available cycle hour for a given date.

    Args:
        day_ymd: Date string (YYYYMMDD)

    Returns:
        Hour string (HH) or None if no cycles found
    """
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
    """
    Determine the latest available RRFS cycle to download.
    Tries recent dates and hours to find active data.
    """
    current_utc = datetime.now(timezone.utc)

    # Try the last several hours
    for hours_back in range(CYCLES_TO_CHECK):
        check_time = current_utc - timedelta(hours=hours_back + 2)  # Account for processing delay
        day_ymd = check_time.strftime("%Y%m%d")

        latest_hour = find_latest_cycle(day_ymd)
        if latest_hour:
            print(f"Found available cycle: {day_ymd}/{latest_hour}z")
            return day_ymd, latest_hour

    # No data found
    print("No recent RRFS cycles found in the last 12 hours")
    return None, None


def list_prslev_keys(day_ymd: str, hh: str) -> list[dict]:
    """
    List pressure level GRIB2 files for a given cycle.

    Args:
        day_ymd: Date string (YYYYMMDD)
        hh: Hour string (HH)

    Returns:
        List of dicts with 'key' and 'size' for each file
    """
    try:
        root = list_bucket(f"{PREFIX_ROOT}/rrfs.{day_ymd}/{hh}/")
        files = []
        for ct in root.findall("{http://s3.amazonaws.com/doc/2006-03-01/}Contents"):
            key_elem = ct.find("{http://s3.amazonaws.com/doc/2006-03-01/}Key")
            size_elem = ct.find("{http://s3.amazonaws.com/doc/2006-03-01/}Size")

            if key_elem is not None and key_elem.text:
                key = key_elem.text
                size = int(size_elem.text) if size_elem is not None else 0

                # Look for pressure level GRIB2 files (contain REFC data)
                if "/rrfs.t" in key and ".prslev" in key and key.endswith(".grib2"):
                    files.append({'key': key, 'size': size})

        return files
    except Exception as e:
        print(f"Error listing files: {e}")
        return []


def ensure_refc_in_idx(grib_url: str) -> bool:
    """
    Check if a GRIB2 file contains REFC (composite reflectivity) data.

    Args:
        grib_url: URL to the GRIB2 file

    Returns:
        True if REFC data is present, False otherwise
    """
    idx_url = grib_url + ".idx"
    try:
        r = requests.get(idx_url, timeout=20)
        if r.status_code != 200:
            return False
        return "REFC:" in r.text
    except Exception:
        return False


def choose_refc_files(files: list[dict], max_files: int = 10, domain_preference: str = "na") -> list[dict]:
    """
    Choose which files to download, prioritizing specified domain and earlier forecast hours.

    Args:
        files: List of file dicts
        max_files: Maximum number of files to select
        domain_preference: Preferred domain (na, conus, ak, hi, pr)

    Returns:
        Filtered list of file dicts
    """
    # Filter for preferred domain if specified
    if domain_preference:
        domain_files = [f for f in files if f".{domain_preference}.grib2" in f['key']]
        if domain_files:
            files = domain_files
            print(f"Filtering for {domain_preference.upper()} domain: {len(files)} files")

    # Sort by forecast hour (f000, f001, etc.)
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

        # Skip subhourly files (subh) for main forecast
        is_subh = ".subh." in key

        return (is_subh, fhour, key)

    sorted_files = sorted(files, key=sort_key)
    return sorted_files[:max_files]


def download_file(url: str, out_path: Path) -> bool:
    """
    Download a file from S3.

    Args:
        url: Full URL to the file
        out_path: Local path to save to

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"Downloading: {out_path.name}")
        t0 = time.time()

        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            file_size = int(r.headers.get('content-length', 0))

            downloaded = 0
            with open(out_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):  # 1 MB chunks
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if file_size > 0:
                            percent = (downloaded / file_size) * 100
                            print(f"  Progress: {percent:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end='\r')

        dt = time.time() - t0
        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        print(f"\n  Downloaded: {size_mb:.1f} MiB in {dt:.1f}s")

        # Also download and save the .idx file
        idx_url = url + ".idx"
        idx_path = out_path.with_suffix('.grib2.idx')
        try:
            r = requests.get(idx_url, timeout=20)
            r.raise_for_status()
            with open(idx_path, 'wb') as f:
                f.write(r.content)

            # Show REFC lines from index
            refc_lines = [ln for ln in r.text.splitlines() if "REFC:" in ln]
            if refc_lines:
                print(f"  REFC fields found: {len(refc_lines)}")
        except Exception as e:
            print(f"  Warning: Could not download .idx file: {e}")

        return True

    except Exception as e:
        print(f"\n  Error downloading: {e}")
        if out_path.exists():
            out_path.unlink()
        return False


def clean_old_files(keep_latest_cycle: bool = False):
    """
    Remove old files. If keep_latest_cycle is True, removes ALL existing files
    to make room for the new cycle. Otherwise keeps files from the current cycle.

    Args:
        keep_latest_cycle: If True, delete all existing files before download
    """
    grib_files = list(DATA_DIR.glob("*.grib2"))

    if not grib_files:
        return

    if keep_latest_cycle:
        # Delete ALL old files to make room for new cycle
        print(f"\nCleaning all old data ({len(grib_files)} files) to make room for new cycle...")
        for old_file in grib_files:
            print(f"  Removing: {old_file.name}")
            old_file.unlink()
            # Also remove associated .idx file
            idx_file = old_file.with_suffix('.grib2.idx')
            if idx_file.exists():
                idx_file.unlink()

        # Also remove old metadata
        metadata_file = DATA_DIR / 'metadata.json'
        if metadata_file.exists():
            metadata_file.unlink()
            print(f"  Removed: metadata.json")
    else:
        print(f"\nExisting files: {len(grib_files)}")


def save_metadata(cycle_date: str, cycle_hour: str, downloaded_files: list[str]):
    """
    Save metadata about the download.

    Args:
        cycle_date: Cycle date string
        cycle_hour: Cycle hour string
        downloaded_files: List of downloaded file names
    """
    metadata = {
        'last_update': datetime.now(timezone.utc).isoformat(),
        'cycle_date': cycle_date,
        'cycle_hour': cycle_hour,
        'files_downloaded': len(downloaded_files),
        'file_list': downloaded_files
    }

    metadata_file = DATA_DIR / 'metadata.json'
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\nMetadata saved to: {metadata_file}")


def main():
    """Main download routine."""
    parser = argparse.ArgumentParser(description='Download RRFS REFC GRIB2 data')
    parser.add_argument('--max-files', type=int, default=MAX_FILES,
                        help=f'Maximum number of GRIB files to keep (default: {MAX_FILES})')
    parser.add_argument('--date', type=str, help='Specific date to download (YYYYMMDD)')
    parser.add_argument('--hour', type=str, help='Specific cycle hour (HH)')
    parser.add_argument('--num-forecasts', type=int, default=3,
                        help='Number of forecast hours to download (default: 3)')
    parser.add_argument('--domain', type=str, default='na',
                        choices=['na', 'conus', 'ak', 'hi', 'pr'],
                        help='Domain to download (default: na for North America)')
    parser.add_argument('--clean-before-download', action='store_true',
                        help='Delete all old data before downloading (keeps only latest cycle)')
    args = parser.parse_args()

    print("=" * 60)
    print("RRFS Composite Reflectivity (REFC) Data Downloader")
    print("=" * 60)

    setup_data_directory()

    # Clean old data BEFORE downloading if requested
    if args.clean_before_download:
        clean_old_files(keep_latest_cycle=True)

    # Determine which cycle to download
    if args.date and args.hour:
        cycle_date, cycle_hour = args.date, args.hour
        print(f"Using specified cycle: {cycle_date}/{cycle_hour}z")
    else:
        cycle_date, cycle_hour = get_latest_available_cycle()
        if cycle_date is None:
            print("\nNo files available for download.")
            print("The RRFS system may be temporarily offline or experiencing delays.")
            print("Check https://registry.opendata.aws/noaa-rrfs/ for status updates.")
            return 1

    # List available files
    print(f"\nListing files at: {PREFIX_ROOT}/rrfs.{cycle_date}/{cycle_hour}/")
    available_files = list_prslev_keys(cycle_date, cycle_hour)

    if not available_files:
        print("\nNo GRIB2 files found for this cycle.")
        return 1

    print(f"Found {len(available_files)} total GRIB2 files")

    # Filter for files with REFC data and choose which to download
    print(f"\nFiltering for {args.domain.upper()} domain files containing REFC data...")
    files_to_download = []
    for file_info in choose_refc_files(available_files, args.num_forecasts * 3, args.domain):
        grib_url = f"{S3_BUCKET}/{file_info['key']}"
        if ensure_refc_in_idx(grib_url):
            files_to_download.append(file_info)
            if len(files_to_download) >= args.num_forecasts:
                break

    if not files_to_download:
        print("No files with REFC data found!")
        return 1

    print(f"Selected {len(files_to_download)} files with REFC data to download")

    # Download files
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
        if download_file(grib_url, local_path):
            downloaded_files.append(filename)

    # Save metadata
    if downloaded_files:
        save_metadata(cycle_date, cycle_hour, downloaded_files)

    print("\n" + "=" * 60)
    print(f"Download complete: {len(downloaded_files)} files")
    print(f"Data directory: {DATA_DIR.absolute()}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
