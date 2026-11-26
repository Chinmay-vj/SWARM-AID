# Phase 10D sensor dataset validation

**25 November 2026 | Local inspection complete; release approval pending.** The corrected source directory is `D:\SWARM-AID\datasets\raw\sensors`. Four files occupy **7,929,937 bytes**. The UCI spreadsheet and CSV cover the same hours. Across the three sources there are 62,630 smoke samples, 9,357 air-quality hours and 36 hydrological summary records. These units represent different observations and should remain separate. NASA POWER is outside scope.

## Method and readiness

Each CSV was parsed in full, checking row width, timestamp or period keys, duplicates and missing values. All numeric smoke and nonsentinel UCI measurements parsed as finite numbers. Tables give flag counts outside the inclusive-quartile 1.5 × IQR fences. These are distributional flags, not automatic error labels. USGS flags use only comparable parameter, parent statistic and interval groups of at least four. No raw value was replaced or removed. Local SHA-256 digests identify the bytes checked. Publisher checksum equivalence, download URLs and download dates were unavailable. Only the Excel workbook is a compressed container in this directory.

The Phase 10A registry records local availability independently of governance. All three entries remain unverified for licence and pending for privacy. The validator accepted 14 registry entries, and its asset checker independently reread the three CSV hashes. No sample-level release manifest or training partition was created. **Phase 10E is not ready for approved model use** pending rights/privacy review and task-specific provenance and split decisions.

## Smoke Detection IoT measurements

smoke_detection_iot.csv: 62,630 nonempty rows, 0 empty records, 16 columns, 0 redundant full rows.

| Column | Parsed type | Unit / scale | Missing | Observed nonmissing range | IQR flags |
|---|---|---|---:|---|---:|
| Temperature[C] | decimal | °C | 0 | -22.01 to 59.93 | 3908 |
| Humidity[%] | decimal | % RH | 0 | 10.74 to 75.2 | 5083 |
| TVOC[ppb] | integer | ppb | 0 | 0 to 60000 | 2463 |
| eCO2[ppm] | integer | ppm equivalent | 0 | 400 to 60000 | 12076 |
| Raw H2 | integer | raw instrument | 0 | 10668 to 13803 | 1953 |
| Raw Ethanol | integer | raw instrument | 0 | 15317 to 21410 | 1951 |
| Pressure[hPa] | decimal | hPa | 0 | 930.852 to 939.861 | 12632 |
| PM1.0 | decimal | PM mass¹ | 0 | 0 to 14333.7 | 1982 |
| PM2.5 | decimal | PM mass¹ | 0 | 0 to 45432.3 | 1840 |
| NC0.5 | decimal | particle count/volume¹ | 0 | 0 to 61482 | 2120 |
| NC1.0 | decimal | particle count/volume¹ | 0 | 0 to 51914.7 | 1858 |
| NC2.5 | decimal | particle count/volume¹ | 0 | 0 to 30026.4 | 3674 |

Row index, UTC epoch seconds, CNT and Fire Alarm parse as integers. Index is sequential. Exact duplicate UTC keys beyond the first: 0.

| Counter-contiguous run | UTC start | UTC end | Rows | Alarm 0 | Alarm 1 |
|---:|---|---|---:|---:|---:|
| 1 | 2022-06-09T00:08:51+00:00 | 2022-06-09T07:05:24+00:00 | 24994 | 3178 | 21816 |
| 2 | 2022-06-09T07:55:43+00:00 | 2022-06-09T14:52:16+00:00 | 24994 | 3178 | 21816 |
| 3 | 2022-06-10T23:16:45+00:00 | 2022-06-10T23:35:58+00:00 | 1154 | 33 | 1121 |
| 4 | 2022-06-08T18:16:27+00:00 | 2022-06-08T19:52:10+00:00 | 5744 | 5742 | 2 |
| 5 | 2022-06-13T12:45:08+00:00 | 2022-06-13T14:20:51+00:00 | 5744 | 5742 | 2 |

Source-order UTC deltas in seconds (delta: frequency): {1: 62625, 3019: 1, 116669: 1, -191971: 1, 406378: 1}. Alarm distribution: {0: 17873, 1: 44757}.

## UCI Air Quality measurements

AirQualityUCI.csv: 9,357 nonempty rows, 114 empty records, 17 columns, 0 redundant full rows.

| Column | Parsed type | Unit / scale | Missing | Observed nonmissing range | IQR flags |
|---|---|---|---:|---|---:|
| CO(GT) | decimal | mg/m³ | 1683 | 0.1 to 11.9 | 215 |
| PT08.S1(CO) | integer | response | 366 | 647 to 2040 | 118 |
| NMHC(GT) | integer | µg/m³ | 8443 | 7 to 1189 | 55 |
| C6H6(GT) | decimal | µg/m³ | 366 | 0.1 to 63.7 | 228 |
| PT08.S2(NMHC) | integer | response | 366 | 383 to 2214 | 65 |
| NOx(GT) | integer | ppb | 1639 | 2 to 1479 | 435 |
| PT08.S3(NOx) | integer | response | 366 | 322 to 2683 | 241 |
| NO2(GT) | integer | µg/m³ | 1642 | 2 to 340 | 107 |
| PT08.S4(NO2) | integer | response | 366 | 551 to 2775 | 97 |
| PT08.S5(O3) | integer | response | 366 | 221 to 2523 | 93 |
| T | decimal | °C | 366 | -1.9 to 44.6 | 3 |
| RH | decimal | % RH | 366 | 9.2 to 88.7 | 0 |
| AH | decimal | absolute humidity² | 366 | 0.1847 to 2.231 | 2 |

CSV measurement cells tagged −200: 16,244 of 121,641. Records with at least one marker: 8,530. Blank measurement cells: 0. Date and time span 2004-03-10 18:00:00 through 2005-04-04 14:00:00 in the source clock. Duplicate date/time keys beyond the first: 0. Successive deltas in seconds: {3600: 9356}.

Excel ZIP CRC passed for 13 members. The worksheet matches all 9,357 record timestamps and all 15 headers. Missing-marker discrepancies: 0. Numeric cells differing from CSV by more than 1e−8: 72,882. Count the two representations once and pin the chosen precision.

## USGS Water Data measurements

USGSWater.csv: 36 nonempty rows, 0 empty records, 34 columns, 0 redundant full rows.

All headers in source order: monitoring_location_id, parameter_code, parent_time_series_id, parent_statistic_id, parent_statistic_name, start_date, end_date, interval_type, monitoring_location_name, site_type, site_type_code, country_code, state_code, county_code, unit_of_measure, x, y, arithmetic_mean, maximum, median, minimum, p5, p10, p25, p50, p75, p90, p95, arithmetic_mean_sample_count, maximum_sample_count, median_sample_count, minimum_sample_count, percentile_sample_count, approval_status.

Blank fields: 10. Redundant series/period keys: 0. Inconsistent percentile, median or mean bounds: 0. Rows whose five sample counts do not all match inclusive calendar days: 5. Date envelope 2016-10-01 through 2018-09-30. Status values: {'approved': 36}.

Per-column null counts (other columns zero): {'p5': 5, 'p95': 5}.

| Station | Parameter | Native unit | Parent statistic | Period type | Rows | Min–max of reported interval means | 1.5 IQR flags on means |
|---|---|---|---|---|---:|---|---:|
| USGS-08074500 | 00060 | ft^3/s | Max | calendar_year | 1 | 1052.48–1052.48 | n/a (<4) |
| USGS-08074500 | 00060 | ft^3/s | Max | month | 1 | 1052.48–1052.48 | n/a (<4) |
| USGS-08074500 | 00060 | ft^3/s | Max | water_year | 1 | 476.533–476.533 | n/a (<4) |
| USGS-08074500 | 00060 | ft^3/s | Mean | calendar_year | 1 | 447.355–447.355 | n/a (<4) |
| USGS-08074500 | 00060 | ft^3/s | Mean | month | 12 | 65.967–3327.77 | 1 |
| USGS-08074500 | 00060 | ft^3/s | Mean | water_year | 2 | 139.068–448.939 | n/a (<4) |
| USGS-08074500 | 00060 | ft^3/s | Min | calendar_year | 1 | 107.194–107.194 | n/a (<4) |
| USGS-08074500 | 00060 | ft^3/s | Min | month | 1 | 107.194–107.194 | n/a (<4) |
| USGS-08074500 | 00060 | ft^3/s | Min | water_year | 1 | 59.199–59.199 | n/a (<4) |
| USGS-08074500 | 00065 | ft | Mean | calendar_year | 1 | 8.486–8.486 | n/a (<4) |
| USGS-08074500 | 00065 | ft | Mean | month | 12 | 7.887–9.309 | 0 |
| USGS-08074500 | 00065 | ft | Mean | water_year | 2 | 8.37–8.629 | n/a (<4) |

## Local file identity

| File under datasets/raw/sensors | Bytes | SHA-256 |
|---|---:|---|
| AirQualityUCI.csv | 785,065 | 13277ae5d8581e80b7be09d47c7d3d06fe9b8e957078f2cf6e859f955e62f996 |
| AirQualityUCI.xlsx | 1,298,197 | c92d102bb35cd4c0b42c0b6a1336c4065ccdca7069f80a6890ee1b7e3124bd5d |
| smoke_detection_iot.csv | 5,834,376 | 7bbf5deaab4c94746b344cee7bfec493f69b7d624ea63f35fabcd3c4a4e6eb7d |
| USGSWater.csv | 12,299 | 7badd4905d47410208498952be2c433a167d41c80744c39620476a8358685244 |

## Interpretation, provenance and leakage controls

### Smoke Detection IoT

The first column has an empty header and is a sequential export index. All 62,630 records have one of the two alarm codes. Within each of five counter runs the interval is exactly one second; one transition goes backwards in UTC. The counter reconstructs candidate recording boundaries but provides no independent experiment IDs. Relative humidity stays within 0–100%. A TVOC or eCO₂ value of 60,000 warrants review for saturation. eCO₂ is **estimated CO₂ equivalent**. Raw H₂ and ethanol signals have no demonstrated concentration calibration.

¹ The collector identifies an SPS30 particle sensor. Its native mass and number concentration units are µg/m³ and particles/cm³. The CSV omits units on these columns. Against the specified ranges of 1,000 µg/m³ and 3,000 particles/cm³, PM1.0 and PM2.5 exceed the respective mass ceiling in 918 and 927 rows. NC0.5, NC1.0 and NC2.5 exceed the number ceiling in 1,014, 707 and 420 rows. These are counts per channel. Confirm firmware scaling and saturation before interpreting the extremes. [Sensor specification](https://sensirion.com/file/datasheet_sps30)

The collector describes Fire Alarm as a target for fire presence in experiments with several fire and nuisance sources. The CSV supplies neither independent event adjudication nor a log identifying an alarm device as the source of each label. The defensible label is **source-provided experimental fire/alarm target**, with generation method unresolved. The author’s description matches the channel set; release identity and applicable redistribution terms require corroboration. Review timestamps for collection-site sensitivity. [Collector’s project](https://community.element14.com/products/arduino/arduino-projects/b/blog/posts/real-time-smoke-detection-with-ai-based-sensor-fusion)

**Two pairs of runs would leak across a recording split.** Comparing rows at equal counter offsets, runs 1 and 2 match on 11 of 12 measurement channels and on every alarm label for all 24,994 offsets. Runs 4 and 5 show the same pattern across 5,744 offsets. Temperature is the only measurement channel that varies between paired runs. There are two redundant 12-channel vectors across the file, despite zero full-row duplicates. Keep each matched pair in one group and audit the three resulting groups for independence and class balance. Class or event coverage in a held-out group may be too sparse for useful validation. Remove the alarm, export index, counter and absolute time from predictor inputs; retain them for provenance. Verify whether the label was generated from any candidate predictors before treating them as independent evidence.

### UCI Air Quality

The CSV uses semicolon delimiters and comma decimals, two empty trailing fields, day-first dates and dotted clock times. The 114 empty records are excluded from the record denominator. The 9,357 nonempty local rows differ from the catalogue's headline of 9,358; both local formats agree on 9,357 timestamps. Source clock times have no explicit zone. Numeric data types above describe the CSV representation. Five PT08 columns are metal-oxide responses; their target gas names do not supply concentration units. Reference analyzer fields can support concentration estimation. No disaster or fire target is present. ² UCI names AH as absolute humidity without specifying its unit in the variable description. Preserve the native scale. [UCI release and dictionary](https://archive.ics.uci.edu/dataset/360/air+quality)

Missing markers affect 8,530 rows. Mask them per field before calibration, resampling or statistics; whole-row deletion would discard most of the series. Preserve masks and keep workbook/CSV representations in the same split. Use chronological holdouts, causal windows and a purge gap covering lookback and forecast horizon. Fit imputation and scaling on training periods only. Exclude the target analyzer channel and its derivatives from predictors. One roadside site cannot establish geographic transfer. UCI lists CC BY 4.0 alongside language limiting use to research and excluding commercial use. Retain the original attribution and resolve this discrepancy and site-metadata scope before release. [UCI terms](https://archive.ics.uci.edu/dataset/360/air+quality)

### USGS Water Data

All records describe Whiteoak Bayou at Houston, Texas. Identifiers, geographic codes and zero-padded parameter/statistic codes are text. Period endpoints are calendar dates. Coordinates and statistics are numeric; sample counts are integers. All 36 rows carry approved status. No instantaneous timestamp, explicit time zone, raw qualifier history, vertical datum or continuous sampling interval is provided. Monthly, calendar-year and water-year summaries overlap; some period endpoints describe partial periods. Five sample counts are short of their inclusive calendar span, by 13, 13, 7, 7 and 2 days. These deficits can overlap; inferring unique missing dates or the raw measurement cadence requires the underlying series. One monthly discharge mean is an IQR flag. Approval status validates neither an event label nor flood stage. [USGS product definitions](https://api.waterdata.usgs.gov/download/)

Preserve original units. For future SI fields, multiply 00060 discharge in ft³/s by 0.028316846592 and 00065 stage in ft by 0.3048. Preserve datum and station identity for stage comparison. Verify a station threshold or dated event reference before assigning a flood label. Hold out complete nonoverlapping periods; remove intersecting annual summaries from a monthly comparison. Station holdout needs additional stations. USGS requests attribution for USGS-produced public-domain data; document the exact query, retrieval date, contributing agency terms and location review for this export. [USGS rights guidance](https://www.usgs.gov/faqs/are-usgs-reportspublications-copyrighted)

## Model 1 compatibility

Repository checks from the project root yielded 249 tests passed, one skipped and three deprecation warnings. Ruff passed. Strict mypy passed across 130 files. An independent final read matched all four file hashes to this report and reconciled the registry counts and storage totals.

| Input | Directly reusable in Phase 10A research | Required preparation or unsupported runtime use |
|---|---|---|
| All three | Environmental modality, source ID, asset reference, digest, and recorded time/interval provenance | Current Model 1 Evidence references artifacts. SensorFrame requires own-agent samples, mission time and battery. EnvironmentalObservation carries a named feature; there is no typed native field for these numeric channels. Retain station or device origin. |
| Smoke | Numeric temperature, RH, pressure, gas responses and particle channels | Keep equivalent CO₂ distinct from direct CO₂; review particle scaling, native raw-response units and shared sessions. Future features could use causal within-recording slopes with missingness and saturation flags. |
| UCI | Hourly environmental measurements and separate analyzer targets | Normalize locale and mask sentinels in derived data. Keep measured concentrations separate from sensor responses. Source-clock zone and AH units require verification. |
| USGS | Station, parameter, original units, summary window and approval status | Optional SI conversion is specified above. Use interval-supported summaries only; future as-of features must wait until the period closes and the value is available. |

These are environmental device or fixed-site observations. Drone GPS, IMU, battery, sensor pose, airborne calibration, synchronized RGB/thermal/audio pair IDs and a mission-clock mapping are absent. Keep source-specific time axes, site/recording group IDs and immutable raw files. Cross-modal alignment and independent event truth remain open. [Model 1 contract](../../agents/shared/domain.py) · [Wire messages](../../communication/messages.py) · [Phase 10A requirements](MODEL1_DATA_REQUIREMENTS.md)
