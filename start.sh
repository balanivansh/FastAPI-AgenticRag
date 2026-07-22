#!/bin/bash
# Start the FastAPI backend in the background on port 8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Start the Streamlit frontend in the foreground on Hugging Face's default port (7860)
python -m streamlit run ui/app.py --server.port 7860 --server.address 0.0.0.0
