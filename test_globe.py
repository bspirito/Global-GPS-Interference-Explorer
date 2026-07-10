import streamlit as st
import pydeck as pdk
deck = pdk.Deck(views=[pdk.View(type='_GlobeView', controller=True)], map_provider='carto')
st.components.v1.html(deck.to_html(as_string=True), height=600)