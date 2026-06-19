# discovery.py
import asyncio
import logging
import httpx
from typing import Optional, List, Dict, Tuple
import config
import database # Import the DatabaseManager

logger = logging.getLogger(__name__)

# --- Buff163 Category Endpoints ---
# These represent the main weapon categories on Buff163 that we might want to scrape.
# Example: Rifles, Snipers, etc. We need their base URLs for pagination.
# You might need to find these actual category URLs/API endpoints.
# For demonstration, let's assume there's a generic search or browse endpoint.
# Buff163 might have specific category IDs (e.g., rifles=100, snipers=101).
# Let's define a list of category IDs to iterate through.
# You'll need to find the actual category IDs from Buff163's website structure/API.
# Placeholder example - Replace with actual Buff163 category identifiers/API paths.
# Example: https://buff.163.com/api/market/goods?game=csgo&page_num=1&category_id=100
# This is hypothetical; the real endpoint might be different.
# Let's assume for now we have a way to list items by category.
# Common CS2 categories: Rifles, Sniper Rifles, SMGs, Shotguns, Machine Guns, Knives, Gloves, Pistols
# Let's define a placeholder list of category IDs or search terms.
# IMPORTANT: You need to find the *actual* way to list items by category on Buff163.
# This might involve inspecting the network tab while browsing categories or finding an undocumented API endpoint.

# Placeholder category identifiers - YOU NEED TO FIND THE ACTUAL ONES
# Example hypothetical structure:
# BUFF_CATEGORY_IDS = [
#     {"name": "rifles", "id": 100},
#     {"name": "snipers", "id": 101},
#     {"name": "smgs", "id": 102},
#     # ... add more as needed
# ]

# For now, let's assume we have a single endpoint that lists *all* items or a very broad category,
# and we'll just iterate through its pages.
# The API endpoint found earlier was for *selling* items for a *specific* goods_id:
# https://buff.163.com/api/market/goods/sell_order?game=csgo&goods_id=33869&page_num=1&sort_by=default&mode=&allow_tradable_cooldown=1&_=1781747831233
# We need the endpoint that lists *all possible* goods_ids and names.
# This might be something like (hypothetical):
# https://buff.163.com/api/market/goods?game=csgo&category_id=X&page_num=Y
# OR a search endpoint that returns goods_ids/names.
# Let's assume a search endpoint exists that can return item metadata without needing a specific goods_id first.
# Another possibility: Browse by category on the web UI and intercept the API call.
# Example intercepted call might reveal the endpoint to list items in a category.
# Let's assume the endpoint found earlier *might* be adaptable or there's a similar one to list items.
# Let's say: https://buff.163.com/api/market/goods?game=csgo&page_num=1
# Let's use this as the base for discovery, iterating pages.
# This is the most common pattern for marketplace listings.

# Base URL for listing items (hypothetical - needs verification)
# Based on the example given, the specific sell_order endpoint requires a goods_id.
# We need the endpoint that lists *possible* goods_ids/names.
# Perhaps https://buff.163.com/api/market/goods?game=csgo&page_num=PAGE_NUM
# OR maybe the search page itself uses an API call.
# Looking back: https://buff.163.com/goods/33869#tab=selling&page_num=1&sort_by=paintwear.asc&min_paintwear=0.15&max_paintwear=0.2
# This is for a specific item.
# How do we get *all* items/goods_ids?
# Maybe navigating categories like "Rifles" triggers an API call like:
# https://buff.163.com/api/market/search?game=csgo&category=rifle&page_num=1
# Or similar.
# Let's assume there's an endpoint to list items by category.
# We need to find the root/base category or a way to iterate all categories programmatically.
# For simplicity in this initial version, let's assume we can iterate a single, broad category API call.
# We'll need to inspect Buff163's web traffic (F12 -> Network) to find the correct endpoint.
# For now, let's define the likely pattern based on the sell_order API.
# Maybe the root listing API is similar but without goods_id?
# Hypothetical: https://buff.163.com/api/market/goods/list?game=csgo&page_num=1
# Or maybe it's integrated into the search API without a specific goods_id.
# https://buff.163.com/api/market/search?game=csgo&page_num=1&category=all
# Let's tentatively use a search-like endpoint for discovery.
# The actual endpoint *must* be found by inspecting the website's network activity.

# Placeholder - REPLACE WITH THE ACTUAL DISCOVERY ENDPOINT
# Example (likely incorrect without inspection): https://buff.163.com/api/market/goods?game=csgo&page_num={}&sort_by=popular
# The correct endpoint should return a list of goods including goods_id and name.
# The response structure is likely similar to the sell_order, but containing basic item info instead of orders.
# Example response structure (hypothetical):
# {
#   "code": "OK",
#   "data": {
#       "total_page": 1705, # <-- This is what we want to iterate
#       "items": [
#           {"goods_id": 33869, "name": "AK-47 | Bloodsport (Field-Tested)", ...},
#           {"goods_id": 33870, "name": "AK-47 | Bloodsport (Minimal Wear)", ...},
#           ...
#       ]
#   }
# }

# IMPORTANT: The following URL is PROBABLY WRONG and needs to be found via network inspection.
# ASSUMPTION FOR DEMONSTRATION ONLY:
# Let's assume the endpoint to list items is similar to sell_order but lists base goods info.
# Maybe: https://buff.163.com/api/market/goods?game=csgo&page_num=PAGE_NUM&category=all&display_kind=sell_order
# Or maybe it's under /goods/ instead of /market/goods/sell_order
# Let's try: https://buff.163.com/api/market/goods?game=csgo&page_num=PAGE_NUM
# This is highly speculative. Inspection is critical.
DISCOVERY_BASE_URL = "https://buff.163.com/api/market/goods" # This is the assumed base, PAGE_NUM will be appended

# Headers to mimic a real browser request for Buff163
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://buff.163.com/", # Important for some sites
    "Connection": "keep-alive",
}


async def fetch_discovery_page(session: httpx.AsyncClient, page_num: int) -> Optional[Dict]:
    """
    Fetches a single page of items from Buff163 for discovery.
    Args:
        session (httpx.AsyncClient): The HTTP client session.
        page_num (int): The page number to fetch.
    Returns:
        Optional[Dict]: The JSON response data or None if failed.
    """
    # Construct the URL for the specific page
    # ASSUMPTION: The discovery endpoint takes page_num as a query parameter
    url = f"{DISCOVERY_BASE_URL}?game=csgo&page_num={page_num}"
    # Add other necessary params if found during inspection, e.g., category, sort order
    # url = f"{DISCOVERY_BASE_URL}?game=csgo&page_num={page_num}&category=all&display_kind=sell_order"

    try:
        logger.debug(f"Fetching Buff163 discovery page {page_num}...")
        # Add a random delay to mimic human behavior for this specific request
        import random
        delay = random.uniform(config.BUFF_DELAY_MIN_SECONDS, config.BUFF_DELAY_MAX_SECONDS)
        await asyncio.sleep(delay)

        response = await session.get(url, headers=HEADERS)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        logger.debug(f"Received discovery page {page_num} response.")
        return response.json()
    except httpx.RequestError as e:
        logger.error(f"Request error fetching Buff163 discovery page {page_num}: {e}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code} fetching Buff163 discovery page {page_num}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching Buff163 discovery page {page_num}: {e}")
        return None


def parse_discovery_response(response_json: Dict) -> List[Tuple[int, str]]:
    """
    Parses the JSON response from the Buff163 discovery endpoint.
    Extracts goods_id and item name.
    Args:
        response_json (Dict): The JSON response from the API.
    Returns:
        List[Tuple[int, str]]: A list of (goods_id, item_name) tuples.
    """
    items_found = []
    # ASSUMPTION ABOUT RESPONSE STRUCTURE: Adjust based on the actual API response
    # Based on the sell_order example, the structure might be similar under a 'data' key.
    # Example from sell_order: "data": { "items": [...] }
    # Let's assume the discovery response follows a similar pattern.
    if response_json and response_json.get("code") == "OK":
        data_block = response_json.get("data", {})
        items_list = data_block.get("items", [])
        total_pages = data_block.get("total_page", 0) # Might be useful for iteration logic

        logger.debug(f"Parsing discovery page. Found {len(items_list)} items, total pages estimated: {total_pages}")

        for item in items_list:
            # Extract goods_id and name - adjust keys based on actual response
            # From sell_order example: item["goods_id"], item["asset_info"]["info"]["name"]? or item["asset_info"]["name"]? or item["name"] directly?
            # The sell_order has 'asset_info' which contains details, but the discovery might list items differently.
            # Let's assume the discovery API returns a simpler list with goods_id and name directly within the item object.
            # Hypothetical keys based on common patterns: 'goods_id', 'name'
            goods_id = item.get("goods_id") # Need to confirm key name
            # The name might be nested or direct.
            # From sell_order: asset_info.info.name or asset_info.market_hash_name
            # For discovery, maybe it's just item.get("name") or item.get("market_hash_name") or item.get("asset_info", {}).get("name")
            # Let's try the most common possibilities.
            # The sell_order example showed: item["asset_info"]["info"]["name"] was not present, but "asset_info" had "market_hash_name" implicitly through "name" context.
            # Actually, looking at the sell_order example again:
            # item["item"]["market_hash_name"] = "AK-47 | Bloodsport (Minimal Wear)"
            # item["item"]["item_name"] = "AK-47 | Bloodsport"
            # item["item"]["wear_name"] = "Minimal Wear"
            # So maybe for discovery, if it lists base goods info, it could be:
            # item["name"] or item["market_hash_name"] or a combination.
            # Let's assume the discovery API returns items similar to the base item info within sell_order, but simpler.
            # For sell_order, the item details are under the root item object itself.
            # item_name = item.get("item", {}).get("market_hash_name") # This looks promising from the sell_order example
            # Let's re-examine sell_order closely:
            # The root object of each item in the 'items' array in sell_order response contains:
            # "id", "price", "asset_info", "goods_id", etc.
            # The actual item identification is within "asset_info" -> "info" -> "market_hash_name" or similar.
            # item["asset_info"]["info"]["market_hash_name"] -> "AK-47 | Bloodsport (Minimal Wear)" (This seems most accurate)
            # item["asset_info"]["item_name"] -> "AK-47 | Bloodsport" (Missing condition)
            # item["asset_info"]["wear_name"] -> "Minimal Wear" (Missing weapon/skin name)
            # So, "AK-47 | Bloodsport (Minimal Wear)" seems like the full name we want.
            # Therefore, for the discovery API, if it lists goods, the structure might mirror the 'asset_info' part or simplify it.
            # Let's assume the discovery API returns items where the equivalent of 'asset_info' is the main item object or a sub-object.
            # For example:
            # items_list = [{"goods_id": 33869, "name": "AK-47 | Bloodsport (Field-Tested)"}, ...] OR
            # items_list = [{"goods_id": 33869, "asset_info": {"market_hash_name": "AK-47 | Bloodsport (Field-Tested)"}}] OR
            # items_list = [{"goods_id": 33869, "item": {"market_hash_name": "AK-47 | Bloodsport (Field-Tested)"}}]
            # Given sell_order structure, the second or third option seems more likely for consistency, maybe:
            # items_list = [{"goods_id": 33869, "asset_info": {"item_name": "...", "wear_name": "..."}}, ...] -> Full name needs combining
            # OR
            # items_list = [{"goods_id": 33869, "market_hash_name": "AK-47 | Bloodsport (Field-Tested)"}, ...] -> Simplest
            # Let's try the simplest first: direct name key, and fall back to asset_info structure if needed.
            # Common key might be 'market_hash_name' or 'name'.
            # Let's try 'market_hash_name' first, as it seemed complete in sell_order.
            # If discovery API mirrors sell_order's 'item' object under the root item, it might be item["market_hash_name"]
            # Or if it's simplified, maybe item["name"] or item["market_hash_name"] directly.
            # Let's try: item.get("market_hash_name") or item.get("name") or item.get("asset_info", {}).get("market_hash_name") or item.get("asset_info", {}).get("item_name") + " (" + item.get("asset_info", {}).get("wear_name") + ")"
            # Let's prioritize the most likely complete name based on sell_order: asset_info.info.market_hash_name or a direct equivalent.
            # Simplified assumption: item.get("market_hash_name") or item.get("name")
            # More complex assumption (matching sell_order): item.get("asset_info", {}).get("market_hash_name") or item.get("asset_info", {}).get("item_name", "") + " (" + item.get("asset_info", {}).get("wear_name", "") + ")"

            # Let's try the direct keys first, as discovery might simplify the response.
            item_name_direct = item.get("market_hash_name") or item.get("name")
            if item_name_direct:
                item_name = item_name_direct
            else:
                # If direct keys fail, try the sell_order-like nested structure
                asset_info = item.get("asset_info", {})
                # Try the full name path first
                item_name_nested = asset_info.get("info", {}).get("market_hash_name")
                if item_name_nested:
                    item_name = item_name_nested
                else:
                    # Fallback: combine item_name and wear_name if available
                    item_part = asset_info.get("item_name", "")
                    wear_part = asset_info.get("wear_name", "")
                    if item_part and wear_part:
                        item_name = f"{item_part} ({wear_part})"
                    else:
                        # If nothing works, skip this item
                        item_name = None

            if goods_id and item_name:
                items_found.append((goods_id, item_name))
                logger.debug(f"Discovered: GoodsID {goods_id} -> {item_name}")
            else:
                logger.warning(f"Could not extract goods_id or name from item: {item}")

    else:
        logger.warning(f"Discovery API response not OK or missing data: {response_json}")

    return items_found


async def run_buff_mapping_discovery(db_manager: database.DatabaseManager):
    """
    Main function to run the Buff163 item mapping discovery process.
    Iterates through pages, extracts mappings, and stores them in the database.
    
    NOTE: This is a HEAVY operation that scrapes ALL items on Buff163.
    It should only be run occasionally (e.g., once per week) due to:
    - Rate limiting risks (Buff163 may block aggressive scraping)
    - Time consumption (1700+ pages × 10-30s delay = 5-14 hours)
    - API stability (undocumented endpoints may change)
    
    Consider running this manually or with extended intervals instead of automated scheduling.
    Args:
        db_manager (database.DatabaseManager): Instance of the database manager.
    """
    logger.warning("Starting Buff163 item mapping discovery... THIS MAY TAKE SEVERAL HOURS.")
    logger.warning("Consider running this manually instead of automated scheduling.")

    # Fetch first page to determine total pages, then iterate
    max_pages_to_check = 10000  # Safety upper limit
    current_page = 1
    items_discovered = 0
    consecutive_empty_pages = 0
    MAX_CONSECUTIVE_EMPTY = 3  # Stop after 3 consecutive empty pages

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        # First, fetch page 1 to get total_page count
        logger.info("Fetching page 1 to determine total pages...")
        response_json = await fetch_discovery_page(client, current_page)
        
        if not response_json:
            logger.error("Failed to get page 1. Stopping discovery.")
            return
        
        # Get total pages from first response
        data_block = response_json.get("data", {})
        total_pages_api = data_block.get("total_page", 0)
        
        if total_pages_api == 0:
            logger.error("Could not determine total pages from API response. Stopping.")
            return
        
        logger.info(f"Total pages to scrape: {total_pages_api}. This will take approximately {total_pages_api * 20 / 3600:.1f} hours.")
        
        # Process page 1
        discovered_items = parse_discovery_response(response_json)
        for goods_id, buff_name in discovered_items:
            db_manager.insert_buff_mapping(goods_id, buff_name)
            items_discovered += 1
        
        current_page = 2  # Start from page 2
        
        # Now iterate through remaining pages
        while current_page <= min(total_pages_api, max_pages_to_check):
            logger.info(f"Discovering items on page {current_page}/{total_pages_api}...")

            response_json = await fetch_discovery_page(client, current_page)
            if not response_json:
                logger.error(f"Failed to get data for page {current_page}. Stopping discovery.")
                break

            discovered_items = parse_discovery_response(response_json)

            if not discovered_items:
                consecutive_empty_pages += 1
                logger.warning(f"Page {current_page} returned no parsed items (consecutive: {consecutive_empty_pages}).")
                
                if consecutive_empty_pages >= MAX_CONSECUTIVE_EMPTY:
                    logger.info(f"{MAX_CONSECUTIVE_EMPTY} consecutive empty pages reached. Assuming end of list.")
                    break
                    
                current_page += 1
                continue
            
            consecutive_empty_pages = 0  # Reset counter on successful parse

            for goods_id, buff_name in discovered_items:
                db_manager.insert_buff_mapping(goods_id, buff_name)
                items_discovered += 1

            current_page += 1

    logger.info(f"Buff163 item mapping discovery finished. Discovered {items_discovered} items total.")


# Example usage (when this file is run directly):
# if __name__ == "__main__":
#     import asyncio
#     import database
#     import config # Ensure config is set up correctly
#     db = database.DatabaseManager()
#     asyncio.run(run_buff_mapping_discovery(db))
#     pass
