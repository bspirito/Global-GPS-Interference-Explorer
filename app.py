import streamlit as st
import pydeck as pdk
import pandas as pd
import sqlite3
import os
from datetime import datetime, timedelta
import video_engine
import plotly.express as px

# Premium UI config
st.set_page_config(page_title="Global GPS Interference Explorer", layout="wide", page_icon="📡")

# Custom CSS for a more premium look
st.markdown("""
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
    .main {
        background-color: #0e1117;
    }
    h1 {
        color: #f0f2f6;
        font-family: 'Inter', sans-serif;
    }
    .stSelectbox label, .stDateInput label {
        color: #f0f2f6 !important;
    }
    </style>
""", unsafe_allow_html=True)

DB_PATH = 'gps_interference_history.db'

@st.cache_data
def get_available_dates():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    dates = pd.read_sql_query("SELECT date FROM manifest ORDER BY date DESC", conn)['date'].tolist()
    conn.close()
    return dates

@st.cache_data
def load_data(target_date):
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    query = """
    SELECT hex, interference_percentage, count_good_aircraft, count_bad_aircraft
    FROM hex_data
    WHERE date = ?
    """
    df = pd.read_sql_query(query, conn, params=(target_date,))
    conn.close()
    return df

def get_color(interference):
    if interference > 0.10:
        return [255, 65, 54, 180]  # Vibrant Red
    elif interference >= 0.02:
        return [255, 220, 0, 180]  # Vibrant Yellow
    else:
        return [46, 204, 64, 100]  # Vibrant Green

# Header
st.title("📡 Global GPS Interference Explorer")
st.markdown("Explore high-resolution H3 geospatial data of GPS/GNSS interference over time.")

available_dates = get_available_dates()
if not available_dates:
    st.error("No data found in database. Please run the scraper first.")
    st.stop()

# Sidebar Navigation (Always at the top)
st.sidebar.header("Navigation")
page = st.sidebar.radio(
    "Go To", 
    ["🗺️ Daily Explorer", "🎥 HD Video Generator", "🌍 Global Trends", "🔥 All-Time Heatmap"]
)

st.sidebar.markdown("---")

# Map controls only on map-centric pages
map_style_choice = "Dark Mode"
if page in ["🗺️ Daily Explorer", "🔥 All-Time Heatmap"]:
    st.sidebar.header("Map Controls")
    map_style_choice = st.sidebar.radio(
        "Map Style",
        ["Dark Mode", "Light Mode", "3D Satellite Terrain", "3D Spinning Globe"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🚦 Map Legend")
    st.sidebar.markdown("""
    <div style="line-height: 1.8;">
        <div><span style='color:#FF4136; font-size: 18px;'>■</span> <strong>Red:</strong> High (>10%)</div>
        <div><span style='color:#FFDC00; font-size: 18px;'>■</span> <strong>Yellow:</strong> Med (2% - 10%)</div>
        <div><span style='color:#2ECC40; font-size: 18px;'>■</span> <strong>Green:</strong> Low (<2%)</div>
    </div>
    """, unsafe_allow_html=True)

# Map Style Mapping
style_mapping = {
    "Dark Mode": pdk.map_styles.DARK,
    "Light Mode": pdk.map_styles.LIGHT,
    "3D Satellite Terrain": False,
    "3D Spinning Globe": pdk.map_styles.DARK
}
selected_style = style_mapping[map_style_choice]

is_3d_terrain = map_style_choice == "3D Satellite Terrain"
is_globe = map_style_choice == "3D Spinning Globe"
is_3d = is_3d_terrain or is_globe

if page == "🗺️ Daily Explorer":
    selected_date = st.selectbox(
        "Select Date", 
        options=available_dates,
        index=0
    )

    # Load Data
    with st.spinner(f'Loading data for {selected_date}...'):
        df = load_data(selected_date)

    if df.empty:
        st.warning(f"No detailed hex data found for {selected_date}.")
    else:
        # Process colors and tooltips
        import h3
        df['lat'] = df['hex'].apply(lambda x: h3.cell_to_latlng(x)[0])
        df = df[(df['lat'] < 80) & (df['lat'] > -80)]
        
        df['color'] = df['interference_percentage'].apply(get_color)
        df['tooltip_html'] = (
            "<b>Interference:</b> " + (df['interference_percentage'] * 100).round(1).astype(str) + "%<br/>" +
            "<b>Jammed Aircraft:</b> " + df['count_bad_aircraft'].astype(str) + "<br/>" +
            "<b>Safe Aircraft:</b> " + df['count_good_aircraft'].astype(str)
        )

        # Define PyDeck Hexagon Layer
        is_3d = map_style_choice == "3D Satellite Terrain"
        hex_layer = pdk.Layer(
            "H3HexagonLayer",
            df,
            pickable=True,
            stroked=not is_3d,
            filled=True,
            extruded=is_3d,
            get_hexagon="hex",
            get_fill_color="color",
            get_elevation="interference_percentage * 100000" if is_3d else None,
            get_line_color="[255, 255, 255, 20]",
            line_width_min_pixels=0,
            wrap_longitude=True
        )

        layers = []
        if is_3d_terrain:
            layers.append(pdk.Layer(
                "TerrainLayer",
                elevation_decoder={"rScaler": 256, "gScaler": 1, "bScaler": 1 / 256, "offset": -32768},
                texture="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                elevation_data="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
                max_requests=10,
                wrap_longitude=True
            ))
            # Overlay Country Borders and Labels (Shifted up by 50m to float above satellite terrain)
            layers.append(pdk.Layer(
                "TerrainLayer",
                elevation_decoder={"rScaler": 256, "gScaler": 1, "bScaler": 1 / 256, "offset": -32718},
                texture="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
                elevation_data="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
                max_requests=10,
                wrap_longitude=True
            ))
        if is_globe:
            layers.append(pdk.Layer(
                "GeoJsonLayer",
                data="https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson",
                get_fill_color=[30, 30, 30],
                get_line_color=[70, 70, 70],
                line_width_min_pixels=1,
                stroked=True,
                filled=True
            ))
            # Text and detailed borders from ArcGIS
            layers.append(pdk.Layer(
                "TileLayer",
                data="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
                max_requests=10
            ))
            
        layers.append(hex_layer)

        # Viewport
        view_state = pdk.ViewState(latitude=30, longitude=0, zoom=1.2, bearing=0, pitch=45 if is_3d else 0)

        # Render Map
        deck_views = [pdk.View(type="_GlobeView", controller=True)] if is_globe else [pdk.View(type="MapView", controller=True)]
        deck = pdk.Deck(
            layers=layers,
            initial_view_state=view_state,
            views=deck_views,
            tooltip={"html": "{tooltip_html}", "style": {"color": "white", "backgroundColor": "#222222", "padding": "10px", "borderRadius": "5px"}},
            map_style=selected_style,
            map_provider=None if (is_3d or is_globe) else "carto"
        )
        if is_globe:
            import streamlit.components.v1 as components
            components.html(deck.to_html(as_string=True), height=600)
        else:
            st.pydeck_chart(deck, use_container_width=True, height=600)
        st.metric(label="Total Regions Tracked", value=f"{len(df):,}")
        
        # Data Export
        st.markdown("### 💾 Export Data")
        colA, colB = st.columns(2)
        with colA:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"gpsjam_{selected_date}.csv",
                mime="text/csv",
            )
        with colB:
            import json
            import h3
            
            def get_lat_lng(hex_id):
                if hasattr(h3, 'h3_to_geo'):
                    return h3.h3_to_geo(hex_id)
                elif hasattr(h3, 'h3_to_latlng'):
                    return h3.h3_to_latlng(hex_id)
                return h3.cell_to_latlng(hex_id)

            features = []
            for _, row in df.iterrows():
                try:
                    lat, lng = get_lat_lng(row['hex'])
                    features.append({
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lng, lat]},
                        "properties": {"hex": row['hex'], "interference_percentage": row['interference_percentage']}
                    })
                except Exception:
                    pass

            geojson = {
                "type": "FeatureCollection",
                "features": features
            }
            st.download_button(
                label="🗺️ Download GeoJSON (Points)",
                data=json.dumps(geojson),
                file_name=f"gpsjam_{selected_date}.geojson",
                mime="application/json"
            )


elif page == "🎥 HD Video Generator":
    st.subheader("Generate Timelapse Video")
    st.markdown("Compile a high-definition `.mp4` video showing the spread of interference over a specified date range. *Note: Rendering requires heavy processing.*")
    
    if 'cam_lat' not in st.session_state: st.session_state.cam_lat = 30.0
    if 'cam_lon' not in st.session_state: st.session_state.cam_lon = 0.0
    if 'cam_zoom' not in st.session_state: st.session_state.cam_zoom = 1.5
    if 'cam_pitch' not in st.session_state: st.session_state.cam_pitch = 45 if map_style_choice == "3D Satellite Terrain" else 0
    if 'cam_bearing' not in st.session_state: st.session_state.cam_bearing = 0
    if 'map_key_counter' not in st.session_state: st.session_state.map_key_counter = 0

    main_left, main_right = st.columns([1, 2.5])
    
    with main_left:
        st.markdown("### 🎞️ Export Settings")
        video_map_style = st.selectbox("Map Style", ["Dark Mode", "Light Mode", "3D Satellite Terrain", "3D Spinning Globe"], index=["Dark Mode", "Light Mode", "3D Satellite Terrain", "3D Spinning Globe"].index(map_style_choice))
        start_date = st.selectbox("Start Date", options=available_dates[::-1], index=len(available_dates)-8)
        end_date = st.selectbox("End Date", options=available_dates, index=0)
        resolution = st.selectbox("Resolution", ["1080p (FHD)", "1440p (QHD)", "4K (UHD)"])
        speed = st.selectbox("Speed (Days/Sec)", [1, 2, 5, 10, 24, 30], index=2)

        # Override global map styles for this specific section
        is_globe = video_map_style == "3D Spinning Globe"
        is_3d = video_map_style == "3D Satellite Terrain"
        if video_map_style == "Dark Mode": selected_style = pdk.map_styles.DARK
        elif video_map_style == "Light Mode": selected_style = pdk.map_styles.LIGHT
        else: selected_style = None

        st.markdown("---")
        
        st.markdown("### 📷 Camera Framing")
        st.caption("*Drag, zoom, and pitch the map. What you see framed is exactly what will be exported!*")
        
        if st.button("🔄 Reset Camera", use_container_width=True):
            st.session_state.cam_lat = 30.0
            st.session_state.cam_lon = 0.0
            st.session_state.cam_zoom = 1.5
            st.session_state.cam_pitch = 45 if video_map_style == "3D Satellite Terrain" else 0
            st.session_state.cam_bearing = 0
            st.session_state.map_key_counter += 1
            st.rerun()
                
        with st.expander("⚙️ Advanced Controls"):
            cam_lat = st.number_input("Latitude", value=float(st.session_state.cam_lat), step=5.0)
            cam_lon = st.number_input("Longitude", value=float(st.session_state.cam_lon), step=5.0)
            cam_zoom = st.slider("Zoom", min_value=0.5, max_value=20.0, value=float(st.session_state.cam_zoom), step=0.5)
            cam_pitch = st.slider("Pitch (3D)", min_value=0, max_value=85, value=int(st.session_state.cam_pitch))
            cam_bearing = st.slider("Bearing", min_value=-180, max_value=180, value=int(st.session_state.cam_bearing))
                
            if (cam_lat != st.session_state.cam_lat or 
                cam_lon != st.session_state.cam_lon or 
                cam_zoom != st.session_state.cam_zoom or 
                cam_pitch != st.session_state.cam_pitch or 
                cam_bearing != st.session_state.cam_bearing):
                st.session_state.cam_lat = cam_lat
                st.session_state.cam_lon = cam_lon
                st.session_state.cam_zoom = cam_zoom
                st.session_state.cam_pitch = cam_pitch
                st.session_state.cam_bearing = cam_bearing
                st.rerun()

    with main_right:
        # Interactive component logic
        preview_layers = []
        with st.spinner("Loading preview data..."):
            preview_df = load_data(available_dates[0])
            
        import streamlit.components.v1 as components
        import os
        component_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deckgl_sync_component")
        deckgl_sync = components.declare_component("deckgl_sync", path=component_dir)
        
        hex_data = []
        if not preview_df.empty:
            preview_df['color'] = preview_df['interference_percentage'].apply(get_color)
            hex_data = preview_df[['hex', 'color', 'interference_percentage']].to_dict('records')
            
        returned_view_state = deckgl_sync(
            view_state={
                "latitude": st.session_state.cam_lat, 
                "longitude": st.session_state.cam_lon, 
                "zoom": st.session_state.cam_zoom, 
                "bearing": st.session_state.cam_bearing, 
                "pitch": st.session_state.cam_pitch,
                "maxPitch": 85
            },
            map_style=selected_style,
            is_globe=is_globe,
            hex_data=hex_data,
            key=f"deckgl_sync_{st.session_state.map_key_counter}"
        )
    
        # Update session state if camera moved
        if returned_view_state:
            d_lat = abs(returned_view_state['lat'] - st.session_state.cam_lat)
            d_lon = abs(returned_view_state['lon'] - st.session_state.cam_lon)
            d_zoom = abs(returned_view_state['zoom'] - st.session_state.cam_zoom)
            d_pitch = abs(returned_view_state['pitch'] - st.session_state.cam_pitch)
            d_bearing = abs(returned_view_state['bearing'] - st.session_state.cam_bearing)
            
            if d_lat > 0.001 or d_lon > 0.001 or d_zoom > 0.01 or d_pitch > 1.0 or d_bearing > 1.0:
                st.session_state.cam_lat = float(returned_view_state['lat'])
                st.session_state.cam_lon = float(returned_view_state['lon'])
                st.session_state.cam_zoom = float(returned_view_state['zoom'])
                st.session_state.cam_pitch = float(returned_view_state['pitch'])
                st.session_state.cam_bearing = float(returned_view_state['bearing'])
                st.rerun()
                
        # Set variables for the generator call
        cam_lat = st.session_state.cam_lat
        cam_lon = st.session_state.cam_lon
        cam_zoom = st.session_state.cam_zoom
        cam_pitch = st.session_state.cam_pitch
        cam_bearing = st.session_state.cam_bearing
        
        st.markdown("<br>", unsafe_allow_html=True)
        btn_placeholder = st.empty()
        
        if btn_placeholder.button("🎬 Generate HD Video", use_container_width=True, type="primary"):
            if start_date >= end_date:
                st.error("Start date must be before end date.")
            else:
                # Calculate estimated time (approx 2s per frame)
                start_idx = available_dates.index(start_date)
                end_idx = available_dates.index(end_date)
                num_frames = abs(start_idx - end_idx) + 1
                est_seconds = num_frames * 2
                est_str = f"{est_seconds} seconds" if est_seconds < 60 else f"{est_seconds // 60}m {est_seconds % 60}s"
                
                # Swap to disabled Please Wait state
                btn_placeholder.button(f"⏳ Please Wait... (Est: {est_str})", use_container_width=True, disabled=True)
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def render_progress(current, total, msg):
                    pct = int((current / total) * 100) if total > 0 else 0
                    progress_bar.progress(current / total)
                    status_text.text(f"{pct}% Complete  —  {msg}")
                    
                try:
                    video_path = video_engine.generate_video(
                        start_date=start_date,
                        end_date=end_date,
                        map_style_choice=video_map_style,
                        resolution_choice=resolution,
                        output_path="timelapse.mp4",
                        progress_callback=render_progress,
                        cam_lat=cam_lat,
                        cam_lon=cam_lon,
                        cam_zoom=cam_zoom,
                        cam_pitch=cam_pitch,
                        cam_bearing=cam_bearing,
                        fps=speed
                    )
                    progress_bar.progress(1.0)
                    status_text.success("Video generated successfully!")
                    
                    # Swap to Complete state
                    btn_placeholder.button("✅ Complete", use_container_width=True, disabled=True, type="primary")
                    
                    with open(video_path, "rb") as v:
                        st.video(v.read())
                        
                    with open(video_path, "rb") as v:
                        st.download_button(
                            label="Download MP4",
                            data=v,
                            file_name=f"gpsjam_timelapse_{start_date}_to_{end_date}.mp4",
                            mime="video/mp4",
                            use_container_width=True
                        )
                except Exception as e:
                    btn_placeholder.button("❌ Error", use_container_width=True, disabled=True)
                    st.error(f"Error generating video: {e}")

elif page == "🌍 Global Trends":
    st.subheader("Global Trends & Analytics")
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    
    # Load Data
    manifest_df = pd.read_sql_query("SELECT date, num_bad_aircraft_hexes as `Hex Locations` FROM manifest ORDER BY date ASC", conn)
    
    try:
        impact_df = pd.read_sql_query("""
            SELECT date, good, bad 
            FROM daily_impact_stats 
            ORDER BY date ASC
        """, conn)
        
        from plotly.subplots import make_subplots
        import plotly.graph_objects as go
        
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05
        )
        
        # Row 1: Healthy
        fig.add_trace(
            go.Scatter(x=impact_df['date'], y=impact_df['good'], name="Healthy Flights", line=dict(color="#1f77b4")),
            row=1, col=1
        )
        fig.add_annotation(text="Commercial Flights Tracked (Healthy)", xref="x domain", yref="y domain", x=0.01, y=0.95, showarrow=False, font=dict(color="#1f77b4", size=14), row=1, col=1)
        
        # Row 2: Jammed
        fig.add_trace(
            go.Scatter(x=impact_df['date'], y=impact_df['bad'], name="Jammed Flights", line=dict(color="#d62728")),
            row=2, col=1
        )
        fig.add_annotation(text="Commercial Flights Tracked (Jammed)", xref="x domain", yref="y domain", x=0.01, y=0.95, showarrow=False, font=dict(color="#d62728", size=14), row=2, col=1)
        
        # Row 3: Hex Locations
        fig.add_trace(
            go.Scatter(x=manifest_df['date'], y=manifest_df['Hex Locations'], name="Hex Locations", line=dict(color="yellow")),
            row=3, col=1
        )
        fig.add_annotation(text="Global Interference Trend (Affected Hex Locations)", xref="x domain", yref="y domain", x=0.01, y=0.95, showarrow=False, font=dict(color="yellow", size=14), row=3, col=1)
        
        fig.update_layout(height=800, template="plotly_dark", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", showlegend=False, margin=dict(t=40, b=40))
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        # Fallback if impact stats aren't built yet
        st.warning("Aircraft impact stats are building.")
        fig1 = px.line(manifest_df, x='date', y='Hex Locations', title="Global Interference Trend (Affected Hex Locations)")
        fig1.update_traces(line_color='yellow')
        fig1.update_layout(template="plotly_dark", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117")
        st.plotly_chart(fig1, use_container_width=True)
    
    # Leaderboard
    st.markdown("### Most Jammed Countries (All-Time)")
    try:
        leaderboard_df = pd.read_sql_query("""
            SELECT c.country_code, SUM(a.count_bad_aircraft) as total_jammed
            FROM all_time_stats a
            JOIN hex_countries c ON a.hex = c.hex
            GROUP BY c.country_code
            ORDER BY total_jammed DESC
            LIMIT 20
        """, conn)
        
        fig3 = px.bar(leaderboard_df, x='country_code', y='total_jammed', title="Top 20 Most Jammed Countries", color='total_jammed', color_continuous_scale="Reds")
        fig3.update_layout(template="plotly_dark", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117")
        st.plotly_chart(fig3, use_container_width=True)
    except Exception as e:
        st.warning("Country leaderboard is currently building in the background. Check back soon!")
    
    # Emerging Hotspots
    st.markdown("### 🔥 Emerging Hotspots (30-Day Delta)")
    st.markdown("The top 10 regions where interference has suddenly spiked compared to their 30-day historical average.")
    hotspots_view = st.radio("View as:", ["Table", "Map"], horizontal=True, key="hotspots_view")
    
    try:
        hotspots_df = pd.read_sql_query("""
            SELECT c.location_name as location, e.hex, e.current_interference, e.avg_interference, e.interference_delta 
            FROM emerging_hotspots e
            LEFT JOIN hex_countries c ON e.hex = c.hex
            LIMIT 10
        """, conn)
        
        if hotspots_view == "Table":
            display_df = hotspots_df.copy()
            for col in ['current_interference', 'avg_interference', 'interference_delta']:
                display_df[col] = (display_df[col] * 100).round(1).astype(str) + '%'
                
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            hotspots_df['color'] = hotspots_df['interference_delta'].apply(lambda x: [255, 65, 54, 200])
            hotspots_df['tooltip'] = hotspots_df['location'].astype(str) + " (+" + (hotspots_df['interference_delta'] * 100).round(1).astype(str) + "% spike)"
            
            layer = pdk.Layer(
                "H3HexagonLayer",
                hotspots_df,
                pickable=True,
                stroked=True,
                filled=True,
                extruded=False,
                get_hexagon="hex",
                get_fill_color="color",
                get_line_color="[255, 255, 255, 100]",
                line_width_min_pixels=2,
            )
            
            view_state = pdk.ViewState(latitude=20, longitude=0, zoom=1)
            deck = pdk.Deck(
                layers=[layer], 
                initial_view_state=view_state, 
                map_style=pdk.map_styles.DARK,
                tooltip={"html": "<b>{tooltip}</b>", "style": {"color": "white", "backgroundColor": "#222222"}}
            )
            st.pydeck_chart(deck, use_container_width=True, height=400)
            
    except Exception as e:
        st.warning("Hotspots table is currently building in the background.")
        
    # Severity Histogram
    st.markdown("### 📊 Global Severity Distribution")
    try:
        all_time_hist = pd.read_sql_query("SELECT interference_percentage FROM all_time_stats WHERE interference_percentage > 0.02", conn)
        fig_hist = px.histogram(all_time_hist, x="interference_percentage", nbins=50, title="Distribution of Interference Severity (Hexes > 2%)")
        fig_hist.update_layout(template="plotly_dark", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", xaxis_title="Interference %", yaxis_title="Number of Regions")
        st.plotly_chart(fig_hist, use_container_width=True)
    except Exception as e:
        st.warning("Histogram data is building.")

    # Day-of-Week Pattern of Life
    st.markdown("### 📅 Pattern of Life (Day of the Week)")
    st.markdown("Analyzes whether jamming events follow human work schedules (e.g., dipping on weekends) or if they are automated 24/7.")
    try:
        dow_df = pd.read_sql_query("""
            SELECT 
                CAST(strftime('%w', date) AS INTEGER) as dow, 
                AVG(bad) as avg_bad_flights
            FROM daily_impact_stats 
            GROUP BY dow
            ORDER BY dow
        """, conn)
        
        day_map = {0: 'Sunday', 1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday', 6: 'Saturday'}
        dow_df['Day'] = dow_df['dow'].map(day_map)
        
        import plotly.express as px
        fig_dow = px.bar(dow_df, x='Day', y='avg_bad_flights', title="Average Jammed Flights by Day of the Week", color='avg_bad_flights', color_continuous_scale="Oranges")
        fig_dow.update_layout(template="plotly_dark", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", yaxis_title="Average Jammed Flights")
        st.plotly_chart(fig_dow, use_container_width=True)
    except Exception as e:
        st.warning(f"Day-of-Week data is building. ({e})")

    # Country-Level Choropleth Map
    st.markdown("### 🗺️ Geopolitical Conflict Map")
    try:
        choro_df = pd.read_sql_query("""
            SELECT c.country_code_iso3 as iso3, AVG(a.interference_percentage) as avg_interference, SUM(a.count_bad_aircraft) as total_jammed
            FROM all_time_stats a
            JOIN hex_countries c ON a.hex = c.hex
            WHERE c.country_code_iso3 != 'Unknown'
            GROUP BY c.country_code_iso3
        """, conn)
        
        fig_map = px.choropleth(
            choro_df, 
            locations="iso3", 
            color="avg_interference",
            hover_name="iso3",
            hover_data=["total_jammed"],
            color_continuous_scale="Reds",
            title="Average National Interference Level"
        )
        fig_map.update_layout(template="plotly_dark", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", geo=dict(showframe=False, showcoastlines=False, projection_type='equirectangular'))
        st.plotly_chart(fig_map, use_container_width=True)
    except Exception as e:
        st.warning(f"Choropleth data is building. ({e})")
    
    conn.close()

elif page == "🔥 All-Time Heatmap":
    st.subheader("All-Time Global GPS Dead-Zones")
    st.markdown("This heatmap aggregates over **100 million** historical records to reveal the absolute worst, permanent GPS dead-zones on Earth.")
    
    with st.spinner("Loading all-time historical data..."):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30.0)
            # Filter out perfectly 0% areas (150,000+ hexes) to prevent WebGL artifacting, but keep low-interference green areas (>0%)
            all_time_df = pd.read_sql_query("SELECT * FROM all_time_stats WHERE interference_percentage > 0.0", conn)
            conn.close()
            
            if not all_time_df.empty:
                import h3
                all_time_df['lat'] = all_time_df['hex'].apply(lambda x: h3.cell_to_latlng(x)[0])
                all_time_df = all_time_df[(all_time_df['lat'] < 80) & (all_time_df['lat'] > -80)]
                
                all_time_df['color'] = all_time_df['interference_percentage'].apply(get_color)
                all_time_df['tooltip_html'] = (
                    "<b>All-Time Interference:</b> " + (all_time_df['interference_percentage'] * 100).round(1).astype(str) + "%<br/>" +
                    "<b>Total Jammed Aircraft:</b> " + all_time_df['count_bad_aircraft'].astype(str) + "<br/>" +
                    "<b>Total Safe Aircraft:</b> " + all_time_df['count_good_aircraft'].astype(str)
                )
                
                is_3d_terrain_all = map_style_choice == "3D Satellite Terrain"
                is_globe_all = map_style_choice == "3D Spinning Globe"
                is_3d_all = is_3d_terrain_all or is_globe_all
                hex_layer_all = pdk.Layer(
                    "H3HexagonLayer",
                    all_time_df,
                    pickable=True,
                    stroked=not is_3d_all,
                    filled=True,
                    extruded=is_3d_all,
                    get_hexagon="hex",
                    get_fill_color="color",
                    get_elevation="interference_percentage * 100000" if is_3d_all else None,
                    get_line_color="[255, 255, 255, 20]",
                    line_width_min_pixels=0,
                    wrap_longitude=True
                )
                
                layers_all = []
                if is_3d_terrain_all:
                    layers_all.append(pdk.Layer(
                        "TerrainLayer",
                        elevation_decoder={"rScaler": 256, "gScaler": 1, "bScaler": 1 / 256, "offset": -32768},
                        texture="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                        elevation_data="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
                        max_requests=10,
                        wrap_longitude=True
                    ))
                    layers_all.append(pdk.Layer(
                        "TerrainLayer",
                        elevation_decoder={"rScaler": 256, "gScaler": 1, "bScaler": 1 / 256, "offset": -32718},
                        texture="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
                        elevation_data="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
                        max_requests=10,
                        wrap_longitude=True
                    ))
                if is_globe_all:
                    layers_all.append(pdk.Layer(
                        "GeoJsonLayer",
                        data="https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson",
                        get_fill_color=[30, 30, 30],
                        get_line_color=[70, 70, 70],
                        line_width_min_pixels=1,
                        stroked=True,
                        filled=True
                    ))
                    # Text and detailed borders from ArcGIS
                    layers_all.append(pdk.Layer(
                        "TileLayer",
                        data="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
                        max_requests=10
                    ))
                layers_all.append(hex_layer_all)
                
                view_state_all = pdk.ViewState(latitude=30, longitude=0, zoom=1.2, bearing=0, pitch=45 if is_3d_all else 0)
                
                deck_views_all = [pdk.View(type="_GlobeView", controller=True)] if is_globe_all else [pdk.View(type="MapView", controller=True)]
                deck_all = pdk.Deck(
                    layers=layers_all,
                    initial_view_state=view_state_all,
                    views=deck_views_all,
                    tooltip={"html": "{tooltip_html}", "style": {"color": "white", "backgroundColor": "#222222", "padding": "10px", "borderRadius": "5px"}},
                    map_style=selected_style,
                    map_provider=None if is_3d_all else "carto"
                )
                if is_globe_all:
                    import streamlit.components.v1 as components
                    components.html(deck_all.to_html(as_string=True), height=600)
                else:
                    st.pydeck_chart(deck_all, use_container_width=True, height=600)
            else:
                st.warning("All-time heatmap data is empty. Ensure the analytics pre-processor has finished running.")
        except Exception as e:
            st.warning(f"All-time heatmap failed to load: {e}")
