# RRFS REFC Data Auto-Downloader

**Automated hourly downloads of NOAA RRFS Composite Reflectivity (radar) data for North America**

## What This Does

This repository automatically downloads the latest weather radar composite reflectivity forecasts from NOAA's Rapid Refresh Forecast System (RRFS) and stores them in Git using an ultra-efficient byte-range extraction method.

### Key Features

✅ **Runs automatically every hour** via GitHub Actions
✅ **Downloads ALL available forecast hours** from latest cycle (18-84 hours depending on cycle type)
✅ **99.85% size reduction** - extracts only the REFC field instead of full GRIB files
✅ **Smart cleanup** - removes old cycles after downloading new data
✅ **Git LFS storage** - handles large files efficiently
✅ **North American coverage** - full continental-scale radar composite

## How It Works

### 1. Data Source
- **NOAA RRFS** (Rapid Refresh Forecast System)
- **Updates**: Hourly (00z, 01z, 02z, ... 23z UTC)
- **Variable**: REFC (Composite Reflectivity) - simulated radar imagery
- **Domain**: North America (3km resolution)
- **Forecast Length**: Varies by cycle
  - Short-range cycles: ~18 hours
  - Long-range cycles: 60-84 hours

### 2. Download Process

**Every hour at :05 past (00:05, 01:05, 02:05...):**

1. **Find Latest Cycle** - Checks NOAA's S3 bucket for most recent available cycle
2. **Detect Forecast Length** - Automatically determines if cycle is short or long-range
3. **Download REFC Data** - Uses HTTP byte-range requests to extract ONLY the reflectivity field
4. **Clean Old Data** - Removes previous cycle's files AFTER new download succeeds
5. **Commit & Push** - Saves new data to repository via Git LFS

### 3. Efficiency Innovation

**The Problem**: Full GRIB files contain 935+ meteorological fields (temperature, wind, pressure, etc.)
**Our Solution**: Extract only the REFC field using HTTP Range headers

**Size Comparison**:
```
Traditional Method:
  18 forecast hours × 5 GB per file = 90 GB ❌

Our Method (Byte-Range Extraction):
  18 forecast hours × 8 MB per file = 144 MB ✅

99.85% size reduction!
```

### 4. File Structure

```
rrfs_data/
├── rrfs.t{HH}z.prslev.3km.f000.na.grib2     # Analysis (current conditions)
├── rrfs.t{HH}z.prslev.3km.f001.na.grib2     # +1 hour forecast
├── rrfs.t{HH}z.prslev.3km.f002.na.grib2     # +2 hour forecast
├── ...                                       # ... through all available hours
├── rrfs.t{HH}z.prslev.3km.f0XX.na.grib2     # Final forecast hour
├── *.grib2.idx                               # Index files for verification
└── metadata.json                             # Download metadata
```

**Filename Format**: `rrfs.t{HH}z.prslev.3km.f{FFF}.na.grib2`
- `HH`: Cycle initialization hour (00-23 UTC)
- `FFF`: Forecast hour (000-018 for short-range, 000-084 for long-range)
- `prslev`: Pressure level file (contains REFC)
- `3km`: 3 kilometer grid resolution
- `na`: North America domain

### 5. Metadata Tracking

Each download creates `metadata.json`:
```json
{
  "last_update": "2025-11-14T23:05:00Z",
  "cycle_date": "20251114",
  "cycle_hour": "23",
  "forecast_range_type": "short",
  "max_forecast_hour": 18,
  "files_downloaded": 18,
  "file_list": ["rrfs.t23z.prslev.3km.f000.na.grib2", ...],
  "note": "Files contain REFC field only (extracted via byte-range request)"
}
```

## Repository Contents

### Core Files
- **`download_rrfs_refc_optimized.py`** - Optimized REFC-only downloader with byte-range extraction
- **`.github/workflows/download_rrfs_refc.yml`** - GitHub Actions workflow (runs hourly)
- **`.gitattributes`** - Git LFS configuration for large files
- **`rrfs_data/`** - Downloaded REFC GRIB2 files (auto-updated)

### Legacy Files
- **`download_rrfs_refc.py`** - Original full-file downloader (kept for reference)

## Storage Strategy

**Rolling Latest-Cycle Storage:**
- Repository contains ONLY the most recent cycle at any time
- When new cycle is downloaded, old cycle is automatically cleaned up
- Total storage: ~144 MB (short-range) to ~672 MB (long-range)
- Git LFS handles large binary files efficiently

**Why Clean After Download?**
- Ensures you always have SOME data (if download fails, old data remains)
- Only removes old data after new data successfully downloads
- More reliable than cleaning before download

## Working with the Data

### Reading REFC in Python

**Using pygrib:**
```python
import pygrib

# Open GRIB file
grib = pygrib.open('rrfs_data/rrfs.t23z.prslev.3km.f001.na.grib2')

# Extract REFC field
refc = grib.select(name='Composite reflectivity')[0]
data = refc.values  # Reflectivity values in dBZ
lats, lons = refc.latlons()  # Latitude/longitude grid

print(f"REFC shape: {data.shape}")
print(f"REFC range: {data.min():.1f} to {data.max():.1f} dBZ")
```

**Using xarray + cfgrib:**
```python
import xarray as xr

ds = xr.open_dataset(
    'rrfs_data/rrfs.t23z.prslev.3km.f001.na.grib2',
    engine='cfgrib',
    backend_kwargs={'filter_by_keys': {'typeOfLevel': 'atmosphere'}}
)

refc = ds['refc']  # Composite reflectivity DataArray
print(refc)
```

**Using wgrib2 (command line):**
```bash
# List contents
wgrib2 rrfs_data/rrfs.t23z.prslev.3km.f001.na.grib2

# Extract REFC to CSV
wgrib2 rrfs_data/rrfs.t23z.prslev.3km.f001.na.grib2 -match "REFC" -csv refc.csv

# Convert to NetCDF
wgrib2 rrfs_data/rrfs.t23z.prslev.3km.f001.na.grib2 -match "REFC" -netcdf refc.nc
```

## Manual Usage

### Running Locally

```bash
# Install dependencies
pip install requests

# Download latest cycle (all forecast hours)
python download_rrfs_refc_optimized.py --domain na --download-all-hours

# Download specific cycle
python download_rrfs_refc_optimized.py --date 20251114 --hour 23 --download-all-hours

# Download limited forecast hours
python download_rrfs_refc_optimized.py --domain na --num-forecasts 6

# Download different domain (smaller files)
python download_rrfs_refc_optimized.py --domain conus --download-all-hours
```

### Script Options

- `--domain {na,conus,ak,hi,pr}` - Geographic domain (default: na)
- `--download-all-hours` - Download ALL available forecast hours (recommended)
- `--num-forecasts N` - Limit to N forecast hours
- `--date YYYYMMDD` - Download specific date
- `--hour HH` - Download specific cycle hour (00-23)

## GitHub Actions Workflow

### Schedule
- **Frequency**: Every hour at :05 past the hour
- **Trigger**: `5 * * * *` (cron schedule)
- **Also runs**: On push to branch, manual trigger

### Workflow Steps
1. Checkout repository with Git LFS
2. Install Python dependencies
3. Run optimized downloader
4. Commit new data (if download succeeded)
5. Clean old data from previous cycle
6. Push to repository

### Permissions
- **contents: write** - Required to commit and push data

## Technical Details

### Byte-Range Extraction Method

The key innovation is using HTTP Range headers to download only the REFC portion:

1. **Fetch .idx file** - Contains byte offsets for all fields in GRIB2 file
2. **Find REFC offset** - Parse index to locate REFC field position
3. **Range request** - Download only bytes containing REFC data
4. **Save result** - Write REFC-only GRIB2 file

Example:
```
Full file: 5 GB (fields 1-935)
REFC location: Field #36 at bytes 245,393,432 to 253,087,912
Download: Only those 7.69 MB
Savings: 99.85%
```

### Data Quality

- **Source**: Official NOAA RRFS forecasts from AWS S3 bucket
- **Resolution**: 3 km grid spacing
- **Coverage**: Full North American domain
- **Update Frequency**: Hourly
- **Latency**: ~5 minutes (RRFS processing time)

### Storage Requirements

**Repository Storage:**
- Short-range cycle (18 hrs): ~144 MB
- Long-range cycle (60 hrs): ~480 MB
- Long-range cycle (84 hrs): ~672 MB

**GitHub Limits:**
- Free tier: 1 GB Git LFS storage, 1 GB/month bandwidth
- Files stored efficiently with LFS
- Old cycles cleaned automatically

## Troubleshooting

### "No files available"
- RRFS may be temporarily offline for maintenance
- Check https://registry.opendata.aws/noaa-rrfs/ for status
- Workflow will retry next hour

### "403 Permission denied"
- Ensure workflow has `contents: write` permission
- Check repository settings > Actions > General > Workflow permissions

### "No space left on device"
- Reduce forecast hours with `--num-forecasts`
- Or switch to smaller domain (conus instead of na)

## Resources

- **NOAA RRFS**: https://gsl.noaa.gov/focus-areas/unified_forecast_system/rrfs
- **AWS Data Registry**: https://registry.opendata.aws/noaa-rrfs/
- **GRIB2 Documentation**: https://www.nco.ncep.noaa.gov/pmb/docs/grib2/
- **pygrib**: https://github.com/jswhit/pygrib
- **cfgrib**: https://github.com/ecmwf/cfgrib
- **wgrib2**: https://www.cpc.ncep.noaa.gov/products/wesley/wgrib2/

## License

This automation script is provided as-is for downloading public NOAA data. RRFS data is freely available through NOAA's Open Data Dissemination program.

## Contributing

Issues and improvements welcome! This is an open-source project for accessing public weather data.

---

**Built with**:
- Python 3.11
- GitHub Actions
- Git LFS
- NOAA RRFS Data
