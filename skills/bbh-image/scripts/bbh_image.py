#!/usr/bin/env python3
"""Dependency-free CLI for the BBH image-generation OpenAPI."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import ssl
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://bbh-ai-server.benbh.cn"
CA_BUNDLE_CANDIDATES = (
    "/etc/ssl/cert.pem",
    "/opt/homebrew/etc/ca-certificates/cert.pem",
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
)
SUCCESS_STATUSES = {"completed", "succeeded", "success"}
FAILURE_STATUSES = {"failed", "error", "cancelled", "canceled", "timeout"}


class BBHError(Exception):
    """Base error for CLI failures."""


class BBHConfigError(BBHError):
    """Invalid local configuration or command input."""


class BBHAPIError(BBHError):
    """Network, HTTP, or API-level response error."""

    def __init__(self, message: str, *, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class BBHTaskError(BBHError):
    """Terminal task failure or wait timeout."""

    def __init__(self, message: str, *, response: Any = None):
        super().__init__(message)
        self.response = response


class BBHClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = timeout
        if not self.base_url:
            raise BBHConfigError("BBH_BASE_URL cannot be empty")
        if not self.api_key:
            raise BBHConfigError("BBH_API_KEY is required")
        if self.timeout <= 0:
            raise BBHConfigError("Request timeout must be greater than 0")
        self.ssl_context = build_ssl_context()

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        query: dict[str, Any] | None = None,
        json_body: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}/{path.lstrip('/')}"
        query_values = {key: value for key, value in (query or {}).items() if value not in (None, "")}
        if query_values:
            url += ("&" if "?" in url else "?") + urlencode(query_values, doseq=True)

        request_headers = {"Accept": "application/json", "X-API-Key": self.api_key}
        request_headers.update(headers or {})
        request_body = body
        if json_body is not None:
            request_body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"

        request = Request(url, data=request_body, headers=request_headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
                status = response.status
                raw = response.read()
        except HTTPError as error:
            raw = error.read()
            payload = decode_response(raw)
            raise BBHAPIError(response_message(payload) or f"HTTP {error.code}", status=error.code, payload=payload) from error
        except URLError as error:
            reason = getattr(error, "reason", error)
            raise BBHAPIError(f"Network request failed: {reason}") from error
        except TimeoutError as error:
            raise BBHAPIError(f"Request timed out after {self.timeout:g} seconds") from error

        payload = decode_response(raw)
        if not 200 <= status < 300:
            raise BBHAPIError(response_message(payload) or f"HTTP {status}", status=status, payload=payload)
        if isinstance(payload, dict) and "code" in payload and payload["code"] != 200:
            raise BBHAPIError(response_message(payload) or "API request failed", status=status, payload=payload)
        return payload

    def models(self, task_type: str | None = None) -> Any:
        return self.request("/api/v5/models", query={"task_type": task_type})

    def points(self) -> Any:
        return self.request("/api/v5/user/points")

    def upload(self, file_path: Path) -> Any:
        if not file_path.is_file():
            raise BBHConfigError(f"File not found: {file_path}")
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        boundary = f"----bbh-cli-{uuid.uuid4().hex}"
        body = encode_multipart(boundary, "file", file_path.name, content_type, file_path.read_bytes())
        return self.request(
            "/api/v3/temp/file/upload",
            method="POST",
            body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    def submit(self, payload: dict[str, Any]) -> Any:
        return self.request("/api/v5/image/submit", method="POST", json_body=payload)

    def status(self, task_id: str) -> Any:
        from urllib.parse import quote

        return self.request(f"/api/v5/task/status/{quote(require_text(task_id, 'task_id'), safe='')}")

    def wait(self, task_id: str, *, interval: float = 5.0, timeout: float = 600.0, quiet: bool = False) -> Any:
        if interval < 1:
            raise BBHConfigError("Poll interval must be at least 1 second")
        if timeout <= 0:
            raise BBHConfigError("Wait timeout must be greater than 0")

        started = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            response = self.status(task_id)
            data = response.get("data", {}) if isinstance(response, dict) else {}
            status = str(data.get("status", "")).lower()
            progress = data.get("progress")
            if not quiet:
                suffix = f", progress={progress}" if progress is not None else ""
                print(f"poll {attempt}: status={status or 'unknown'}{suffix}", file=sys.stderr, flush=True)

            if status in SUCCESS_STATUSES:
                return response
            if status in FAILURE_STATUSES:
                message = data.get("error_message") or data.get("message") or f"Task failed: {status}"
                raise BBHTaskError(str(message), response=response)

            elapsed = time.monotonic() - started
            if elapsed >= timeout:
                raise BBHTaskError(f"Task polling timed out after {timeout:g} seconds", response=response)
            time.sleep(min(interval, timeout - elapsed))


def decode_response(raw: bytes) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def build_ssl_context() -> ssl.SSLContext:
    configured = os.getenv("BBH_CA_BUNDLE")
    if configured:
        ca_bundle = Path(configured).expanduser()
        if not ca_bundle.is_file():
            raise BBHConfigError(f"BBH_CA_BUNDLE file not found: {ca_bundle}")
        return ssl.create_default_context(cafile=str(ca_bundle))

    default_paths = ssl.get_default_verify_paths()
    candidates = [os.getenv("SSL_CERT_FILE"), default_paths.cafile, *CA_BUNDLE_CANDIDATES]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


def response_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("message") or payload.get("error") or "")


def encode_multipart(boundary: str, field: str, filename: str, content_type: str, content: bytes) -> bytes:
    safe_filename = filename.replace('"', "_")
    prefix = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{safe_filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    return prefix + content + f"\r\n--{boundary}--\r\n".encode("ascii")


def require_text(value: Any, name: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise BBHConfigError(f"{name} is required")
    return text


def parse_scalar(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def parse_pairs(values: list[str] | None, flag: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for item in values or []:
        if "=" not in item:
            raise BBHConfigError(f"{flag} expects KEY=VALUE: {item}")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise BBHConfigError(f"{flag} key cannot be empty")
        output[key] = parse_scalar(raw_value)
    return output


def file_to_data_uri(file_path: Path) -> str:
    if not file_path.is_file():
        raise BBHConfigError(f"File not found: {file_path}")
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def build_submit_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = parse_pairs(args.param, "--param")
    payload.update(
        {
            "model_id": require_text(args.model_id, "model_id"),
            "prompt": require_text(args.prompt, "prompt"),
        }
    )
    optional_fields = {
        "tier_id": args.tier_id,
        "aspect_ratio": args.aspect_ratio,
        "image_size": args.image_size,
        "quality": args.quality,
    }
    payload.update({key: value for key, value in optional_fields.items() if value not in (None, "")})

    images = [{"type": "url", "data": url} for url in args.image_url or []]
    images.extend({"type": "base64", "data": file_to_data_uri(Path(path))} for path in args.image_file or [])
    if images:
        payload["images"] = images

    user_params = parse_pairs(args.user_param, "--user-param")
    if user_params:
        payload["user_params"] = user_params
    return payload


def extract_results(response: Any) -> list[dict[str, Any]]:
    data = response.get("data", {}) if isinstance(response, dict) else {}
    results = data.get("results")
    if isinstance(results, list):
        return [item for item in results if isinstance(item, dict) and item.get("url")]
    if data.get("result_url"):
        return [{"output_type": "image", "url": data["result_url"]}]
    return []


def add_submit_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model-id", required=True, help="Model ID from the models endpoint")
    parser.add_argument("--prompt", required=True, help="Generation prompt")
    parser.add_argument("--tier-id", help="Optional model tier ID")
    parser.add_argument("--aspect-ratio", help="For example 1:1, 16:9, or 9:16")
    parser.add_argument("--image-size", help="For example 1K, 2K, or 4K")
    parser.add_argument("--quality", help="Model-specific output quality")
    parser.add_argument("--image-url", action="append", help="Repeatable URL reference image")
    parser.add_argument("--image-file", action="append", help="Repeatable local image encoded as a Data URI")
    parser.add_argument("--param", action="append", metavar="KEY=VALUE", help="Repeatable model-specific top-level parameter")
    parser.add_argument("--user-param", action="append", metavar="KEY=VALUE", help="Repeatable user_params entry")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call the BBH image-generation OpenAPI")
    parser.add_argument("--api-key", default=os.getenv("BBH_API_KEY"), help="Defaults to BBH_API_KEY")
    parser.add_argument("--base-url", default=os.getenv("BBH_BASE_URL", DEFAULT_BASE_URL), help="BBH API base URL")
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=os.getenv("BBH_REQUEST_TIMEOUT", "30"),
        help="Per-request timeout in seconds",
    )
    parser.add_argument("--compact", action="store_true", help="Print one-line JSON")
    parser.add_argument("--quiet", action="store_true", help="Suppress polling progress on stderr")

    subparsers = parser.add_subparsers(dest="command", required=True)

    models = subparsers.add_parser("models", help="List available models")
    models.add_argument("--task-type", help="Optional task_type filter")
    subparsers.add_parser("points", help="Show account points")

    upload = subparsers.add_parser("upload", help="Upload a temporary reference file")
    upload.add_argument("file", type=Path)

    submit = subparsers.add_parser("submit", help="Submit an image task without waiting")
    add_submit_arguments(submit)

    status = subparsers.add_parser("status", help="Get task status once")
    status.add_argument("task_id")

    wait = subparsers.add_parser("wait", help="Poll a task until it finishes")
    wait.add_argument("task_id")
    wait.add_argument("--interval", type=float, default=5.0, help="Polling interval in seconds")
    wait.add_argument("--timeout", type=float, default=600.0, help="Overall wait timeout in seconds")

    generate = subparsers.add_parser("generate", help="Submit an image task and wait for the result")
    add_submit_arguments(generate)
    generate.add_argument("--interval", type=float, default=5.0, help="Polling interval in seconds")
    generate.add_argument("--timeout", type=float, default=600.0, help="Overall wait timeout in seconds")
    return parser


def print_json(value: Any, compact: bool) -> None:
    separators = (",", ":") if compact else None
    indent = None if compact else 2
    print(json.dumps(value, ensure_ascii=False, indent=indent, separators=separators))


def run(args: argparse.Namespace) -> Any:
    client = BBHClient(args.base_url, args.api_key or "", args.request_timeout)
    if args.command == "models":
        return client.models(args.task_type)
    if args.command == "points":
        return client.points()
    if args.command == "upload":
        return client.upload(args.file)
    if args.command == "submit":
        return client.submit(build_submit_payload(args))
    if args.command == "status":
        return client.status(args.task_id)
    if args.command == "wait":
        return client.wait(args.task_id, interval=args.interval, timeout=args.timeout, quiet=args.quiet)
    if args.command == "generate":
        submit_response = client.submit(build_submit_payload(args))
        task_id = submit_response.get("data", {}).get("task_id") if isinstance(submit_response, dict) else None
        if not task_id:
            raise BBHAPIError("Submit succeeded but data.task_id is missing", payload=submit_response)
        status_response = client.wait(task_id, interval=args.interval, timeout=args.timeout, quiet=args.quiet)
        results = extract_results(status_response)
        return {
            "task_id": task_id,
            "submit": submit_response,
            "status": status_response,
            "results": results,
            "image_urls": [item["url"] for item in results if item.get("url")],
        }
    raise BBHConfigError(f"Unknown command: {args.command}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        output = run(args)
        print_json(output, args.compact)
        return 0
    except BBHConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except BBHAPIError as error:
        details = {"error": str(error), "status": error.status, "payload": error.payload}
        print_json(details, args.compact)
        return 3
    except BBHTaskError as error:
        details = {"error": str(error), "response": error.response}
        print_json(details, args.compact)
        return 4
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
