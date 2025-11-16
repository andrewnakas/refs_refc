# RRFS Visualization Research - NOAA Developer Approaches

## Researchers from the PDF

From the NOAA UIFCW 2023 presentation:

1. **Curtis Alexander** - GSL Deputy Director at NOAA's Global Systems Laboratory (NOAA-GSL)
2. **Jacob Carley** - Physical Scientist at NOAA NCEP Environmental Modeling Center (NOAA-EMC)
3. **Matt Pyle** - RRFS Project Lead and Code Manager (matthew.pyle@noaa.gov)

## Key GitHub Repositories

### 1. NOAA-GSL/pygraf
- **Purpose**: Official Python graphics package for RAP/HRRR/FV3/RRFS data
- **Status**: Replaced NCL as the real-time graphics creation package at NOAA GSL
- **Projection Approach**: Uses **Basemap** (not Cartopy) with Lambert Conformal Conic
- **Key Finding**: Does **NOT handle native rotated pole grids** - works with regridded data only
- **Aspect Ratio**: Managed through corner coordinates, Basemap handles scaling automatically
- **Link**: https://github.com/NOAA-GSL/pygraf

### 2. NOAA-EMC/rrfs-workflow
- **Purpose**: Main workflow repository for RRFSv1
- **Maintainer**: Matt Pyle (Code Manager)
- **Link**: https://github.com/NOAA-EMC/rrfs-workflow

### 3. NOAA-GSL/rrfs_utl
- **Purpose**: Utilities for RRFS applications
- **Language**: Primarily Fortran (97%)
- **Link**: https://github.com/NOAA-GSL/rrfs_utl

### 4. NOAA-GSL/unified-graphics
- **Purpose**: Experimental visualization system for 3D-RTMA & RRFS model output
- **Status**: **Ended September 2024**
- **Link**: https://github.com/NOAA-GSL/unified-graphics

### 5. blaylockbk/Herbie
- **Author**: Brian Blaylock (University of Utah, community developer)
- **Purpose**: Download and visualize HRRR, RAP, RRFS, GFS data
- **Projection Support**: Includes Cartopy integration (early development)
- **Key Feature**: Abstracts grid complexity, provides xarray datasets with projection metadata
- **Link**: https://github.com/blaylockbk/Herbie

## Critical Grid Information

### RRFS Has TWO Different Grids:

#### 1. CONUS Grid (prslev files)
- **Projection**: Lambert Conformal Conic
- **Dimensions**: 1,799 × 1,059 points
- **Spacing**: 3 km
- **Parameters**:
  - Standard parallels: 38.5°N
  - Central meridian: 262.5°W
  - Coverage: Contiguous United States

#### 2. Native Grid (.na files) ⭐ **THIS IS WHAT WE'RE USING**
- **Projection**: **Rotated Latitude-Longitude**
- **Dimensions**: **4,881 × 2,961 points** (aspect ratio ~1.65:1)
- **Spacing**: 0.025°
- **Rotated Pole Parameters**:
  - Pole Latitude: **-35.0°N** (south pole of rotated grid)
  - Pole Longitude: **247.0°E** (or -113.0°W)
  - Grid Center: 55.0°N, -112.5°W
- **Coverage**: Full North America domain

## The "Not Square" Issue

### Why the PDF Says "Not Square":
1. The native grid dimensions are **4,881 × 2,961** - clearly not square (ratio ~1.65:1)
2. In **rotated coordinates**, this grid IS roughly rectangular
3. In **geographic coordinates**, the grid appears curved/distorted

### Why Our Map Might Look Square:
- **Leaflet** (our current approach) only supports Web Mercator/PlateCarree projections
- We're regridding from rotated lat-lon to regular lat-lon
- The regridded extent (15°-75°N, -180°W to -40°W) might not match the original aspect ratio
- Leaflet's viewport aspect ratio is controlled by the div size, not the data

## Proper Visualization Approaches

### Option A: Static Maps with Cartopy (NOAA approach)
```python
import cartopy.crs as ccrs

# Create RotatedPole projection
rp = ccrs.RotatedPole(
    pole_longitude=247.0 - 180,  # Cartopy convention: subtract 180
    pole_latitude=-35.0,
    globe=ccrs.Globe(semimajor_axis=6371229, semiminor_axis=6371229)
)

# Plot with proper aspect ratio
fig = plt.figure(figsize=(16, 16/1.65))  # Match 1.65:1 aspect
ax = plt.axes(projection=ccrs.PlateCarree())
ax.pcolormesh(lons, lats, data, transform=ccrs.PlateCarree())
```

### Option B: Herbie + Cartopy (Community approach)
```python
from herbie import Herbie
import matplotlib.pyplot as plt

H = Herbie('2025-01-01', model='rrfs', product='nat', fxx=0)
ds = H.xarray('REFC')
ax = ds.refc.plot(transform=ds.crs)  # Automatic projection handling
```

### Option C: Leaflet with Proper Aspect (Current approach - needs fixing)
- Regrid to regular lat-lon with **aspect ratio matching original grid**
- Ensure output grid is ~1.65:1 ratio
- Set Leaflet div height to maintain aspect ratio

## Key Learnings from Stack Overflow

When using Cartopy's RotatedPole:
1. **pole_longitude** in Cartopy = basemap's o_lon_p **minus 180**
2. Use `transform_points()` to set extent correctly
3. Don't use `set_extent()` directly - transform coordinates first

Example:
```python
xs, ys, zs = rp.transform_points(
    ccrs.PlateCarree(),
    np.array([lon_min, lon_max]),
    np.array([lat_min, lat_max])
).T
ax.set_xlim(xs)
ax.set_ylim(ys)
```

## Recommendations

### For Web Visualization (Leaflet):
1. Calculate proper output grid aspect ratio to match 4881×2961 (1.65:1)
2. Ensure regridding preserves this aspect ratio
3. Set container CSS to maintain aspect ratio

### For Static Images (Better for Research):
1. Use Cartopy with RotatedPole projection
2. Display in native rotated coordinates or properly transformed geographic coords
3. Reference: See `create_static_map.py` for implementation

### For Production (NOAA approach):
1. Regrid to Lambert Conformal (like prslev files)
2. Use pygraf-style Basemap approach
3. Or wait for NOAA's next-gen visualization tools

## References

- **UFS SRWeather App**: https://ufs-srweather-app.readthedocs.io
- **Herbie Documentation**: https://herbie.readthedocs.io
- **NOAA RRFS Data**: https://registry.opendata.aws/noaa-rrfs/
- **Cartopy RotatedPole**: https://scitools.org.uk/cartopy/docs/latest/gallery/lines_and_polygons/rotated_pole.html
- **Stack Overflow Solution**: https://stackoverflow.com/questions/35760566/plotting-rotated-pole-projection-in-cartopy

## Contact Information

- **Matt Pyle** (RRFS Project Lead): matthew.pyle@noaa.gov
- **Jacob Carley** (EMC): jacob.carley@noaa.gov
- **Curtis Alexander** (GSL Deputy Director): via NOAA GSL

## Summary

**The visualization issue is that RRFS .na files use a 4881×2961 rotated lat-lon grid, but we're displaying it on Leaflet which can't handle rotated projections. NOAA's official tools (pygraf) work with regridded Lambert Conformal data instead of native grids. For proper aspect ratio, we need to either:**

1. **Switch to static Cartopy-based maps** (proper solution)
2. **Fix the regridding to maintain 1.65:1 aspect ratio** (Leaflet compromise)
3. **Use Herbie for data access** (community best practice)
