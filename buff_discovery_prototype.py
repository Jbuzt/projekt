"""
Buff163 Brute-Force Discovery Prototype

This script brute-forces Buff163 API pages to discover all available goods_id,
collecting price and float/wear data. It stores aggregated statistics in a
new 'buff_discovery_cache' table.

WARNING: This is a HEAVY operation that will make thousands of API calls.
         Expect this to run for several hours.
"""

import asyncio
import aiohttp
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict
import json

# Import from existing modules
from config import BUFF163_API_KEY, SUPABASE_URL, SUPABASE_KEY
from database import Database

# Buff163 category IDs (you may need to expand this list)
# Common categories: 5=Knives, 20=Rifles, 21=Pistols, 22=SMGs, 23=Shotguns, 
# 24=Machine Guns, 25=Gloves, 26=Agents, 27=Stickers, 28=Cases, 29=Keys
CATEGORY_IDS = [5, 20, 21, 22, 23, 24, 25]

# You can filter by specific skin names if you only want certain items
# Leave empty to discover everything
TARGET_SKIN_NAMES = [
    # "AK-47 | Bloodsport",
    # "AWP | Dragon Lore",
]

class BuffDiscoveryBot:
    def __init__(self):
        self.db = Database()
        self.session: Optional[aiohttp.ClientSession] = None
        self.stats = {
            'total_pages_checked': 0,
            'total_items_found': 0,
            'unique_goods_ids': 0,
            'empty_pages': 0,
            'start_time': None,
        }
        
    async def init_session(self):
        """Initialize aiohttp session with proper headers"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        }
        if BUFF163_API_KEY:
            headers['Authorization'] = f'Bearer {BUFF163_API_KEY}'
            
        self.session = aiohttp.ClientSession(headers=headers)
        
    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            
    def get_wear_category_from_name(self, item_name: str) -> str:
        """Extract wear category from Buff163 item name"""
        name_lower = item_name.lower()
        if 'factory new' in name_lower or '(fn)' in name_lower:
            return 'FN'
        elif 'minimal wear' in name_lower or '(mw)' in name_lower:
            return 'MW'
        elif 'field-tested' in name_lower or '(ft)' in name_lower:
            return 'FT'
        elif 'well-worn' in name_lower or '(ww)' in name_lower:
            return 'WW'
        elif 'battle-scarred' in name_lower or '(bs)' in name_lower:
            return 'BS'
        else:
            return 'UNKNOWN'
            
    async def fetch_category_page(self, category_id: int, page: int) -> Optional[Dict]:
        """Fetch a single page from Buff163 category"""
        url = "https://buff.163.com/api/market/sell_order"
        params = {
            'game': 'csgo',
            'category_id': category_id,
            'page_num': page,
            'page_size': 50,  # Max allowed
            'sort_by': 'price.desc',  # Sort to get varied results
        }
        
        try:
            async with self.session.get(url, params=params, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == 'OK':
                        return data.get('data', {})
                elif resp.status == 429:
                    print(f"⚠️  Rate limited! Waiting 60s...")
                    await asyncio.sleep(60)
                    return await self.fetch_category_page(category_id, page)
                else:
                    print(f"❌ HTTP {resp.status} for cat {category_id} page {page}")
        except Exception as e:
            print(f"❌ Error fetching cat {category_id} page {page}: {e}")
        return None
        
    async def process_listings(self, listings: List[Dict]):
        """Process a batch of listings and store in buff_discovery_cache"""
        if not listings:
            return
            
        # Aggregate data by goods_id
        aggregated: Dict[int, Dict] = defaultdict(lambda: {
            'item_name': '',
            'wear_category': 'UNKNOWN',
            'prices': [],
            'floats': [],
        })
        
        for item in listings:
            goods_id = item.get('goods_id')
            if not goods_id:
                continue
                
            item_name = item.get('goods_info', {}).get('name', 'Unknown Item')
            wear_category = self.get_wear_category_from_name(item_name)
            price = float(item.get('price', 0)) / 100  # Buff stores price * 100
            paintwear = item.get('paintwear')
            
            # Convert paintwear string to float
            float_val = None
            if paintwear:
                try:
                    float_val = float(paintwear)
                except (ValueError, TypeError):
                    pass
            
            # Aggregate
            agg = aggregated[goods_id]
            agg['item_name'] = item_name
            agg['wear_category'] = wear_category
            agg['prices'].append(price)
            if float_val is not None:
                agg['floats'].append(float_val)
                
        # Store aggregated data in database
        for goods_id, data in aggregated.items():
            if not data['prices']:
                continue
                
            prices = data['prices']
            floats = data['floats']
            
            await self.db.upsert_buff_discovery(
                goods_id=goods_id,
                item_name=data['item_name'],
                wear_category=data['wear_category'],
                min_price=min(prices),
                max_price=max(prices),
                avg_price=sum(prices) / len(prices),
                sample_count=len(prices),
                min_float=min(floats) if floats else None,
                max_float=max(floats) if floats else None,
            )
            
            self.stats['total_items_found'] += len(prices)
            
    async def scrape_category(self, category_id: int):
        """Scrape all pages for a single category"""
        print(f"\n📦 Starting category {category_id}...")
        page = 1
        consecutive_empty = 0
        max_consecutive_empty = 3  # Stop after 3 empty pages
        
        while consecutive_empty < max_consecutive_empty:
            # Fetch page
            data = await self.fetch_category_page(category_id, page)
            self.stats['total_pages_checked'] += 1
            
            if not data:
                consecutive_empty += 1
                self.stats['empty_pages'] += 1
                print(f"  Page {page}: Empty/ERROR ({consecutive_empty}/{max_consecutive_empty})")
                await asyncio.sleep(2)  # Short delay for errors
                page += 1
                continue
                
            listings = data.get('items', [])
            
            if not listings:
                consecutive_empty += 1
                self.stats['empty_pages'] += 1
                print(f"  Page {page}: No listings ({consecutive_empty}/{max_consecutive_empty})")
                page += 1
                await asyncio.sleep(1)
                continue
                
            # Process listings
            await self.process_listings(listings)
            consecutive_empty = 0  # Reset counter
            
            # Progress logging
            elapsed = time.time() - self.stats['start_time']
            pages_per_hour = self.stats['total_pages_checked'] / (elapsed / 3600) if elapsed > 0 else 0
            print(f"  Page {page}: Found {len(listings)} items | "
                  f"Total: {self.stats['total_items_found']} | "
                  f"Speed: {pages_per_hour:.0f} pages/hr")
            
            # Move to next page
            page += 1
            
            # Rate limiting: Buff163 is strict, use 20-30s delay
            await asyncio.sleep(20)
            
        print(f"✅ Category {category_id} complete. Checked {page} pages.")
        
    async def run(self):
        """Main execution"""
        print("🚀 Buff163 Brute-Force Discovery Prototype")
        print("=" * 50)
        print(f"Categories to scan: {CATEGORY_IDS}")
        if TARGET_SKIN_NAMES:
            print(f"Target skins: {TARGET_SKIN_NAMES}")
        else:
            print("Target skins: ALL (no filter)")
        print("=" * 50)
        print("⚠️  WARNING: This will take several hours!")
        print(f"Estimated time: {len(CATEGORY_IDS) * 500 * 20 / 3600:.1f} hours "
              f"(assuming ~500 pages per category, 20s delay)")
        print()
        
        # Initialize
        await self.init_session()
        await self.db.connect()
        self.stats['start_time'] = time.time()
        
        try:
            # Scan each category
            for category_id in CATEGORY_IDS:
                await self.scrape_category(category_id)
                
                # Longer delay between categories
                print(f"⏸️  Waiting 60s before next category...")
                await asyncio.sleep(60)
                
        finally:
            # Cleanup
            await self.close_session()
            await self.db.disconnect()
            
            # Final stats
            elapsed = time.time() - self.stats['start_time']
            print("\n" + "=" * 50)
            print("📊 DISCOVERY COMPLETE")
            print(f"Total runtime: {elapsed / 3600:.2f} hours")
            print(f"Pages checked: {self.stats['total_pages_checked']}")
            print(f"Items processed: {self.stats['total_items_found']}")
            print(f"Empty pages: {self.stats['empty_pages']}")
            print("=" * 50)


async def main():
    bot = BuffDiscoveryBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
