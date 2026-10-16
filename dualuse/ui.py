"""Streamlit demo front end, a client of the API in `dualuse.api`.

Run: bash scripts/uv-run.sh streamlit run dualuse/ui.py --server.port 8501
"""

import os

import httpx
import streamlit as st

API_URL = os.environ.get("DUALUSE_API_URL", "http://localhost:8000")

st.set_page_config(page_title="Dual-Use Hackathon", layout="wide")
st.title("Dual-Use Hackathon")

try:
    status = httpx.get(f"{API_URL}/health", timeout=2).raise_for_status().json()["status"]
except httpx.HTTPError as error:
    st.error(f"API at {API_URL} is unreachable: {error}")
else:
    st.success(f"API at {API_URL}: {status}")
