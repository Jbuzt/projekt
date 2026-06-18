# utils.py
import logging
from datetime import datetime, timezone
import requests # For fetching currency rates
import database # Import DatabaseManager if needed within utils
import config # Import config for currency URL

logger = logging.getLogger(__name__)

def generate_timestamp_string() -> str:
    """
    Generates a timestamp string in the format 'DD/MM/YYYY HH:MM AM/PM'.
    e.g., '18/06/2026 02:30 PM'
    Returns:
        str: The formatted timestamp string.
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%d/%m/%Y %I:%M %p")

def parse_timestamp_string(timestamp_str: str) -> datetime:
    """
    Parses a timestamp string in the format 'DD/MM/YYYY HH:MM AM/PM' into a datetime object.
    e.g., '18/06/2026 02:30 PM' -> datetime object
    Args:
        timestamp_str (str): The timestamp string to parse.
    Returns:
        datetime: The parsed datetime object (timezone-aware, UTC).
    """
    dt_naive = datetime.strptime(timestamp_str, "%d/%m/%Y %I:%M %p")
    return dt_naive.replace(tzinfo=timezone.utc)


def fetch_and_store_currency_rate(db_manager: database.DatabaseManager):
    """
    Fetches the latest CNY to USD exchange rate from the free API
    and stores it in the database for the current date.
    Args:
        db_manager (database.DatabaseManager): Instance of the database manager.
    """
    logger.info("Fetching latest CNY to USD exchange rate...")
    try:
        response = requests.get(config.CURRENCY_API_URL) # Use URL from config
        response.raise_for_status()
        data = response.json()

        if data.get("result") == "success":
            rate = data["rates"].get("USD") # Get USD rate where base is CNY
            if rate is not None:
                # Get today's date string in YYYY-MM-DD format
                today_str = datetime.now(timezone.utc).date().strftime('%Y-%m-%d')
                logger.info(f"Fetched CNY->USD rate: {rate} for date {today_str}")
                # Store the rate in the database
                db_manager.insert_currency_rate(today_str, rate)
            else:
                logger.error("Could not find USD rate in API response.")
        else:
            logger.error(f"API returned error: {data.get('result')}, {data.get('error-type', 'Unknown error')}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch currency rate: {e}")
    except KeyError as e:
        logger.error(f"Unexpected API response structure: missing key {e}. Response: {data}")
    except Exception as e:
        logger.error(f"Unexpected error fetching/storing currency rate: {e}")


# Example usage (when this file is run directly):
# if __name__ == "__main__":
#     ts = generate_timestamp_string()
#     print(f"Generated: {ts}")
#     parsed_ts = parse_timestamp_string(ts)
#     print(f"Parsed: {parsed_ts}, Type: {type(parsed_ts)}")
#
#     # Example for fetching currency (requires config.CURRENCY_API_URL and db_manager)
#     # import config
#     # import database
#     # db = database.DatabaseManager()
#     # fetch_and_store_currency_rate(db)
#     pass
