# Compliance (GDPR-oriented)

WeatherPredict is a demonstration climate platform. Personal data held:

| Field | Collection | Purpose | Retention |
|-------|------------|---------|-----------|
| username, email, role, region_focus | `users` | Authentication and data scoping | Account lifetime; delete the user document to remove |
| notifications addressed to a username | `notifications` | Alerts | Until deleted or account removed |
| tickets / feedback | `support_tickets`, `feedback` | Support | Until resolved + 1 year (operational policy) |

Climate observations (`weather_station_records`, `sensor_readings`, `satellite_imagery`, `anomalies`) are **not personal data**.

**Deletion path:** an Administrator deactivates then removes the `users` document. Related `notifications` for that username should be deleted in the same change. Climate data is retained.

No phone numbers or other extra PII are stored. Production deployments must terminate TLS at a reverse proxy and use an authenticated MongoDB URI.
