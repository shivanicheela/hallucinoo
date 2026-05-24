"""
HalluciNO - AI Hallucination Detector
Backend Entry Point

To run the backend:
1. Install dependencies: pip install -r requirements.txt
2. Run: python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
3. Access API docs: http://localhost:8000/docs
"""

import uvicorn
from app.main import app

if _name_ == "_main_":
    import os, uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
