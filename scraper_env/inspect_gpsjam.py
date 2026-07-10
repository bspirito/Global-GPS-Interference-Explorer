from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def handle_response(response):
            url = response.url
            if ".json" in url or ".csv" in url or ".pbf" in url or "data" in url or "api" in url or "geojson" in url:
                print(f"Interesting URL: {url}")

        page.on("response", handle_response)
        
        print("Navigating to gpsjam.org...")
        page.goto("https://gpsjam.org/?date=2024-02-14", wait_until="networkidle")
        time.sleep(5)
        
        browser.close()

if __name__ == "__main__":
    run()
