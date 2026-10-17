# Android ADB 4G/LTE Mobile Proxy & IP Rotator
### Универсальный мобильный 4G/LTE прокси и авто-ротатор IP через USB ADB

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Android](https://img.shields.io/badge/platform-Android_9--15-brightgreen.svg)](https://android.com)

Turn any Android smartphone into an ultra-fast, zero-detection residential 4G/LTE mobile proxy via USB ADB with zero-drop cellular IP rotation and strict DNS/egress pinning.

Превратите любой Android-смартфон в высокоскоростной резидентный 4G/LTE мобильный прокси через USB ADB с мгновенной ротацией IP и защитой от утечек DNS.

---

## 🏛 Architecture / Архитектура

```mermaid
flowchart TD
    subgraph Host["Host Machine (macOS / Linux / Windows)"]
        Browser["Scraper / Antidetect Browser"]
        ApiServer["iProxy API Server (:5000)"]
        Rotator["rotate_ip.py (State Machine)"]
        AdbDaemon["ADB Host Service"]
    end

    subgraph USB["USB 3.0 / ADB High-Speed Bus"]
        AdbForward["ADB Port Forward (:8080 HTTP / :1080 SOCKS5)"]
        AdbCmd["ADB Shell / Broadcast Control"]
    end

    subgraph Phone["Android Device (Unrooted or Rooted)"]
        Gost["Proxy Engine (gost / agent_bridge)"]
        DnsResolver["Cellular UDP-DNS Bridge (:5353)"]
        CellularIf["Cellular Interface (seth_lte0 / rmnet_data*)"]
        WiFiIf["Wi-Fi / Ethernet Interface (Bypassed)"]
    end

    subgraph Carrier["Mobile Telecom Carrier (4G/LTE)"]
        eNodeB["Base Station / Tower"]
        CarrierIP["Dynamic Cellular WAN IPv4 / IPv6"]
    end

    Browser -->|HTTP/SOCKS5| AdbForward
    ApiServer -->|Trigger Rotation| Rotator
    Rotator -->|cmd connectivity airplane-mode| AdbCmd
    AdbForward --> Gost
    Gost -->|SO_BINDTODEVICE| CellularIf
    Gost -->|DNS Query| DnsResolver
    DnsResolver -->|Cellular DNS Pinning| CellularIf
    CellularIf --> eNodeB
    eNodeB --> CarrierIP

    classDef host fill:#2d3748,stroke:#4a5568,color:#fff;
    classDef phone fill:#1a365d,stroke:#2b6cb0,color:#fff;
    classDef carrier fill:#22543d,stroke:#38a169,color:#fff;
    class Host,Browser,ApiServer,Rotator,AdbDaemon host;
    class Phone,Gost,DnsResolver,CellularIf,WiFiIf phone;
    class Carrier,eNodeB,CarrierIP carrier;
```

### Key Features / Ключевые возможности:
- **Zero-Root Operation**: Works out-of-the-box on standard retail Android firmware without unlocking the bootloader or voiding warranty.
- **Root / Magisk Policy Routing**: Optional kernel-level `ip rule` / `ip route` policy tables for enterprise high-concurrency scraping.
- **Cellular Interface Pinning**: Guarantees all proxy traffic egresses through `seth_lte0` / `rmnet_data0`, preventing accidental Wi-Fi leaks.
- **Zero-Drop Fast IP Rotation**: Sub-5-second radio cycling with automated carrier re-registration verification.
- **iProxy REST API**: Drop-in compatible endpoints (`/rotate`, `/status`, `/ip`) for antidetect browsers (Dolphin Anty, AdsPower, Multilogin, Octo, Undetectable).

---

## 🚀 Quick Start / Быстрый старт

### 1. Requirements / Требования
- Android Phone (Android 9 to Android 15) with Developer Options & USB Debugging enabled.
- Python 3.9+ installed on the host machine.
- Android platform-tools (`adb`) installed in `PATH`.

### 2. Installation / Установка
```bash
git clone https://github.com/spartak-dev/android-adb-lte-proxy.git
cd android-adb-lte-proxy

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

### 3. Start the Proxy / Запуск прокси
```bash
# Auto-detect device and run in Zero-Root mode
python3 adb_lte_proxy.py

# Or specify device serial and custom ports
python3 adb_lte_proxy.py --serial YOUR_DEVICE_SERIAL --http-port 8080 --socks-port 1080
```

### 4. Trigger IP Rotation / Ротация IP-адреса
```bash
# CLI rotation
python3 rotate_ip.py --json

# Or start the REST API server
python3 iproxy_api.py
# Then trigger rotation via HTTP:
curl -X POST http://127.0.0.1:5000/rotate
```

---

## ⚙️ Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `ADB_SERIAL` | `""` | Target device ADB serial (from `adb devices`) |
| `CELLULAR_INTERFACE` | `seth_lte0` | Mobile data interface name (`rmnet_data0`, `seth_lte0`) |
| `PROXY_HTTP_PORT` | `8080` | Local HTTP proxy port |
| `PROXY_SOCKS_PORT` | `1080` | Local SOCKS5 proxy port |
| `API_PORT` | `5000` | Management REST API port |
| `API_KEY` | `""` | Optional secret key for securing REST endpoints |

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
Copyright (c) 2026 spartak.
