"""Utilities for fetching product information from barcode lookup services."""

from typing import Any

import httpx


class BarcodeAPIError(Exception):
    """Exception raised when barcode lookup fails."""


def _title_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def fetch_product_title_sync(upc: str, timeout: float = 10.0) -> str | None:
    """Fetch product title from UPC/itemdb or Open Food Facts.

    Args:
        upc: The UPC code to lookup
        timeout: Request timeout in seconds

    Returns:
        Product title if found, None if not found

    Raises:
        BarcodeAPIError: If there's an error fetching from all APIs
    """
    try:
        title = _fetch_upcitemdb(upc, timeout)
        if title:
            return title
    except BarcodeAPIError:
        pass

    try:
        title = _fetch_openfoodfacts(upc, timeout)
        if title:
            return title
    except BarcodeAPIError:
        pass

    return None


def _fetch_upcitemdb(upc: str, timeout: float) -> str | None:
    """Lookup via UPC/itemdb free API."""
    url = "https://api.upcitemdb.com/prod/trial/lookup"
    params = {"upc": upc}
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params=params)
            if response.status_code == 429:
                raise BarcodeAPIError("UPCitemdb rate limit exceeded")
            response.raise_for_status()

        data = response.json()
        items = data.get("items", [])
        if items:
            return _title_str(items[0].get("title"))
        return None
    except BarcodeAPIError:
        raise
    except httpx.TimeoutException:
        raise BarcodeAPIError(f"Timeout while fetching product for UPC {upc}")
    except httpx.HTTPStatusError as e:
        raise BarcodeAPIError(f"HTTP error {e.response.status_code} for UPC {upc}")
    except Exception as e:
        raise BarcodeAPIError(f"Error fetching product for UPC {upc}: {e}")


def _fetch_openfoodfacts(upc: str, timeout: float) -> str | None:
    """Lookup via Open Food Facts API."""
    url = f"https://world.openfoodfacts.org/api/v2/product/{upc}.json"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()

        data = response.json()
        if data.get("status") == 1:
            product = data.get("product", {})
            product_name = _title_str(product.get("product_name"))
            brands = _title_str(product.get("brands"))
            if product_name:
                if brands:
                    return f"{brands} {product_name}"
                return product_name
        return None
    except BarcodeAPIError:
        raise
    except httpx.TimeoutException:
        raise BarcodeAPIError(f"Timeout while fetching product for UPC {upc}")
    except httpx.HTTPStatusError as e:
        raise BarcodeAPIError(f"HTTP error {e.response.status_code} for UPC {upc}")
    except Exception as e:
        raise BarcodeAPIError(f"Error fetching product for UPC {upc}: {e}")
