"""Tests for OpenAPI drift monitor and parameter deprecation checking."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_openapi_drift import (
    check_drift,
    is_parameter_deprecated,
    load_allowlist,
    normalize_path,
    parse_spec,
)


def test_normalize_path():
    assert normalize_path("/trade-api/v2/markets/{ticker}") == "/markets/{}"
    assert normalize_path("events/{event_ticker}") == "/events/{}"
    assert normalize_path("/portfolio/orders?status=open") == "/portfolio/orders"


def test_is_parameter_deprecated():
    assert is_parameter_deprecated({"deprecated": True}) is True
    assert (
        is_parameter_deprecated({"description": "This parameter is [Deprecated] in v2"})
        is True
    )
    assert is_parameter_deprecated({"title": "Deprecated Param"}) is True
    assert (
        is_parameter_deprecated({"name": "status", "description": "Active orders"})
        is False
    )


def test_parse_spec():
    raw_spec = {
        "paths": {
            "/markets": {
                "get": {
                    "parameters": [
                        {"name": "limit", "in": "query", "required": False},
                        {"name": "old_param", "in": "query", "deprecated": True},
                    ]
                }
            },
            "/deprecated_route": {"post": {"deprecated": True, "parameters": []}},
        }
    }
    endpoints = parse_spec(raw_spec)
    assert ("GET", "/markets") in endpoints
    ep = endpoints[("GET", "/markets")]
    assert "limit" in ep.query_params
    assert "old_param" in ep.deprecated_params

    assert ("POST", "/deprecated_route") in endpoints
    assert endpoints[("POST", "/deprecated_route")].is_deprecated_route is True


def test_load_allowlist():
    with tempfile.NamedTemporaryFile("w+", delete=False) as f:
        f.write("# Comment line\n\nPOST /portfolio/withdrawals  # Justification\n")
        f_path = Path(f.name)

    try:
        allowed = load_allowlist(f_path)
        assert ("POST", "/portfolio/withdrawals") in allowed
    finally:
        f_path.unlink()


def test_check_drift_with_mock_spec(tmp_path):
    mock_spec_file = tmp_path / "mock_spec.yaml"
    mock_spec_file.write_text("""
paths:
  /exchange/status:
    get:
      parameters: []
  /exchange/schedule:
    get:
      parameters: []
  /markets:
    get:
      parameters: []
  /markets/{ticker}:
    get:
      parameters: []
  /markets/{ticker}/orderbook:
    get:
      parameters: []
  /series/{series_ticker}/markets/{ticker}/candlesticks:
    get:
      parameters: []
  /markets/trades:
    get:
      parameters: []
  /events:
    get:
      parameters: []
  /events/{event_ticker}:
    get:
      parameters: []
  /series:
    get:
      parameters: []
  /series/{series_ticker}:
    get:
      parameters: []
  /portfolio/balance:
    get:
      parameters: []
  /portfolio/positions:
    get:
      parameters: []
  /portfolio/fills:
    get:
      parameters: []
  /portfolio/settlements:
    get:
      parameters: []
  /portfolio/orders:
    get:
      parameters: []
  /portfolio/orders/{order_id}:
    get:
      parameters: []
  /portfolio/events/orders:
    post:
      parameters: []
  /portfolio/events/orders/{order_id}:
    delete:
      parameters: []
  /portfolio/events/orders/{order_id}/amend:
    post:
      parameters: []
  /portfolio/events/orders/{order_id}/decrease:
    post:
      parameters: []
  /portfolio/events/orders/batched:
    post:
      parameters: []
    delete:
      parameters: []
  /portfolio/summary/total_resting_order_value:
    get:
      parameters: []
  /search/tags_by_categories:
    get:
      parameters: []
  /search/filters_by_sport:
    get:
      parameters: []
  /milestones:
    get:
      parameters: []
  /milestones/{milestone_id}:
    get:
      parameters: []
  /live_data/events/{event_ticker}:
    get:
      parameters: []
  /multivariate_event_collections:
    get:
      parameters: []
  /multivariate_event_collections/{collection_ticker}:
    get:
      parameters: []
  /portfolio/order_groups:
    get:
      parameters: []
  /portfolio/order_groups/{order_group_id}:
    delete:
      parameters: []
""")

    code = check_drift(local_spec=mock_spec_file)
    assert code == 0
