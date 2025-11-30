"""Output parsers for various benchmark tools."""
from __future__ import annotations

import re
from typing import Dict

from ..utils import parse_float


def parse_openssl_output(output: str, algorithm: str) -> Dict[str, float]:
    """Parse OpenSSL speed test output."""
    pattern = rf"^{re.escape(algorithm)}\s+(.+)$"
    match = re.search(pattern, output, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"Unable to find throughput table for {algorithm!r}")

    values_str = match.group(1).split()
    block_sizes = ["16B", "64B", "256B", "1KiB", "8KiB", "16KiB"]
    values = {}
    for size, token in zip(block_sizes, values_str):
        values[size] = float(token.rstrip("k"))

    values["max_kbytes_per_sec"] = max(values.values())
    return values


def parse_7zip_output(output: str) -> Dict[str, float]:
    """Parse 7-Zip benchmark output."""
    totals_match = re.search(r"Tot:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", output)
    avg_match = re.search(
        r"Avr:\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+\|\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)",
        output,
    )
    result: Dict[str, float] = {}

    if totals_match:
        result["total_usage_pct"] = float(totals_match.group(1))
        result["total_ru"] = float(totals_match.group(2))
        result["total_rating_mips"] = float(totals_match.group(3))

    if avg_match:
        result["compress_usage_pct"] = float(avg_match.group(1))
        result["compress_ru_mips"] = float(avg_match.group(2))
        result["compress_rating_mips"] = float(avg_match.group(3))
        result["decompress_usage_pct"] = float(avg_match.group(4))
        result["decompress_ru_mips"] = float(avg_match.group(5))
        result["decompress_rating_mips"] = float(avg_match.group(6))

    if not result:
        raise ValueError("Unable to parse 7-Zip benchmark output")

    return result


def parse_stress_ng_output(output: str) -> Dict[str, float]:
    """Parse stress-ng benchmark output."""
    pattern = re.compile(
        r"stress-ng:\s+\w+:\s+\[\d+\]\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
        r"\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
    )
    for line in output.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        stressor_name = match.group(1)
        if stressor_name == "stressor" or stressor_name.startswith("("):
            continue
        return {
            "stressor": stressor_name,
            "bogo_ops": float(match.group(2)),
            "real_time_secs": float(match.group(3)),
            "user_time_secs": float(match.group(4)),
            "system_time_secs": float(match.group(5)),
            "bogo_ops_per_sec_real": float(match.group(6)),
            "bogo_ops_per_sec_cpu": float(match.group(7)),
        }
    raise ValueError("Unable to parse stress-ng metrics (try increasing runtime)")


def parse_sysbench_cpu_output(output: str) -> Dict[str, float]:
    """Parse sysbench CPU benchmark output."""
    metrics: Dict[str, float] = {}
    events_per_sec = re.search(r"events per second:\s+([\d.]+)", output)
    total_time = re.search(r"total time:\s+([\d.]+)s", output)
    total_events = re.search(r"total number of events:\s+([\d.]+)", output)
    if events_per_sec:
        metrics["events_per_sec"] = float(events_per_sec.group(1))
    if total_time:
        metrics["total_time_secs"] = float(total_time.group(1))
    if total_events:
        metrics["total_events"] = float(total_events.group(1))
    if not metrics:
        raise ValueError("Unable to parse sysbench CPU output")
    return metrics


def parse_sysbench_memory_output(output: str) -> Dict[str, float]:
    """Parse sysbench memory benchmark output."""
    metrics: Dict[str, float] = {}
    operations = re.search(
        r"Total operations:\s+([\d.]+)\s+\(([\d.]+)\s+per second\)", output
    )
    throughput = re.search(
        r"([\d.]+)\s+MiB transferred\s+\(([\d.]+)\s+MiB/sec\)", output
    )
    total_time = re.search(r"total time:\s+([\d.]+)s", output)
    if operations:
        metrics["operations"] = float(operations.group(1))
        metrics["operations_per_sec"] = float(operations.group(2))
    if throughput:
        metrics["transferred_mib"] = float(throughput.group(1))
        metrics["throughput_mib_per_s"] = float(throughput.group(2))
    if total_time:
        metrics["total_time_secs"] = float(total_time.group(1))
    if not metrics:
        raise ValueError("Unable to parse sysbench memory output")
    return metrics


def parse_glmark2_output(output: str) -> Dict[str, float]:
    """Parse glmark2 benchmark output."""
    match = re.search(r"glmark2 Score:\s+(\d+)", output)
    if not match:
        raise ValueError("Unable to parse glmark2 score from output")
    return {"score": float(match.group(1))}


def parse_vkmark_output(output: str) -> Dict[str, float]:
    """Parse vkmark benchmark output."""
    scene_pattern = re.compile(
        r"(?P<scene>[\w-]+).*?(?P<frames>[\d.]+)\s+frames\s+in\s+[\d.]+\s+seconds\s*="
        r"\s*(?P<fps>[\d.]+)\s*FPS",
        flags=re.IGNORECASE,
    )
    fps_values = [float(match.group("fps")) for match in scene_pattern.finditer(output)]
    if not fps_values:
        fps_values = [
            float(match)
            for match in re.findall(r"FPS[:=]\s*([\d.]+)", output, flags=re.IGNORECASE)
        ]
    if not fps_values:
        raise ValueError("Unable to parse vkmark FPS results")
    return {
        "fps_avg": sum(fps_values) / len(fps_values),
        "fps_min": min(fps_values),
        "fps_max": max(fps_values),
        "samples": len(fps_values),
    }


def parse_ffmpeg_progress(output: str) -> Dict[str, float]:
    """Parse ffmpeg encoding progress output."""
    fps_matches = re.findall(r"fps=\s*([\d.]+)", output)
    speed_matches = re.findall(r"speed=\s*([\d.]+)x", output)
    metrics: Dict[str, float] = {}
    if fps_matches:
        metrics["reported_fps"] = float(fps_matches[-1])
    if speed_matches:
        metrics["speed_factor"] = float(speed_matches[-1])
    return metrics


def parse_x264_output(output: str) -> Dict[str, float]:
    """Parse x264 encoder benchmark output."""
    match = re.search(
        r"encoded\s+\d+\s+frames,\s+([\d.]+)\s+fps,\s+([\d.]+)\s+kb/s", output
    )
    if not match:
        raise ValueError("Unable to parse x264 summary")
    return {"fps": float(match.group(1)), "kb_per_s": float(match.group(2))}


def parse_tinymembench_output(output: str) -> Dict[str, float]:
    """Parse tinymembench output."""
    metrics: Dict[str, float] = {}
    for line in output.splitlines():
        match = re.match(r"\s*([A-Za-z0-9 +/_-]+?)\s*:?\s+([\d.,]+)\s+M(?:i)?B/s", line)
        if not match:
            continue
        label = re.sub(r"\s+", "_", match.group(1).strip().lower())
        metrics[f"{label}_mb_per_s"] = parse_float(match.group(2))
    if not metrics:
        raise ValueError("Unable to parse tinymembench throughput")
    return metrics


def parse_clpeak_output(output: str) -> Dict[str, float]:
    """Parse clpeak OpenCL benchmark output."""
    if "no platforms found" in output.lower() or "clgetplatformids" in output.lower():
        raise ValueError("No OpenCL platforms found")
    metrics: Dict[str, float] = {}
    bandwidth_pattern = re.compile(
        r"Global memory bandwidth.*?:\s*([\d.]+)\s*GB/s", flags=re.IGNORECASE
    )
    compute_patterns = [
        (r"Single-precision.*?:\s*([\d.]+)\s*GFLOPS", "compute_sp_gflops"),
        (r"Double-precision.*?:\s*([\d.]+)\s*GFLOPS", "compute_dp_gflops"),
        (r"Integer.*?:\s*([\d.]+)\s*GIOPS", "compute_int_giops"),
    ]
    for line in output.splitlines():
        bw_match = bandwidth_pattern.search(line)
        if bw_match:
            metrics["global_memory_bandwidth_gb_per_s"] = float(bw_match.group(1))
        for pattern, key in compute_patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                metrics[key] = float(match.group(1))
    if not metrics:
        raise ValueError("Unable to parse clpeak metrics")
    return metrics


def parse_cryptsetup_output(output: str) -> Dict[str, float]:
    """Parse cryptsetup benchmark output."""
    metrics: Dict[str, float] = {}
    pattern = re.compile(
        r"^(?P<cipher>[a-z0-9-]+)\s+(?P<keybits>\d+)b\s+(?P<enc>[\d.]+)\s+MiB/s\s+(?P<dec>[\d.]+)\s+MiB/s",
        flags=re.IGNORECASE,
    )
    for line in output.splitlines():
        match = pattern.search(line)
        if not match:
            continue
        cipher = match.group("cipher")
        keybits = int(match.group("keybits"))
        enc = float(match.group("enc"))
        dec = float(match.group("dec"))
        metrics[f"{cipher}_{keybits}_enc_mib_per_s"] = enc
        metrics[f"{cipher}_{keybits}_dec_mib_per_s"] = dec
    if not metrics:
        raise ValueError("Unable to parse cryptsetup benchmark results")
    return metrics


def parse_ioping_output(output: str) -> Dict[str, float]:
    """Parse ioping latency benchmark output."""
    match = re.search(
        r"min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", output
    )
    if not match:
        raise ValueError("Unable to parse ioping summary")
    return {
        "latency_min_ms": float(match.group(1)),
        "latency_avg_ms": float(match.group(2)),
        "latency_max_ms": float(match.group(3)),
        "latency_mdev_ms": float(match.group(4)),
    }


def parse_fsmark_output(output: str) -> Dict[str, float]:
    """Parse fsmark filesystem benchmark output."""
    match = re.search(r"Throughput\s*=\s*([\d.]+)\s+files/sec", output)
    if not match:
        raise ValueError("Unable to parse fsmark throughput")
    return {"files_per_sec": float(match.group(1))}


def parse_filebench_output(output: str) -> Dict[str, float]:
    """Parse filebench output."""
    match = re.search(r"IO Summary:\s+([\d.]+)\s+ops/s", output)
    if not match:
        raise ValueError("Unable to parse filebench IO summary")
    return {"ops_per_sec": float(match.group(1))}


def parse_pgbench_output(output: str) -> Dict[str, float]:
    """Parse PostgreSQL pgbench output."""
    tps_match = re.search(r"tps = ([\d.]+)", output)
    latency_match = re.search(r"latency average = ([\d.]+) ms", output)
    metrics: Dict[str, float] = {}
    if tps_match:
        metrics["tps"] = float(tps_match.group(1))
    if latency_match:
        metrics["latency_ms"] = float(latency_match.group(1))
    if not metrics:
        raise ValueError("Unable to parse pgbench output")
    return metrics


def parse_netperf_output(output: str) -> Dict[str, float]:
    """Parse netperf TCP_STREAM output."""
    values = [
        float(token)
        for token in re.findall(r"([\d.]+)\s*$", output, flags=re.MULTILINE)
        if token
    ]
    if not values:
        raise ValueError("Unable to parse netperf throughput")
    throughput_mbps = values[-1]
    return {"throughput_mbps": throughput_mbps}
