# Environmental data standards

## Weather variables (CF-style mapping)

| Stored field | CF standard name | Units |
|--------------|------------------|-------|
| `temp_c` | `air_temperature` | °C (stored; CF prefers K) |
| `precip_mm` | `precipitation_amount` | mm |
| `humidity_pct` | `relative_humidity` | % |
| `pressure_hpa` | `air_pressure` | hPa |
| `wind_ms` | `wind_speed` | m s-1 |

**Deliberate non-conformance:** temperatures stay in Celsius for analyst readability; time is UTC ISO-8601 rather than CF numeric time axes; NetCDF is not ingested in the local demo (CSV/JSON/XLSX only).

## Satellite metadata (STAC-oriented)

`satellite_imagery` is a **scene catalogue**, not a raster store. Field mapping:

| Stored | STAC |
|--------|------|
| `scene_id` | `id` |
| `bbox` | `bbox` |
| `acquired_at` | `datetime` |
| `cloud_cover_pct` | `properties.eo:cloud_cover` |
| `storage_uri` | `assets` href (catalogue key; file may not exist on disk) |

No COG/GeoTIFF is read. A production feed would replace the generator with a STAC API harvest.
