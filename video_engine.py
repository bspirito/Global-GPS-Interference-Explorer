import sqlite3
import pandas as pd
import pydeck as pdk
import os
import time
import tempfile
from playwright.sync_api import sync_playwright
import imageio.v3 as iio
import logging

logging.basicConfig(level=logging.INFO)

DB_PATH = 'gps_interference_history.db'

def get_color(interference):
    if interference > 0.10:
        return [255, 65, 54, 180]
    elif interference >= 0.02:
        return [255, 220, 0, 180]
    else:
        return [46, 204, 64, 100]

def generate_video(start_date, end_date, map_style_choice, resolution_choice="1080p (FHD)", output_path="timelapse.mp4", progress_callback=None, cam_lat=30, cam_lon=0, cam_zoom=1.5, cam_pitch=45, cam_bearing=0, fps=5):
    """
    Generates a timelapse video of the GPS interference map.
    """
    conn = sqlite3.connect(DB_PATH)
    # Get all available dates in range, sorted chronologically
    dates_df = pd.read_sql_query(
        "SELECT date FROM manifest WHERE date >= ? AND date <= ? ORDER BY date ASC",
        conn, params=(start_date, end_date)
    )
    
    if dates_df.empty:
        conn.close()
        raise ValueError("No data found for the selected date range.")
        
    dates = dates_df['date'].tolist()
    total_frames = len(dates)
    
    temp_dir = tempfile.mkdtemp()
    frame_files = []
    
    # Map styling
    is_3d = map_style_choice == "3D Satellite Terrain"
    map_provider = None if is_3d else "carto"
    if map_style_choice == "Dark Mode":
        style = pdk.map_styles.DARK
    elif map_style_choice == "Light Mode":
        style = pdk.map_styles.LIGHT
    else:
        style = None # Satellite handled via TileLayer/TerrainLayer
    
    # Resolution mapping
    res_map = {
        "1080p (FHD)": {"width": 1920, "height": 1080},
        "1440p (QHD)": {"width": 2560, "height": 1440},
        "4K (UHD)": {"width": 3840, "height": 2160}
    }
    viewport = res_map.get(resolution_choice, {"width": 1920, "height": 1080})
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport)
        
        for i, target_date in enumerate(dates):
            if progress_callback:
                progress_callback(i, total_frames, f"Rendering map for {target_date}...")
                
            query = "SELECT hex, interference_percentage FROM hex_data WHERE date = ?"
            df = pd.read_sql_query(query, conn, params=(target_date,))
            
            if df.empty:
                continue
                
            df['color'] = df['interference_percentage'].apply(get_color)
            
            is_3d = map_style_choice == "3D Satellite Terrain"
            is_globe = map_style_choice == "3D Spinning Globe"
            should_extrude = is_3d or is_globe
            
            hex_layer = pdk.Layer(
                "H3HexagonLayer",
                df,
                get_hexagon="hex",
                get_fill_color="color",
                get_line_color="[255, 255, 255, 20]",
                line_width_min_pixels=0,
                extruded=should_extrude,
                get_elevation="interference_percentage * 100000" if should_extrude else None
            )
            
            layers = []
            if is_3d:
                layers.append(pdk.Layer(
                    "TerrainLayer",
                    elevation_decoder={"rScaler": 256, "gScaler": 1, "bScaler": 1 / 256, "offset": -32768},
                    texture="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                    elevation_data="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
                    max_requests=10,
                ))
                layers.append(pdk.Layer(
                    "TerrainLayer",
                    elevation_decoder={"rScaler": 256, "gScaler": 1, "bScaler": 1 / 256, "offset": -32718},
                    texture="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
                    elevation_data="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
                    max_requests=10,
                ))
                
            if is_globe:
                # Add solid ocean base to prevent seeing through the globe
                layers.append(pdk.Layer(
                    "GeoJsonLayer",
                    data={
                        "type": "FeatureCollection",
                        "features": [
                            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[-180, -90], [0, -90], [0, 90], [-180, 90], [-180, -90]]]}},
                            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, -90], [180, -90], [180, 90], [0, 90], [0, -90]]]}}
                        ]
                    },
                    get_fill_color=[10, 15, 25],
                    stroked=False,
                    filled=True,
                ))
            
            if not is_3d:
                # Add GeoJson borders for countries
                layers.append(pdk.Layer(
                    "GeoJsonLayer",
                    data="https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson",
                    get_fill_color=[30, 30, 30] if is_globe else [0, 0, 0, 0], # Transparent fill unless globe
                    get_line_color=[150, 150, 150, 100],
                    line_width_min_pixels=1,
                    stroked=True,
                    filled=is_globe,
                ))
                
                # Add text labels for continents
                continent_labels = [
                    {"name": "North America", "coordinates": [-100.0, 40.0, 100000]},
                    {"name": "South America", "coordinates": [-60.0, -15.0, 100000]},
                    {"name": "Europe", "coordinates": [15.0, 50.0, 100000]},
                    {"name": "Africa", "coordinates": [20.0, 0.0, 100000]},
                    {"name": "Asia", "coordinates": [90.0, 45.0, 100000]},
                    {"name": "Australia", "coordinates": [135.0, -25.0, 100000]},
                    {"name": "Antarctica", "coordinates": [0.0, -80.0, 100000]}
                ]
                layers.append(pdk.Layer(
                    "TextLayer",
                    continent_labels,
                    get_position="coordinates",
                    get_text="name",
                    get_size=32,
                    get_color=[255, 255, 255, 200],
                    get_alignment_baseline="'center'",
                ))
            
            # Append data layer last so it renders on top of oceans and borders
            layers.append(hex_layer)
            
            current_lon = cam_lon
            if is_globe:
                # Spin the globe by 1 degree per frame
                current_lon = (cam_lon + (i * 1.0)) % 360
            
            view_state = pdk.ViewState(
                latitude=cam_lat, 
                longitude=current_lon, 
                zoom=cam_zoom, 
                bearing=cam_bearing, 
                pitch=cam_pitch
            )
            
            deck = pdk.Deck(
                layers=layers,
                initial_view_state=view_state,
                map_style=style,
                map_provider=map_provider,
                views=[pdk.View(type="_GlobeView", controller=False)] if is_globe else [pdk.View(type="MapView", controller=False)]
            )
            
            html_path = os.path.join(temp_dir, f"frame_{i}.html")
            deck.to_html(html_path)
            
            # Load in playwright
            file_url = f"file:///{html_path.replace(chr(92), '/')}"
            page.goto(file_url, wait_until="networkidle")
            
            # Inject Date Watermark
            page.evaluate(f"""() => {{
                let dateDiv = document.createElement('div');
                dateDiv.innerText = 'Date: {target_date}';
                dateDiv.style.position = 'absolute';
                dateDiv.style.bottom = '50px';
                dateDiv.style.left = '50px';
                dateDiv.style.color = 'white';
                dateDiv.style.fontSize = '48px';
                dateDiv.style.fontWeight = 'bold';
                dateDiv.style.fontFamily = 'sans-serif';
                dateDiv.style.textShadow = '2px 2px 4px #000000';
                dateDiv.style.zIndex = '9999';
                document.body.appendChild(dateDiv);
            }}""")
            
            # Wait for tiles/webgl to fully render.
            time.sleep(1.5)
            
            screenshot_path = os.path.join(temp_dir, f"frame_{i:04d}.png")
            page.screenshot(path=screenshot_path)
            frame_files.append(screenshot_path)
            
            # Cleanup html
            os.remove(html_path)
            
        browser.close()
    conn.close()
    
    if not frame_files:
        raise ValueError("No frames were generated.")
        
    if progress_callback:
        progress_callback(total_frames, total_frames, f"Stitching {len(frame_files)} frames into video...")
        
    # Stitch video using imageio at dynamic fps
    frames = [iio.imread(f) for f in frame_files]
    iio.imwrite(output_path, frames, plugin="pyav", fps=fps, codec="libx264")
    
    # Cleanup pngs
    for f in frame_files:
        try:
            os.remove(f)
        except:
            pass
    try:
        os.rmdir(temp_dir)
    except:
        pass
        
    return output_path
