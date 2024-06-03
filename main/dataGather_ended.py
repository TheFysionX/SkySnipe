import requests
import json
from tqdm import tqdm
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Constants
API_URL = "https://api.hypixel.net/skyblock/auctions"
API_KEY = "your_api_key_here"
MAX_WORKERS = 24  # Utilize 24 cores

# Fetch all pages and return the total number of pages
def fetch_initial_data():
    response = requests.get(f"{API_URL}?key={API_KEY}&page=0")
    data = response.json()
    return data['totalPages']

# Fetch a single page of auction data
def fetch_page(session, page):
    response = session.get(f"{API_URL}?key={API_KEY}&page={page}")
    return response.json()

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

# Filter ended auctions
def filter_ended_auctions(data):
    ended_auctions = []
    for page in data:
        for auction in page['auctions']:
            if auction['claimed']:
                ended_auctions.append(auction)
    return ended_auctions

# Append new auction data to JSON file
def update_json_file(file_path, new_data):
    with open(file_path, 'r') as f:
        data = json.load(f)
    data.extend(new_data)
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

# Main function
def main(file_path):
    total_pages = fetch_initial_data()
    print(f"Total pages to fetch: {total_pages}")
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    future = asyncio.ensure_future(fetch_all_data(total_pages))
    data = loop.run_until_complete(future)
    
    ended_auctions = filter_ended_auctions(data)
    
    update_json_file(file_path, ended_auctions)
    print(f"Appended {len(ended_auctions)} ended auctions to {file_path}")

if __name__ == "__main__":
    # Specify the file path where your BIN data JSON is stored
    bin_file_path = "./storage/data.json"  # Change this to your actual file path
    main(bin_file_path)