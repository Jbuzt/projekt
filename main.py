# main.py
import asyncio
import logging
import schedule # pip install schedule
import time
from datetime import datetime, timedelta
import config
import database
import discovery
import scraper
import utils

# --- Setup Logging ---
class _ExcludeHttpxFilter(logging.Filter):
    def filter(self, record):
        return record.name not in ('httpx', 'httpcore', 'hpack')

_LOG_FMT  = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
_DATE_FMT = '%d-%m-%Y @ %H:%M:%S'

class _ColorConsoleFormatter(logging.Formatter):
    """Applies ANSI colors to console output only (never written to log file)."""
    _RESET  = '\033[0m'
    _BOLD   = '\033[1m'
    # Level colors
    _LEVEL  = {
        'DEBUG':    '\033[90m',    # dark gray
        'INFO':     '\033[97m',    # bright white
        'WARNING':  '\033[93m',    # bright yellow
        'ERROR':    '\033[91m',    # bright red
        'CRITICAL': '\033[1;91m',  # bold bright red
    }
    # Prefix-specific colors override INFO color
    _PREFIX = {
        '[CSFloat]': '\033[96m',   # cyan
        '[Buff163]': '\033[95m',   # magenta
        '[Scrape]':  '\033[92m',   # bright green
        '---':       '\033[33m',   # orange/yellow  (cycle banners)
    }

    def format(self, record):
        msg = super().format(record)
        if record.levelname == 'INFO':
            for prefix, color in self._PREFIX.items():
                if prefix in msg:
                    return f"{color}{msg}{self._RESET}"
        color = self._LEVEL.get(record.levelname, '')
        return f"{color}{msg}{self._RESET}" if color else msg

# Plain formatter for the log file (no ANSI codes)
_file_formatter = logging.Formatter(fmt=_LOG_FMT, datefmt=_DATE_FMT)
_file_handler = logging.FileHandler("logs/bot.log")
_file_handler.setFormatter(_file_formatter)
_file_handler.addFilter(_ExcludeHttpxFilter())

# Color formatter for the terminal
_console_formatter = _ColorConsoleFormatter(fmt=_LOG_FMT, datefmt=_DATE_FMT)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_console_formatter)
_console_handler.addFilter(_ExcludeHttpxFilter())

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    handlers=[_file_handler, _console_handler]
)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def main():
    """
    Main asynchronous function to orchestrate the bot.
    Initializes components and runs scheduled tasks.
    """
    logger.info("Starting CS2 Skin Trader Bot...")

    # Initialize Database Manager
    try:
        db_manager = database.DatabaseManager()
    except Exception as e:
        logger.critical(f"Failed to initialize Database Manager. Exiting. Error: {e}")
        return # Exit if DB connection fails

    # --- CORRECTED BLOCK: Fetch currency rate immediately on startup if not present ---
    logger.info("Checking for existing currency rate in DB...")
    initial_rate_check = db_manager.get_latest_currency_rate()
    if initial_rate_check is None:
        logger.info("No currency rate found in DB. Fetching initial rate now...")
        utils.fetch_and_store_currency_rate(db_manager)
        # After fetching, check again to confirm it was stored
        # A small delay might be needed here if fetch_and_store_currency_rate is purely synchronous
        # and writes might be slightly delayed. However, it's likely synchronous.
        # Let's re-fetch to be sure.
        # Note: fetch_and_store_currency_rate in utils.py is synchronous.
        # We might need to wait a tiny bit if Supabase write is async underneath.
        # For now, assume it's effectively synchronous for this check.
        time.sleep(1) # Brief pause to allow potential async DB write to settle
        recheck_rate = db_manager.get_latest_currency_rate()
        if recheck_rate is not None:
            logger.info(f"Initial currency rate fetched and stored successfully: {recheck_rate}")
        else:
            logger.warning("Attempted to fetch initial currency rate, but it's still not found in DB. Buff scraping might fail.")
    else:
        logger.info(f"Currency rate found in DB: {initial_rate_check}")
    # --- END OF CORRECTED BLOCK ---

    # Schedule tasks
    # 1. Buff163 global scrape (discovery + aggregate min prices) — every 6 hours
    BUFF_GLOBAL_INTERVAL_HOURS = 6
    schedule.every(BUFF_GLOBAL_INTERVAL_HOURS).hours.do(
        lambda: asyncio.ensure_future(scraper.scrape_buff_global(db_manager))
    )
    # 2. Buff163 individual sell_order scrape (float + pattern per listing) — same interval
    schedule.every(BUFF_GLOBAL_INTERVAL_HOURS).hours.do(
        lambda: asyncio.ensure_future(scraper.scrape_buff_sell_orders_for_monitored(db_manager))
    )
    # 3. Fetch currency rate daily at the specified hour
    schedule.every().day.at(f"{config.CURRENCY_FETCH_HOUR:02d}:00").do(lambda: utils.fetch_and_store_currency_rate(db_manager))

    # CSFloat items to monitor — paint_index + float range only (no goods_id, Buff163 is independent)
    ITEMS_TO_MONITOR = [
        # (paint_index, min_float, max_float)
        (639, 0.00, 0.07),   # AK-47 | Bloodsport — Factory New range
        (639, 0.15, 0.25),   # AK-47 | Bloodsport — Field-Tested range
    ]

    # Kick off an immediate Buff163 global scrape on startup
    logger.info("[Buff163] Scheduling immediate global scrape on startup...")
    asyncio.ensure_future(scraper.scrape_buff_global(db_manager))

    logger.info(f"Monitoring {len(ITEMS_TO_MONITOR)} item configuration(s). Scrape interval: {config.SCRAPE_INTERVAL_SECONDS}s.")
    logger.info("Entering main scraping loop...")
    last_scrape_times = {}

    while True:
        current_time = time.time()
        due_tasks = []

        for item_info in ITEMS_TO_MONITOR:
            paint_idx, min_flt, max_flt = item_info
            item_key = (paint_idx, min_flt, max_flt)

            last_scrape_time = last_scrape_times.get(item_key, 0)
            if current_time - last_scrape_time >= config.SCRAPE_INTERVAL_SECONDS:
                due_tasks.append((paint_idx, min_flt, max_flt))
                last_scrape_times[item_key] = current_time

        if due_tasks:
            logger.info(f"--- Scrape cycle starting: {len(due_tasks)} item(s) queued (running concurrently) ---")
            cycle_start = time.time()
            await asyncio.gather(*[
                run_specific_scrape_task(db_manager, p, mn, mx)
                for p, mn, mx in due_tasks
            ])
            logger.info(f"--- Scrape cycle complete in {time.time() - cycle_start:.1f}s. Next check in {config.SCRAPE_INTERVAL_SECONDS}s. ---")

        # Run scheduled tasks (discovery, currency fetch)
        schedule.run_pending()

        await asyncio.sleep(5)


async def run_specific_scrape_task(db_man, paint_idx, min_flt, max_flt):
    try:
        await scraper.scrape_item(db_man, paint_idx, min_float=min_flt, max_float=max_flt)
    except Exception as e:
        logger.error(f"Error during scrape task for paint_index {paint_idx}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
