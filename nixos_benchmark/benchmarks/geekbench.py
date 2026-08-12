from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import socketserver
import ssl
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib import error, request

from ..models import BenchmarkMetrics, BenchmarkParameters, BenchmarkResult
from ..utils import read_command_version, run_command
from .base import BenchmarkBase
from .types import BenchmarkType


RESULT_URL_PATTERN = re.compile(r"(https?://browser\.geekbench\.com/\S+)", re.IGNORECASE)
SCORE_BLOCK_TEMPLATE = (
    r"<div class=['\"]score['\"]>\s*([\d,]+)\s*</div>\s*<div class=['\"]note['\"]>\s*{label}\s*</div>"
)

CAPTURE_HOST = "browser.geekbench.com"
_UPLOAD_PATH_PATTERN = re.compile(r"/v6/[a-z]+/upload\.json", re.IGNORECASE)


def _resolve_command() -> str | None:
    """Locate the geekbench binary."""
    for candidate in ("geekbench6", "geekbench"):
        if shutil.which(candidate):
            return candidate
    return None


def _extract_result_url(stdout: str) -> str:
    match = RESULT_URL_PATTERN.search(stdout)
    return match.group(1) if match else ""


def _download_result_page(url: str, timeout: float = 10.0) -> str:
    try:
        with request.urlopen(url, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            data = response.read()
            if not isinstance(data, (bytes, bytearray)):
                return ""
            return data.decode(charset, errors="replace")
    except (OSError, error.URLError, error.HTTPError):
        return ""


def _parse_score_from_text(text: str, label: str) -> float | None:
    """Extract a score from Geekbench HTML or plain text output."""
    html_pattern = re.compile(SCORE_BLOCK_TEMPLATE.format(label=re.escape(label)), re.IGNORECASE | re.DOTALL)
    match = html_pattern.search(text)
    if not match:
        text_pattern = re.compile(rf"{re.escape(label)}\s+([\d,]+)", re.IGNORECASE)
        match = text_pattern.search(text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _generate_capture_certs(openssl: str, tmpdir: str) -> tuple[str, str, str]:
    """Create a throwaway CA + server cert for browser.geekbench.com.

    Returns (ca_crt, srv_crt, srv_key) paths.
    """
    tmp = Path(tmpdir)
    ca_key = tmp / "ca.key"
    ca_crt = tmp / "ca.crt"
    srv_key = tmp / "srv.key"
    srv_csr = tmp / "srv.csr"
    srv_crt = tmp / "srv.crt"
    ext = tmp / "srv.ext"

    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(ca_key),
            "-out",
            str(ca_crt),
            "-days",
            "1",
            "-subj",
            "/CN=geekbench-benchmark-capture-ca",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            openssl,
            "req",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(srv_key),
            "-out",
            str(srv_csr),
            "-subj",
            f"/CN={CAPTURE_HOST}",
        ],
        check=True,
        capture_output=True,
    )
    ext.write_text(f"subjectAltName=DNS:{CAPTURE_HOST}\n")
    subprocess.run(
        [
            openssl,
            "x509",
            "-req",
            "-in",
            str(srv_csr),
            "-CA",
            str(ca_crt),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(srv_crt),
            "-days",
            "1",
            "-extfile",
            str(ext),
        ],
        check=True,
        capture_output=True,
    )
    return str(ca_crt), str(srv_crt), str(srv_key)


class _UploadCaptureHandler(socketserver.BaseRequestHandler):
    """CONNECT proxy handler that MITMs the Geekbench upload and saves its body."""

    def handle(self) -> None:
        conn = self.request
        try:
            connect_line = b""
            while b"\r\n\r\n" not in connect_line:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                connect_line += chunk
            hostport = connect_line.split(b" ", 2)[1]
            if not hostport.lower().startswith(b"browser.geekbench.com"):
                conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                return

            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(self.server.srv_crt, self.server.srv_key)
            tls = ctx.wrap_socket(conn, server_side=True)
            tls.settimeout(60)

            data = self._read_request(tls)
            if not data:
                return
            headers, _, body = data.partition(b"\r\n\r\n")
            if _UPLOAD_PATH_PATTERN.search(headers.decode("latin-1")):
                full = self._read_upload_body(tls, headers, body)
                if full:
                    self.server.captured_body = full

            tls.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}"
            )
        except (OSError, ssl.SSLError, ValueError):
            pass
        finally:
            with contextlib.suppress(OSError):
                conn.close()

    @staticmethod
    def _read_request(tls: ssl.SSLSocket) -> bytes:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = tls.recv(65536)
            if not chunk:
                return b""
            data += chunk
        return data

    @staticmethod
    def _read_upload_body(tls: ssl.SSLSocket, headers: bytes, body: bytes) -> bytes | None:
        length = 0
        for line in headers.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":", 1)[1].strip())
        while len(body) < length:
            chunk = tls.recv(65536)
            if not chunk:
                break
            body += chunk
        if not body:
            return None
        return headers + b"\r\n\r\n" + body[:length]


class _UploadCaptureServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr: tuple[str, int], srv_crt: str, srv_key: str):
        self.srv_crt = srv_crt
        self.srv_key = srv_key
        self.captured_body: bytes | None = None
        super().__init__(addr, _UploadCaptureHandler)


def _run_with_upload_capture(command: list[str]) -> tuple[str, float, int, dict | None]:
    """Run geekbench through a local MITM proxy and return captured result document.

    Returns (stdout, duration, returncode, captured_document_or_None).
    Falls back to a plain run if openssl is unavailable or the proxy fails.
    """
    openssl = shutil.which("openssl")
    if not openssl:
        stdout, duration, returncode = run_command(command)
        return stdout, duration, returncode, None

    with tempfile.TemporaryDirectory(prefix="geekbench-capture-") as tmpdir:
        try:
            ca_crt, srv_crt, srv_key = _generate_capture_certs(openssl, tmpdir)
        except subprocess.CalledProcessError:
            stdout, duration, returncode = run_command(command)
            return stdout, duration, returncode, None

        server = _UploadCaptureServer(("127.0.0.1", 0), srv_crt, srv_key)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {
                "HTTPS_PROXY": f"http://127.0.0.1:{port}",
                "HTTP_PROXY": f"http://127.0.0.1:{port}",
                "ALL_PROXY": f"http://127.0.0.1:{port}",
                "SSL_CERT_FILE": ca_crt,
            }
            stdout, duration, returncode = run_command(command, env=env)
        finally:
            server.shutdown()
            server.server_close()

    document = _extract_document_json(server.captured_body)
    return stdout, duration, returncode, document


def _extract_document_json(body: bytes | None) -> dict | None:
    """Pull the JSON 'document' field out of the multipart upload body."""
    if not body:
        return None
    boundary = None
    head, _, payload = body.partition(b"\r\n\r\n")
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"content-type:"):
            m = re.search(rb"boundary=([^\r\n;]+)", line)
            if m:
                boundary = m.group(1).strip(b'"')
    if not boundary:
        return None
    marker = b'name="document"'
    for part in payload.split(b"--" + boundary):
        if marker in part:
            _, _, doc = part.partition(b"\r\n\r\n")
            doc = doc.rstrip(b"\r\n")
            try:
                return json.loads(doc)
            except ValueError:
                return None
    return None


def _parse_captured_document(document: dict) -> dict[str, float | str | int]:
    """Convert a captured result document into the metrics dict.

    CPU documents carry 'score' (single-core) and 'multicore_score'.
    GPU documents carry 'score' plus sections keyed by API name.
    """
    metrics: dict[str, float | str | int] = {}
    single = document.get("score")
    multi = document.get("multicore_score")

    is_gpu = "compute_api" in document or "compute_device_name" in document
    if is_gpu:
        api_keys = {"vulkan": "vulkan_score", "opencl": "opencl_score", "metal": "metal_score", "cuda": "cuda_score"}
        for section in document.get("sections", []):
            score = section.get("score")
            if score is None:
                continue
            key = api_keys.get(str(section.get("name", "")).lower(), "compute_score")
            metrics.setdefault(key, score)
        if single is not None:
            metrics.setdefault("compute_score", single)
        if multi is not None:
            metrics["multicore_score"] = multi
    else:
        if single is not None:
            metrics["single_core_score"] = single
        if multi is not None:
            metrics["multi_core_score"] = multi
    return metrics


def _auto_detect_gpu_backend() -> str | None:
    """Pick a usable GPU backend from `geekbench6 --gpu-list`.

    Plain `--compute` defaults to OpenCL, which is often unavailable (e.g. Vulkan-only
    RADV). Fall back to the first backend listed by the tool itself.
    """
    command = _resolve_command()
    if not command:
        return None
    stdout, _, returncode = run_command([command, "--gpu-list"])
    if returncode != 0:
        return None
    for line in stdout.splitlines():
        name = line.strip().lower()
        for backend in ("vulkan", "opencl", "metal", "cuda"):
            if name.startswith(backend):
                return backend
    return None


class GeekbenchBase(BenchmarkBase):
    mode_flag: str
    mode_label: str
    benchmark_type: BenchmarkType
    description: str

    def validate(self, args: argparse.Namespace | None = None) -> tuple[bool, str]:
        command = _resolve_command()
        if not command:
            return False, "Command 'geekbench6' (or 'geekbench') was not found in PATH"
        if not shutil.which("openssl"):
            return False, "Command 'openssl' is required to capture Geekbench results offline"
        return True, ""

    def get_version(self) -> str:
        command = _resolve_command()
        if command:
            version = read_command_version((command, "--version"))
            if version:
                return version
        return super().get_version()

    def _build_command(self) -> list[str]:
        command_name = _resolve_command()
        if not command_name:
            raise RuntimeError("geekbench6 not found in PATH")
        return [command_name, self.mode_flag]

    def _parse_metrics(self, stdout: str) -> tuple[dict[str, float | str | int], str, str]:
        raise NotImplementedError

    def build_parameters(self) -> BenchmarkParameters:
        return BenchmarkParameters({"mode": self.mode_label})

    def execute(self, args: argparse.Namespace) -> BenchmarkResult:
        command = self._build_command()
        stdout, duration, returncode, document = _run_with_upload_capture(command)

        metrics_data: dict[str, float | str | int] = {}
        status = "ok"
        message = ""

        if document:
            metrics_data = _parse_captured_document(document)

        if not metrics_data:
            if returncode != 0:
                raise subprocess.CalledProcessError(returncode, command, stdout)
            metrics_data, status, message = self._parse_metrics(stdout)

        result_url = _extract_result_url(stdout)
        if result_url:
            metrics_data["result_url"] = result_url
            if status != "ok" and not message:
                message = f"View Geekbench results at {result_url}"

        if status == "ok" and not metrics_data:
            status = "error"
            message = "Unable to parse Geekbench scores (requires internet access to fetch results)"

        return BenchmarkResult(
            benchmark_type=self.benchmark_type,
            status=status,
            presets=(),
            metrics=BenchmarkMetrics(metrics_data),
            parameters=self.build_parameters(),
            duration_seconds=duration,
            command=self.format_command(command),
            raw_output=stdout,
            message=message,
            version=self.get_version(),
        )


class GeekbenchBenchmark(GeekbenchBase):
    benchmark_type = BenchmarkType.GEEKBENCH
    description = "Geekbench 6 CPU benchmark"
    mode_flag = "--cpu"
    mode_label = "cpu"

    def _parse_metrics(self, stdout: str) -> tuple[dict[str, float | str | int], str, str]:
        metrics_data: dict[str, float | str | int] = {}
        status = "ok"
        message = ""

        result_url = _extract_result_url(stdout)
        result_page = _download_result_page(result_url) if result_url else ""

        search_spaces = [stdout]
        if result_page:
            search_spaces.insert(0, result_page)

        def find_score(label: str) -> float | None:
            for text in search_spaces:
                score = _parse_score_from_text(text, label)
                if score is not None:
                    return score
            return None

        single_score = find_score("Single-Core Score")
        multi_score = find_score("Multi-Core Score")

        if single_score is not None:
            metrics_data["single_core_score"] = single_score
        if multi_score is not None:
            metrics_data["multi_core_score"] = multi_score

        if not metrics_data:
            status = "error"
            message = (
                "Unable to parse Geekbench CPU scores (results are only available online; "
                "ensure the benchmark can reach the Geekbench Browser)"
            )

        return metrics_data, status, message

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        single = result.metrics.get("single_core_score")
        multi = result.metrics.get("multi_core_score")
        result_url = result.metrics.get("result_url")
        if single is not None and multi is not None:
            return f"single {single:.0f}, multi {multi:.0f}"
        if single is not None:
            return f"single {single:.0f}"
        if multi is not None:
            return f"multi {multi:.0f}"
        if result_url:
            return str(result_url)
        return ""


class GeekbenchGPUBenchmark(GeekbenchBase):
    benchmark_type = BenchmarkType.GEEKBENCH_GPU
    description = "Geekbench 6 GPU compute benchmark"
    mode_flag = "--compute"
    mode_label = "gpu"

    def __init__(
        self,
        *,
        backend: str | None = None,
        benchmark_type: BenchmarkType | None = None,
        description: str | None = None,
        mode_label: str | None = None,
    ):
        self.gpu_backend = backend
        if benchmark_type:
            self.benchmark_type = benchmark_type
        if description:
            self.description = description
        if mode_label:
            self.mode_label = mode_label

    def _build_command(self) -> list[str]:
        command = super()._build_command()
        backend = self.gpu_backend or _auto_detect_gpu_backend()
        if backend:
            command.extend(["--gpu", backend])
        return command

    def build_parameters(self) -> BenchmarkParameters:
        params: dict[str, str] = {"mode": self.mode_label}
        backend = self.gpu_backend or _auto_detect_gpu_backend()
        if backend:
            params["backend"] = backend
        return BenchmarkParameters(params)

    def _parse_metrics(self, stdout: str) -> tuple[dict[str, float | str | int], str, str]:
        metrics_data: dict[str, float | str | int] = {}
        status = "ok"
        message = ""

        result_url = _extract_result_url(stdout)
        result_page = _download_result_page(result_url) if result_url else ""

        search_spaces = [stdout]
        if result_page:
            search_spaces.insert(0, result_page)

        score_patterns = {
            "compute_score": "Compute Benchmark Score",
            "metal_score": "Metal Score",
            "opencl_score": "OpenCL Score",
            "vulkan_score": "Vulkan Score",
            "cuda_score": "CUDA Score",
        }
        for key, label in score_patterns.items():
            for text in search_spaces:
                score = _parse_score_from_text(text, label)
                if score is not None:
                    metrics_data[key] = score
                    break

        if not metrics_data:
            status = "error"
            message = (
                "Unable to parse Geekbench GPU scores (results are only available online; "
                "ensure the benchmark can reach the Geekbench Browser)"
            )

        return metrics_data, status, message

    def format_result(self, result: BenchmarkResult) -> str:
        status_message = self.format_status_message(result)
        if status_message:
            return status_message

        compute_score = result.metrics.get("compute_score")
        vulkan_score = result.metrics.get("vulkan_score")
        opencl_score = result.metrics.get("opencl_score")
        metal_score = result.metrics.get("metal_score")
        cuda_score = result.metrics.get("cuda_score")
        result_url = result.metrics.get("result_url")

        for score in (compute_score, vulkan_score, opencl_score, metal_score, cuda_score):
            if score is not None:
                return f"{float(score):.0f} pts"
        if result_url:
            return str(result_url)
        return ""


class GeekbenchVulkanBenchmark(GeekbenchGPUBenchmark):
    def __init__(self):
        super().__init__(
            backend="vulkan",
            benchmark_type=BenchmarkType.GEEKBENCH_GPU_VULKAN,
            description="Geekbench 6 GPU compute benchmark (Vulkan)",
            mode_label="gpu-vulkan",
        )
