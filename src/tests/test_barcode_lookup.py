"""Tests for the barcode_lookup module."""

from unittest.mock import Mock, patch

import httpx
import pytest

from csv_upc_omg.barcode_lookup import (
    BarcodeAPIError,
    _fetch_openfoodfacts,
    _fetch_upcitemdb,
    fetch_product_title_sync,
)


@patch("csv_upc_omg.barcode_lookup._fetch_openfoodfacts", return_value=None)
@patch("csv_upc_omg.barcode_lookup._fetch_upcitemdb")
def test_fetch_product_title_sync_success(mock_upcitemdb, mock_off):
    """Test successful product title fetch."""
    mock_upcitemdb.return_value = "Test Product Name"

    result = fetch_product_title_sync("123456789012")
    assert result == "Test Product Name"
    mock_upcitemdb.assert_called_once_with("123456789012", 10.0)


@patch("csv_upc_omg.barcode_lookup._fetch_openfoodfacts", return_value=None)
@patch("csv_upc_omg.barcode_lookup._fetch_upcitemdb", return_value=None)
def test_fetch_product_title_sync_not_found(mock_upcitemdb, mock_off):
    """Test when both APIs return no results."""
    result = fetch_product_title_sync("123456789012")
    assert result is None


@patch("csv_upc_omg.barcode_lookup._fetch_openfoodfacts", return_value="OFF Product")
@patch("csv_upc_omg.barcode_lookup._fetch_upcitemdb", return_value=None)
def test_fetch_product_title_sync_fallback_to_off(mock_upcitemdb, mock_off):
    """Test fallback to Open Food Facts when UPCitemdb returns nothing."""
    result = fetch_product_title_sync("123456789012")
    assert result == "OFF Product"


@patch("csv_upc_omg.barcode_lookup._fetch_openfoodfacts")
@patch("csv_upc_omg.barcode_lookup._fetch_upcitemdb")
def test_fetch_product_title_sync_both_fail(mock_upcitemdb, mock_off):
    """Test when both APIs raise BarcodeAPIError."""
    mock_upcitemdb.side_effect = BarcodeAPIError("rate limit")
    mock_off.side_effect = BarcodeAPIError("network error")

    result = fetch_product_title_sync("123456789012")
    assert result is None


# -- UPCitemdb tests -- #


def _mock_httpx_client(response=None, side_effect=None):
    """Create a mocked httpx.Client context manager."""
    mock_client = Mock()
    if response is not None:
        mock_client.get.return_value = response
    if side_effect is not None:
        mock_client.get.side_effect = side_effect
    mock_ctx = Mock()
    mock_ctx.__enter__ = Mock(return_value=mock_client)
    mock_ctx.__exit__ = Mock(return_value=False)
    return mock_ctx


def _make_response(status_code=200, json_data=None):
    mock = Mock()
    mock.status_code = status_code
    mock.json.return_value = json_data if json_data is not None else {}
    mock.raise_for_status = Mock()
    return mock


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_success(mock_client_cls):
    """Test UPCitemdb returns title."""
    resp = _make_response(
        200, {"items": [{"title": "Test Product", "ean": "123456789012"}]}
    )
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_upcitemdb("123456789012", 10.0)
    assert result == "Test Product"
    mock_client_cls.assert_called_once_with(timeout=10.0)


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_not_found(mock_client_cls):
    """Test UPCitemdb returns empty items list."""
    resp = _make_response(200, {"items": []})
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_upcitemdb("123456789012", 10.0)
    assert result is None


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_rate_limit(mock_client_cls):
    """Test UPCitemdb 429 raises BarcodeAPIError."""
    resp = _make_response(429, {})
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    with pytest.raises(BarcodeAPIError, match="rate limit"):
        _fetch_upcitemdb("123456789012", 10.0)


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_http_error(mock_client_cls):
    """Test UPCitemdb non-200 status raises BarcodeAPIError via raise_for_status."""
    resp = Mock()
    resp.status_code = 500
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Internal Server Error", request=Mock(), response=resp
    )
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    with pytest.raises(BarcodeAPIError):
        _fetch_upcitemdb("123456789012", 10.0)


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_timeout(mock_client_cls):
    """Test UPCitemdb timeout raises BarcodeAPIError."""
    mock_client_cls.return_value = _mock_httpx_client(
        side_effect=httpx.TimeoutException("Timeout")
    )

    with pytest.raises(BarcodeAPIError, match="Timeout"):
        _fetch_upcitemdb("123456789012", 10.0)


# -- Open Food Facts tests -- #


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_openfoodfacts_success(mock_client_cls):
    """Test Open Food Facts returns product with brands."""
    resp = _make_response(
        200,
        {
            "status": 1,
            "product": {"product_name": "Organic Milk", "brands": "Dairy Co"},
        },
    )
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_openfoodfacts("0123456789012", 10.0)
    assert result == "Dairy Co Organic Milk"


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_openfoodfacts_no_brands(mock_client_cls):
    """Test Open Food Facts returns product without brands."""
    resp = _make_response(
        200, {"status": 1, "product": {"product_name": "Simple Product"}}
    )
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_openfoodfacts("0123456789012", 10.0)
    assert result == "Simple Product"


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_openfoodfacts_not_found(mock_client_cls):
    """Test Open Food Facts returns nothing for unknown UPC."""
    resp = _make_response(200, {"status": 0})
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_openfoodfacts("0123456789012", 10.0)
    assert result is None


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_openfoodfacts_http_error(mock_client_cls):
    """Test Open Food Facts HTTP error raises BarcodeAPIError."""
    resp = Mock()
    resp.status_code = 500
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Error", request=Mock(), response=resp
    )
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    with pytest.raises(BarcodeAPIError):
        _fetch_openfoodfacts("0123456789012", 10.0)


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_openfoodfacts_timeout(mock_client_cls):
    """Test Open Food Facts timeout raises BarcodeAPIError."""
    mock_client_cls.return_value = _mock_httpx_client(
        side_effect=httpx.TimeoutException("Timeout")
    )

    with pytest.raises(BarcodeAPIError, match="Timeout"):
        _fetch_openfoodfacts("0123456789012", 10.0)


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_custom_timeout(mock_client_cls):
    """Test custom timeout is passed to httpx.Client."""
    resp = _make_response(200, {"items": [{"title": "Product"}]})
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    _fetch_upcitemdb("123456789012", 5.0)
    mock_client_cls.assert_called_once_with(timeout=5.0)
