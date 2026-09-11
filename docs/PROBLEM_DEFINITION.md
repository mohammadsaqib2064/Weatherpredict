# Problem definition

EarthScape Climate Agency monitors climate change using satellite, weather-station and environmental-sensor data. Operators need a single website to ingest that data, store it, process it in batch and near-real-time, detect anomalies, forecast regional trends, and alert people when thresholds are crossed.

**Stakeholders:** Administrators (operations, access, pipelines) and Analysts (investigation).

**In scope:** authentication with those two roles; CSV/JSON/XLSX ingestion; MongoDB storage; local batch clean/aggregate; simulated live sensors merged with batch; scikit-learn trend, anomaly and correlation models; in-app threshold alerts; support tickets; Streamlit dashboards.

**Out of scope (documented substitutions):** a real Hadoop cluster, HDFS, MapReduce job submission, Impala, Tableau, live satellite rasters, multi-node 99% uptime hosting.
