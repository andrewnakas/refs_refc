# RRFS REFC Visualization

This directory contains the web visualization for RRFS Composite Reflectivity (REFC) forecast data.

## Two Visualization Approaches

### 1. Static Maps with Proper Projection (Default) ⭐
- **File**: `index.html` - Gallery viewer with animation controls
- **Maps**: `maps/` - Cartopy-generated PNGs with correct rotated pole projection
- **Metadata**: `maps_data.json` - Grid info and forecast metadata
- **Projection**: Native rotated lat-lon (4881×2961, aspect 1.65:1)
- **Why**: Mathematically correct representation of RRFS native grid

### 2. Interactive Leaflet Map (Legacy)
- **File**: `index_leaflet.html` - Interactive pan/zoom map
- **Tiles**: `tiles/` - PNG tiles regridded to PlateCarree
- **Metadata**: `data.json` - Tile locations and bounds
- **Projection**: Regridded to regular lat-lon for Web Mercator compatibility
- **Note**: Cannot display native rotated pole projection (Leaflet limitation)

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
