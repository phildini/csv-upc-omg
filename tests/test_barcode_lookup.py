"""Tests for the barcode_lookup module."""

from unittest.mock import Mock, patch

import httpx
import pytest

from csv_upc_omg.barcode_lookup import (
    BarcodeAPIError,
    fetch_product_title_sync,
)


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_product_title_sync_success(mock_client_class):
    """Test successful product title fetch."""
    mock_response = Mock()
    mock_response.text = """
    <html>
        <body>
            <div class="product-details">
                <h4>Test Product Name</h4>
            </div>
        </body>
    </html>
    """
    mock_response.raise_for_status.return_value = None

    mock_client = Mock()
    mock_client.get.return_value = mock_response
    mock_client_class.return_value.__enter__.return_value = mock_client

    result = fetch_product_title_sync("123456789012")
    assert result == "Test Product Name"
    mock_client.get.assert_called_once_with(
        "https://www.barcodelookup.com/123456789012"
    )


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_product_title_sync_selector_not_found(mock_client_class):
    """Test when .product-details h4 selector is not found."""
    mock_response = Mock()
    mock_response.text = """
    <html>
        <body>
            <h1>Some Other Title</h1>
        </body>
    </html>
    """
    mock_response.raise_for_status.return_value = None

    mock_client = Mock()
    mock_client.get.side_effect = AttributeError("'NoneType' object has no attribute 'text'")
    mock_client_class.return_value.__enter__.return_value = mock_client

    with pytest.raises(BarcodeAPIError, match="Error fetching product"):
        fetch_product_title_sync("123456789012")


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_product_title_sync_no_selector_match(mock_client_class):
    """Test when .product-details h4 selector doesn't match anything."""
    mock_response = Mock()
    mock_response.text = """
    <html>
        <body>
            <p>No product information available</p>
        </body>
    </html>
    """
    mock_response.raise_for_status.return_value = None

    mock_client = Mock()
    mock_client.get.side_effect = AttributeError("'NoneType' object has no attribute 'text'")
    mock_client_class.return_value.__enter__.return_value = mock_client

    with pytest.raises(BarcodeAPIError, match="Error fetching product"):
        fetch_product_title_sync("123456789012")


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_product_title_sync_404_error(mock_client_class):
    """Test handling of 404 errors."""
    mock_response = Mock()
    mock_response.status_code = 404

    mock_client = Mock()
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "404 Not Found", request=Mock(), response=mock_response
    )
    mock_client_class.return_value.__enter__.return_value = mock_client

    result = fetch_product_title_sync("123456789012")
    assert result is None


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_product_title_sync_http_error(mock_client_class):
    """Test handling of HTTP errors other than 404."""
    mock_response = Mock()
    mock_response.status_code = 500

    mock_client = Mock()
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "500 Server Error", request=Mock(), response=mock_response
    )
    mock_client_class.return_value.__enter__.return_value = mock_client

    with pytest.raises(BarcodeAPIError, match="HTTP error 500"):
        fetch_product_title_sync("123456789012")


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_product_title_sync_timeout(mock_client_class):
    """Test handling of timeout errors."""
    mock_client = Mock()
    mock_client.get.side_effect = httpx.TimeoutException("Timeout")
    mock_client_class.return_value.__enter__.return_value = mock_client

    with pytest.raises(BarcodeAPIError, match="Timeout while fetching"):
        fetch_product_title_sync("123456789012")


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_product_title_sync_generic_error(mock_client_class):
    """Test handling of generic errors."""
    mock_client = Mock()
    mock_client.get.side_effect = Exception("Something went wrong")
    mock_client_class.return_value.__enter__.return_value = mock_client

    with pytest.raises(BarcodeAPIError, match="Error fetching product"):
        fetch_product_title_sync("123456789012")


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_product_title_sync_empty_title(mock_client_class):
    """Test when h4 element exists but is empty."""
    mock_response = Mock()
    mock_response.text = """
    <html>
        <body>
            <div class="product-details">
                <h4></h4>
            </div>
        </body>
    </html>
    """
    mock_response.raise_for_status.return_value = None

    mock_client = Mock()
    mock_client.get.return_value = mock_response
    mock_client_class.return_value.__enter__.return_value = mock_client

    result = fetch_product_title_sync("123456789012")
    assert result == ""


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_product_title_sync_whitespace_only(mock_client_class):
    """Test when h4 element contains only whitespace."""
    mock_response = Mock()
    mock_response.text = """
    <html>
        <body>
            <div class="product-details">
                <h4>   \n\t   </h4>
            </div>
        </body>
    </html>
    """
    mock_response.raise_for_status.return_value = None

    mock_client = Mock()
    mock_client.get.return_value = mock_response
    mock_client_class.return_value.__enter__.return_value = mock_client

    result = fetch_product_title_sync("123456789012")
    assert result == ""


@patch("csv_upc_omg.barcode_lookup.httpx.Client")
def test_fetch_product_title_sync_custom_timeout(mock_client_class):
    """Test custom timeout parameter."""
    mock_response = Mock()
    mock_response.text = """
    <html>
        <body>
            <div class="product-details">
                <h4>Test Product</h4>
            </div>
        </body>
    </html>
    """
    mock_response.raise_for_status.return_value = None

    mock_client = Mock()
    mock_client.get.return_value = mock_response
    mock_client_class.return_value.__enter__.return_value = mock_client

    result = fetch_product_title_sync("123456789012", timeout=5.0)
    assert result == "Test Product"

    # Verify timeout was passed to client
    mock_client_class.assert_called_once_with(timeout=5.0)
