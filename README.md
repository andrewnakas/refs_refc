# RRFS REFC Data Downloader

Automated download of NOAA RRFS (Rapid Refresh Forecast System) composite reflectivity (REFC) GRIB2 data using GitHub Actions.

## Overview

This repository automatically downloads RRFS composite reflectivity forecast data from NOAA's AWS S3 bucket and stores it on a rolling basis.

### Data Source

- **Source**: NOAA RRFS on AWS S3 (`noaa-rrfs-pds`)
- **Data Type**: GRIB2 format (pressure level, 3km resolution)
- **Variable**: Composite Reflectivity (REFC)
- **Domain**: North America (NA)
- **Update Frequency**: Hourly cycles (when operational)
- **Forecast Hours Downloaded**: 3 (f000, f001, f002)
- **File Size**: ~4-6 GB per file

## Features

- ✅ Automatic download of latest RRFS REFC data (North American domain)
- ✅ Latest-only storage (deletes old cycle before downloading new)
- ✅ Runs every 3 hours via GitHub Actions
- ✅ Triggers on push to branch
- ✅ Manual trigger available
- ✅ Git LFS support for large files (4-6 GB each)
- ✅ Space-efficient: Downloads 3 forecast hours (~12-18 GB total)

## Repository Structure

```
.
├── .github/
│   └── workflows/
│       └── download_rrfs_refc.yml    # GitHub Actions workflow
├── download_rrfs_refc.py              # Python download script
├── rrfs_data/                         # Downloaded GRIB files (auto-created)
│   ├── *.grib2                        # RRFS forecast files
│   └── metadata.json                  # Download metadata
└── README.md                          # This file
```

## Usage

### Automatic Downloads (GitHub Actions)

The workflow runs automatically:
- **On schedule**: Every 3 hours
- **On push**: When code is pushed to the branch
- **Manual**: Via GitHub Actions "Run workflow" button

### Manual Local Download

```bash
# Install dependencies
pip install requests

# Run the download script
python download_rrfs_refc.py

# With custom options
python download_rrfs_refc.py --max-files 100
python download_rrfs_refc.py --date 20241201 --hour 12
```

### Script Options

- `--domain DOMAIN`: Geographic domain (na, conus, ak, hi, pr) - default: na
- `--num-forecasts N`: Number of forecast hours to download (default: 3)
- `--clean-before-download`: Delete all old data before downloading new cycle
- `--date YYYYMMDD`: Download specific date
- `--hour HH`: Download specific cycle hour (00-23)

## Data Files

### GRIB2 Files

Files follow the naming pattern: `rrfs.tHHz.prslev.3km.fXXX.na.grib2`

- `HH`: Initialization hour (00-23 UTC)
- `XXX`: Forecast hour (000-002 in this configuration)
- `prslev`: Pressure level data (includes REFC)
- `3km`: 3 kilometer resolution
- `na`: North America domain

### Metadata

The `metadata.json` file contains:
```json
{
  "last_update": "2025-11-14T12:00:00",
  "cycle_date": "20251114",
  "cycle_hour": "09",
  "files_downloaded": 10,
  "file_list": ["rrfs.t09z.natlev.f000.grib2", ...]
}
```

## Working with GRIB Data

### Reading GRIB Files

To work with the downloaded GRIB2 files, you can use:

**Python (pygrib)**:
```python
import pygrib

grib = pygrib.open('rrfs_data/rrfs.t12z.natlev.f001.grib2')
refc = grib.select(name='Composite reflectivity')[0]
data = refc.values
lats, lons = refc.latlons()
```

**Python (xarray + cfgrib)**:
```python
import xarray as xr

ds = xr.open_dataset('rrfs_data/rrfs.t12z.natlev.f001.grib2',
                      engine='cfgrib',
                      backend_kwargs={'filter_by_keys': {'typeOfLevel': 'atmosphere'}})
refc = ds['refc']
```

**Command line (wgrib2)**:
```bash
# List contents
wgrib2 rrfs_data/rrfs.t12z.natlev.f001.grib2

# Extract REFC to CSV
wgrib2 rrfs_data/rrfs.t12z.natlev.f001.grib2 -match "REFC" -csv output.csv
```

## Important Notes

### Data Availability

RRFS data is operational and updated hourly. Check the [NOAA RRFS AWS Registry](https://registry.opendata.aws/noaa-rrfs/) for current status.

### Storage Considerations

- **File size**: Each NA domain GRIB2 file is ~4-6 GB
- **Default configuration**: 3 forecast hours = ~12-18 GB total
- **Storage strategy**: Only the latest cycle is kept (old data deleted before new download)
- **Git LFS required**: Large files are stored using Git LFS
- **GitHub Actions space**: Runner has ~14 GB available, fits 3 files comfortably

### GitHub Actions Limits

- **Workflow runs**: Limited minutes per month (2,000 for free accounts)
- **Storage**: LFS and artifact storage counted separately
- Consider adjusting schedule frequency based on needs

## Configuration

### Adjusting Update Frequency

Edit `.github/workflows/download_rrfs_refc.yml`:

```yaml
schedule:
  - cron: '0 */3 * * *'  # Every 3 hours (change as needed)
```

Common schedules:
- Every hour: `'0 * * * *'`
- Every 6 hours: `'0 */6 * * *'`
- Daily at midnight UTC: `'0 0 * * *'`

### Adjusting Forecast Hours

In the workflow file or when running locally:

```yaml
# Download more forecast hours (ensure you have enough disk space!)
run: python download_rrfs_refc.py --domain na --num-forecasts 6 --clean-before-download
```

**Note**: Each NA file is ~5 GB. GitHub Actions runners have ~14 GB free space.
- 2 forecast hours: ~10 GB (safe)
- 3 forecast hours: ~15 GB (current default, may be tight)
- 6 forecast hours: ~30 GB (will fail - not enough space!)

### Using Different Domains

For smaller file sizes, use CONUS domain instead:

```yaml
# CONUS files are ~800 MB each - much smaller!
run: python download_rrfs_refc.py --domain conus --num-forecasts 18 --clean-before-download
```

## Resources

- [NOAA RRFS on AWS](https://registry.opendata.aws/noaa-rrfs/)
- [RRFS Information (NOAA GSL)](https://gsl.noaa.gov/focus-areas/unified_forecast_system/rrfs)
- [GRIB2 Documentation](https://www.nco.ncep.noaa.gov/pmb/docs/grib2/)
- [Python pygrib](https://github.com/jswhit/pygrib)
- [wgrib2 Tool](https://www.cpc.ncep.noaa.gov/products/wesley/wgrib2/)

## Support

For issues with:
- **This repository**: Open an issue
- **RRFS data access**: Contact [email protected]
- **GitHub Actions**: See [GitHub Actions Documentation](https://docs.github.com/actions)

## License

This script is provided as-is for downloading public NOAA data. RRFS data is publicly available through NOAA's Open Data Dissemination program.
