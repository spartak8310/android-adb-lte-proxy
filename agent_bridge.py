#!/usr/bin/env python3
"""
Cellular Interface Binding & DNS Resolver Bridge
Provides UDP-DNS redirection and cellular interface socket pinning for mobile proxy egress.
"""

import os
import sys
import socket
import select
import threading
import logging
import subprocess
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [Bridge] %(message)s")
logger = logging.getLogger("agent_bridge")

ADB_SERIAL = os.getenv("ADB_SERIAL", "")
BIND_INTERFACE = os.getenv("CELLULAR_INTERFACE", "seth_lte0")
LOCAL_DNS_PORT = int(os.getenv("DNS_BRIDGE_PORT", "5353"))
CARRIER_DNS = os.getenv("CARRIER_DNS", "8.8.8.8")

class DnsResolverBridge:
    def __init__(self, bind_ip="127.0.0.1", port=LOCAL_DNS_PORT, upstream_dns=CARRIER_DNS, interface=BIND_INTERFACE):
        self.bind_ip = bind_ip
        self.port = port
        self.upstream_dns = upstream_dns
        self.interface = interface
        self.running = False
        self.sock = None

    def start(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.bind_ip, self.port))
        self.running = True
        logger.info(f"DNS Resolver Bridge active on {self.bind_ip}:{self.port} -> Upstream: {self.upstream_dns}")

        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                threading.Thread(target=self._handle_dns_query, args=(data, addr), daemon=True).start()
            except Exception as e:
                if self.running:
                    logger.error(f"DNS receive error: {e}")

    def _handle_dns_query(self, data, client_addr):
        upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        upstream_sock.settimeout(3.0)
        
        # Linux / Android interface binding if supported
        if sys.platform.startswith("linux") and self.interface:
            try:
                upstream_sock.setsockopt(socket.SOL_SOCKET, 25, self.interface.encode() + b'\0')
            except PermissionError:
                pass
            except Exception as e:
                logger.debug(f"SO_BINDTODEVICE notice: {e}")

        try:
            upstream_sock.sendto(data, (self.upstream_dns, 53))
            resp, _ = upstream_sock.recvfrom(4096)
            self.sock.sendto(resp, client_addr)
        except socket.timeout:
            logger.warning(f"DNS query timeout to upstream {self.upstream_dns}")
        except Exception as e:
            logger.error(f"DNS resolution failure: {e}")
        finally:
            upstream_sock.close()

    def stop(self):
        self.running = False
        if self.sock:
            self.sock.close()
            logger.info("DNS Resolver Bridge stopped.")

def main():
    bridge = DnsResolverBridge()
    try:
        bridge.start()
    except KeyboardInterrupt:
        bridge.stop()

if __name__ == "__main__":
    main()
