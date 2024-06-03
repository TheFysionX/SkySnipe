import asyncio
import re
import os
import time
import json
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import requests
from tqdm import tqdm

# Constants
API_URL = "https://api.hypixel.net/skyblock/auctions?page="
MAX_WORKERS = 24  # Utilize 24 cores
PRICE_THRESHOLD = 1_000_000  # Minimum price to consider
UPPER_PRICE_LIMIT = 200_000_000  # Maximum price to consider
MIN_ITEM_COUNT = 12  # Minimum number of the same item in JSON to consider

# Reforges to remove
REFORGES = [" ✦", "⚚ ", " ✪", "✪", "Stiff ", "Lucky ", "Jerry's ", "Dirty ", "Fabled ", "Suspicious ", "Gilded ", "Warped ", "Withered ", "Bulky ", "Stellar ", "Heated ", "Ambered ", "Fruitful ", "Magnetic ", "Fleet ", "Mithraic ", "Auspicious ", "Refined ", "Headstrong ", "Precise ", "Spiritual ", "Moil ", "Blessed ", "Toil ", "Bountiful ", "Candied ", "Submerged ", "Reinforced ", "Cubic ", "Warped ", "Undead ", "Ridiculous ", "Necrotic ", "Spiked ", "Jaded ", "Loving ", "Perfect ", "Renowned ", "Giant ", "Empowered ", "Ancient ", "Sweet ", "Silky ", "Bloody ", "Shaded ", "Gentle ", "Odd ", "Fast ", "Fair ", "Epic ", "Sharp ", "Heroic ", "Spicy ", "Legendary ", "Deadly ", "Fine ", "Grand ", "Hasty ", "Neat ", "Rapid ", "Unreal ", "Awkward ", "Rich ", "Clean ", "Fierce ", "Heavy ", "Light ", "Mythic ", "Pure ", "Smart ", "Titanic ", "Wise ", "Bizarre ", "Itchy ", "Ominous ", "Pleasant ", "Pretty ", "Shiny ", "Simple ", "Strange ", "Vivid ", "Godly ", "Demonic ", "Forceful ", "Hurtful ", "Keen ", "Strong ", "Superior ", "Unpleasant ", "Zealous "]

# Blacklist words
BLACKLIST = ["Skin", "Rune"]  # Add words to this list

# Blacklist categories
CATEGORY_BLACKLIST = ["misc"]

# Load pre-saved BIN auction data from JSON file
def load_bin_data(file_path):
    with open(file_path, 'r') as f:
        bin_data = json.load(f)
    return bin_data

# Initialize RAM and lowest prices and item counts from pre-saved BIN auction data
def initialize_ram_and_lowest_prices(bin_data):
    lowest_prices = {}
    item_counts = {}
    ram = {}
    item_occurrences = {}

    for auction in bin_data:
        index = re.sub("\[[^\]]*\]", "", auction['item_name'])
        for reforge in REFORGES:
            index = index.replace(reforge, "")
        index += auction['tier']
        item_occurrences[index] = item_occurrences.get(index, 0) + 1
        if index in lowest_prices:
            if auction['starting_bid'] < lowest_prices[index]:
                lowest_prices[index] = auction['starting_bid']
            item_counts[index] += 1
        else:
            lowest_prices[index] = auction['starting_bid']
            item_counts[index] = 1

    # Sort items by occurrence and add top 150 to RAM
    sorted_items = sorted(item_occurrences.items(), key=lambda x: x[1], reverse=True)[:150]
    for item, _ in sorted_items:
        ram[item] = lowest_prices[item]

    return lowest_prices, item_counts, ram

# Fetch all pages and return the total number of pages
def fetch_initial_data():
    response = requests.get(API_URL + "0")
    data = response.json()
    return data['lastUpdated'], data['totalPages']

# Fetch a single page of auction data
def fetch_page(session, page):
    response = session.get(API_URL + str(page))
    return response.json()

# Check if the item name or category contains any blacklisted words
def is_blacklisted(item_name, item_category):
    if any(word.lower() in item_name.lower() for word in BLACKLIST):
        return True
    if item_category.lower() in CATEGORY_BLACKLIST:
        return True
    return False

# Process auction data
def process_auction(auction, results, now, lowest_prices, item_counts, new_data, ram):
    if not auction['claimed'] and auction['bin'] and auction['uuid'] not in seen_auctions:
        if auction['start'] + 60000 > now:  # New auctions within the last 60 seconds
            if is_blacklisted(auction['item_name'], auction['category']):
                return
            seen_auctions.add(auction['uuid'])
            index = re.sub("\[[^\]]*\]", "", auction['item_name'])
            for reforge in REFORGES:
                index = index.replace(reforge, "")
            index += auction['tier']
            starting_bid = auction['starting_bid']

            # Calculate tax based on the price
            if starting_bid > 100_000_000:
                tax = 0.025 * starting_bid
            elif 10_000_000 <= starting_bid <= 100_000_000:
                tax = 0.02 * starting_bid
            else:
                tax = 0.01 * starting_bid

            # Always add new auctions to new_data for JSON update
            new_data.append(auction)

            # Check in RAM first, if not found, check in lowest_prices
            lowest_price = ram.get(index, lowest_prices.get(index))
            if index not in ram and lowest_price is not None:
                ram[index] = lowest_price

            # Only add to results if it meets criteria
            if lowest_price and PRICE_THRESHOLD <= starting_bid <= UPPER_PRICE_LIMIT and item_counts.get(index, 0) >= MIN_ITEM_COUNT:
                profit = lowest_price - starting_bid - tax
                if profit > 0:
                    results.append((auction['uuid'], auction['item_name'], starting_bid, lowest_price, profit))

# Asynchronous data fetcher
async def fetch_all_data(total_pages):
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        with requests.Session() as session:
            loop = asyncio.get_event_loop()
            tasks = [loop.run_in_executor(executor, fetch_page, session, page) for page in range(total_pages)]
            for response in tqdm(await asyncio.gather(*tasks), total=total_pages, desc="Fetching auction data"):
                results.append(response)
    return results

# Update the JSON file with new auction data
def update_json_file(file_path, new_data):
    with open(file_path, 'r') as f:
        data = json.load(f)
    data.extend(new_data)
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

# Main function
def main(bin_file_path):
    global results, seen_auctions, lowest_prices, item_counts, ram
    seen_auctions = set()

    # Load BIN data and initialize RAM, lowest prices, and item counts
    bin_data = load_bin_data(bin_file_path)
    lowest_prices, item_counts, ram = initialize_ram_and_lowest_prices(bin_data)

    # Synchronize with the next full minute
    current_time = time.time()
    next_minute = (current_time // 60 + 1) * 60
    wait_time = next_minute - current_time
    print(f"Waiting for {wait_time} seconds to synchronize with the Hypixel auctions reset timer.")
    time.sleep(wait_time)

    while True:
        now, total_pages = fetch_initial_data()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        future = asyncio.ensure_future(fetch_all_data(total_pages))
        responses = loop.run_until_complete(future)

        results = []
        new_data = []

        for data in responses:
            for auction in data['auctions']:
                process_auction(auction, results, now, lowest_prices, item_counts, new_data, ram)

        # Utilize the idle time to update JSON file with new auction data
        print("Storing new data to JSON file...")
        update_json_file(bin_file_path, new_data)

        # Get top 10 best deals (highest profit)
        best_deals = sorted(results, key=lambda x: x[4], reverse=True)[:10]

        if best_deals:
            best_deal = best_deals[0]
            df = pd.DataFrame([f'/viewauction {best_deal[0]}'])
            df.to_clipboard(index=False, header=False)
            print("Top 10 best deals for new BIN auctions:")
            for auction in best_deals:
                print(f"UUID: {auction[0]}, Item: {auction[1]}, Price: {auction[2]}, Lowest Price: {auction[3]}, Profit: {auction[4]:,}")

            if os.name == 'nt':
                import winsound
                winsound.Beep(500, 500)  # Emit a beep sound

        print("Looking for new BIN auctions...")
        
        # Wait until the next full minute to fetch data again
        current_time = time.time()
        next_minute = (current_time // 60 + 1) * 60
        wait_time = next_minute - current_time
        time.sleep(wait_time)

if __name__ == "__main__":
    # Specify the file path where your BIN data JSON is stored
    bin_file_path = "./storage/data.json"  # Change this to your actual file path
    main(bin_file_path)