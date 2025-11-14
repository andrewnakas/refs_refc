# RRFS REFC Data Downloader

Automated download of NOAA RRFS (Rapid Refresh Forecast System) composite reflectivity (REFC) GRIB2 data using GitHub Actions.

## Overview

This repository automatically downloads RRFS composite reflectivity forecast data from NOAA's AWS S3 bucket and stores it on a rolling basis.

### Data Source

- **Source**: NOAA RRFS on AWS S3 (`noaa-rrfs-pds`)
- **Data Type**: GRIB2 format
- **Variable**: Composite Reflectivity (REFC)
- **Update Frequency**: Hourly cycles (when operational)
- **Forecast Length**: Up to 84 hours

## Features

- ✅ Automatic download of latest RRFS REFC data
- ✅ Rolling storage (keeps 50 most recent files by default)
- ✅ Runs every 3 hours via GitHub Actions
- ✅ Triggers on push to branch
- ✅ Manual trigger available
- ✅ Metadata tracking with JSON logs

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

- `--max-files N`: Keep N most recent GRIB files (default: 50)
- `--date YYYYMMDD`: Download specific date
- `--hour HH`: Download specific cycle hour (00-23)

## Data Files

### GRIB2 Files

Files follow the naming pattern: `rrfs.tHHz.natlev.fXXX.grib2`

- `HH`: Initialization hour (00-23 UTC)
- `XXX`: Forecast hour (000-084)
- `natlev`: Native level data (includes all fields)

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

⚠️ **Note**: Real-time RRFS output was temporarily suspended starting December 2024 for retrospective testing. The system is expected to return to operational status. Check the [NOAA RRFS AWS Registry](https://registry.opendata.aws/noaa-rrfs/) for current status.

### Storage Considerations

- Each GRIB2 file is typically 20-100 MB
- Default limit of 50 files = approximately 1-5 GB storage
- Adjust `--max-files` based on your GitHub storage limits
- GitHub repositories have a soft limit of 1 GB

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

### Adjusting Storage Limit

In the workflow file or when running locally:

```yaml
run: python download_rrfs_refc.py --max-files 100
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
