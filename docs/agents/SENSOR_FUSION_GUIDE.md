# SENSOR FUSION GUIDE

Fusion groups by finding kind, label, grid cell and capture time. Each group retains its original evidence IDs exactly once. The synthetic score takes the minimum contributing score. Different terrain labels at the same cell in the current view trigger an explicit conflict and additional observation request. A possible person and terrain at one cell can coexist. The implementation performs exact capture-time alignment.
