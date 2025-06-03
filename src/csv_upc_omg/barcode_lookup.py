"""Utilities for fetching product information from barcode lookup services."""

import httpx
from bs4 import BeautifulSoup


class BarcodeAPIError(Exception):
    """Exception raised when barcode lookup fails."""


def fetch_product_title_sync(upc: str, timeout: float = 10.0) -> str | None:
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

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:138.0) "
            "Gecko/20100101 Firefox/138.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Alt-Used": "www.barcodelookup.com",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "DNT": "1",
        "Sec-GPC": "1",
        "Priority": "u=0, i",
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            return soup.select_one(".product-details h4").text.strip()

    except httpx.TimeoutException:
        raise BarcodeAPIError(f"Timeout while fetching product for UPC {upc}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise BarcodeAPIError(f"HTTP error {e.response.status_code} for UPC {upc}")
    except Exception as e:
        raise BarcodeAPIError(f"Error fetching product for UPC {upc}: {e}")
