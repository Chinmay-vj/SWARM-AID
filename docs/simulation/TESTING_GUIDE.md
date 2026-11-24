# TESTING GUIDE

Install the dev and simulation extras, then run python -m pytest -q. The integration suite runs seven full episodes and replays their metrics, checks isolation, dropout, false positives, movement, latency and validates the parallel adapter using parallel_api_test. SDL dummy video exercises rendering without an interactive desktop.
