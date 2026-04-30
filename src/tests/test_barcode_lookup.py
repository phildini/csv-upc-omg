"""Tests for the barcode_lookup module."""

from unittest.mock import Mock, patch

import httpx
import pytest

from csv_upc_omg.barcode_lookup import (
    BarcodeAPIError,
    _fetch_openfoodfacts,
    _fetch_openfoodfacts_details,
    _fetch_upcitemdb,
    _fetch_upcitemdb_details,
    fetch_product_details_sync,
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


# -- UPCitemdb details tests -- #


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_details_success(mock_client_cls):
    """Test UPCitemdb returns full product details."""
    resp = _make_response(
        200,
        {
            "items": [
                {
                    "title": "Test Product",
                    "brand": "Test Brand",
                    "category": "Snacks",
                    "description": "A test snack product",
                    "images": ["https://example.com/img.jpg"],
                }
            ]
        },
    )
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_upcitemdb_details("123456789012", 10.0)
    assert result["title"] == "Test Product"
    assert result["brand"] == "Test Brand"
    assert result["category"] == "Snacks"
    assert result["description"] == "A test snack product"
    assert result["image_url"] == "https://example.com/img.jpg"
    assert result["source"] == "upcitemdb"


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_details_no_images(mock_client_cls):
    """Test UPCitemdb returns details with no images."""
    resp = _make_response(
        200,
        {
            "items": [
                {
                    "title": "Product No Images",
                    "brand": "Brand",
                    "category": "Cat",
                    "description": "Desc",
                    "images": [],
                }
            ]
        },
    )
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_upcitemdb_details("123456789012", 10.0)
    assert result["image_url"] is None


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_details_not_found(mock_client_cls):
    """Test UPCitemdb returns empty dict for unknown UPC."""
    resp = _make_response(200, {"items": []})
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_upcitemdb_details("123456789012", 10.0)
    assert result == {}


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_details_rate_limit(mock_client_cls):
    """Test UPCitemdb 429 raises BarcodeAPIError."""
    resp = _make_response(429, {})
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    with pytest.raises(BarcodeAPIError, match="rate limit"):
        _fetch_upcitemdb_details("123456789012", 10.0)


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_upcitemdb_details_timeout(mock_client_cls):
    """Test UPCitemdb timeout raises BarcodeAPIError."""
    mock_client_cls.return_value = _mock_httpx_client(
        side_effect=httpx.TimeoutException("Timeout")
    )

    with pytest.raises(BarcodeAPIError, match="Timeout"):
        _fetch_upcitemdb_details("123456789012", 10.0)


# -- Open Food Facts details tests -- #


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_openfoodfacts_details_success(mock_client_cls):
    """Test Open Food Facts returns full product details."""
    resp = _make_response(
        200,
        {
            "status": 1,
            "product": {
                "product_name": "Organic Milk",
                "brands": "Dairy Co",
                "categories": "Beverages, Milk",
                "generic_name": "Milk Product",
                "images": {"1": {"url": "https://example.com/milk.jpg"}},
            },
        },
    )
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_openfoodfacts_details("0123456789012", 10.0)
    assert result["title"] == "Organic Milk"
    assert result["brand"] == "Dairy Co"
    assert result["category"] == "Beverages, Milk"
    assert result["description"] == "Milk Product"
    assert result["image_url"] == "https://example.com/milk.jpg"
    assert result["source"] == "openfoodfacts"


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_openfoodfacts_details_no_images(mock_client_cls):
    """Test Open Food Facts returns details with no images."""
    resp = _make_response(
        200,
        {
            "status": 1,
            "product": {
                "product_name": "Plain Product",
                "brands": "Brand",
                "categories": "Cat",
                "generic_name": "Desc",
                "images": {},
            },
        },
    )
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_openfoodfacts_details("0123456789012", 10.0)
    assert result["image_url"] is None


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_openfoodfacts_details_not_found(mock_client_cls):
    """Test Open Food Facts returns empty dict for unknown UPC."""
    resp = _make_response(200, {"status": 0})
    mock_client_cls.return_value = _mock_httpx_client(response=resp)

    result = _fetch_openfoodfacts_details("0123456789012", 10.0)
    assert result == {}


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_openfoodfacts_details_timeout(mock_client_cls):
    """Test Open Food Facts timeout raises BarcodeAPIError."""
    mock_client_cls.return_value = _mock_httpx_client(
        side_effect=httpx.TimeoutException("Timeout")
    )

    with pytest.raises(BarcodeAPIError, match="Timeout"):
        _fetch_openfoodfacts_details("0123456789012", 10.0)


# -- fetch_product_details_sync tests -- #


@patch("csv_upc_omg.barcode_lookup._fetch_upcitemdb_details")
@patch("csv_upc_omg.barcode_lookup._fetch_openfoodfacts_details")
def test_fetch_product_details_sync_upcitemdb_first(mock_off, mock_upc):
    """Test UPCitemdb success returns immediately."""
    mock_upc.return_value = {"title": "Product", "source": "upcitemdb"}
    mock_off.return_value = {"title": "Other Product", "source": "openfoodfacts"}

    result = fetch_product_details_sync("123456789012")
    assert result["source"] == "upcitemdb"
    mock_upc.assert_called_once()
    mock_off.assert_not_called()


@patch("csv_upc_omg.barcode_lookup._fetch_upcitemdb_details", return_value={})
@patch("csv_upc_omg.barcode_lookup._fetch_openfoodfacts_details")
def test_fetch_product_details_sync_fallback_to_off(mock_off, mock_upc):
    """Test fallback to Open Food Facts when UPCitemdb returns empty."""
    mock_off.return_value = {"title": "OFF Product", "source": "openfoodfacts"}

    result = fetch_product_details_sync("123456789012")
    assert result["source"] == "openfoodfacts"
    mock_off.assert_called_once()


@patch("csv_upc_omg.barcode_lookup._fetch_upcitemdb_details", return_value={})
@patch("csv_upc_omg.barcode_lookup._fetch_openfoodfacts_details", return_value={})
def test_fetch_product_details_sync_both_empty(mock_off, mock_upc):
    """Test raises BarcodeAPIError when both APIs return nothing."""
    with pytest.raises(BarcodeAPIError, match="No product found"):
        fetch_product_details_sync("123456789012")


@patch("csv_upc_omg.barcode_lookup._fetch_upcitemdb_details")
@patch("csv_upc_omg.barcode_lookup._fetch_openfoodfacts_details")
def test_fetch_product_details_sync_upcitemdb_error_fallback(mock_off, mock_upc):
    """Test fallback to OFF when UPCitemdb raises BarcodeAPIError."""
    mock_upc.side_effect = BarcodeAPIError("rate limit")
    mock_off.return_value = {"title": "Backup", "source": "openfoodfacts"}

    result = fetch_product_details_sync("123456789012")
    assert result["title"] == "Backup"
    mock_off.assert_called_once()


@patch("csv_upc_omg.barcode_lookup._fetch_upcitemdb_details")
@patch("csv_upc_omg.barcode_lookup._fetch_openfoodfacts_details")
def test_fetch_product_details_sync_both_error(mock_off, mock_upc):
    """Test raises BarcodeAPIError when both APIs raise errors."""
    mock_upc.side_effect = BarcodeAPIError("rate limit")
    mock_off.side_effect = BarcodeAPIError("network error")

    with pytest.raises(BarcodeAPIError, match="No product found"):
        fetch_product_details_sync("123456789012")
