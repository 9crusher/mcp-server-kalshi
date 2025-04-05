import pytest
import pytest_asyncio
from unittest.mock import Mock, patch
import httpx
from mcp_server_kalshi.kalshi_client import KalshiAPIClient
from mcp_server_kalshi.schema import (
    GetPositionsRequest,
    GetOrdersRequest,
    CreateOrderRequest,
    GetFillsRequest,
    GetSettlementsRequest
)

@pytest.fixture
def mock_private_key():
    with patch('mcp_server_kalshi.kalshi_client.load_private_key_from_file') as mock:
        mock.return_value = Mock()
        yield mock

@pytest.fixture
def mock_sign_pss():
    with patch('mcp_server_kalshi.kalshi_client.sign_pss_text') as mock:
        mock.return_value = "mocked_signature"
        yield mock

@pytest_asyncio.fixture
async def kalshi_client(mock_private_key, mock_sign_pss):
    client = KalshiAPIClient(
        base_url="https://fake-url.com",
        private_key_path="dummy_key.pem",
        api_key="test_api_key"
    )
    yield client
    await client.close()

@pytest.mark.asyncio
async def test_get_positions(kalshi_client):
    # Mock response data
    mock_positions_response = {
        "positions": [
            {
                "market_id": "TEST-MKT",
                "yes_amount": 10,
                "no_amount": 0,
            }
        ]
    }

    # Create a mock response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_positions_response
    mock_response.raise_for_status.return_value = None
    mock_response.text = "mock_text"

    # Patch the client's get method
    with patch.object(kalshi_client.client, 'get', return_value=mock_response):
        request = GetPositionsRequest(market_id="TEST-MKT")
        result = await kalshi_client.get_positions(request)
        
        assert result == mock_positions_response
        assert result["positions"][0]["market_id"] == "TEST-MKT"

@pytest.mark.asyncio
async def test_get_orders(kalshi_client):
    # Mock response data
    mock_orders_response = {
        "orders": [
            {
                "order_id": "order-123",
                "market_id": "TEST-MKT",
                "side": "yes",
                "price": 50,
                "amount": 10,
            }
        ]
    }

    # Create a mock response
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_orders_response
    mock_response.raise_for_status.return_value = None
    mock_response.text = "mock_text"

    # Patch the client's get method
    with patch.object(kalshi_client.client, 'get', return_value=mock_response):
        request = GetOrdersRequest(market_id="TEST-MKT", status="open")
        result = await kalshi_client.get_orders(request)
        
        assert result == mock_orders_response
        assert result["orders"][0]["market_id"] == "TEST-MKT"


@pytest.mark.asyncio
async def test_error_handling(kalshi_client):
    # Mock an error response
    mock_error_response = {
        "error": {
            "code": 400,
            "message": "Bad Request",
            "details": "Invalid parameters"
        }
    }

    # Create a mock response with error status code
    mock_response = Mock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.json.return_value = mock_error_response
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Bad Request", request=Mock(), response=mock_response
    )
    mock_response.text = "mock_error_text"

    # Patch the client's get method
    with patch.object(kalshi_client.client, 'get', return_value=mock_response):
        request = GetPositionsRequest(market_id="TEST-MKT")
        
        # Test that the error is properly handled
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await kalshi_client.get_positions(request)
        
        assert excinfo.value.response.status_code == 400
        assert excinfo.value.response.json() == mock_error_response

