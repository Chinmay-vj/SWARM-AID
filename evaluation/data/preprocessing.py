"""CPU transforms for review and approved development inputs. No fitted defaults."""

import csv
import hashlib
import importlib
import json
import math
import re
import shutil
import stat
import unicodedata
import wave
import zipfile
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TypeVar

from evaluation.data.contracts import relative_path

T = TypeVar("T")


def batches(records: Iterable[T], size: int) -> Iterator[list[T]]:
    from itertools import islice

    if size < 1:
        raise ValueError("positive batch size required")
    rows = iter(records)
    while chunk := list(islice(rows, size)):
        yield chunk


def normalized_text(value: str | None, replace_urls: bool = False) -> str | None:
    if value is None:
        return None
    value = unicodedata.normalize("NFC", value)
    if replace_urls:
        value = re.sub(r"https?://\S+", "[URL]", value)
    return " ".join(value.split()) or None


def group_split(key: str, train: int = 80, validation: int = 10) -> str:
    if not key.strip() or min(train, validation) < 0 or train + validation > 100:
        raise ValueError("invalid group split")
    bucket = int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100
    return "train" if bucket < train else "validation" if bucket < train + validation else "test"


def require_training(split: str, approved: bool, seed: int | None) -> None:
    if split != "train" or not approved or seed in range(42, 47):
        raise ValueError("requires an approved training sample outside protected seeds")


def fit(records: Iterable[tuple[str, bool, int | None, str, float]]) -> dict[str, Any]:
    count, mean, ss = 0, 0.0, 0.0
    lineage = hashlib.sha256()
    for split, approved, seed, ref, value in records:
        require_training(split, approved, seed)
        if not math.isfinite(value) or not ref:
            raise ValueError("invalid measurement or provenance")
        lineage.update(json.dumps([ref, value]).encode() + b"\n")
        count += 1
        delta = value - mean
        mean += delta / count
        ss += delta * (value - mean)
    if not count:
        raise ValueError("empty training partition")
    return {
        "split": "train",
        "count": count,
        "mean": mean,
        "scale": math.sqrt(ss / count) or 1.0,
        "source_sha256": lineage.hexdigest(),
    }


def extract_zip(source: Path, destination: Path, budget: int, reserve: int) -> None:
    if destination.exists() or min(budget, reserve) < 0:
        raise ValueError("invalid extraction destination or budget")
    with zipfile.ZipFile(source) as archive, TemporaryDirectory(dir=destination.parent) as tmp:
        stage = Path(tmp) / "extracted"
        stage.mkdir()
        seen: set[str] = set()
        total = 0
        for info in archive.infolist():
            name = relative_path(info.filename.rstrip("/"))
            if name.casefold() in seen or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("ambiguous archive member")
            seen.add(name.casefold())
            total += info.file_size
            if total > budget or shutil.disk_usage(tmp).free < reserve + info.file_size:
                raise ValueError("archive exceeds storage limit")
            target = stage / name
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
        stage.rename(destination)


def image(path: Path) -> Any:
    with importlib.import_module("PIL.Image").open(path) as source:
        source.load()
        return source.copy()


def letterbox(
    source: Any,
    size: tuple[int, int],
    boxes: Iterable[tuple[float, ...]] = (),
    mask: Any = None,
    ignore: int | None = None,
) -> tuple[Any, list[tuple[float, ...]], Any]:
    pil = importlib.import_module("PIL.Image")
    w, h = source.size
    if min(*size, w, h) <= 0 or mask is not None and (mask.size != source.size or ignore is None):
        raise ValueError("invalid dimensions or mask padding")
    ratio = min(size[0] / w, size[1] / h)
    ow, oh = max(1, round(w * ratio)), max(1, round(h * ratio))
    x, y = (size[0] - ow) // 2, (size[1] - oh) // 2
    transformed: list[tuple[float, ...]] = []
    for a, b, c, d in boxes:
        if not (0 <= a < a + c <= w and 0 <= b < b + d <= h):
            raise ValueError("invalid COCO box")
        transformed.append((x + a * ow / w, y + b * oh / h, c * ow / w, d * oh / h))
    output = pil.new(source.mode, size)
    output.paste(source.resize((ow, oh), pil.Resampling.BILINEAR), (x, y))
    labels = None
    if mask is not None:
        labels = pil.new(mask.mode, size, ignore)
        labels.paste(mask.resize((ow, oh), pil.Resampling.NEAREST), (x, y))
    return output, transformed, labels


def brightness(source: Any, factor: float, split: str, approved: bool, seed: int | None) -> Any:
    require_training(split, approved, seed)
    if source.mode != "RGB" or not 0.8 <= factor <= 1.2:
        raise ValueError("requires RGB and a bounded brightness factor")
    return importlib.import_module("PIL.ImageEnhance").Brightness(source).enhance(factor)


def audio(path: Path, rate: int = 16000, seconds: float | None = None) -> dict[str, Any]:
    np = importlib.import_module("numpy")
    if rate < 400 or seconds is not None and seconds <= 0:
        raise ValueError("invalid audio configuration")
    with wave.open(str(path)) as f:
        if f.getsampwidth() != 2:
            raise ValueError("expected PCM16")
        original = f.getframerate()
        frames = f.readframes(f.getnframes())
        if len(frames) != f.getnframes() * 2 * f.getnchannels() or not frames:
            raise ValueError("incomplete waveform")
        mono = np.frombuffer(frames, dtype="<i2").reshape(-1, f.getnchannels()).mean(axis=1) / 32768
    # Remove frequencies above the destination Nyquist frequency before interpolation.
    if original > rate:
        spectrum = np.fft.rfft(mono)
        spectrum[np.fft.rfftfreq(len(mono), 1 / original) > rate / 2] = 0
        mono = np.fft.irfft(spectrum, n=len(mono))
    signal = np.interp(
        np.arange(round(len(mono) * rate / original)) * original / rate, np.arange(len(mono)), mono
    )
    if seconds is not None:
        length = max(1, round(seconds * rate))
        signal = np.pad(signal[:length], (0, max(0, length - len(signal))))
    window, hop = round(rate * 0.025), round(rate * 0.010)
    padded = np.pad(signal, (0, max(0, window - len(signal))))
    chunks = np.lib.stride_tricks.sliding_window_view(padded, window)[::hop]
    power = abs(np.fft.rfft(chunks * np.hanning(window))) ** 2
    freq = np.fft.rfftfreq(window, 1 / rate)
    edges = 700 * (10 ** (np.linspace(0, 2595 * np.log10(1 + rate / 1400), 42) / 2595) - 1)
    filters = [
        np.maximum(0, np.minimum((freq - a) / (b - a), (c - freq) / (c - b)))
        for a, b, c in zip(edges, edges[1:], edges[2:])
    ]
    return {
        "waveform": signal,
        "log_mel": np.log(np.maximum(power @ np.array(filters).T, 1e-10)),
        "rate": rate,
        "source_rate": original,
        "window": window,
        "hop": hop,
        "mel_bins": 40,
    }


def sensor_rows(path: Path) -> Iterator[dict[str, Any]]:
    uci = path.name == "AirQualityUCI.csv"
    smoke = path.name == "smoke_detection_iot.csv"
    if not uci and not smoke and path.name != "USGSWater.csv":
        raise ValueError("unknown sensor source")
    units = {
        "T": "degC",
        "RH": "%",
        "CO(GT)": "mg/m3",
        "NMHC(GT)": "ug/m3",
        "C6H6(GT)": "ug/m3",
        "NOx(GT)": "ppb",
        "NO2(GT)": "ug/m3",
    }
    run = 0
    last = -1
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for line, row in enumerate(csv.DictReader(stream, delimiter=";" if uci else ","), 2):
            if not any(row.values()):
                continue
            if uci:
                keys = [k for k in row if k and k not in ("Date", "Time")]
                date = (row.get("Date") or "").strip()
                clock = (row.get("Time") or "").strip()
                if not date or not clock:
                    has_measurement = any(
                        (row.get(key) or "").strip() not in {"", "-200"} for key in keys
                    )
                    if not has_measurement:
                        continue
                    raise ValueError(f"missing UCI timestamp for measurement at source row {line}")
                try:
                    timestamp = datetime.strptime(
                        date + " " + clock, "%d/%m/%Y %H.%M.%S"
                    ).isoformat()
                except ValueError as exc:
                    raise ValueError(f"invalid UCI timestamp at source row {line}") from exc
                device = flag = None
            elif smoke:
                counter = int(row["CNT"])
                run += int(counter <= last or last == -1)
                last = counter
                timestamp = datetime.fromtimestamp(int(row["UTC"]), UTC).isoformat()
                keys = [k for k in row if k not in ("", "Unnamed: 0", "UTC", "CNT", "Fire Alarm")]
                device = None
                flag = None
            else:
                timestamp = row["start_date"]
                device, flag = row["monitoring_location_id"], row["approval_status"]
                keys = [
                    "arithmetic_mean",
                    "maximum",
                    "minimum",
                    "median",
                    "p5",
                    "p10",
                    "p25",
                    "p50",
                    "p75",
                    "p90",
                    "p95",
                ]
            for k in keys:
                raw = row[k]
                value = float(raw.replace(",", ".")) if raw.strip() else None
                if uci and value == -200:
                    value = None
                if value is not None and not math.isfinite(value):
                    raise ValueError(f"nonfinite measurement at {line}")
                unit = (
                    row.get("unit_of_measure")
                    or units.get(k)
                    or (k.split("[")[1].rstrip("]") if "[" in k else None)
                )
                factor, si = {
                    "ft": (0.3048, "m"),
                    "ft^3/s": (0.028316846592, "m3/s"),
                    "hPa": (100.0, "Pa"),
                }.get(unit or "", (1.0, unit))
                yield {
                    "source": path.name,
                    "line": line,
                    "measurement": k,
                    "original": raw,
                    "unit": unit,
                    "standardized": None if value is None else value * factor,
                    "standard_unit": si,
                    "missing": value is None,
                    "timestamp": timestamp,
                    "device": device,
                    "quality": flag,
                    "sequence": run if smoke else None,
                    "period_end": row.get("end_date"),
                    "parameter": row.get("parameter_code"),
                    "alarm": row.get("Fire Alarm"),
                }
