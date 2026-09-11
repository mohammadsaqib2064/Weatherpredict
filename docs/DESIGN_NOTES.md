# Design notes — WeatherPredict UI (Streamlit)

Climate / Earth-science product language for **EarthScape Climate Agency**.

## Global system

- **Palette:** ocean navy `#0B3D5C`, glacier `#A8D0E6`, warm sand ground `#F7F5F1`. Coral `#D96B4C` only for alerts, anomalies, failures. Configured in `.streamlit/config.toml` and `weatherpredict/ui/theme.py`.
- **Type:** Space Grotesk (display) + IBM Plex Sans (body) injected in theme CSS.
- **Charts:** Plotly only, diverging cool↔warm scales, heatmaps pinned `zmin=-1, zmax=1`.
- **Layout:** asymmetric columns, information-dense. No purple gradient heroes, no glassmorphism, no twin CTAs.

## Screens

Administrator: Operations console, Data & pipelines, Users, Alert rules.
Analyst: Workspace (scoped to `region_focus`), then shared investigation pages.
Shared: Explore, Trends, Anomalies, Correlations, Live, Ingest, Notifications, Support.

Login is a split rail + single form — one action, not a marketing hero.
