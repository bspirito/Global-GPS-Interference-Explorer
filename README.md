<img width="1588" height="833" alt="image" src="https://github.com/user-attachments/assets/a2eca07c-50b3-41b1-9923-5341cf6bdbea" />
<img width="1586" height="898" alt="image" src="https://github.com/user-attachments/assets/06566558-dbaf-4b0f-ba31-9cb706fb6529" />
<img width="1834" height="884" alt="image" src="https://github.com/user-attachments/assets/f7c4c160-8b49-4bd2-afb0-69bdbbfead93" />
<img width="564" height="529" alt="image" src="https://github.com/user-attachments/assets/3ef5a540-2411-4a74-bc25-af591274ff82" />
<img width="1531" height="800" alt="newplot (5)" src="https://github.com/user-attachments/assets/9f2d6fd8-d1a5-41ed-b4a4-d2f2c04e688f" />

# Global GPS Interference Explorer

A high-performance, cinematic spatial-temporal analysis dashboard for tracking global GPS interference and spoofing. Built with Python, Streamlit, PyDeck, and custom DeckGL integrations, this tool allows intelligence analysts and researchers to visualize spoofing campaigns, analyze regional hotspots, and generate HD timelapse videos of GPS denial over time.

## 🌟 Key Features
- **Cinematic 3D Visualization:** Explore the data on a 3D spinning globe or high-resolution satellite terrain maps with true two-way camera interactivity.
- **HD Video Generator:** Automatically compile high-definition (1080p, 1440p, 4K) mp4 timelapse videos showing the spread of interference over a specified date range.
- **Global Trends & Pattern of Life:** Analyze geopolitical hotspots, sudden spikes in interference, and day-of-week "pattern of life" trends to determine if jamming events follow human schedules or automated systems.
- **Automated Data Pipeline:** A robust background scraper and analytics engine that pulls raw hex-level flight data, reverse-geocodes locations, and calculates historical metrics.

## 🛠️ Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/bspirito/Global-GPS-Interference-Explorer.git
   cd Global-GPS-Interference-Explorer
   ```

2. **Set up a virtual environment (Recommended):**
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

## 🚀 Running the Project

### 1. Build the Database
Before running the dashboard, you must fetch the raw data and build the local SQLite analytics database.
Run the scraper and analytics pipeline:
```bash
python scraper.py
python build_analytics.py
```
*(Alternatively, you can just execute the `run_scraper.bat` script on Windows).*

### 2. Launch the Dashboard
Once the database `gps_interference_history.db` is built, launch the Streamlit application:
```bash
streamlit run app.py
```
The dashboard will open automatically in your web browser.

## 📁 Architecture
- `app.py`: The main Streamlit dashboard application.
- `scraper.py`: Nightly data pipeline script that downloads daily H3 resolution hex data.
- `build_analytics.py`: Pre-computes complex statistical aggregations, reverse geocoding, and historical deltas to ensure the dashboard remains lightning fast.
- `video_engine.py`: Headless Playwright engine that drives DeckGL to stitch together cinematic video renders.
- `deckgl_sync_component/`: Custom HTML/JS component bridging raw DeckGL Javascript events with Python's Streamlit state.
