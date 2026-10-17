#!/usr/bin/env python3
"""
Self-Hosted iProxy-Compatible REST API Server
Provides management, telemetry, and cellular IP rotation endpoints for automated scrapers and browsers.
"""

import os
import sys
import time
import subprocess
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [API] %(message)s")
logger = logging.getLogger("iproxy_api")

API_PORT = int(os.getenv("API_PORT", "5000"))
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_KEY_SECRET = os.getenv("API_KEY", "")
ADB_SERIAL = os.getenv("ADB_SERIAL", "")
PROXY_HTTP_PORT = int(os.getenv("PROXY_HTTP_PORT", "8080"))
PROXY_SOCKS_PORT = int(os.getenv("PROXY_SOCKS_PORT", "1080"))

app = FastAPI(
    title="Android ADB LTE Proxy API",
    description="iProxy-compatible REST API for cellular mobile proxy rotation and monitoring",
    version="1.0.0"
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)):
    if API_KEY_SECRET and api_key != API_KEY_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key"
        )
    return api_key

class RotateResponse(BaseModel):
    status: str
    old_ip: Optional[str]
    new_ip: Optional[str]
    duration_sec: float
    carrier: Optional[str] = None

class StatusResponse(BaseModel):
    device_serial: str
    model: str
    carrier: str
    cellular_ip: Optional[str]
    proxy_http: str
    proxy_socks5: str
    uptime_sec: float

start_time = time.time()

def get_adb_info():
    cmd_base = ["adb"]
    if ADB_SERIAL:
        cmd_base.extend(["-s", ADB_SERIAL])
    
    try:
        model = subprocess.run(cmd_base + ["shell", "getprop", "ro.product.model"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        model = "Unknown"

    try:
        carrier = subprocess.run(cmd_base + ["shell", "getprop", "gsm.operator.alpha"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        carrier = "Unknown"

    return model, carrier

@app.get("/", tags=["Info"])
def root():
    return {
        "service": "Android ADB LTE Proxy",
        "version": "1.0.0",
        "endpoints": ["/status", "/rotate", "/ip", "/metrics"]
    }

@app.get("/status", response_model=StatusResponse, tags=["Telemetry"], dependencies=[Security(verify_api_key)])
def get_status():
    model, carrier = get_adb_info()
    from rotate_ip import CellularIpRotator
    rotator = CellularIpRotator(serial=ADB_SERIAL)
    current_ip = rotator.get_current_ip()
    
    return StatusResponse(
        device_serial=ADB_SERIAL or "default",
        model=model,
        carrier=carrier,
        cellular_ip=current_ip,
        proxy_http=f"http://127.0.0.1:{PROXY_HTTP_PORT}",
        proxy_socks5=f"socks5://127.0.0.1:{PROXY_SOCKS_PORT}",
        uptime_sec=round(time.time() - start_time, 1)
    )

@app.get("/rotate", response_model=RotateResponse, tags=["Rotation"], dependencies=[Security(verify_api_key)])
@app.post("/rotate", response_model=RotateResponse, tags=["Rotation"], dependencies=[Security(verify_api_key)])
def trigger_rotation():
    from rotate_ip import CellularIpRotator
    rotator = CellularIpRotator(serial=ADB_SERIAL)
    res = rotator.rotate()
    _, carrier = get_adb_info()
    res["carrier"] = carrier
    return res

@app.get("/ip", tags=["Telemetry"])
def get_ip():
    from rotate_ip import CellularIpRotator
    rotator = CellularIpRotator(serial=ADB_SERIAL)
    ip = rotator.get_current_ip()
    return {"ip": ip or "offline"}

def main():
    logger.info(f"Starting iProxy API Server on {API_HOST}:{API_PORT}...")
    uvicorn.run(app, host=API_HOST, port=API_PORT, log_level="info")

if __name__ == "__main__":
    main()
