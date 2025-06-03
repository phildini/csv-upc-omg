"""Utilities for fetching product information from barcode lookup services."""

import httpx
from bs4 import BeautifulSoup


class BarcodeAPIError(Exception):
    """Exception raised when barcode lookup fails."""


async def fetch_product_title(upc: str, timeout: float = 10.0) -> str | None:
    """Fetch product title from barcodelookup.com.

    Args:
        upc: The UPC code to lookup
        timeout: Request timeout in seconds

    Returns:
        Product title if found, None if not found

    Raises:
        BarcodeAPIError: If there's an error fetching or parsing the page
    """
    url = f"https://www.barcodelookup.com/{upc}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Look for product title in various possible locations
            title_selectors = [
                "h1.product-title",
                "h1",
                ".product-name",
                ".title",
                '[data-testid="product-title"]',
            ]

            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title = title_element.get_text(strip=True)
                    if title and title.lower() not in ["not found", "error", ""]:
                        return title

            # If no title found in expected locations, return None
            return None

    except httpx.TimeoutException:
        raise BarcodeAPIError(f"Timeout while fetching product for UPC {upc}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise BarcodeAPIError(f"HTTP error {e.response.status_code} for UPC {upc}")
    except Exception as e:
        raise BarcodeAPIError(f"Error fetching product for UPC {upc}: {e}")


def fetch_product_title_sync(upc: str, timeout: float = 10.0) -> str | None:
    """Synchronous version of fetch_product_title.

    Args:
        upc: The UPC code to lookup
        timeout: Request timeout in seconds

    Returns:
        Product title if found, None if not found

    Raises:
        BarcodeAPIError: If there's an error fetching or parsing the page
    """
    url = f"https://www.barcodelookup.com/{upc}"

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Look for product title in various possible locations
            title_selectors = [
                "h1.product-title",
                "h1",
                ".product-name",
                ".title",
                '[data-testid="product-title"]',
            ]

            for selector in title_selectors:
                title_element = soup.select_one(selector)
                if title_element:
                    title = title_element.get_text(strip=True)
                    if title and title.lower() not in ["not found", "error", ""]:
                        return title

            # If no title found in expected locations, return None
            return None

    except httpx.TimeoutException:
        raise BarcodeAPIError(f"Timeout while fetching product for UPC {upc}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise BarcodeAPIError(f"HTTP error {e.response.status_code} for UPC {upc}")
    except Exception as e:
        raise BarcodeAPIError(f"Error fetching product for UPC {upc}: {e}")
