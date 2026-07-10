import sqlite3
import pandas as pd
import requests
import io
import os
from datetime import datetime
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_PATH = 'gps_interference_history.db'
MANIFEST_URL = 'https://gpsjam.org/data/manifest.csv'
DAILY_DATA_URL_TEMPLATE = 'https://gpsjam.org/data/{date}-h3_4.csv'
START_DATE = '2022-02-14'

def init_db():
    conn = sqlite3.connect('gps_interference_history.db')
    cursor = conn.cursor()
    
    # Create manifest table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS manifest (
            date TEXT PRIMARY KEY,
            suspect BOOLEAN,
            num_bad_aircraft_hexes INTEGER
        )
    ''')
    
    # Create hex_data table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hex_data (
            date TEXT,
            hex TEXT,
            count_good_aircraft INTEGER,
            count_bad_aircraft INTEGER,
            interference_percentage REAL,
            PRIMARY KEY (date, hex)
        )
    ''')
    
    conn.commit()
    return conn

def fetch_manifest():
    logging.info(f"Fetching manifest from {MANIFEST_URL}")
    response = requests.get(MANIFEST_URL)
    response.raise_for_status()
    df = pd.read_csv(io.StringIO(response.text))
    # Filter dates from START_DATE
    df = df[df['date'] >= START_DATE]
    return df

def get_processed_dates(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT date FROM hex_data")
    return {row[0] for row in cursor.fetchall()}

def download_and_insert_daily_data(conn, date):
    url = DAILY_DATA_URL_TEMPLATE.format(date=date)
    logging.info(f"Fetching daily data for {date} from {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        df = pd.read_csv(io.StringIO(response.text))
        
        if df.empty:
            logging.warning(f"No data found for {date}")
            return
            
        df['date'] = date
        df['interference_percentage'] = df['count_bad_aircraft'] / (df['count_good_aircraft'] + df['count_bad_aircraft'])
        
        # Ensure correct column order and write to SQLite
        cols = ['date', 'hex', 'count_good_aircraft', 'count_bad_aircraft', 'interference_percentage']
        df = df[cols]
        
        df.to_sql('hex_data', conn, if_exists='append', index=False)
        logging.info(f"Successfully inserted {len(df)} rows for {date}")
        
    except requests.exceptions.HTTPError as e:
        if response.status_code == 404:
            logging.warning(f"Data file not found for {date} (404)")
        else:
            logging.error(f"HTTP Error for {date}: {e}")
    except Exception as e:
        logging.error(f"Error processing {date}: {e}")

def update_manifest_db(conn, df_manifest):
    df_manifest.to_sql('manifest', conn, if_exists='replace', index=False)

def run():
    conn = init_db()
    
    # 1. Fetch manifest
    try:
        df_manifest = fetch_manifest()
        update_manifest_db(conn, df_manifest)
    except Exception as e:
        logging.error(f"Failed to fetch manifest: {e}")
        return

    # 2. Find missing dates
    processed_dates = get_processed_dates(conn)
    manifest_dates = df_manifest['date'].tolist()
    
    missing_dates = [d for d in manifest_dates if d not in processed_dates]
    logging.info(f"Found {len(missing_dates)} dates to process.")
    
    # 3. Download and insert
    for i, date in enumerate(missing_dates):
        download_and_insert_daily_data(conn, date)
        
        # Be nice to the server, wait a tiny bit
        if (i + 1) % 10 == 0:
            logging.info(f"Processed {i + 1} of {len(missing_dates)} dates...")
            time.sleep(1)
            
    conn.close()
    logging.info("Finished data synchronization.")

if __name__ == '__main__':
    run()
