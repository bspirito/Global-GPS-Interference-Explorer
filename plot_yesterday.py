import sqlite3
import pandas as pd
import pydeck as pdk
import logging

logging.basicConfig(level=logging.INFO)

DB_PATH = 'gps_interference_history.db'
TARGET_DATE = '2026-07-08'
OUTPUT_FILE = 'yesterday_map.html'

def get_color(interference):
    if interference > 0.10:
        return [255, 0, 0, 150]  # Red
    elif interference >= 0.02:
        return [255, 255, 0, 150]  # Yellow
    else:
        return [0, 255, 0, 100]  # Green

def run():
    logging.info(f"Loading data for {TARGET_DATE}...")
    conn = sqlite3.connect(DB_PATH)
    
    query = """
    SELECT hex, interference_percentage 
    FROM hex_data 
    WHERE date = ?
    """
    df = pd.read_sql_query(query, conn, params=(TARGET_DATE,))
    conn.close()
    
    logging.info(f"Loaded {len(df)} hexes.")
    
    # Calculate colors
    df['color'] = df['interference_percentage'].apply(get_color)
    # Format interference for tooltip
    df['tooltip_text'] = (df['interference_percentage'] * 100).round(1).astype(str) + "%"

    # Define the H3 Hexagon Layer for pydeck
    layer = pdk.Layer(
        "H3HexagonLayer",
        df,
        pickable=True,
        stroked=True,
        filled=True,
        extruded=False,
        get_hexagon="hex",
        get_fill_color="color",
        get_line_color="[255, 255, 255, 30]",
        line_width_min_pixels=0,
    )

    # Set the viewport to be centered globally
    view_state = pdk.ViewState(latitude=30, longitude=0, zoom=1.5, bearing=0, pitch=0)

    # Render
    logging.info("Building pydeck map...")
    r = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "Interference: {tooltip_text}"},
        map_style="mapbox://styles/mapbox/dark-v10",
    )
    
    logging.info(f"Saving to {OUTPUT_FILE}...")
    r.to_html(OUTPUT_FILE)
    logging.info("Done!")

if __name__ == '__main__':
    run()
