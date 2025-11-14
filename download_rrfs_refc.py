#!/usr/bin/env python3
"""
Download RRFS Composite Reflectivity (REFC) GRIB2 files from NOAA S3 bucket.

This script downloads the latest RRFS forecast data containing composite
reflectivity information and manages storage on a rolling basis.
"""

import os
import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET
import argparse
import json

# Configuration
S3_BUCKET = "noaa-rrfs-pds"
S3_BASE_URL = f"https://{S3_BUCKET}.s3.amazonaws.com"
DATA_DIR = Path("rrfs_data")
MAX_FILES = 50  # Maximum number of GRIB files to keep (rolling basis)

# RRFS runs every hour, forecasts out to 84 hours
FORECAST_HOURS = list(range(0, 19))  # Download first 18 hours of forecast
CYCLES_TO_CHECK = 6  # Check last 6 cycles (6 hours back)


def setup_data_directory():
    """Create data directory if it doesn't exist."""
    DATA_DIR.mkdir(exist_ok=True)
    print(f"Data directory: {DATA_DIR.absolute()}")


def get_latest_cycle():
    """
    Determine the latest available RRFS cycle to download.
    RRFS runs hourly, but data may have a delay.
    """
    current_utc = datetime.utcnow()
    # Go back a few hours to account for processing delay
    start_time = current_utc - timedelta(hours=3)

    # Try recent cycles
    for hours_back in range(CYCLES_TO_CHECK):
        check_time = start_time - timedelta(hours=hours_back)
        cycle_date = check_time.strftime("%Y%m%d")
        cycle_hour = check_time.strftime("%H")

        # Check if this cycle exists in S3
        prefix = f"rrfs_a/rrfs_a.{cycle_date}/{cycle_hour}/"
        url = f"{S3_BASE_URL}/?prefix={prefix}&max-keys=1"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                # Check if any files exist
                contents = root.findall(".//{http://s3.amazonaws.com/doc/2006-03-01/}Contents")
                if contents:
                    print(f"Found available cycle: {cycle_date}/{cycle_hour}z")
                    return cycle_date, cycle_hour
        except Exception as e:
            print(f"Error checking cycle {cycle_date}/{cycle_hour}z: {e}")
            continue

    # If no recent data found, return latest expected time anyway
    fallback_time = current_utc - timedelta(hours=3)
    cycle_date = fallback_time.strftime("%Y%m%d")
    cycle_hour = fallback_time.strftime("%H")
    print(f"No recent data found, using fallback: {cycle_date}/{cycle_hour}z")
    return cycle_date, cycle_hour


def list_available_files(cycle_date, cycle_hour):
    """
    List available GRIB2 files for a given cycle.

    Args:
        cycle_date: Date string (YYYYMMDD)
        cycle_hour: Hour string (HH)

    Returns:
        List of file keys (S3 paths)
    """
    prefix = f"rrfs_a/rrfs_a.{cycle_date}/{cycle_hour}/"
    url = f"{S3_BASE_URL}/?prefix={prefix}"

    print(f"Listing files at: {prefix}")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        files = []

        # Find all grib2 files
        for content in root.findall(".//{http://s3.amazonaws.com/doc/2006-03-01/}Contents"):
            key_elem = content.find("{http://s3.amazonaws.com/doc/2006-03-01/}Key")
            size_elem = content.find("{http://s3.amazonaws.com/doc/2006-03-01/}Size")

            if key_elem is not None and key_elem.text:
                key = key_elem.text
                size = int(size_elem.text) if size_elem is not None else 0

                # Filter for grib2 files with native level (contains all fields including REFC)
                if key.endswith('.grib2') and 'natlev' in key:
                    files.append({'key': key, 'size': size})

        print(f"Found {len(files)} grib2 files")
        return files

    except Exception as e:
        print(f"Error listing files: {e}")
        return []


def download_file(s3_key, local_path):
    """
    Download a file from S3.

    Args:
        s3_key: S3 object key
        local_path: Local file path to save to

    Returns:
        True if successful, False otherwise
    """
    url = f"{S3_BASE_URL}/{s3_key}"

    try:
        print(f"Downloading: {s3_key}")
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        # Get file size
        file_size = int(response.headers.get('content-length', 0))

        # Download with progress
        downloaded = 0
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if file_size > 0:
                        percent = (downloaded / file_size) * 100
                        print(f"  Progress: {percent:.1f}% ({downloaded / 1024 / 1024:.1f} MB)", end='\r')

        print(f"\n  Downloaded: {local_path.name} ({downloaded / 1024 / 1024:.1f} MB)")
        return True

    except Exception as e:
        print(f"  Error downloading {s3_key}: {e}")
        if local_path.exists():
            local_path.unlink()
        return False


def clean_old_files(max_files=MAX_FILES):
    """
    Remove oldest files to maintain rolling storage limit.

    Args:
        max_files: Maximum number of files to keep
    """
    grib_files = sorted(DATA_DIR.glob("*.grib2"), key=lambda x: x.stat().st_mtime)

    if len(grib_files) > max_files:
        files_to_remove = len(grib_files) - max_files
        print(f"\nCleaning up: removing {files_to_remove} old file(s)")

        for old_file in grib_files[:files_to_remove]:
            print(f"  Removing: {old_file.name}")
            old_file.unlink()


def save_metadata(cycle_date, cycle_hour, downloaded_files):
    """
    Save metadata about the download.

    Args:
        cycle_date: Cycle date string
        cycle_hour: Cycle hour string
        downloaded_files: List of downloaded file names
    """
    metadata = {
        'last_update': datetime.utcnow().isoformat(),
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
    args = parser.parse_args()

    print("=" * 60)
    print("RRFS Composite Reflectivity (REFC) Data Downloader")
    print("=" * 60)

    setup_data_directory()

    # Determine which cycle to download
    if args.date and args.hour:
        cycle_date, cycle_hour = args.date, args.hour
        print(f"Using specified cycle: {cycle_date}/{cycle_hour}z")
    else:
        cycle_date, cycle_hour = get_latest_cycle()

    # List available files
    available_files = list_available_files(cycle_date, cycle_hour)

    if not available_files:
        print("\nNo files available for download. The RRFS system may be offline.")
        print("Note: Real-time RRFS data was temporarily suspended starting Dec 2024.")
        print("Check https://registry.opendata.aws/noaa-rrfs/ for status updates.")
        return 1

    # Download files
    downloaded_files = []
    for file_info in available_files[:10]:  # Limit to first 10 forecast hours
        s3_key = file_info['key']
        filename = Path(s3_key).name
        local_path = DATA_DIR / filename

        # Skip if already exists
        if local_path.exists():
            print(f"Skipping (already exists): {filename}")
            downloaded_files.append(filename)
            continue

        if download_file(s3_key, local_path):
            downloaded_files.append(filename)

    # Clean up old files
    clean_old_files(args.max_files)

    # Save metadata
    save_metadata(cycle_date, cycle_hour, downloaded_files)

    print("\n" + "=" * 60)
    print(f"Download complete: {len(downloaded_files)} files")
    print(f"Data directory: {DATA_DIR.absolute()}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
