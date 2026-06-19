-- Table to store raw Buff163 discovery data (goods_id, price, float/wear)
-- Used for brute-force prototyping and analysis
CREATE TABLE IF NOT EXISTS buff_discovery_cache (
    id BIGSERIAL PRIMARY KEY,
    goods_id BIGINT NOT NULL,
    item_name TEXT NOT NULL,
    wear_category TEXT NOT NULL, -- FN, MW, FT, WW, BS
    min_price NUMERIC(10, 2), -- Lowest price found for this goods_id
    max_price NUMERIC(10, 2), -- Highest price found for this goods_id
    avg_price NUMERIC(10, 2), -- Average price found for this goods_id
    sample_count INTEGER DEFAULT 1, -- How many listings we've seen for this goods_id
    min_float NUMERIC(10, 6), -- Lowest float found
    max_float NUMERIC(10, 6), -- Highest float found
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(goods_id)
);

-- Index for faster lookups by wear category or item name
CREATE INDEX IF NOT EXISTS idx_buff_discovery_wear ON buff_discovery_cache(wear_category);
CREATE INDEX IF NOT EXISTS idx_buff_discovery_name ON buff_discovery_cache(item_name);
