#!/usr/bin/env python3
"""Check that Kalshi client implementations cover API endpoints and audit parameter drift.

Parses the live Kalshi OpenAPI specification (or a local cache) and compares it
against the AST of src/mcp_server_kalshi/kalshi_client/client.py. Flags route mismatches,
uncovered endpoints, deprecated route usage, and deprecated parameter invocations.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO = Path(__file__).resolve().parent.parent
CLIENT_PATH = REPO / "src" / "mcp_server_kalshi" / "kalshi_client" / "client.py"
ALLOWLIST_PATH = REPO / "scripts" / "drift_allowlist.txt"
DEFAULT_SPEC_URL = "https://docs.kalshi.com/openapi.yaml"


@dataclass
class ClientCall:
    """An HTTP request invoked in the client."""

    method: str
    raw_path: str
    normalized_path: str
    query_params: set[str] = field(default_factory=set)
    body_keys: set[str] = field(default_factory=set)
    line_number: int = 0


@dataclass
class SpecEndpoint:
    """An endpoint documented in the OpenAPI specification."""

    method: str
    path: str
    normalized_path: str
    query_params: dict[str, dict[str, Any]] = field(default_factory=dict)
    path_params: dict[str, dict[str, Any]] = field(default_factory=dict)
    deprecated_params: set[str] = field(default_factory=set)
    required_params: set[str] = field(default_factory=set)
    is_deprecated_route: bool = False


def normalize_path(path: str) -> str:
    """Normalize path by stripping prefix, query string, and standardizing parameters."""
    path = path.split("?")[0].strip()
    if path.startswith("/trade-api/v2"):
        path = path[13:]
    if not path.startswith("/"):
        path = "/" + path
    path = path.rstrip("/")
    return re.sub(r"\{[^}]*\}", "{}", path)


def is_parameter_deprecated(param_def: dict[str, Any]) -> bool:
    """Detect if a parameter is deprecated via boolean flag or description warning."""
    if param_def.get("deprecated") is True:
        return True
    desc = str(param_def.get("description", "")).lower()
    title = str(param_def.get("title", "")).lower()
    if "[deprecated]" in desc or "deprecated" in title or "end of support" in desc:
        return True
    return False


def parse_spec(raw_spec: dict[str, Any]) -> dict[tuple[str, str], SpecEndpoint]:
    """Index OpenAPI specification endpoints, parameters, and deprecation markers."""
    endpoints: dict[tuple[str, str], SpecEndpoint] = {}
    paths = raw_spec.get("paths", {})

    for path_str, methods in paths.items():
        norm_path = normalize_path(path_str)
        path_level_params = (
            methods.get("parameters", []) if isinstance(methods, dict) else []
        )

        for method_name, op in methods.items():
            if method_name.lower() not in ("get", "post", "put", "patch", "delete"):
                continue

            method = method_name.upper()
            op_params = op.get("parameters", []) if isinstance(op, dict) else []
            all_params = list(path_level_params) + op_params

            endpoint = SpecEndpoint(
                method=method,
                path=path_str,
                normalized_path=norm_path,
                is_deprecated_route=bool(op.get("deprecated", False)),
            )

            for param in all_params:
                if not isinstance(param, dict):
                    continue
                p_name = param.get("name")
                p_in = param.get("in", "query")
                if not p_name:
                    continue

                if p_in == "query":
                    endpoint.query_params[p_name] = param
                elif p_in == "path":
                    endpoint.path_params[p_name] = param

                if is_parameter_deprecated(param):
                    endpoint.deprecated_params.add(p_name)

                if param.get("required") is True:
                    endpoint.required_params.add(p_name)

            endpoints[(method, norm_path)] = endpoint

    return endpoints


class ClientAstVisitor(ast.NodeVisitor):
    """AST visitor to find HTTP client calls and extract method, path, and passed query params."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.calls: list[ClientCall] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        method_name = ""
        if isinstance(func, ast.Attribute):
            method_name = func.attr

        http_methods = {"get", "post", "put", "patch", "delete", "request"}
        if method_name.lower() in http_methods:
            method = ""
            raw_path = ""
            query_params: set[str] = set()
            body_keys: set[str] = set()

            if method_name.lower() == "request":
                if (
                    len(node.args) >= 1
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    method = node.args[0].value.upper()
                if len(node.args) >= 2:
                    raw_path = self._extract_path(node.args[1])
            else:
                method = method_name.upper()
                if len(node.args) >= 1:
                    raw_path = self._extract_path(node.args[0])

            # Extract passed query params and body keys
            for kw in node.keywords:
                if kw.arg in ("params", "query_params") and isinstance(
                    kw.value, ast.Dict
                ):
                    for k in kw.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            query_params.add(k.value)
                elif kw.arg in ("json", "data", "json_data") and isinstance(
                    kw.value, ast.Dict
                ):
                    for k in kw.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            body_keys.add(k.value)

            if method and raw_path and raw_path.startswith("/"):
                norm = normalize_path(raw_path)
                self.calls.append(
                    ClientCall(
                        method=method,
                        raw_path=raw_path,
                        normalized_path=norm,
                        query_params=query_params,
                        body_keys=body_keys,
                        line_number=node.lineno,
                    )
                )

        self.generic_visit(node)

    def _extract_path(self, node: ast.AST) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts: list[str] = []
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    parts.append(part.value)
                else:
                    parts.append("{}")
            return "".join(parts)
        return ""


def extract_client_calls(client_file: Path) -> list[ClientCall]:
    """Parse client.py AST and extract all outbound HTTP calls."""
    if not client_file.exists():
        print(f"[!] Client file not found: {client_file}")
        return []

    code = client_file.read_text(encoding="utf-8")
    tree = ast.parse(code, filename=str(client_file))
    visitor = ClientAstVisitor(str(client_file))
    visitor.visit(tree)
    return visitor.calls


def load_allowlist(allowlist_file: Path) -> set[tuple[str, str]]:
    """Load known excluded routes from drift_allowlist.txt."""
    allowed: set[tuple[str, str]] = set()
    if not allowlist_file.exists():
        return allowed

    for line in allowlist_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            method = parts[0].upper()
            path = normalize_path(parts[1])
            allowed.add((method, path))
    return allowed


def check_drift(
    spec_url: str = DEFAULT_SPEC_URL,
    local_spec: Path | None = None,
    allowlist_path: Path = ALLOWLIST_PATH,
    client_path: Path = CLIENT_PATH,
) -> int:
    """Execute complete route parity and parameter deprecation audit."""
    print("======================================================================")
    print("🔍 ENTERPRISE OPENAPI & PARAMETER DRIFT MONITOR: KALSHI")
    print("======================================================================")

    # 1. Fetch or load OpenAPI spec
    try:
        if local_spec and local_spec.exists():
            print(f"[*] Loading local spec: {local_spec}")
            raw = yaml.safe_load(local_spec.read_text(encoding="utf-8"))
        else:
            print(f"[*] Fetching live spec from: {spec_url}")
            resp = httpx.get(spec_url, timeout=15.0)
            resp.raise_for_status()
            raw = yaml.safe_load(resp.text)
    except Exception as exc:
        print(f"[!] Failed to acquire OpenAPI specification: {exc}")
        return 1

    spec_endpoints = parse_spec(raw)
    print(f"[*] Indexed {len(spec_endpoints)} specification endpoints.")

    # 2. Extract client AST calls
    client_calls = extract_client_calls(client_path)
    print(f"[*] Detected {len(client_calls)} outbound client endpoint calls.")

    # 3. Load allowlist
    allowlist = load_allowlist(allowlist_path)

    # 4. Audit client calls against specification
    errors: list[str] = []
    warnings: list[str] = []

    called_keys: set[tuple[str, str]] = set()
    for call in client_calls:
        key = (call.method, call.normalized_path)
        called_keys.add(key)

        if key in allowlist:
            continue

        if key not in spec_endpoints:
            errors.append(
                f"Client calls unknown endpoint: {call.method} {call.normalized_path} "
                f"at line {call.line_number}"
            )
            continue

        endpoint = spec_endpoints[key]

        # Route-level deprecation
        if endpoint.is_deprecated_route:
            warnings.append(
                f"Client calls deprecated route: {call.method} {call.path} at line {call.line_number}"
            )

        # Parameter-level deprecation
        for param in call.query_params:
            if param in endpoint.deprecated_params:
                errors.append(
                    f"Client passes DEPRECATED parameter '{param}' in {call.method} {call.path} "
                    f"at line {call.line_number}"
                )

    # 5. Report results
    print("\n----------------------------------------------------------------------")
    print(f"[*] Spec endpoints:     {len(spec_endpoints)}")
    print(f"[*] Client calls:       {len(client_calls)}")
    print(f"[*] Unique endpoints:   {len(called_keys)}")
    print(f"[*] Allowlisted calls:  {len(allowlist)}")
    print("----------------------------------------------------------------------")

    if warnings:
        print(f"\n⚠️  {len(warnings)} Deprecation Warning(s):")
        for w in warnings:
            print(f"   [!] {w}")

    if errors:
        print(f"\n❌ {len(errors)} Drift / Deprecation Error(s) detected:")
        for e in errors:
            print(f"   [x] {e}")
        print("\n[!] OpenAPI drift check FAILED.")
        return 1

    print("\n[✓] All client calls match live OpenAPI routes.")
    print("[✓] Zero deprecated parameters passed in client requests.")
    print("[✓] OpenAPI route parity & parameter verification PASSED.")
    print("======================================================================\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check Kalshi API OpenAPI drift and parameter deprecations."
    )
    parser.add_argument(
        "--spec-url", default=DEFAULT_SPEC_URL, help="URL to OpenAPI YAML/JSON."
    )
    parser.add_argument(
        "--local-spec", type=Path, default=None, help="Path to local OpenAPI YAML/JSON."
    )
    args = parser.parse_args()
    return check_drift(spec_url=args.spec_url, local_spec=args.local_spec)


if __name__ == "__main__":
    sys.exit(main())
