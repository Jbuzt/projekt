# scraper.py
import asyncio
import json
import logging
import os
import time
import httpx
from typing import Optional, List, Dict, Tuple
import config
import database
import utils

import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scrape state persistence
# Stores progress (last completed page, in-progress flag) in a JSON file
# alongside this script so the bot can resume after a pause/restart.
# ---------------------------------------------------------------------------
_STATE_FILE = os.path.join(os.path.dirname(__file__), "scrape_state.json")

def _load_state() -> dict:
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_state(state: dict):
    try:
        with open(_STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not save scrape state: {e}")

_CONDITION_SUFFIXES = re.compile(
    r'\s*\((Factory New|Minimal Wear|Field-Tested|Well-Worn|Battle-Scarred)\)$'
)
_STATTRAK_PREFIX   = re.compile(r'^StatTrak\u2122\s+')
_SOUVENIR_PREFIX   = re.compile(r'^Souvenir\s+')

def _base_skin_name(market_hash_name: str) -> str:
    """Strips condition suffix and StatTrak™/Souvenir prefix to get the bare skin name.
    e.g. 'StatTrak™ AK-47 | Bloodsport (Factory New)' -> 'AK-47 | Bloodsport'
    """
    name = _CONDITION_SUFFIXES.sub('', market_hash_name).strip()
    name = _STATTRAK_PREFIX.sub('', name).strip()
    name = _SOUVENIR_PREFIX.sub('', name).strip()
    return name

# --- CSFloat API Endpoint ---
CSFLOAT_LISTINGS_URL = "https://csfloat.com/api/v1/listings"

# --- Buff163 API Endpoints ---
# Global listing endpoint for discovery (already in discovery.py)
# BUFF_DISCOVERY_BASE_URL = "https://buff.163.com/api/market/goods"
# Specific item listings endpoint for active listings
BUFF_SELL_ORDER_URL = "https://buff.163.com/api/market/goods/sell_order"

# Headers for CSFloat (standard JSON API request)
CSFLOAT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://csfloat.com/",
    "Authorization": config.CSFLOAT_API_KEY,
}

# Headers for Buff163 (mimicking browser)
BUFF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://buff.163.com/", # Important for Buff163
    "Connection": "keep-alive",
}


async def fetch_csfloat_listings(session: httpx.AsyncClient, paint_index: int, min_float: Optional[float] = None, max_float: Optional[float] = None) -> Optional[List[Dict]]:
    """
    Fetches active listings from CSFloat for a specific paint_index and optional float range.
    Args:
        session (httpx.AsyncClient): The HTTP client session.
        paint_index (int): The CSFloat paint_index (e.g., 639).
        min_float (Optional[float]): Minimum float value to filter.
        max_float (Optional[float]): Maximum float value to filter.
    Returns:
        Optional[List[Dict]]: A list of listing dictionaries or None if failed.
    """
    # Construct the URL with required and optional parameters
    # Example: https://csfloat.com/api/v1/listings?limit=40&max_float=0.45&type=buy_now&def_index=7&paint_index=639
    # We'll use 'type=buy_now' and 'limit' (default or set high enough).
    # def_index might be derivable from paint_index or might be needed separately if it changes meaningfully.
    # For now, let's assume we can pass paint_index directly and maybe def_index if known separately or derived.
    # The example URL provided used def_index=7 for AK-47 Bloodsport (paint_index=639).
    # Let's see if def_index is always needed or if paint_index is sufficient for filtering.
    # For initial implementation, let's include def_index if available or use a placeholder if it's consistent for skin types.
    # CSFloat API documentation might specify if def_index is mandatory with paint_index.
    # Let's assume it's needed and derive it somehow or pass it. For now, let's make it optional in the call but include if provided.
    # We need to determine def_index. It seems related to weapon type. AK-47 is def_index 7.
    # This might require looking up def_index based on paint_index or item name, potentially using CSFloat's item definitions if available via API.
    # For now, let's pass it as an argument or assume a default if not provided, acknowledging this might need refinement.
    # Let's make a helper function or lookup if def_index is predictable per paint_index.
    # For now, let's just pass it as an argument to this function if available, or omit if not critical.
    # Looking at the example: def_index=7, paint_index=639. 7 is AK-47's definition index.
    # This implies a mapping might be needed: paint_index -> def_index.
    # This could be another discovery step or a static map if stable.
    # For now, let's make def_index optional here and see if the API works with just paint_index.
    # If it fails often, we'll need the mapping.
    # Let's assume for now that paint_index is sufficient or def_index can be passed if needed.
    # We'll add def_index as a parameter to this function.
    # Example call: fetch_csfloat_listings(client, 639, def_index=7, min_float=0.15, max_float=0.20)
    # Let's add def_index as an optional parameter here, defaulting to None.
    # params = {"paint_index": paint_index, "type": "buy_now", "limit": 100} # Use a high limit to get more results if available
    # if def_index is not None:
    #     params["def_index"] = def_index
    # if min_float is not None:
    #     params["min_float"] = min_float
    # if max_float is not None:
    #     params["max_float"] = max_float

    # Actually, looking back at the original example URL provided:
    # https://csfloat.com/api/v1/listings?limit=40&max_float=0.45&type=buy_now&def_index=7&paint_index=639
    # It had def_index=7 and paint_index=639.
    # And another filter example:
    # https://csfloat.com/search?category=1&min_float=0.07&max_float=0.2&type=buy_now&paint_index=639
    # This one only had paint_index and float filters, no explicit def_index in the URL, but maybe it's inferred internally.
    # Let's assume paint_index is the primary filter. We might need def_index for completeness.
    # Let's tentatively proceed with paint_index and float filters.
    # If scraping fails often due to missing def_index, we'll investigate further.
    # For now, let's build the request based on the information we have.
    # We know paint_index is key. Let's see if def_index is always needed by testing or checking API behavior.
    # Let's build the params based on the examples.
    # limit=40 was in the example, but we might want more. Let's check if there's an upper limit or if we can increase it significantly.
    # type=buy_now is consistent.
    # max_float=0.45 was in the example, maybe a default high value if max_float is not specified by the caller.
    # Let's construct it dynamically.
    params = {
        "paint_index": paint_index,
        "type": "buy_now",
        "limit": 50  # CSFloat API max is 50
    }
    # Optional filters
    if min_float is not None:
        params["min_float"] = min_float
    if max_float is not None:
        params["max_float"] = max_float
    # def_index - let's see if it's truly required based on API response. Assume not for now, add if needed later.
    # params["def_index"] = def_index # Add this if necessary after testing.

    url = CSFLOAT_LISTINGS_URL

    try:
        logger.debug(f"Fetching CSFloat listings for paint_index {paint_index} with params {params}...")
        # No specific delay needed here as it's not Buff163, but good practice to respect rate limits.
        # CSFloat might have its own rate limits, monitor for 429s.
        # Adding a small, fixed delay might be prudent depending on how frequently this is called per item.
        # For a single item scrape cycle, a delay might not be strictly necessary if not calling excessively.
        # await asyncio.sleep(1) # Example delay, adjust or remove based on CSFloat's tolerance.

        response = await session.get(url, params=params, headers=CSFLOAT_HEADERS)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        json_data = response.json()
        logger.debug(f"Received CSFloat listings response for paint_index {paint_index}.")
        # CSFloat API response structure based on the example:
        # {"data": [ {listing1}, {listing2}, ... ] }
        listings = json_data.get("data", []) # Extract the 'data' array
        return listings
    except httpx.RequestError as e:
        logger.error(f"Request error fetching CSFloat listings for paint_index {paint_index}: {e}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code} fetching CSFloat listings for paint_index {paint_index}: {e}")
        return None
    except KeyError as e:
        logger.error(f"Key error parsing CSFloat listings response for paint_index {paint_index}: {e}. Response: {response.text if 'response' in locals() else 'No response object'}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching CSFloat listings for paint_index {paint_index}: {e}")
        return None


def parse_csfloat_listings(raw_listings: List[Dict], paint_index: int) -> List[Dict]:
    """
    Parses raw CSFloat listing data into the format suitable for database insertion.
    Returns a list of dicts with keys: skin_name, asset_id, pattern_id, float_val,
    src, original_price_usd, current_price_usd, timestamp_str.
    """
    parsed_listings = []
    current_timestamp_str = utils.generate_timestamp_string()

    for raw_listing in raw_listings:
        try:
            item_details = raw_listing.get("item", {})

            listing_paint_index = item_details.get("paint_index")
            if listing_paint_index != paint_index:
                logger.warning(f"Mismatched paint_index for listing {raw_listing.get('id')}: expected {paint_index}, got {listing_paint_index}. Skipping.")
                continue

            asset_id        = item_details.get("asset_id")
            float_val       = item_details.get("float_value")
            skin_name       = item_details.get("market_hash_name")
            pattern_id      = item_details.get("paint_seed")  # integer or None

            if not asset_id or not skin_name:
                logger.warning(f"Listing {raw_listing.get('id')} missing asset_id or name, skipping.")
                continue

            price_cents = raw_listing.get("price")
            if price_cents is None:
                logger.warning(f"Listing {raw_listing.get('id')} has no price, skipping.")
                continue
            price_usd = price_cents / 100.0

            parsed_listings.append({
                "skin_name":          skin_name,
                "asset_id":           asset_id,
                "pattern_id":         pattern_id,
                "src":                "CSFL",
                "original_price_usd": price_usd,
                "current_price_usd":  price_usd,
                "timestamp_str":      current_timestamp_str,
                "float_val":          float_val,
            })

        except (KeyError, TypeError) as e:
            logger.warning(f"Could not parse CSFloat listing: {e}. Raw listing: {raw_listing}")
            continue

    logger.debug(f"Parsed {len(parsed_listings)} CSFloat listings for paint_index {paint_index}.")
    return parsed_listings


async def fetch_buff_listings(session: httpx.AsyncClient, goods_id: int, min_paintwear: Optional[float] = None, max_paintwear: Optional[float] = None) -> Optional[List[Dict]]:
    """
    Fetches all listing pages from Buff163 for a specific goods_id and optional paintwear range.
    Paginates automatically through all available pages.
    Args:
        session (httpx.AsyncClient): The HTTP client session.
        goods_id (int): The Buff163 goods_id (e.g., 33869).
        min_paintwear (Optional[float]): Minimum paintwear (float) to filter.
        max_paintwear (Optional[float]): Maximum paintwear (float) to filter.
    Returns:
        Optional[List[Dict]]: A combined list of listing dictionaries from all pages, or None if the first page failed.
    """
    import random
    all_listings = []
    page_num = 1
    first_page_failed = False

    while True:
        # Delay between every page request to mimic human behavior
        delay = random.uniform(config.BUFF_DELAY_MIN_SECONDS, config.BUFF_DELAY_MAX_SECONDS)
        logger.info(f"[Buff163] Waiting {delay:.0f}s before page {page_num} (goods_id {goods_id})...")
        await asyncio.sleep(delay)

        params = {
            "game": "csgo",
            "goods_id": goods_id,
            "page_num": page_num,
            "sort_by": "paintwear.asc",
            "mode": "",
            "allow_tradable_cooldown": 1,
            "_": int(time.time() * 1000)
        }
        if min_paintwear is not None:
            params["min_paintwear"] = min_paintwear
        if max_paintwear is not None:
            params["max_paintwear"] = max_paintwear

        try:
            logger.debug(f"Fetching Buff163 page {page_num} for goods_id {goods_id}...")
            response = await session.get(BUFF_SELL_ORDER_URL, params=params, headers=BUFF_HEADERS)
            response.raise_for_status()
            json_data = response.json()

            items_data = json_data.get("data", {})
            page_listings = items_data.get("items", [])
            total_page = items_data.get("total_page", 1)

            all_listings.extend(page_listings)
            logger.info(f"[Buff163] Page {page_num}/{total_page} — {len(page_listings)} listings fetched (goods_id {goods_id})")

            if page_num >= total_page:
                break  # All pages fetched
            page_num += 1

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} fetching Buff163 page {page_num} for goods_id {goods_id}: {e}")
            if page_num == 1:
                first_page_failed = True
            break
        except httpx.RequestError as e:
            logger.error(f"Request error fetching Buff163 page {page_num} for goods_id {goods_id}: {e}")
            if page_num == 1:
                first_page_failed = True
            break
        except Exception as e:
            logger.error(f"Unexpected error fetching Buff163 page {page_num} for goods_id {goods_id}: {e}")
            if page_num == 1:
                first_page_failed = True
            break

    if first_page_failed:
        return None
    return all_listings


def parse_buff_listings(raw_listings: List[Dict], goods_id: int, currency_rate: Optional[float]) -> List[Dict]:
    """
    Parses raw Buff163 listing data into the format suitable for database insertion/update.
    Converts CNY prices to USD using the provided currency rate.
    Args:
        raw_listings (List[Dict]): Raw data from Buff163 API.
        goods_id (int): The goods_id these listings belong to.
        currency_rate (Optional[float]): The CNY to USD conversion rate.
    Returns:
        List[Dict]: A list of parsed listing dictionaries.
    """
def parse_buff_listings(raw_listings: List[Dict], goods_id: int, currency_rate: Optional[float]) -> List[Dict]:
    """
    Parses raw Buff163 sell_order listing data into the format suitable for database insertion.
    Extracts: skin_name, asset_id (Steam assetid), float_val (paintwear),
    pattern_id (paintseed), price (CNY -> USD).
    Returns a list of dicts with the same keys as parse_csfloat_listings.
    """
    parsed_listings = []
    current_timestamp_str = utils.generate_timestamp_string()

    if currency_rate is None:
        logger.error("Cannot parse Buff163 listings: currency rate is None.")
        return []

    for raw_listing in raw_listings:
        try:
            asset_info      = raw_listing.get("asset_info", {})
            info            = asset_info.get("info", {})

            asset_id        = asset_info.get("assetid")
            listing_goods_id = asset_info.get("goods_id")
            if listing_goods_id != goods_id:
                logger.warning(f"Mismatched goods_id for listing {raw_listing.get('id')}: expected {goods_id}, got {listing_goods_id}. Skipping.")
                continue

            # Float: paintwear is a string e.g. "0.2016877830028534"
            paintwear_str = asset_info.get("paintwear")
            if paintwear_str is None:
                logger.warning(f"Listing {raw_listing.get('id')} has no paintwear, skipping.")
                continue
            float_val = float(paintwear_str)

            # Pattern: paintseed inside asset_info.info
            pattern_id = info.get("paintseed")  # integer or None

            # Skin name: top-level 'name' field is the full market hash name
            skin_name = raw_listing.get("name")
            if not skin_name:
                tags = info.get("tags", {})
                item_part = tags.get("type", {}).get("localized_name") or info.get("item_name", "")
                wear_part = tags.get("exterior", {}).get("localized_name") or info.get("wear_name", "")
                skin_name = f"{item_part} ({wear_part})" if item_part and wear_part else f"GoodsID_{goods_id}_Asset_{asset_id}"

            # Price: CNY string -> USD float
            price_cny_str = raw_listing.get("price")
            if price_cny_str is None:
                logger.warning(f"Listing {raw_listing.get('id')} has no price, skipping.")
                continue
            price_usd = float(price_cny_str) * currency_rate

            if not asset_id:
                logger.warning(f"Listing {raw_listing.get('id')} has no assetid, skipping.")
                continue

            parsed_listings.append({
                "skin_name":          skin_name,
                "asset_id":           asset_id,
                "pattern_id":         pattern_id,
                "src":                "BUFF",
                "original_price_usd": price_usd,
                "current_price_usd":  price_usd,
                "timestamp_str":      current_timestamp_str,
                "float_val":          float_val,
            })

        except (KeyError, TypeError, ValueError) as e:
            logger.warning(f"Could not parse Buff163 listing: {e}. Raw listing: {raw_listing}")
            continue

    logger.debug(f"Parsed {len(parsed_listings)} Buff163 sell_order listings for goods_id {goods_id}.")
    return parsed_listings


async def scrape_item(db_manager: database.DatabaseManager, paint_index: int, min_float: Optional[float] = None, max_float: Optional[float] = None):
    """
    Scrapes CSFloat listings for a specific paint_index and float range.
    Buff163 is scraped independently via scrape_buff_global().
    """
    label = f"paint_index {paint_index} | float {min_float}-{max_float}"
    logger.info(f"[Scrape] Starting — {label}")
    start_time = time.time()

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        logger.info(f"[CSFloat] Fetching listings — paint_index {paint_index} ({min_float}-{max_float})...")
        csfloat_raw = await fetch_csfloat_listings(client, paint_index, min_float, max_float)

        if isinstance(csfloat_raw, Exception) or csfloat_raw is None:
            logger.error(f"[CSFloat] No data returned for paint_index {paint_index}.")
        else:
            parsed = parse_csfloat_listings(csfloat_raw, paint_index)
            saved = 0
            # Collect unique base skin names seen in this scrape to auto-link buff_mapping
            seen_base_names: set = set()
            for listing_info in parsed:
                db_manager.insert_or_update_listing(
                    skin_name=listing_info["skin_name"],
                    asset_id=listing_info["asset_id"],
                    source=listing_info["src"],
                    original_price_usd=listing_info["original_price_usd"],
                    current_price_usd=listing_info["current_price_usd"],
                    timestamp_str=listing_info["timestamp_str"],
                    float_val=listing_info["float_val"],
                    pattern_id=listing_info["pattern_id"],
                )
                saved += 1
                seen_base_names.add(_base_skin_name(listing_info["skin_name"]))

            logger.info(f"[CSFloat] Done — {saved}/{len(csfloat_raw)} listings saved for paint_index {paint_index}")

            # Auto-link: update buff_mapping rows whose buff_name contains any of the
            # base names seen, setting csfloat_paint_index = paint_index on unlinked rows.
            for base_name in seen_base_names:
                db_manager.link_buff_mapping_to_paint_index(base_name, paint_index)

    elapsed = time.time() - start_time
    logger.info(f"[Scrape] Finished — {label} in {elapsed:.1f}s")


# --- Buff163 global endpoint ---
BUFF_GOODS_URL = "https://buff.163.com/api/market/goods"


async def scrape_buff_global(db_manager: database.DatabaseManager):
    """
    Independently scrapes ALL pages of the Buff163 global market listing.
    For each item found it:
      1. Upserts goods_id -> name into buff_mapping (auto-learning IDs).
      2. Saves the current min sell price as a BUFF listing in Supabase.
    This function is completely decoupled from CSFloat's paint_index system.
    """
    import random
    logger.info("[Buff163] Starting global market scrape...")
    start_time = time.time()
    currency_rate = db_manager.get_latest_currency_rate()
    if currency_rate is None:
        logger.error("[Buff163] No currency rate available — aborting global scrape.")
        return

    # --- Resume support ---
    state = _load_state()
    if state.get("buff_global_in_progress"):
        page_num = state.get("buff_global_last_page", 1)
        logger.info(f"[Buff163] Resuming global scrape from page {page_num} (previous run was interrupted).")
    else:
        page_num = 1
        logger.info("[Buff163] Starting fresh global scrape from page 1.")

    state["buff_global_in_progress"] = True
    state["buff_global_last_page"] = page_num
    _save_state(state)

    # --- Load existing prices into memory for dedup ---
    # {"BUFF-{goods_id}": price_usd, ...} — skip items whose price hasn't changed
    existing_prices: Dict[str, float] = db_manager.get_buff_global_prices()
    logger.info(f"[Buff163] Loaded {len(existing_prices)} existing Buff163 prices for dedup.")

    total_saved = 0
    total_skipped = 0
    total_learned = 0
    timestamp_str = utils.generate_timestamp_string()

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        while True:
            delay = random.uniform(config.BUFF_DELAY_MIN_SECONDS, config.BUFF_DELAY_MAX_SECONDS)
            logger.info(f"[Buff163] Waiting {delay:.0f}s before page {page_num}...")
            await asyncio.sleep(delay)

            params = {
                "game": "csgo",
                "page_num": page_num,
                "tab": "selling",
                "_": int(time.time() * 1000)
            }

            try:
                response = await client.get(BUFF_GOODS_URL, params=params, headers=BUFF_HEADERS)
                response.raise_for_status()
                json_data = response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"[Buff163] HTTP {e.response.status_code} on page {page_num} — stopping.")
                break
            except Exception as e:
                logger.error(f"[Buff163] Error on page {page_num}: {e} — stopping.")
                break

            if json_data.get("code") != "OK":
                logger.error(f"[Buff163] API returned non-OK on page {page_num}: {json_data.get('code')} — stopping.")
                break

            data_block = json_data.get("data", {})
            items = data_block.get("items", [])
            total_page = data_block.get("total_page", 1)

            if not items:
                logger.info(f"[Buff163] Page {page_num} empty — end of listing reached.")
                break

            page_saved = 0
            page_skipped = 0
            for item in items:
                try:
                    goods_id = item.get("id")
                    name = item.get("name")
                    if not goods_id or not name:
                        continue

                    db_manager.insert_buff_mapping(goods_id, name)
                    total_learned += 1

                    price_cny_str = item.get("sell_min_price")
                    if not price_cny_str:
                        continue
                    price_usd = round(float(price_cny_str) * currency_rate, 6)

                    buff_asset_id = f"BUFF-{goods_id}"

                    # Skip if already in DB with the exact same price
                    if existing_prices.get(buff_asset_id) == price_usd:
                        page_skipped += 1
                        total_skipped += 1
                        continue

                    db_manager.insert_or_update_listing(
                        skin_name=name,
                        asset_id=buff_asset_id,
                        source="BUFF",
                        original_price_usd=price_usd,
                        current_price_usd=price_usd,
                        timestamp_str=timestamp_str,
                        float_val=None,
                        pattern_id=None,
                    )
                    # Update in-memory cache so later pages see the new price too
                    existing_prices[buff_asset_id] = price_usd
                    page_saved += 1
                    total_saved += 1

                except Exception as e:
                    logger.warning(f"[Buff163] Could not process item on page {page_num}: {e}")
                    continue

            logger.info(
                f"[Buff163] Page {page_num}/{total_page} — "
                f"{page_saved} saved, {page_skipped} skipped (price unchanged), "
                f"{len(items)} items processed"
            )

            # Persist progress after every page
            state["buff_global_last_page"] = page_num
            _save_state(state)

            if page_num >= total_page:
                logger.info(f"[Buff163] All {total_page} pages scraped.")
                break
            page_num += 1

    # Mark scrape as complete — next run starts fresh from page 1
    state["buff_global_in_progress"] = False
    state["buff_global_last_page"] = 1
    _save_state(state)

    elapsed = time.time() - start_time
    logger.info(
        f"[Buff163] Global scrape complete — {total_saved} saved, "
        f"{total_skipped} skipped (unchanged), {total_learned} IDs learned in {elapsed:.1f}s"
    )


async def scrape_buff_sell_orders_for_monitored(db_manager: database.DatabaseManager):
    """
    For every goods_id in buff_mapping that has been linked to a CSFloat paint_index,
    fetches individual sell_order listings (with paintwear/float and paintseed/pattern)
    and saves them to Supabase — matching the same column structure as CSFloat listings.
    """
    import random
    logger.info("[Buff163] Starting individual sell_order scrape for monitored items...")
    start_time = time.time()

    currency_rate = db_manager.get_latest_currency_rate()
    if currency_rate is None:
        logger.error("[Buff163] No currency rate available — aborting sell_order scrape.")
        return

    # Fetch all buff_mapping rows that are linked to a CSFloat paint_index
    linked_mappings = db_manager.get_all_linked_buff_mappings()
    if not linked_mappings:
        logger.info("[Buff163] No linked goods_ids found in buff_mapping yet. Run global scrape first.")
        return

    logger.info(f"[Buff163] Scraping sell orders for {len(linked_mappings)} linked goods_id(s)...")
    total_saved = 0

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        for mapping in linked_mappings:
            goods_id   = mapping.get("goods_id")
            buff_name  = mapping.get("buff_name", f"goods_id_{goods_id}")

            logger.info(f"[Buff163] Fetching sell orders for goods_id {goods_id} ({buff_name})...")
            raw_listings = await fetch_buff_listings(client, goods_id)

            if raw_listings is None:
                logger.error(f"[Buff163] Failed to fetch sell orders for goods_id {goods_id}.")
                continue

            parsed = parse_buff_listings(raw_listings, goods_id, currency_rate)
            saved = 0
            for listing_info in parsed:
                db_manager.insert_or_update_listing(
                    skin_name=listing_info["skin_name"],
                    asset_id=listing_info["asset_id"],
                    source=listing_info["src"],
                    original_price_usd=listing_info["original_price_usd"],
                    current_price_usd=listing_info["current_price_usd"],
                    timestamp_str=listing_info["timestamp_str"],
                    float_val=listing_info["float_val"],
                    pattern_id=listing_info["pattern_id"],
                )
                saved += 1

            total_saved += saved
            logger.info(f"[Buff163] goods_id {goods_id} — {saved}/{len(raw_listings)} listings saved")

    elapsed = time.time() - start_time
    logger.info(f"[Buff163] Sell-order scrape complete — {total_saved} individual listings saved in {elapsed:.1f}s")
