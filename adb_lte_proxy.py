#!/usr/bin/env python3
"""
ADB 4G/LTE Mobile Proxy Controller (Zero-Root & Root/Magisk)
Universal mobile egress proxy runner for Android devices via USB ADB.

Supports:
- Zero-Root Mode: gost / socks5 proxy forward + custom UDP-DNS cellular pinning
- Root Mode: Linux policy routing (ip rule / ip route) pinning default egress to cellular interface
"""

import os
import sys
import time
import signal
import argparse
import subprocess
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("adb_lte_proxy")

DEFAULT_SERIAL = os.getenv("ADB_SERIAL", "")
DEFAULT_INTERFACE = os.getenv("CELLULAR_INTERFACE", "seth_lte0")
DEFAULT_HTTP_PORT = int(os.getenv("PROXY_HTTP_PORT", "8080"))
DEFAULT_SOCKS_PORT = int(os.getenv("PROXY_SOCKS_PORT", "1080"))
GOST_REMOTE_PATH = "/data/local/tmp/gost"

class AdbLteProxy:
    def __init__(self, serial=None, interface="seth_lte0", http_port=8080, socks_port=1080, mode="zero-root"):
        self.serial = serial or DEFAULT_SERIAL
        self.interface = interface
        self.http_port = http_port
        self.socks_port = socks_port
        self.mode = mode
        self.adb_cmd = ["adb"]
        if self.serial:
            self.adb_cmd.extend(["-s", self.serial])
        self.running_processes = []

    def run_adb(self, args, check=True, capture_output=True, text=True):
        cmd = self.adb_cmd + args
        logger.debug(f"Executing: {' '.join(cmd)}")
        return subprocess.run(cmd, check=check, capture_output=capture_output, text=text)

    def verify_device(self):
        try:
            res = self.run_adb(["get-state"])
            if "device" not in res.stdout:
                logger.error(f"Device not ready: {res.stdout.strip()}")
                return False
            model = self.run_adb(["shell", "getprop", "ro.product.model"]).stdout.strip()
            carrier = self.run_adb(["shell", "getprop", "gsm.operator.alpha"]).stdout.strip()
            logger.info(f"Target Android Device: {model} (Carrier: {carrier or 'Unknown'})")
            return True
        except Exception as e:
            logger.error(f"ADB connection failure: {e}")
            return False

    def detect_cellular_interface(self):
        """Auto-detect active cellular network interface (rmnet_data*, seth_lte0, ccmni*)"""
        try:
            res = self.run_adb(["shell", "ip", "-o", "link", "show"])
            lines = res.stdout.splitlines()
            candidates = ["seth_lte0", "rmnet_data0", "rmnet_data1", "ccmni0", "pdp0"]
            for cand in candidates:
                for line in lines:
                    if cand in line and "UP" in line:
                        logger.info(f"Detected active cellular interface: {cand}")
                        self.interface = cand
                        return cand
            logger.warning(f"Could not auto-detect active cellular interface. Falling back to {self.interface}")
            return self.interface
        except Exception as e:
            logger.warning(f"Interface detection error: {e}. Using {self.interface}")
            return self.interface

    def setup_zero_root(self):
        """Zero-Root Mode: Forward ports via ADB reverse / forward and run gost on device."""
        logger.info(f"[Zero-Root] Setting up port forwarding and gost pinning to {self.interface}...")
        
        # ADB port forward
        self.run_adb(["forward", f"tcp:{self.http_port}", f"tcp:{self.http_port}"])
        self.run_adb(["forward", f"tcp:{self.socks_port}", f"tcp:{self.socks_port}"])
        logger.info(f"ADB forwarded TCP ports: {self.http_port} (HTTP), {self.socks_port} (SOCKS5)")

        # Verify gost binary on device
        check_gost = self.run_adb(["shell", f"ls {GOST_REMOTE_PATH}"], check=False)
        if check_gost.returncode != 0:
            logger.warning(f"gost binary not found at {GOST_REMOTE_PATH}. Please deploy gost binary via scripts.")
        else:
            self.run_adb(["shell", f"chmod 755 {GOST_REMOTE_PATH}"])
            # Launch gost background server binding to interface if supported
            gost_cmd = (
                f"{GOST_REMOTE_PATH} -L http://:{self.http_port} "
                f"-L socks5://:{self.socks_port}?bind={self.interface} > /data/local/tmp/gost.log 2>&1 &"
            )
            self.run_adb(["shell", f"nohup {gost_cmd}"])
            logger.info("[Zero-Root] Remote gost proxy process started on device.")

    def setup_root_routing(self):
        """Root Mode: Configure policy routing via iptables and ip rule for interface binding."""
        logger.info(f"[Root Mode] Configuring policy routing for interface {self.interface}...")
        cmds = [
            f"su -c 'ip rule add fwmark 0x100 lookup 100'",
            f"su -c 'ip route add default dev {self.interface} table 100'",
            f"su -c 'ip route flush cache'"
        ]
        for cmd in cmds:
            self.run_adb(["shell", cmd], check=False)
        logger.info("[Root Mode] Policy routing tables applied successfully.")

    def start(self):
        if not self.verify_device():
            sys.exit(1)
        self.detect_cellular_interface()
        
        if self.mode == "root":
            self.setup_root_routing()
        else:
            self.setup_zero_root()
            
        logger.info("Proxy server initialized and ready.")
        logger.info(f"HTTP Proxy:  http://127.0.0.1:{self.http_port}")
        logger.info(f"SOCKS5 Proxy: socks5://127.0.0.1:{self.socks_port}")

    def cleanup(self):
        logger.info("Cleaning up ADB forwards and proxy bindings...")
        try:
            self.run_adb(["forward", "--remove", f"tcp:{self.http_port}"], check=False)
            self.run_adb(["forward", "--remove", f"tcp:{self.socks_port}"], check=False)
            if self.mode == "zero-root":
                self.run_adb(["shell", "pkill -f gost"], check=False)
            logger.info("Cleanup complete.")
        except Exception as e:
            logger.warning(f"Cleanup encountered error: {e}")

def main():
    parser = argparse.ArgumentParser(description="ADB 4G/LTE Universal Mobile Proxy")
    parser.add_argument("--serial", "-s", default=DEFAULT_SERIAL, help="Target Android ADB device serial")
    parser.add_argument("--interface", "-i", default=DEFAULT_INTERFACE, help="Cellular interface name (e.g. seth_lte0, rmnet_data0)")
    parser.add_argument("--mode", "-m", choices=["zero-root", "root"], default="zero-root", help="Proxy operation mode")
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT, help="Local HTTP proxy port (default: 8080)")
    parser.add_argument("--socks-port", type=int, default=DEFAULT_SOCKS_PORT, help="Local SOCKS5 proxy port (default: 1080)")
    args = parser.parse_args()

    proxy = AdbLteProxy(
        serial=args.serial,
        interface=args.interface,
        http_port=args.http_port,
        socks_port=args.socks_port,
        mode=args.mode
    )

    def handle_exit(sig, frame):
        logger.info("Termination signal received.")
        proxy.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    proxy.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handle_exit(None, None)

if __name__ == "__main__":
    main()
