import sqlite3
import pandas as pd
import h3
import reverse_geocoder as rg
import time
import pycountry

DB_PATH = 'gps_interference_history.db'

def build_analytics():
    print("Connecting to database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Generate All-Time Heatmap
    print("Building all_time_stats table...")
    cursor.execute("DROP TABLE IF EXISTS all_time_stats")
    cursor.execute("""
        CREATE TABLE all_time_stats AS
        SELECT 
            hex,
            SUM(count_good_aircraft) as count_good_aircraft,
            SUM(count_bad_aircraft) as count_bad_aircraft,
            CAST(SUM(count_bad_aircraft) AS FLOAT) / (SUM(count_good_aircraft) + SUM(count_bad_aircraft)) as interference_percentage
        FROM hex_data
        GROUP BY hex
    """)
    conn.commit()
    print("all_time_stats created successfully!")
    
    print("Building daily_impact_stats table...")
    cursor.execute("DROP TABLE IF EXISTS daily_impact_stats")
    cursor.execute("""
        CREATE TABLE daily_impact_stats AS
        SELECT date, SUM(count_good_aircraft) as good, SUM(count_bad_aircraft) as bad 
        FROM hex_data 
        GROUP BY date
    """)
    conn.commit()
    print("daily_impact_stats created successfully!")
    
    # 1.5 Generate Emerging Hotspots (30-Day Delta)
    print("Building emerging_hotspots table...")
    cursor.execute("DROP TABLE IF EXISTS emerging_hotspots")
    
    # Get the most recent date
    cursor.execute("SELECT MAX(date) FROM hex_data")
    latest_date = cursor.fetchone()[0]
    
    if latest_date:
        cursor.execute("""
            CREATE TABLE emerging_hotspots AS
            WITH recent AS (
                SELECT hex, interference_percentage as current_interference
                FROM hex_data WHERE date = ?
            ),
            historical AS (
                SELECT hex, 
                       CAST(SUM(count_bad_aircraft) AS FLOAT) / (SUM(count_good_aircraft) + SUM(count_bad_aircraft)) as avg_interference
                FROM hex_data 
                WHERE date < ? AND date >= date(?, '-30 days')
                GROUP BY hex
            )
            SELECT r.hex, r.current_interference, h.avg_interference, 
                   (r.current_interference - COALESCE(h.avg_interference, 0)) as interference_delta
            FROM recent r
            LEFT JOIN historical h ON r.hex = h.hex
            WHERE interference_delta > 0
            ORDER BY interference_delta DESC
        """, (latest_date, latest_date, latest_date))
        conn.commit()
    print("emerging_hotspots created successfully!")
    
    # 2. Build Hex to Country mapping
    print("Extracting unique hexes for reverse geocoding...")
    cursor.execute("SELECT hex FROM all_time_stats")
    rows = cursor.fetchall()
    hex_list = [row[0] for row in rows]
    
    print(f"Found {len(hex_list)} unique hexes. Resolving coordinates...")
    
    coords = []
    # Try h3 v3 and v4 syntax
    h3_func = None
    if hasattr(h3, 'h3_to_geo'):
        h3_func = h3.h3_to_geo
    elif hasattr(h3, 'h3_to_latlng'):
        h3_func = h3.h3_to_latlng
    elif hasattr(h3, 'cell_to_latlng'):
        h3_func = h3.cell_to_latlng
        
    for h in hex_list:
        try:
            coords.append(h3_func(h))
        except Exception:
            coords.append((0.0, 0.0))
            
    print("Running offline reverse geocoding...")
    start_time = time.time()
    results = rg.search(coords) # Extremely fast batch process
    print(f"Reverse geocoding completed in {time.time() - start_time:.2f} seconds.")
    
    print("Building hex_countries table...")
    cursor.execute("DROP TABLE IF EXISTS hex_countries")
    cursor.execute("""
        CREATE TABLE hex_countries (
            hex TEXT PRIMARY KEY,
            country_code TEXT,
            country_code_iso3 TEXT,
            location_name TEXT
        )
    """)
    
    insert_data = []
    for i, h in enumerate(hex_list):
        cc_iso2 = results[i].get('cc', 'Unknown')
        name = results[i].get('name', 'Unknown')
        admin1 = results[i].get('admin1', '')
        loc_name = f"{name}, {admin1}" if admin1 else name
        cc_iso3 = 'Unknown'
        if cc_iso2 != 'Unknown':
            try:
                c = pycountry.countries.get(alpha_2=cc_iso2)
                if c:
                    cc_iso3 = c.alpha_3
            except Exception:
                pass
        insert_data.append((h, cc_iso2, cc_iso3, loc_name))
        
    cursor.executemany("INSERT INTO hex_countries (hex, country_code, country_code_iso3, location_name) VALUES (?, ?, ?, ?)", insert_data)
    conn.commit()
    
    print("hex_countries table created successfully!")
    conn.close()
    print("Analytics build complete!")

if __name__ == "__main__":
    build_analytics()
