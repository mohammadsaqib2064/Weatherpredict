# Test data used in the project

Curated samples for ingestion validation and the project deliverable "Test Data Used".

| File | Type | Rows | Notes |
|------|------|------|-------|
| `weather_sample.csv` | weather-station | 5 | One incomplete row (missing `temp_c`) expected skipped or imported with nulls |
| `sensor_sample.csv` | sensor | 5 | One incomplete `uv_index` |
| `satellite_sample.json` | satellite metadata | 2 | One missing `cloud_cover_pct` |

Expected behaviour: complete rows import; incomplete optional fields are kept and flagged rather than crashing the job.

These files are **not** the full synthetic corpus. Generate that with:

```
python -m weatherpredict.seed --with-data --years 2 --train
```
