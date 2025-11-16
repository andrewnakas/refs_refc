# RRFS REFC Visualization

This directory contains the web visualization for RRFS Composite Reflectivity (REFC) forecast data.

## Contents

- **index.html** - Interactive Leaflet map showing animated radar reflectivity forecasts
- **tiles/** - PNG tiles of REFC data for each forecast hour
- **data.json** - Metadata about forecast data and tile locations

## Live Visualization

The visualization is automatically deployed to GitHub Pages whenever new RRFS data is downloaded.

Visit: https://[username].github.io/[repository]/

## Features

- **Interactive Map**: Pan and zoom to explore forecast radar coverage
- **Animation Controls**: Play/pause and step through forecast hours
- **NWS Color Scale**: Standard weather radar reflectivity colors
- **Metadata Display**: Shows cycle time, valid time, and data statistics

## Data Source

- **Model**: NOAA Rapid Refresh Forecast System (RRFS)
- **Variable**: REFC (Composite Reflectivity)
- **Domain**: North America (3km resolution)
- **Update Frequency**: Hourly
- **Forecast Length**: 18-84 hours (varies by cycle)

## Technical Details

The visualization uses:
- Leaflet.js for interactive mapping
- GRIB2 data processed to PNG tiles with georeferencing
- Responsive design for desktop and mobile
- Dark theme optimized for radar visualization

---

**Automated by GitHub Actions**
