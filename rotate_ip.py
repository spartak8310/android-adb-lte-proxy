#!/usr/bin/env python3
"""
Zero-Drop Cellular IP Rotation via ADB Radio / Airplane State Machine.
Cycles the radio connection and confirms external carrier IP re-registration.
"""

import os
import sys
import time
import json
import argparse
import logging
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [Rotator] %(message)s")
logger = logging.getLogger("rotate_ip")

DEFAULT_SERIAL = os.getenv("ADB_SERIAL", "")
IP_CHECK_URL = os.getenv("IP_CHECK_URL", "https://api.ipify.org?format=json")
CHECK_TIMEOUT = float(os.getenv("IP_CHECK_TIMEOUT", "5.0"))
RETRY_DELAY = float(os.getenv("ROTATION_DELAY", "1.5"))

class CellularIpRotator:
    def __init__(self, serial=None, check_url=IP_CHECK_URL, proxy_url=None):
        self.serial = serial or DEFAULT_SERIAL
        self.check_url = check_url
        self.proxy_url = proxy_url
        self.adb_cmd = ["adb"]
        if self.serial:
            self.adb_cmd.extend(["-s", self.serial])

    def run_adb(self, args, check=True):
        cmd = self.adb_cmd + args
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def get_current_ip(self):
        proxies = {"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None
        try:
            resp = requests.get(self.check_url, proxies=proxies, timeout=CHECK_TIMEOUT)
            if resp.status_code == 200:
                try:
                    return resp.json().get("ip")
                except Exception:
                    return resp.text.strip()
        except Exception as e:
            logger.warning(f"IP check error: {e}")
        return None

    def toggle_airplane_mode(self):
        logger.info("Executing airplane mode cycle via ADB...")
        # Step 1: Enable airplane mode
        res1 = self.run_adb(["shell", "cmd", "connectivity", "airplane-mode", "enable"], check=False)
        if res1.returncode != 0:
            # Fallback legacy settings + broadcast
            self.run_adb(["shell", "settings", "put", "global", "airplane_mode_on", "1"], check=False)
            self.run_adb(["shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "true"], check=False)

        time.sleep(RETRY_DELAY)

        # Step 2: Disable airplane mode
        res2 = self.run_adb(["shell", "cmd", "connectivity", "airplane-mode", "disable"], check=False)
        if res2.returncode != 0:
            self.run_adb(["shell", "settings", "put", "global", "airplane_mode_on", "0"], check=False)
            self.run_adb(["shell", "am", "broadcast", "-a", "android.intent.action.AIRPLANE_MODE", "--ez", "state", "false"], check=False)

    def wait_for_carrier_registration(self, max_wait=20):
        logger.info("Waiting for LTE/4G radio registration...")
        start_time = time.time()
        while time.time() - start_time < max_wait:
            res = self.run_adb(["shell", "dumpsys", "telephony.registry"], check=False)
            if "mDataConnectionState=2" in res.stdout or "mDataRegistrationState=0" in res.stdout:
                logger.info("Cellular radio data connection re-established.")
                return True
            time.sleep(0.5)
        logger.warning("Radio state wait reached timeout, continuing to IP check...")
        return False

    def rotate(self, max_attempts=3):
        t0 = time.time()
        initial_ip = self.get_current_ip()
        logger.info(f"Initial WAN IP: {initial_ip or 'Unknown/Offline'}")

        for attempt in range(1, max_attempts + 1):
            logger.info(f"Rotation attempt {attempt}/{max_attempts}...")
            self.toggle_airplane_mode()
            self.wait_for_carrier_registration()

            # Poll for new IP
            for _ in range(15):
                new_ip = self.get_current_ip()
                if new_ip and new_ip != initial_ip:
                    duration = round(time.time() - t0, 2)
                    result = {
                        "status": "success",
                        "old_ip": initial_ip,
                        "new_ip": new_ip,
                        "duration_sec": duration,
                        "attempts": attempt
                    }
                    logger.info(f"Rotation SUCCESS in {duration}s: {initial_ip} -> {new_ip}")
                    return result
                time.sleep(0.8)

        duration = round(time.time() - t0, 2)
        final_ip = self.get_current_ip()
        return {
            "status": "partial" if final_ip else "failed",
            "old_ip": initial_ip,
            "new_ip": final_ip,
            "duration_sec": duration,
            "attempts": max_attempts
        }

def main():
    parser = argparse.ArgumentParser(description="Zero-Drop Cellular IP Rotator via ADB")
    parser.add_argument("--serial", "-s", default=DEFAULT_SERIAL, help="Target Android ADB device serial")
    parser.add_argument("--proxy", "-p", default=None, help="Proxy URL for IP verification (e.g. socks5://127.0.0.1:1080)")
    parser.add_argument("--json", action="store_true", help="Output JSON response format")
    args = parser.parse_args()

    rotator = CellularIpRotator(serial=args.serial, proxy_url=args.proxy)
    result = rotator.rotate()

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Status: {result['status'].upper()} | Old: {result['old_ip']} -> New: {result['new_ip']} ({result['duration_sec']}s)")

    if result["status"] != "success":
        sys.exit(1)

if __name__ == "__main__":
    main()
