# config.py

# --- Supabase Configuration ---
SUPABASE_URL = "https://lshasbzcngiffanwxzgj.supabase.co" # e.g., "https://abcdeftghijk.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxzaGFzYnpjbmdpZmZhbnd4emdqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODE3Mzk4ODksImV4cCI6MjA5NzMxNTg4OX0.tzYWzjwiyyBFtujoeLo-OLRBzN7IcBUNigaj-k7jhNg" # e.g., "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# --- CSFloat API ---
CSFLOAT_API_KEY = "le4QBmkzrj1kZJX_qVvT6HnPoT2gFO-4" # Add this line

# --- Scheduling Configuration ---
SCRAPE_INTERVAL_SECONDS = 180  # How often to scrape a specific item category (e.g., 180 seconds = 3 minutes)
DISCOVERY_INTERVAL_HOURS = 168 # How often to run the Buff163 discovery process (e.g., 168 hours = 1 week)
CURRENCY_FETCH_HOUR = 13       # Hour of the day (24-hour format) to fetch currency rate (e.g., 13 for 1 PM)

# --- Marketplace Configuration ---
# Buff163 specific delays/ranges (for anti-bot measures)
BUFF_DELAY_MIN_SECONDS = 10    # Minimum delay between Buff163 requests
BUFF_DELAY_MAX_SECONDS = 30    # Maximum delay between Buff163 requests

# --- Currency API ---
CURRENCY_API_URL = "https://open.er-api.com/v6/latest/CNY" # Free API endpoint for CNY base

# --- Logging Configuration ---
LOG_LEVEL = "INFO" # Options: DEBUG, INFO, WARNING, ERROR, CRITICAL

# --- Calculation Weights ---
CSFLOAT_WEIGHT = 0.7           # Weight for CSFloat prices in baseline calculation
BUFF163_WEIGHT = 0.3           # Weight for Buff163 prices in baseline calculation