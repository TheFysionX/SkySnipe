import os
import json
import requests
import asyncio
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm  # For loading bar

# Constants
API_URL = "https://api.hypixel.net/skyblock/auctions?page="
MAX_WORKERS = 24  # Utilize 24 cores

# Fetch initial data to get the total number of pages
def fetch_initial_data():
    response = requests.get(API_URL + "0")
    data = response.json()
    return data['totalPages']

# Fetch a single page of auction data
def fetch_page(session, page):
    response = session.get(API_URL + str(page))
    return response.json()

# Asynchronous data fetcher
async def fetch_all_data(total_pages):
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        with requests.Session() as session:
            loop = asyncio.get_event_loop()
            tasks = [
                loop.run_in_executor(
                    executor,
                    fetch_page,
                    *(session, page)
                )
                for page in range(total_pages)
            ]
            for response in tqdm(await asyncio.gather(*tasks), total=total_pages, desc="Fetching auction data"):
                results.append(response)
    return results

# Process and store data
def process_and_store_data(data, file_path):
    bin_auctions = []
    for page_data in data:
        for auction in page_data['auctions']:
            if auction['bin']:
                bin_auctions.append(auction)
    
    with open(file_path, 'w') as f:
        json.dump(bin_auctions, f, indent=4)

def main(file_path):
    print("Starting to fetch auction data...")
    total_pages = fetch_initial_data()
    print(f"Total pages to fetch: {total_pages}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    future = asyncio.ensure_future(fetch_all_data(total_pages))
    data = loop.run_until_complete(future)
    
    print("Processing and storing auction data...")
    process_and_store_data(data, file_path)
    print(f"Data successfully stored in {file_path}")

if __name__ == "__main__":
    # Specify the file path where you want to save the JSON data
    file_path = "./storage/data.json"  # Change this to your desired path
    main(file_path)
