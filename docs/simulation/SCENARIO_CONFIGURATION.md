# SCENARIO CONFIGURATION

Load a registered JSON filename or pass its path to --scenario. Example files are under configs/scenarios. Coordinates start at (0,0) in the upper left. Tick durations are milliseconds; radius and communication range are grid cells. Sensor latency and packet delay count steps. Configuration rejects overlapping initial terrain, insufficient placement space and out-of-bounds coordinates. Events run after action commitment. Outage steps disable radio; weak_radio disables local connectivity. The partition flag separates peer links across the map midpoint.
