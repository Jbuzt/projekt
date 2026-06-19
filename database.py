# database.py
import logging
from typing import Dict, List, Optional, Tuple
from supabase import create_client, Client
import config # Import the config file to get Supabase credentials

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Manages connection and interactions with the Supabase database.
    """
    def __init__(self):
        self.url: str = config.SUPABASE_URL
        self.key: str = config.SUPABASE_KEY
        self.client: Optional[Client] = None
        self._connect()

    def _connect(self):
        """Initializes the Supabase client."""
        try:
            self.client = create_client(self.url, self.key)
            logger.info("Successfully connected to Supabase.")
        except Exception as e:
            logger.critical(f"Failed to connect to Supabase: {e}")
            raise # Re-raise the exception to halt execution if connection fails

    def insert_or_update_listing(self, skin_name: str, asset_id: str, source: str, original_price_usd: float, current_price_usd: float, timestamp_str: str, float_val: Optional[float] = None, pattern_id: Optional[int] = None, skin_id: Optional[int] = None):
        """
        Inserts or updates a listing in the 'listings' table.
        Upserts on (asset_id, src) — asset_id is the Steam asset ID for CSFloat
        or the Buff163 asset ID for Buff163 individual listings.
        Args:
            skin_name (str): The market hash name, e.g. 'AK-47 | Bloodsport (Field-Tested)'.
            asset_id (str): Unique item identifier (Steam asset ID or Buff163 asset ID).
            source (str): 'CSFL' or 'BUFF'.
            original_price_usd (float): Original listed price in USD.
            current_price_usd (float): Most recent price in USD.
            timestamp_str (str): Timestamp string in 'DD/MM/YYYY HH:MM AM/PM' format.
            float_val (Optional[float]): Item float value.
            pattern_id (Optional[int]): Paint seed / pattern ID.
            skin_id (Optional[int]): Platform-specific skin identifier (paint_index for CSFloat, goods_id for BUFF).
        """
        from utils import parse_timestamp_string
        timestamp_dt = parse_timestamp_string(timestamp_str)

        record = {
            "item_k":     skin_name,
            "asset_id":   asset_id,
            "src":        source,
            "og_prc":     original_price_usd,
            "found_at":   timestamp_dt.isoformat(),
            "up_prc":     current_price_usd,
            "up_at":      timestamp_dt.isoformat(),
            "float_value": float_val,
            "pattern_id": pattern_id,
            "skin_id":    skin_id,
        }

        try:
            data, count = self.client.table('listings').upsert(record, on_conflict='asset_id,src').execute()
            logger.debug(f"Upserted listing {asset_id} ({source}): {skin_name} @ ${current_price_usd:.2f}")
        except Exception as e:
            logger.error(f"Failed to upsert listing for {asset_id} - {skin_name} ({source}): {e}")

    def get_active_listings_for_item(self, item_paint_index: int, min_float: Optional[float] = None, max_float: Optional[float] = None) -> List[Dict]:
        """
        Retrieves active listings from the database for a specific CSFloat paint_index,
        optionally filtered by float range.
        Args:
            item_paint_index (int): The CSFloat paint_index (e.g., 639 for AK-47 Bloodsport).
            min_float (Optional[float]): Minimum float value to filter.
            max_float (Optional[float]): Maximum float value to filter.
        Returns:
            List[Dict]: A list of dictionaries representing the listings.
        """
        # Build the query dynamically based on filters
        query = self.client.table('listings').select('*').ilike('item_k', f'%-{item_paint_index}-%') # Use ilike to find the paint_index within the item_k string

        if min_float is not None:
            query = query.gte('float_value', min_float) # gte = greater than or equal
        if max_float is not None:
            query = query.lte('float_value', max_float) # lte = less than or equal

        try:
            data, count = query.execute()
            logger.debug(f"Fetched {count} listings for paint_index {item_paint_index} from DB.")
            # The data returned by supabase-py is typically [ [row1_dict, row2_dict, ...], count ]
            # Extract the list of rows
            if data:
                return data[0] # Return the list of dictionaries
            else:
                return [] # Return empty list if no data
        except Exception as e:
            logger.error(f"Failed to fetch listings for paint_index {item_paint_index} from DB: {e}")
            return []

    def get_latest_currency_rate(self) -> Optional[float]:
        """
        Retrieves the most recently fetched CNY to USD exchange rate from the database.
        Returns:
            Optional[float]: The latest exchange rate or None if not found.
        """
        try:
             # Order by date_recorded descending and limit to 1 to get the latest
             # The execute() method typically returns (data, count)
             # data is usually [[row1, row2, ...], count] or just [row1, row2, ...] depending on the library version/query type
             # For a select query, it's often [[rows...]]
             result = self.client.table('currency_rates').select('cny_to_usd_rate').order('date_recorded', desc=True).limit(1).execute()
             # Check the structure of 'result'
             # print(f"DEBUG: get_latest_currency_rate result: {result}") # Uncomment for debugging if needed

             # SupabasePy v2+ typically returns an object like { "data": [...], "count": ... }
             # Let's adapt to this newer structure.
             if hasattr(result, 'data'): # Check if result has a 'data' attribute (SupabasePy v2+ style)
                 data_rows = result.data
                 count = getattr(result, 'count', None) # Get count if available
             else: # Fallback for older style [data, count]
                 data_rows, count = result

             if data_rows and len(data_rows) > 0: # Check if the data list exists and is not empty
                 rate_entry = data_rows[0] # Get the first row dictionary
                 if isinstance(rate_entry, dict): # Ensure it's a dictionary
                     rate_value = rate_entry.get('cny_to_usd_rate') # Use .get() for safety
                     if rate_value is not None:
                         logger.debug(f"Fetched latest currency rate: {rate_value}")
                         return rate_value
                     else:
                         logger.warning("Currency rate entry found but 'cny_to_usd_rate' key is missing or None.")
                         return None
                 else:
                     logger.error(f"Expected a dictionary for currency rate entry, got {type(rate_entry)}: {rate_entry}")
                     return None
             else:
                 logger.warning("No currency rate found in database or data structure was empty.")
                 return None
        except Exception as e:
            logger.error(f"Failed to fetch latest currency rate from DB: {e}")
            # print(f"DEBUG: Exception in get_latest_currency_rate: {e}") # Uncomment for debugging if needed
            return None

    def insert_currency_rate(self, date_str: str, rate: float):
        """
        Inserts a new currency rate entry into the 'currency_rates' table.
        Args:
            date_str (str): The date string (e.g., 'YYYY-MM-DD').
            rate (float): The CNY to USD exchange rate.
        """
        from datetime import datetime
        # Convert date string to date object if necessary, assuming input is already 'YYYY-MM-DD'
        # Supabase should handle the DATE type conversion if passed correctly.
        record = {
            "date_recorded": date_str, # Pass the date string, Supabase should handle conversion
            "cny_to_usd_rate": rate
        }
        try:
            data, count = self.client.table('currency_rates').insert(record).execute()
            logger.info(f"Inserted currency rate for {date_str}: {rate}")
        except Exception as e:
            logger.error(f"Failed to insert currency rate for {date_str}: {e}")

    def insert_buff_mapping(self, goods_id: int, buff_name: str, csfloat_paint_index: Optional[int] = None):
        """
        Inserts or updates a Buff163 mapping entry.
        Args:
            goods_id (int): The Buff163 goods_id.
            buff_name (str): The Buff163 item name.
            csfloat_paint_index (Optional[int]): The linked CSFloat paint_index (if known).
        """
        record = {
            "goods_id": goods_id,
            "buff_name": buff_name,
            "csfloat_paint_index": csfloat_paint_index
        }
        try:
            # Upsert based on goods_id (which is the primary key)
            data, count = self.client.table('buff_mapping').upsert(record, on_conflict='goods_id').execute()
            logger.debug(f"Upserted Buff163 mapping for goods_id {goods_id}: {buff_name}")
        except Exception as e:
            logger.error(f"Failed to upsert Buff163 mapping for goods_id {goods_id}: {e}")

    def get_buff_mapping_by_name(self, buff_name: str) -> Optional[Dict]:
        """
        Retrieves a Buff163 mapping entry by name.
        Args:
            buff_name (str): The Buff163 item name.
        Returns:
            Optional[Dict]: The mapping entry or None if not found.
        """
        try:
            data, count = self.client.table('buff_mapping').select('*').eq('buff_name', buff_name).execute()
            if data and len(data[0]) > 0:
                 mapping_entry = data[0][0]
                 logger.debug(f"Found Buff163 mapping for name '{buff_name}': {mapping_entry}")
                 return mapping_entry
            else:
                 logger.debug(f"No Buff163 mapping found for name '{buff_name}'.")
                 return None
        except Exception as e:
            logger.error(f"Failed to fetch Buff163 mapping for name '{buff_name}' from DB: {e}")
            return None

    def get_buff_mapping_by_goods_id(self, goods_id: int) -> Optional[Dict]:
        """
        Retrieves a Buff163 mapping entry by goods_id.
        Args:
            goods_id (int): The Buff163 goods_id.
        Returns:
            Optional[Dict]: The mapping entry or None if not found.
        """
        try:
            data, count = self.client.table('buff_mapping').select('*').eq('goods_id', goods_id).execute()
            if data and len(data[0]) > 0:
                 mapping_entry = data[0][0]
                 logger.debug(f"Found Buff163 mapping for goods_id {goods_id}: {mapping_entry}")
                 return mapping_entry
            else:
                 logger.debug(f"No Buff163 mapping found for goods_id {goods_id}.")
                 return None
        except Exception as e:
            logger.error(f"Failed to fetch Buff163 mapping for goods_id {goods_id} from DB: {e}")
            return None
    def get_buff_mapping_by_csfloat_paint_index(self, paint_index: int) -> Optional[Dict]:
        """
        Retrieves a Buff163 mapping entry by CSFloat paint_index.
        Args:
            paint_index (int): The CSFloat paint_index.
        Returns:
            Optional[Dict]: The mapping entry (containing goods_id) or None if not found.
        """
        try:
            # Query the buff_mapping table where csfloat_paint_index matches
            # SupabasePy v2+ returns an object like { "data": [...], "count": ... }
            result = self.client.table('buff_mapping').select('*').eq('csfloat_paint_index', paint_index).execute()

            # Handle the v2+ response structure
            if hasattr(result, 'data'):
                 data_rows = result.data
                 # count = getattr(result, 'count', None) # Get count if needed
            else: # Fallback for older style [data, count]
                 data_rows, count = result

            if data_rows and len(data_rows) > 0:
                 mapping_entry = data_rows[0] # Get the first row dictionary
                 if isinstance(mapping_entry, dict): # Ensure it's a dictionary
                     logger.debug(f"Found Buff163 mapping for CSFloat paint_index {paint_index}: {mapping_entry}")
                     return mapping_entry
                 else:
                     logger.error(f"Expected a dictionary for buff mapping entry, got {type(mapping_entry)}: {mapping_entry}")
                     return None
            else:
                 logger.debug(f"No Buff163 mapping found for CSFloat paint_index {paint_index}.")
                 return None
        except Exception as e:
            logger.error(f"Failed to fetch Buff163 mapping for CSFloat paint_index {paint_index} from DB: {e}")
            return None

    def get_buff_global_prices(self) -> Dict[str, float]:
        """
        Returns a dict of {asset_id: up_prc} for all rows in listings where
        src='BUFF' and asset_id starts with 'BUFF-' (i.e. aggregate global entries).
        Used for price-change deduplication in scrape_buff_global.
        """
        try:
            result = (
                self.client.table('listings')
                .select('asset_id, up_prc')
                .eq('src', 'BUFF')
                .like('asset_id', 'BUFF-%')
                .execute()
            )
            rows = result.data if hasattr(result, 'data') else []
            return {row['asset_id']: row['up_prc'] for row in rows if row.get('asset_id') and row.get('up_prc') is not None}
        except Exception as e:
            logger.error(f"Failed to fetch existing Buff163 prices: {e}")
            return {}

    def get_all_linked_buff_mappings(self) -> List[Dict]:
        """
        Returns all buff_mapping rows where csfloat_paint_index IS NOT NULL.
        These are goods_ids that have been cross-linked to a CSFloat paint_index
        and should be scraped for individual sell_order listings.
        """
        try:
            result = (
                self.client.table('buff_mapping')
                .select('goods_id, buff_name, csfloat_paint_index')
                .not_.is_('csfloat_paint_index', 'null')
                .execute()
            )
            rows = result.data if hasattr(result, 'data') else []
            logger.debug(f"Found {len(rows)} linked buff_mapping entries.")
            return rows
        except Exception as e:
            logger.error(f"Failed to fetch linked buff_mapping entries: {e}")
            return []

    def link_buff_mapping_to_paint_index(self, base_name: str, paint_index: int) -> int:
        """
        Updates buff_mapping rows whose buff_name contains base_name (e.g. 'AK-47 | Bloodsport'),
        setting csfloat_paint_index = paint_index on any row that does not already have one.
        This links ALL Buff163 variants (StatTrak™, FN, FT, WW, BS, etc.) to a single
        CSFloat paint_index, since CSFloat uses one paint_index across all conditions/types.
        Returns the number of rows updated.
        """
        try:
            result = (
                self.client.table('buff_mapping')
                .update({'csfloat_paint_index': paint_index})
                .ilike('buff_name', f'%{base_name}%')
                .is_('csfloat_paint_index', 'null')
                .execute()
            )
            rows = result.data if hasattr(result, 'data') else []
            if rows:
                logger.info(f"[Mapping] Linked {len(rows)} Buff163 variant(s) for '{base_name}' → paint_index {paint_index}")
            return len(rows)
        except Exception as e:
            logger.error(f"Failed to link buff_mapping for '{base_name}' → paint_index {paint_index}: {e}")
            return 0

    def upsert_buff_discovery(
        self,
        goods_id: int,
        item_name: str,
        wear_category: str,
        min_price: float,
        max_price: float,
        avg_price: float,
        sample_count: int,
        min_float: Optional[float] = None,
        max_float: Optional[float] = None,
    ):
        """
        Upsert aggregated discovery data into buff_discovery_cache table.
        Updates existing records with new price/float statistics.
        """
        try:
            # Check if record exists
            existing = (
                self.client.table('buff_discovery_cache')
                .select('goods_id')
                .eq('goods_id', goods_id)
                .execute()
            )
            
            record = {
                'goods_id': goods_id,
                'item_name': item_name,
                'wear_category': wear_category,
                'min_price': round(min_price, 2),
                'max_price': round(max_price, 2),
                'avg_price': round(avg_price, 2),
                'sample_count': sample_count,
                'min_float': round(min_float, 6) if min_float is not None else None,
                'max_float': round(max_float, 6) if max_float is not None else None,
                'last_seen_at': datetime.now().isoformat(),
            }
            
            if existing.data and len(existing.data) > 0:
                # Update existing record - merge statistics
                current = existing.data[0]
                new_sample_count = current.get('sample_count', 0) + sample_count
                
                # Recalculate averages weighted by sample count
                old_avg = current.get('avg_price', 0)
                old_count = current.get('sample_count', 0)
                new_avg = ((old_avg * old_count) + (avg_price * sample_count)) / new_sample_count
                
                update_data = {
                    'min_price': min(current.get('min_price', min_price), min_price),
                    'max_price': max(current.get('max_price', max_price), max_price),
                    'avg_price': round(new_avg, 2),
                    'sample_count': new_sample_count,
                    'last_seen_at': datetime.now().isoformat(),
                }
                
                # Update float ranges if we have new data
                if min_float is not None:
                    old_min_float = current.get('min_float')
                    if old_min_float is None or min_float < old_min_float:
                        update_data['min_float'] = round(min_float, 6)
                        
                if max_float is not None:
                    old_max_float = current.get('max_float')
                    if old_max_float is None or max_float > old_max_float:
                        update_data['max_float'] = round(max_float, 6)
                
                result = (
                    self.client.table('buff_discovery_cache')
                    .update(update_data)
                    .eq('goods_id', goods_id)
                    .execute()
                )
                logger.debug(f"[BuffDiscovery] Updated goods_id {goods_id} ({item_name})")
            else:
                # Insert new record
                result = (
                    self.client.table('buff_discovery_cache')
                    .insert([record])
                    .execute()
                )
                logger.debug(f"[BuffDiscovery] Inserted goods_id {goods_id} ({item_name})")
                
        except Exception as e:
            logger.error(f"Failed to upsert buff_discovery for goods_id {goods_id}: {e}")

# Example usage (when this file is run directly):
# if __name__ == "__main__":
#     db = DatabaseManager()
#     # Example: Insert a dummy listing
#     # db.insert_or_update_listing("12345 - AWP | Dragon Lore (FN) - 0.000123456789012345 - [384]", "CSFL", 1000.0, 999.0, "18/06/26 02:00PM", 0.000123456789012345)
#     # Example: Fetch listings
#     # listings = db.get_active_listings_for_item(639, min_float=0.15, max_float=0.20)
#     # print(listings)
#     # Example: Insert currency rate
#     # from datetime import date
#     # today_str = date.today().strftime('%Y-%m-%d')
#     # db.insert_currency_rate(today_str, 0.14762)
#     # Example: Get latest rate
#     # rate = db.get_latest_currency_rate()
#     # print(f"Latest rate: {rate}")
#     # Example: Insert mapping
#     # db.insert_buff_mapping(33869, "AK-47 | Bloodsport (Field-Tested)", 639) # Assuming 639 is the CSFloat paint_index
#     # Example: Get mapping
#     # mapping = db.get_buff_mapping_by_name("AK-47 | Bloodsport (Field-Tested)")
#     # print(mapping)
#     pass
