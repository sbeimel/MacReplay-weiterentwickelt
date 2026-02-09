#############################################################################################

import os

# Read from environment variables (set by Docker)
PORT = int(os.getenv("VAVOO_PORT", "4323"))
PUBLIC_HOST = os.getenv("VAVOO_PUBLIC_HOST", "")
PLAYLIST_DIR = "/app/data/vavoo_playlists"  # Docker-optimized path

#############################################################################################

import pwd
import grp
import json
import subprocess
import gzip
import requests
import uuid
import time
import socket
import re
from collections import defaultdict
from flask import Flask, request, Response, abort, redirect, session
from urllib.parse import urljoin
import os
from flask import send_from_directory
import threading
import multiprocessing
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
os.chdir(os.path.dirname(os.path.abspath(__file__)))
PLAYLIST_OWNER = "www-data"  
PLAYLIST_GROUP = "www-data"  
PLAYLIST_MODE  = 0o755           
FFMPEG_READ_TIMEOUT_US = 8_000_000  
FFMPEG_PROBE_SECONDS   = 1.5     
FFMPEG_PROCESS_TIMEOUT = 12   
FFPROBE_PROCESS_TIMEOUT = 15
SEGMENT_GRACE = 120
CONNECTION_TIMEOUT = 300 
PLAYLIST_REBUILD_ON_START = True
RES_DEBUG = True
BANNER_REFRESH = multiprocessing.Event()
RES_READY = multiprocessing.Event()
REFRESH_INTERVAL = 600
FORCE_REFRESH = multiprocessing.Event()
FORCE_REGIONS = multiprocessing.Manager().list()  
REBUILD_REGIONS = multiprocessing.Manager().list()
PRINT_LOCK = multiprocessing.Lock()
PLAYLIST_CACHE = {}
PLAYLIST_CACHE_TTL = 10
FALLBACK_CACHE = {}
FALLBACK_TTL = 45
CONFIG_FILE = "config.json"
MAPPING_FILE = "mapping.json"

MAPPINGS = {
    "channel": {},
    "tvg-id": {},
    "tvg-name": {},
    "tvg-logo": {},
}
CONFIG = multiprocessing.Manager().dict({
    "RES": False,
    "PLAYLIST_REBUILD_ON_START": True,
    "FILTER_ENABLED": False,
    "FILTER_KEYWORDS": [], 
    "LOCALES": [("de", "DE")],
})
LANGUAGE = "de"
REGION = "DE"
REGION_NAMES = {
    "AL": "Albania",
    "BG": "Bulgaria",
    "CR": "Croatia",
    "FR": "France",
    "DE": "Germany",
    "IT": "Italy",
    "NL": "Netherlands",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "ES": "Spain",
    "TR": "Turkey",
    "GB": "United Kingdom",
}
REF_DATA = {
    "groups": [
        {"group-title": "OeR", "channels": [
            {"channel": "Das Erste"}, {"channel": "ZDF"}, {"channel": "phoenix"}, {"channel": "ARD-alpha"},
            {"channel": "ZDFneo"}, {"channel": "ONE"}, {"channel": "ZDFinfo"}, {"channel": "ARTE"}, {"channel": "3sat"},
            {"channel": "WDR Köln"}, {"channel": "NDR Niedersachsen"}, {"channel": "SWR Rheinland-Pfalz"}, {"channel": "SR"},
            {"channel": "RBB Berlin"}, {"channel": "MDR Sachsen"}, {"channel": "hr-fernsehen"}, {"channel": "BR Nord"},
            {"channel": "ORF 1"}, {"channel": "ORF 2"}, {"channel": "tagesschau24"}, {"channel": "ntv"}, {"channel": "WELT"},
            {"channel": "euronews"}, {"channel": "CNN Europe"}, {"channel": "Al Jazeera English"}
        ]},
        {"group-title": "Private", "channels": [
            {"channel": "RTL"}, {"channel": "SAT.1"}, {"channel": "ProSieben"}, {"channel": "Kabel Eins"}, {"channel": "RTLZWEI"},
            {"channel": "Super RTL"}, {"channel": "VOX"}, {"channel": "DMAX"}, {"channel": "RTLup"}, {"channel": "RTL Crime"},
            {"channel": "RTL Passion"}, {"channel": "NITRO"}, {"channel": "ProSieben MAXX"}, {"channel": "ProSieben FUN"},
            {"channel": "SAT.1 emotions"}, {"channel": "SAT.1 GOLD"}, {"channel": "VOXup"}, {"channel": "sixx"},
            {"channel": "Romance TV"}, {"channel": "TLC"}, {"channel": "TELE 5"}, {"channel": "DF1"}, {"channel": "Comedy Central"}
        ]},
        {"group-title": "Sky", "channels": [
            {"channel": "Sky One"}, {"channel": "Sky Replay"}, {"channel": "Sky Showcase"}, {"channel": "Sky Atlantic"},
            {"channel": "Sky Action"}, {"channel": "Sky Cinema Highlights"}, {"channel": "Sky Cinema Classics"},
            {"channel": "Sky Cinema Family"}, {"channel": "Sky Cinema Premieren"}, {"channel": "Sky Krimi"}, {"channel": "SyFy"},
            {"channel": "WarnerTV Film"}, {"channel": "WarnerTV Serie"}, {"channel": "WarnerTV Comedy"}, {"channel": "Universal TV"},
            {"channel": "13th Street"}, {"channel": "Kabel Eins CLASSICS"}, {"channel": "KinoweltTV"}, {"channel": "AXN White"},
            {"channel": "AXN Black"}, {"channel": "Heimatkanal"}
        ]},
        {"group-title": "Doku", "channels": [
            {"channel": "Sky Crime"}, {"channel": "Sky Documentaries"}, {"channel": "Sky Nature"}, {"channel": "Animal Planet"},
            {"channel": "GEO Television"}, {"channel": "Discovery Channel"}, {"channel": "National Geographic WILD"},
            {"channel": "National Geographic"}, {"channel": "History"}, {"channel": "Crime + Investigation"}, {"channel": "Curiosity Channel"},
            {"channel": "SPIEGEL Geschichte"}, {"channel": "Welt der Wunder"}, {"channel": "N24 Doku"}, {"channel": "Kabel Eins Doku"},{"channel": "HGTV"},
            {"channel": "RTL Living"}, {"channel": "travelxp"}, {"channel": "BonGusto"}, {"channel": "Marco Polo TV"}
        ]},
        {"group-title": "Bundesliga", "channels": [
            {"channel": "DAZN 1"}, {"channel": "DAZN 2"}, {"channel": "Sky Sport Bundesliga"}, {"channel": "Sky Sport Bundesliga 1"},
            {"channel": "Sky Sport Bundesliga 2"}, {"channel": "Sky Sport Bundesliga 3"}, {"channel": "Sky Sport Bundesliga 4"},
            {"channel": "Sky Sport Bundesliga 5"}, {"channel": "Sky Sport Bundesliga 6"}, {"channel": "Sky Sport Bundesliga 7"},
            {"channel": "Sky Sport Bundesliga 8"}, {"channel": "Sky Sport Bundesliga 9"}, {"channel": "Sky Sport Bundesliga 10"}
        ]},
        {"group-title": "Dazn", "channels": [
            {"channel": "DAZN 1"}, {"channel": "DAZN 2"}, {"channel": "DAZN RISE"}, {"channel": "DAZN FAST+"}, {"channel": "Eurosport 1"},
            {"channel": "Eurosport 2"}, {"channel": "SPORTDIGITAL FUSSBALL"}, {"channel": "Billiard TV"}, {"channel": "Red Bull TV"},
            {"channel": "PowerSports World"}, {"channel": "ACL Cornhole TV"}, {"channel": "PLL Network"}, {"channel": "Unbeaten"},
            {"channel": "MLB Network"}, {"channel": "NFL Network"}
        ]},
        {"group-title": "Sport", "channels": [
            {"channel": "Sky Sport F1"}, {"channel": "Sky Sport Top Event"}, {"channel": "Sky Sport Premier League"},
            {"channel": "Sky Sport Mix"}, {"channel": "Sky Sport Tennis"}, {"channel": "Sky Sport Golf"}, {"channel": "Sky Sport News"},
            {"channel": "Sky Sport 1"}, {"channel": "Sky Sport 2"}, {"channel": "Sky Sport 3"}, {"channel": "Sky Sport 4"},
            {"channel": "Sky Sport 5"}, {"channel": "Sky Sport 6"}, {"channel": "Sky Sport 7"}, {"channel": "Sky Sport 8"},
            {"channel": "Sky Sport 9"}, {"channel": "Sky Sport 10"}, {"channel": "Sky Sport Austria 1"}, {"channel": "Sky Sport Austria 2"},
            {"channel": "Sky Sport Austria 3"}, {"channel": "Sky Sport Austria 4"}, {"channel": "Sky Sport Austria 5"},
            {"channel": "Sky Sport Austria 6"}, {"channel": "Sky Sport Austria 7"}, {"channel": "SPORT1"}, {"channel": "SPORTDIGITAL1+"},
            {"channel": "ORF Sport +"}, {"channel": "auto motor sport channel"}, {"channel": "Eurosport 1"}, {"channel": "Eurosport 2"},
            {"channel": "DAZN RISE"}, {"channel": "DAZN FAST"}, {"channel": "MOTORVISION+"}, {"channel": "eSportsONE"},
            {"channel": "More Than Sports TV"}, {"channel": "Sportdigital EDGE"}, {"channel": "Red Bull TV Extreme"}
        ]},
        {"group-title": "Magenta Sport", "channels": [
            {"channel": "Sport 1 - myTeamTV"}, {"channel": "Sport 2 - myTeamTV"}, {"channel": "Sport 3 - myTeamTV"},
            {"channel": "Sport 4 - myTeamTV"}, {"channel": "Sport 5 - myTeamTV"}, {"channel": "Sport 6 - myTeamTV"},
            {"channel": "Sport 7 - myTeamTV"}, {"channel": "Sport 8 - myTeamTV"}, {"channel": "Sport 9 - myTeamTV"},
            {"channel": "Sport 10 - myTeamTV"}, {"channel": "Sport 11 - myTeamTV"}, {"channel": "Sport 12 - myTeamTV"},
            {"channel": "Sport 13 - myTeamTV"}, {"channel": "Sport 14 - myTeamTV"}, {"channel": "Sport 15 - myTeamTV"},
            {"channel": "Sport 16 - myTeamTV"}, {"channel": "Sport 17 - myTeamTV"}, {"channel": "Sport 18 - myTeamTV"}
        ]}
    ]
}
GEOIP_URL = "https://www.vavoo.tv/geoip"
PING_URL = "https://www.vavoo.tv/api/app/ping"
CATALOG_URL = "https://vavoo.to/mediahubmx-catalog.json"
RESOLVE_URL = "https://vavoo.to/mediahubmx-resolve.json"
HEADERS = {
    "accept": "*/*",
    "user-agent": "electron-fetch/1.0 electron (+https://github.com/arantes555/electron-fetch)",
    "Accept-Language": LANGUAGE,
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}
class SharedState:
    def __init__(self):
        self.manager = multiprocessing.Manager()
        self.items_by_region = self.manager.dict()
        self.last_refresh = self.manager.dict()
        self.refresh_in_progress = self.manager.dict()
        self.common_headers = self.manager.dict()
        self.addon_sig = self.manager.Value('s', '')
        self.res_cache = self.manager.dict()
        self.res_expected = self.manager.Value('i', 0)
        self.res_done = self.manager.Value('i', 0)
        self.connections = self.manager.dict()
shared_state = SharedState()

def fast_stream_alive(url):
    try:
        r = requests.head(
            url,
            timeout=1.2,
            allow_redirects=True,
            headers={
                "User-Agent": HEADERS["user-agent"],
                "Accept": "*/*",
            }
        )
        return r.status_code < 400
    except:
        return False
        
def get_fallback_candidates(region, wanted_item):
    items = shared_state.items_by_region.get(region, [])
    key = fallback_channel_key(wanted_item)

    candidates = []
    for i in items:
        if i.get("resolved_url") and fallback_channel_key(i) == key:
            candidates.append(i)

    return candidates

def combined_playlist_name(regions):
    return "_".join(r.upper() for r in regions)

def cleanup_single_playlists():
    if not CONFIG.get("COMBINED_PLAYLISTS"):
        return

    for _, region in list(CONFIG.get("LOCALES", [])):
        fn = f"vavoo_playlist_{region}.m3u"
        path = os.path.join(PLAYLIST_DIR, fn) if PLAYLIST_DIR else fn
        if os.path.exists(path):
            os.remove(path)

def save_combined_playlist(regions):
    if not regions or len(regions) < 2:
        return

    host = public_host()
    output = "#EXTM3U\n"

    regions = [r.upper() for r in regions]

    for region in regions:
        items = shared_state.items_by_region.get(region)
        if not items:
            continue

        region_name = REGION_NAMES.get(region, region)

        for item in items:
            name = clean_display_name(item["name"])
            name = map_channel(name)

            tvg_id = build_tvg_id(name, region)
            tvg_id = map_tvg_id(tvg_id)
            tvg_name = map_tvg_name(name)

            if region == "DE":
                group = item.get("group") or region_name
            else:
                group = region_name

            mapped_logo = map_tvg_logo(name)
            logo_file = (
                mapped_logo
                if mapped_logo != name
                else re.sub(r"[^a-z0-9]", "", name.lower()) + ".png"
            )

            logo_url = f"http://{host}:{PORT}/logos/{logo_file}"

            output += (
                f'#EXTINF:-1 '
                f'tvg-id="{tvg_id}" '
                f'tvg-name="{tvg_name}" '
                f'tvg-logo="{logo_url}" '
                f'group-title="{group}",{name}\n'
            )

            output += (
                f"http://{host}:{PORT}/vavoo?"
                f"channel={item['id']}&region={region}\n"
            )

    name = "_".join(regions) 
    filename = f"vavoo_playlist_{name}.m3u"
    path = os.path.join(PLAYLIST_DIR, filename) if PLAYLIST_DIR else filename

    with open(path, "w", encoding="utf-8") as f:
        f.write(output)

    apply_file_permissions(path)

def load_mappings():
    global MAPPINGS

    if not os.path.exists(MAPPING_FILE):
        print("⚠ mapping.json not found – mappings disabled")
        return

    try:
        with open(MAPPING_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        for section in MAPPINGS.keys():
            data = raw.get(section, {})
            MAPPINGS[section] = {
                str(k).strip().lower(): str(v)
                for k, v in data.items()
                if k and v
            }

        print("✔ mapping.json loaded")

    except Exception as e:
        print(f"❌ Failed to load mapping.json: {e}")

def map_value(section, value):
    if not value:
        return value

    mapping = MAPPINGS.get(section, {})
    key = value.strip().lower()

    return mapping.get(key, value)

def map_channel(name):
    return map_value("channel", name)


def map_tvg_id(tvg_id):
    return map_value("tvg-id", tvg_id)

def map_tvg_name(tvg_name):
    return map_value("tvg-name", tvg_name)

def map_tvg_logo(logo):
    return map_value("tvg-logo", logo)
    
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated
    
def load_config():
    return CONFIG

def get_resolved_channel_url(channel_id, region):
    items = shared_state.items_by_region.get(region.upper())
    if not items:
        return None

    for item in items:
        if item.get("id") == channel_id:
            return item.get("resolved_url")

    return None
       
def get_channel_name(region, cid):
    items = shared_state.items_by_region.get(region, [])
    for i in items:
        if i["id"] == cid:
            return clean_display_name(i["name"])
    return cid

def load_config_from_disk():
    if not os.path.exists(CONFIG_FILE):
        CONFIG["LOCALES"] = [("de", "DE")]
        CONFIG["COMBINED_PLAYLISTS"] = []
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    CONFIG.clear()

    for k, v in data.items():
        CONFIG[k] = v

    locales = []
    for entry in data.get("LOCALES", []):
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            l, r = entry
            locales.append((str(l).strip(), str(r).strip().upper()))
        elif isinstance(entry, dict):
            l = entry.get("lang")
            r = entry.get("region")
            if l and r:
                locales.append((str(l).strip(), str(r).strip().upper()))

    CONFIG["LOCALES"] = locales or [("de", "DE")]

    combined = []
    for c in data.get("COMBINED_PLAYLISTS", []):
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        regions = c.get("regions")
        if not name or not isinstance(regions, list):
            continue
        regs = [str(r).strip().upper() for r in regions if isinstance(r, str) and r.strip()]
        if len(regs) >= 2:
            combined.append({
                "name": str(name).strip(),
                "regions": regs
            })

    CONFIG["COMBINED_PLAYLISTS"] = combined

def save_config_to_disk():
    cfg = {}

    for k, v in CONFIG.items():
        if k == "LOCALES":
            cfg["LOCALES"] = [
                [l, r.upper()] for l, r in v
            ]
        elif k == "COMBINED_PLAYLISTS":
            cfg["COMBINED_PLAYLISTS"] = [
                {
                    "name": c["name"],
                    "regions": [r.upper() for r in c["regions"]]
                }
                for c in v
                if len(c.get("regions", [])) >= 2
            ]
        else:
            cfg[k] = v

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def get_locales():
    return list(CONFIG["LOCALES"])
    
def request_refresh(region="*", rebuild=False):
    rg = (region or "*").upper()
    FORCE_REGIONS.append(rg)
    if rebuild:
        REBUILD_REGIONS.append(rg)
    FORCE_REFRESH.set()
   
def build_tvg_id(name: str, region: str) -> str:
    if not isinstance(name, str):
        return ""
    if region.upper() != "DE":
        return name

    base = re.sub(r"[^a-z0-9]", "", name.lower())
    return f"{base}.de"

def remove_plus_unless_timeshift(name: str) -> str:
    if not isinstance(name, str):
        return ""
    return re.sub(r"\+(?!\s*(1|24)\b)", "", name)
    
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_overview_banner():
    print(f"\n{'='*60}")
    print(f"🚀 Vavoo IPTV Proxy Server - Multiprocessing Edition")
    print(f"{'='*60}")

    if CONFIG["RES"]:
        print("🎯 RES MODE ENABLED: highest working resolution will be locked")
        print("⏳ First refresh will wait for FFmpeg resolution pass")

    if CONFIG["FILTER_ENABLED"] and CONFIG.get("FILTER_KEYWORDS"):
        locales = list(CONFIG["LOCALES"])
        first_region = locales[0][1] if locales else "N/A"
        print(f"⚠️  FILTER ACTIVE (only affects first region: {first_region}):")
        for kw in CONFIG["FILTER_KEYWORDS"]:
            print(f"     • '{kw}'")
    else:
        print("✅ Filter disabled - all channels included")

    print(f"{'='*60}")
    print(f"Host: {public_host()}")
    print(f"Port: {public_port()}")
    print(f"Refresh Interval: {REFRESH_INTERVAL // 60} minutes")
    print(f"{'='*60}\n")
   
def res_status():
    total = shared_state.res_expected.value
    done = shared_state.res_done.value
    if total == 0:
        return "idle"
    if done < total:
        return f"in progress ({done}/{total})"
    return "complete"
    
def ensure_playlist_dir():
    os.makedirs(PLAYLIST_DIR, exist_ok=True)

def apply_file_permissions(path):
    try:
        if PLAYLIST_OWNER or PLAYLIST_GROUP:
            uid = pwd.getpwnam(PLAYLIST_OWNER).pw_uid if PLAYLIST_OWNER else -1
            gid = grp.getgrnam(PLAYLIST_GROUP).gr_gid if PLAYLIST_GROUP else -1
            os.chown(path, uid, gid)

        if PLAYLIST_MODE is not None:
            os.chmod(path, PLAYLIST_MODE)

    except PermissionError:
        print(f"⚠️ Permission warning: cannot change owner/mode for {path}")
    except Exception as e:
        print(f"⚠️ Permission error for {path}: {e}")
            
def parse_master_variants(text, base_url):
    variants = []
    lines = text.splitlines()

    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            attrs = dict(re.findall(r'([A-Z\-]+)=([^,]+)', line))
            uri = lines[i + 1].strip()

            res = attrs.get("RESOLUTION", "0x0")
            _, h = map(int, res.split("x"))

            variants.append({
                "url": urljoin(base_url, uri),
                "height": h,
                "fps": int(float(attrs.get("FRAME-RATE", 0))),
                "bandwidth": int(attrs.get("BANDWIDTH", 0)),
            })
    return variants

def ffmpeg_check(m3u8_url):
    try:
        p = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-loglevel", "error",

                "-rw_timeout", str(FFMPEG_READ_TIMEOUT_US),
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "2",

                "-i", m3u8_url,
                "-t", str(FFMPEG_PROBE_SECONDS),

                "-f", "null",
                "-"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=FFMPEG_PROCESS_TIMEOUT
        )
        return p.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False

def canonicalize_channel_name(name: str) -> str:
    if not isinstance(name, str):
        return ""

    s = name.strip()
    low = s.lower()

    if "rtl 2" in low or "rtl zwei" in low:
        return "RTL ZWEI"

    if "ard das erste" in low:
        return "Das Erste"

    if low == "discovery" or low.startswith("discovery "):
        return "Discovery Channel"

    if "history channel" in low:
        return "History"

    if "n24 docu" in low or "n24 doku" in low:
        return "N24 Doku"

    if "kabel 1 doku" in low or "kabel eins doku" in low:
        return "Kabel eins Doku"

    if "spiegel tv wissen" in low or low == "spiegel wissen":
        return "Spiegel Geschichte"
    if "sky nostalgie" in low:
        return "Sky Cinema Classics"
    if "sony axn" in low or low == "axn":
        return "AXN Black"

    if "sony channel" in low:
        return "AXN White"
    if low == "axn" or low.startswith("axn "):
        return "AXN White"

    return s

def channel_main_key(name: str):
	
    if not isinstance(name, str):
        return ("", None)

    s = name.upper()
    
    s = re.sub(r"\s+", " ", s)
    
    m = re.search(r"(.*?)(?:\s+(\d{1,2}))$", s)
    if m:
        base = m.group(1).strip()
        num = int(m.group(2))
        return base, num

    return s.strip(), None

def sort_by_resolution_inside_same_channel(items):
    buckets = []
    index_map = {}

    for item in items:
        key = channel_main_key(item["name"])
        if key not in index_map:
            index_map[key] = len(buckets)
            buckets.append([])

        buckets[index_map[key]].append(item)

    out = []

    for bucket in buckets:
        if len(bucket) == 1:
            out.extend(bucket)
            continue

        def rank(i):
            c = shared_state.res_cache.get(i["id"])
            if not c:
                return 99
            return variant_rank({
                "height": c["height"],
                "fps": c["fps"]
            })

        bucket.sort(key=rank)
        out.extend(bucket)

    return out

def select_best_variant(session_obj, master_url, cid=None):
    try:
        r = session_obj.get(
            master_url,
            timeout=(3, 5),
            allow_redirects=True
        )
        r.raise_for_status()
    except Exception:
        return None

    base = master_url.rsplit("/", 1)[0] + "/"
    lines = r.text.splitlines()
    variants = []
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue

        attrs = dict(re.findall(r'([A-Z\-]+)=([^,]+)', line))
        uri = lines[i + 1].strip() if i + 1 < len(lines) else None
        if not uri:
            continue

        try:
            _, h = map(int, attrs.get("RESOLUTION", "0x0").split("x"))
        except Exception:
            h = 0

        try:
            fps = int(float(attrs.get("FRAME-RATE", 0) or 0))
        except Exception:
            fps = 0

        bw = int(attrs.get("BANDWIDTH", 0) or 0)

        variants.append({
            "url": urljoin(base, uri),
            "height": h,
            "fps": fps,
            "bandwidth": bw,
        })
    if variants:
        variants.sort(key=variant_rank)

        best = variants[0]

        if cid:
            print(
                f"✅ RES OK cid={cid} "
                f"[{best['height']}p {best['fps']}fps]"
            )

        return best
    info = ffprobe_media_info(master_url)

    if info:
        if cid:
            print(
                f"✅ RES OK cid={cid} "
                f"[{info['height']}p {info['fps']}fps]"
            )

        return {
            "url": master_url,
            "height": info["height"],
            "fps": info["fps"],
            "bandwidth": 0,
        }
    if cid:
        print(f"⚠️ RES UNKNOWN cid={cid} [assumed playable]")

    return {
        "url": master_url,
        "height": 0,
        "fps": 0,
        "bandwidth": 0,
    }

def ffprobe_media_info(url):
    cmd = [
        "ffprobe",
        "-v", "error",

        "-rw_timeout", str(FFMPEG_READ_TIMEOUT_US),
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "2",

        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        url,
    ]

    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=FFPROBE_PROCESS_TIMEOUT,
            text=True
        )

        if p.returncode != 0:
            return None

        lines = p.stdout.strip().splitlines()
        if len(lines) < 3:
            return None

        width = int(lines[0])
        height = int(lines[1])

        num, den = lines[2].split("/")
        fps = int(round(float(num) / float(den)))

        return {
            "height": height,
            "fps": fps,
        }

    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None

def apply_special_channel_names(name: str) -> str:
    if not isinstance(name, str):
        return ""

    s = name.strip()
    low = s.lower()

    if "rtl 2" in low or "rtl zwei" in low:
        return "RTL ZWEI"

    if "ard das erste" in low or low == "ard":
        return "Das Erste"

    if "discovery" in low:
        return "Discovery Channel"

    if "history channel" in low:
        return "History"

    if "n24 docu" in low or "n24 doku" in low:
        return "N24 Doku"

    return s

def canonical_channel_key(name: str) -> str:
    if not isinstance(name, str):
        return ""

    n = name.lower()
    n = re.sub(r"\(.*?\)", "", n)
    n = re.sub(r"\[.*?\]", "", n)
    n = re.sub(
        r"\b("
        r"hd|fhd|uhd|sd|4k|hevc|h\.?265|h\.?264|avc|x265|x264"
        r")\b",
        "",
        n,
        flags=re.IGNORECASE
    )
    n = re.sub(r"\s*\+\s*(1|24)?\b", "", n)
    n = re.sub(r"\s*\.\s*[a-z]$", "", n)
    n = re.sub(r"[._\-]+", " ", n)
    n = re.sub(r"\s+", " ", n)

    return n.strip()

def dedup_name_key(name: str) -> str:
    if not isinstance(name, str):
        return ""

    name = remove_plus_unless_timeshift(name)

    n = name.lower()
    n = re.sub(r"\([^)]*\)", "", n)
    n = re.sub(r"\[[^\]]*\]", "", n)
    n = re.sub(r"\s+", " ", n)
    return n.strip()
    
def deduplicate_by_name(items):
    best = {}

    for item in items:
        key = dedup_name_key(item["name"])
        cached = shared_state.res_cache.get(item["id"])

        if not cached:
            continue

        rank = variant_rank({
            "height": cached["height"],
            "fps": cached["fps"],
        })

        if key not in best or rank < best[key]["rank"]:
            best[key] = {"rank": rank, "item": item}

    return [v["item"] for v in best.values()]

def cached_stream_alive(url):
    try:
        r = requests.head(url, timeout=6, allow_redirects=True)
        return r.status_code < 400
    except:
        return False
def apply_res_cache(items):
    out = []

    for item in items:
        cid = item["id"]
        cached = shared_state.res_cache.get(cid)

        if not cached:
            continue

        item["resolved_url"] = cached["url"]
        out.append(item)

    return out

def resolution_worker(queue):
    session = requests.Session()

    try:
        while True:
            try:
                job = queue.get()

                if job is None:
                    return

                cid, master_url = job
                now = time.time()

                try:
                    best = select_best_variant(session, master_url)

                    if best:
                        shared_state.res_cache[cid] = {
                            "url": best["url"],
                            "height": best["height"],
                            "fps": best["fps"],
                            "bandwidth": best["bandwidth"],
                            "last_ok": now,
                        }

                except KeyboardInterrupt:
                    return

                except Exception:
                    pass

                finally:
                    shared_state.res_done.value += 1
                    if shared_state.res_done.value >= shared_state.res_expected.value:
                        RES_READY.set()

            except KeyboardInterrupt:
                return

    except KeyboardInterrupt:
        return
        
def reset_res_state():
    shared_state.res_expected.value = 0
    shared_state.res_done.value = 0
    RES_READY.set()

    try:
        while True:
            RES_QUEUE.get_nowait()
    except:
        pass

def public_host():
    if PUBLIC_HOST:
        return PUBLIC_HOST
    return ip()

def public_port():
    # Return PORT (which is read from environment variable)
    return PORT
    
def decode(r):
    if not r or not getattr(r, "content", None):
        return {}
    if r.content[:2] == b"\x1f\x8b":
        try:
            return json.loads(gzip.decompress(r.content))
        except:
            return {}
    try:
        return r.json()
    except:
        return {}
        
def ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        a = s.getsockname()[0]
        s.close()
        return a
    except:
        return "127.0.0.1"
        
def norm_key(name):
    if not isinstance(name, str):
        return ""
    n = name.upper()
    n = re.sub(r"\bKABEL\s*1\b", "KABEL EINS", n)
    n = re.sub(r"\bPRO\s*7\b", "PROSIEBEN", n)
    n = re.sub(r"\bS\.\s*", "SKY ", n)
    n = re.sub(r"\bSKY\s+BUNDESLIGA\b", "SKY SPORT BUNDESLIGA", n)
    n = re.sub(r"\s*\.[SB C]$", "", n)
    n = re.sub(r"(?:4K|UHD|FHD|HD\+?|SD|HEVC|H\.?265|H\.?264|AVC|ʜᴅ)", "", n)
    n = re.sub(r"\([^)]*\)", "", n)
    n = re.sub(r"[^A-Z0-9]", "", n)
    return n.lower()
    
def clean_display_name(n):
    if not isinstance(n, str):
        return ""

    n = remove_plus_unless_timeshift(n)

    s = n
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(
        r"\b(?:4K|UHD|FHD|HD\+?|SD|HEVC|H\.?265|H\.?264|AVC|ʜᴅ)\b",
        "",
        s,
        flags=re.IGNORECASE
    )
    s = re.sub(r"\s*\.[sb c]$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s)
    s = s.strip()

    s = apply_special_channel_names(s)

    return s
    
def base_name(name):
    if not isinstance(name, str):
        return ""
    n = name.upper()
    n = re.sub(r"\bKABEL\s*1\b", "KABEL EINS", n)
    n = re.sub(r"\bPRO\s*7\b", "PROSIEBEN", n)
    n = re.sub(r"\bS\.\s*SPORT\b", "SKY SPORT", n)
    n = re.sub(r"\bS\.\s*", "SKY ", n)
    n = re.sub(r"\bSKY\s+BUNDESLIGA\b", "SKY SPORT BUNDESLIGA", n)
    n = re.sub(r"\s*\.[SB C]$", "", n)
    n = re.sub(r"(?:4K|UHD|FHD|HD\+?|SD|HEVC|H\.?265|H\.?264|AVC|ʜᴅ)", "", n)
    n = re.sub(r"\[[^\]]*\]", "", n)
    n = re.sub(r"\([^)]*\)", "", n)
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    n = re.sub(r"\s+\d+\s*$", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n
    
def resolve_iptv(session_obj, url, language, region):
    p = {"language": language, "region": region, "url": url, "clientVersion": "3.0.2"}
    try:
        r = decode(session_obj.post(RESOLVE_URL, json=p, headers=dict(shared_state.common_headers), timeout=6))
        return r[0]["url"] if r else None
    except Exception as e:
        print(f"Resolve error: {e}")
        return None
        
def canon(s: str) -> str:
    s = s.lower()
    s = re.sub(r"(^|[^a-z0-9])s[\.\-\s]+sport([^a-z0-9]|$)", r"\1skysport\2", s)
    s = re.sub(r"\s*[+-]\s*\d*", "", s)
    s = re.sub(r"(hd|uhd|4k)$", "", s)
    s = s.replace("&", "and")
    s = re.sub(r"[^a-z0-9]", "", s)
    return s
    
def build_logo_index(path="logos.txt"):
    index = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                fn = line.strip()
                if fn.endswith(".png"):
                    index[canon(fn[:-4])] = fn
    except FileNotFoundError:
        pass
    return index
    
LOGO_INDEX = build_logo_index("logos.txt")

def resolve_logo_for_channel(name: str) -> str:
    key = canon(name)
    if key == "sky1" and "skyone" in LOGO_INDEX:
        return LOGO_INDEX["skyone"]
    if key in LOGO_INDEX:
        return LOGO_INDEX[key]
    if f"{key}hd" in LOGO_INDEX:
        return LOGO_INDEX[f"{key}hd"]
    specials = {
        "kabel1": "kabeleins",
        "kabel1classics": "kabeleinsclassics",
        "geotelevision": "geotv",
        "spiegelgeschichte": "spiegeltvgeschichte",
    }
    if key in specials:
        k = specials[key]
        if k in LOGO_INDEX:
            return LOGO_INDEX[k]
        if f"{k}hd" in LOGO_INDEX:
            return LOGO_INDEX[f"{k}hd"]
    m = re.match(r"skybundesliga(\d{1,2})$", key)
    if m:
        k = f"skysportbundesliga{m.group(1)}"
        if k in LOGO_INDEX:
            return LOGO_INDEX[k]
        if f"{k}hd" in LOGO_INDEX:
            return LOGO_INDEX[f"{k}hd"]
    if key.endswith("f1") and "skysportf1" in LOGO_INDEX:
        return LOGO_INDEX["skysportf1"]
    raise KeyError(f"NO LOGO FOUND for: {name}")
    
def get_addon_signature():
    session_obj = requests.Session()
    session_obj.headers.update(HEADERS)
    try:
        session_obj.get(GEOIP_URL, timeout=8).raise_for_status()
    except Exception as e:
        print(f"Warning: GEOIP check failed: {e}")
    uid = str(uuid.uuid4())
    ts = int(time.time() * 1000)
    init = {
        "reason": "app-focus",
        "locale": LANGUAGE,
        "theme": "dark",
        "metadata": {
            "device": {"type": "desktop", "uniqueId": uid},
            "os": {"name": "win32", "version": "Windows 10 Pro", "abis": ["x64"], "host": "Lenovo"},
            "app": {"platform": "electron"},
            "version": {"package": "tv.vavoo.app", "binary": "3.1.8", "js": "3.1.8"},
        },
        "appFocusTime": 0,
        "playerActive": False,
        "playDuration": 0,
        "devMode": False,
        "hasAddon": True,
        "castConnected": False,
        "package": "tv.vavoo.app",
        "version": "3.1.8",
        "process": "app",
        "firstAppStart": ts,
        "lastAppStart": ts,
        "ipLocation": None,
        "adblockEnabled": True,
        "proxy": {"supported": ["ss"], "engine": "Mu", "enabled": False, "autoServer": True},
        "iap": {"supported": False},
    }
    try:
        addon_sig = decode(session_obj.post(PING_URL, json=init, timeout=8)).get("addonSig")
        if not addon_sig:
            raise RuntimeError("Failed to get addonSig from Vavoo API")
        common_headers = {
            "content-type": "application/json; charset=utf-8",
            "mediahubmx-signature": addon_sig,
            "user-agent": "MediaHubMX/2",
            "accept": "*/*",
            "Accept-Language": LANGUAGE,
            "Accept-Encoding": "gzip, deflate",
            "Connection": "close",
        }
        return session_obj, addon_sig, common_headers
    except Exception as e:
        print(f"Error getting addon signature: {e}")
        raise
        
def fetch_catalog(session_obj, language, region):
    items_list = []
    cursor = None

    while True:
        payload = {
            "language": language,
            "region": region,
            "catalogId": "iptv",
            "id": "iptv",
            "adult": False,
            "search": "",
            "sort": "",
            "filter": {},
            "cursor": cursor,
            "clientVersion": "3.0.2",
        }

        try:
            data = decode(
                session_obj.post(
                    CATALOG_URL,
                    json=payload,
                    headers=dict(shared_state.common_headers),
                    timeout=8
                )
            )
        except Exception as e:
            print(f"Error fetching catalog: {e}")
            break

        for item in data.get("items", []):
            if item.get("type") != "iptv":
                continue

            raw_name = item.get("name", "")
            fixed_name = canonicalize_channel_name(raw_name)

            items_list.append({
                "id": item["ids"]["id"],
                "url": item["url"],
                "name": fixed_name,                
                "_key": norm_key(fixed_name),    
                "_base": base_name(fixed_name),   
                "group": "",
                "resolved_url": None,
            })

        cursor = data.get("nextCursor")
        if cursor is None:
            break

    return items_list
    
def group_channels(items_list, region):
    if region.upper() != "DE":
        return items_list

    ref_map = {}
    ref_order = []
    for g in REF_DATA["groups"]:
        for ch in g["channels"]:
            k = norm_key(ch["channel"])
            ref_map[k] = g["group-title"]
            ref_order.append(k)

    base_count = defaultdict(int)
    for i in items_list:
        if i["_base"]:
            base_count[i["_base"]] += 1

    def special_group(name):
        if not isinstance(name, str):
            return None
        up = name.upper()
        up = re.sub(r"\bKABEL\s*1\b", "KABEL EINS", up)
        up = re.sub(r"\bS\.\s*SPORT\b", "SKY SPORT", up)
        up = re.sub(r"\bS\.\s*", "SKY ", up)
        if re.match(r"^(WDR|MDR|NDR|RBB|RBW)\b", up):
            return "OeR"
        if re.search(r"\bRTL\s*NITRO\b", up):
            return "Private"
        if re.match(r"\b(BR|BR\s+TV)\b", up):
            return "OeR"
        if up.startswith("EURONEWS"):
            return "Sport"
        if re.match(r"^SWR\b", up):
            return "OeR"
        if up.startswith("WELT"):
            return "OeR"
        if up.startswith("SKY PREMIEREN"):
            return "Sky"
        if "EUROSPORT" in up:
            return "Sport"
        if re.search(r"\bSERVUS\s*TV\b", up):
            return "Private"
        if up.startswith("BLUETV"):
            return "BLUETV"
        if re.search(r"\bSILVERLINE\b", up):
            return "Sky"
        if re.match(r"\bSKY\s*\d+\b", up):
            return "Sky"
        if re.search(r"\bSKY\s*(BEST\s*OF|BEST)\b", up):
            return "Sky"
        if re.search(r"\bSKY\s*BUNDESLIGA\d+\b", up):
            return "Bundesliga"
        if re.search(r"\bSKY\s*(CLASSICS|COMEDY|FAMILY|FUN|HITS|SPECIAL|THRILLER)\b", up):
            return "Sky"
        if re.search(r"\bSKY\s*SERIEN\s*&?\s*SHOWS\b", up):
            return "Sky"
        if up.startswith("SKY BOX"):
            return "Sky"
        if up.startswith("SKY CINEMA"):
            return "Sky"
        if up.startswith("TNT"):
            return "Sky"
        if up.startswith("WARNER"):
            return "Sky"
        if "SKY SELECT" in up:
            return "Sky Select"
        if "SKY SPORT BUNDESLIGA" in up or re.search(r"\bSKY\s+BUNDESLIGA\b", up):
            return "Bundesliga"
        if re.search(r"\bDB\s+LIGA\b", up):
            return "DB LIGA"
        if up.startswith("DAZN") or "DAZN SPORT" in up:
            return "Dazn"
        if up.startswith("SKY SPORT"):
            return "Sport"
        if "SPORT DIGITAL" in up or "SPORTDIGITAL" in up:
            return "Sport"
        if "MOTOR" in up or "AUTO" in up:
            return "Sport"
        if "NAT GEO" in up:
            return "Doku"
        if "SPIEGEL" in up:
            return "Doku"
        return None

    ordered = []
    used = set()

    for k in ref_order:
        for i in items_list:
            if i["_key"] == k and i["id"] not in used:
                i["group"] = ref_map[k]
                ordered.append(i)
                used.add(i["id"])

    for i in items_list:
        if i["id"] in used:
            continue
        sg = special_group(i["name"])
        if sg:
            i["group"] = sg
        elif base_count.get(i["_base"], 0) >= 5:
            i["group"] = i["_base"]
        else:
            i["group"] = "Germany"
        ordered.append(i)

    return ordered

def parse_filter_config(keywords_list):
    filter_keywords = []
    group_mappings = {}
    for item in keywords_list:
        if not item or not isinstance(item, str):
            continue
        if ':' in item:
            kw, gt = item.split(':', 1)
            kw = kw.strip().lower()
            gt = gt.strip()
            filter_keywords.append(kw)
            group_mappings[kw] = gt
        else:
            filter_keywords.append(item.strip().lower())
    return filter_keywords, group_mappings
    
def apply_filter_to_first_region(items_list, region):
    if not CONFIG.get("FILTER_ENABLED", False):
        return items_list

    locales = list(CONFIG.get("LOCALES", []))
    if not locales:
        return items_list

    first_region = locales[0][1].upper()
    if region.upper() != first_region:
        return items_list

    keywords = list(CONFIG.get("FILTER_KEYWORDS", []))
    if not keywords:
        return []  # filter enabled but no keywords → EMPTY playlist

    filter_keywords, group_mappings = parse_filter_config(keywords)

    out = []
    for item in items_list:
        name = (item.get("name") or "").lower()
        matched = None
        for kw in filter_keywords:
            if kw in name:
                matched = kw
                break
        if not matched:
            continue

        if matched in group_mappings:
            item["group"] = group_mappings[matched]

        out.append(item)

    return out
    
def pre_resolve_urls(session_obj, items, language, region):
    def resolve_one(item):
        try:
            url = resolve_iptv(session_obj, item["url"], language, region)
            return item["id"], url
        except:
            return item["id"], None

    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(resolve_one, item): item for item in items}
        for f in as_completed(futures):
            item = futures[f]
            cid, resolved = f.result()
            item["resolved_url"] = resolved
            if CONFIG["RES"] and resolved:
                RES_QUEUE.put((cid, resolved))

    return items

def variant_rank(v):
    if v["height"] == 1080 and v["fps"] == 50:
        return 0
    if v["height"] == 720 and v["fps"] == 50:
        return 1
    if v["height"] == 1080 and v["fps"] == 25:
        return 2
    if v["height"] == 720 and v["fps"] == 25:
        return 3
    return 4

def save_tv_playlist_external(region, items):
    host = public_host()
    output = "#EXTM3U\n"

    region_name = REGION_NAMES.get(region.upper(), region.upper())

    for item in items:
        if not item.get("group"):
            item["group"] = region_name

        name = clean_display_name(item["name"])
        name = map_channel(name)

        tvg_id = build_tvg_id(name, region)
        tvg_id = map_tvg_id(tvg_id)

        tvg_name = map_tvg_name(name)

        mapped_logo = map_tvg_logo(name)

        if mapped_logo != name:
            logo_file = mapped_logo
        else:
            logo_file = (
                re.sub(r"[^a-z0-9]", "", name.lower())
                + ".png"
            )

        logo_url = f"http://{host}:{PORT}/logos/{logo_file}"

        output += (
            f'#EXTINF:-1 '
            f'tvg-id="{tvg_id}" '
            f'tvg-name="{tvg_name}" '
            f'tvg-logo="{logo_url}" '
            f'group-title="{item["group"]}",{name}\n'
        )

        output += (
            f"http://{host}:{PORT}/vavoo?"
            f"channel={item['id']}&region={region}\n"
        )

    filename = f"vavoo_playlist_{region}.m3u"
    path = os.path.join(PLAYLIST_DIR, filename) if PLAYLIST_DIR else filename

    if PLAYLIST_DIR:
        os.makedirs(PLAYLIST_DIR, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        f.write(output)

    apply_file_permissions(path)

def extract_channel_number(name: str):
    if not name:
        return None
    m = re.search(r'\b(\d{1,2})\b', name)
    if not m:
        return None

    num = int(m.group(1))
    if num in (1, 24) and "+" in name:
        return None

    return num

def sort_by_resolution_and_number(items):
    def sort_key(item):
        cached = shared_state.res_cache.get(item["id"], {})
        height = cached.get("height", 0)
        fps = cached.get("fps", 0)
        res_rank = variant_rank({
            "height": height,
            "fps": fps
        })

        name = item.get("name", "")
        num = extract_channel_number(name)
        if num is not None:
            return (res_rank, num, name.lower())
        return (res_rank, 999, name.lower())

    return sorted(items, key=sort_key)

def main_channel_name(name: str) -> str:
    if not isinstance(name, str):
        return ""

    s = name.lower()
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\[.*?\]", "", s)
    s = re.sub(r"\b(hd|fhd|uhd|sd|4k|hevc|h\.?265|h\.?264|avc|x265|x264)\b", "", s, flags=re.I)
    s = re.sub(r"\s*\+\s*\d+\b", "", s)
    s = re.sub(r"(bundesliga)(\d{1,2})\b", r"\1 \2", s)
    s = re.sub(r"\b\d{1,2}\b", "", s)
    s = re.sub(r"[._\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    return s
def sort_channels_grouped(items):
    def res_rank_for_item(item):
        cached = shared_state.res_cache.get(item["id"]) or {}
        return variant_rank({
            "height": cached.get("height", 0),
            "fps": cached.get("fps", 0),
        })

    def sort_key(item):
        name = item.get("name", "")
        main = main_channel_name(name)
        num = extract_real_channel_number(name)
        num_key = num if num is not None else 999
        rr = res_rank_for_item(item)

        return (main, num_key, rr, name.lower())

    return sorted(items, key=sort_key)

def extract_real_channel_number(name: str):
    if not isinstance(name, str):
        return None

    s = name.lower()
    s2 = re.sub(r"\s*\+\s*\d+\b", "", s)
    s2 = re.sub(r"(bundesliga)(\d{1,2})\b", r"\1 \2", s2)

    m = re.search(r"\b(\d{1,2})\b", s2)
    if not m:
        return None
    return int(m.group(1))

def consume_refresh_request():
    regions = []
    rebuild_set = set()

    while len(FORCE_REGIONS) > 0:
        regions.append(FORCE_REGIONS.pop(0))

    while len(REBUILD_REGIONS) > 0:
        rebuild_set.add(REBUILD_REGIONS.pop(0))

    if not regions:
        return None, rebuild_set

    if "*" in regions or "*" in rebuild_set:
        all_regions = set(r for _, r in CONFIG.get("LOCALES", []))
        for c in CONFIG.get("COMBINED_PLAYLISTS", []):
            for r in c.get("regions", []):
                all_regions.add(r.upper())
        return list(all_regions), set(all_regions)

    uniq = []
    seen = set()
    for r in regions:
        r = (r or "").upper()
        if r and r not in seen:
            uniq.append(r)
            seen.add(r)

    return uniq, rebuild_set

def refresh_worker():
    global LANGUAGE, REGION

    try:
        while True:
            try:
                session_obj, addon_sig, common_headers = get_addon_signature()
                shared_state.addon_sig.value = addon_sig
                shared_state.common_headers.clear()
                shared_state.common_headers.update(common_headers)

                if FORCE_REFRESH.is_set():
                    regions_to_refresh, rebuild_set = consume_refresh_request()
                    FORCE_REFRESH.clear()
                    if not regions_to_refresh:
                        time.sleep(1)
                        continue
                else:
                    regions = set(r for _, r in CONFIG.get("LOCALES", []))
                    for c in CONFIG.get("COMBINED_PLAYLISTS", []):
                        for r in c.get("regions", []):
                            regions.add(r.upper())
                    regions_to_refresh = list(regions)
                    rebuild_set = set()

                locales_map = {}
                for l, r in CONFIG.get("LOCALES", []):
                    locales_map[r.upper()] = (l, r.upper())

                for c in CONFIG.get("COMBINED_PLAYLISTS", []):
                    for r in c.get("regions", []):
                        rr = r.upper()
                        if rr not in locales_map:
                            locales_map[rr] = (rr.lower(), rr)

                refreshed_regions = set()

                for region in regions_to_refresh:
                    region = region.upper()
                    if region not in locales_map:
                        continue

                    language, region = locales_map[region]
                    shared_state.refresh_in_progress[region] = True

                    try:
                        LANGUAGE = language
                        REGION = region
                        shared_state.common_headers["Accept-Language"] = language

                        forced_rebuild = region in rebuild_set
                        rebuild = (
                            forced_rebuild
                            or CONFIG.get("PLAYLIST_REBUILD_ON_START", True)
                            or region not in shared_state.items_by_region
                        )

                        if rebuild:
                            items = fetch_catalog(session_obj, language, region)
                            items = group_channels(items, region)
                            items = apply_filter_to_first_region(items, region)
                        else:
                            items = list(shared_state.items_by_region.get(region, []))

                        items = pre_resolve_urls(session_obj, items, language, region)

                        if CONFIG.get("RES", False):
                            enqueued = 0
                            for item in items:
                                if item.get("resolved_url"):
                                    RES_QUEUE.put((item["id"], item["resolved_url"]))
                                    enqueued += 1

                            shared_state.res_expected.value = enqueued
                            shared_state.res_done.value = 0
                            RES_READY.clear()

                            if enqueued:
                                start = time.time()
                                while not RES_READY.is_set():
                                    if not CONFIG.get("RES", False):
                                        break
                                    if time.time() - start > 300:
                                        break
                                    time.sleep(0.2)

                                for item in items:
                                    cached = shared_state.res_cache.get(item["id"])
                                    if cached:
                                        item["resolved_url"] = cached["url"]

                        shared_state.items_by_region[region] = items
                        shared_state.last_refresh[region] = time.time()
                        refreshed_regions.add(region)

                        if any(r == region for _, r in CONFIG.get("LOCALES", [])):
                            save_tv_playlist_external(region, items)

                    except Exception as e:
                        print(f"❌ Refresh failed for {region}: {e}", flush=True)

                    finally:
                        shared_state.refresh_in_progress[region] = False
                        time.sleep(0.3)

                for combo in CONFIG.get("COMBINED_PLAYLISTS", []):
                    cregions = [r.upper() for r in combo.get("regions", [])]
                    if len(cregions) < 2:
                        continue

                    name = combo.get("name") or "_".join(cregions)
                    filename = f"vavoo_playlist_{name}.m3u"
                    path = os.path.join(PLAYLIST_DIR, filename) if PLAYLIST_DIR else filename

                    has_data = any(shared_state.items_by_region.get(r) for r in cregions)
                    if not has_data:
                        continue

                    needs_rebuild = (
                        not os.path.exists(path)
                        or set(cregions) & refreshed_regions
                        or (
                            os.path.exists(path)
                            and (time.time() - os.path.getmtime(path)) > (REFRESH_INTERVAL + 120)
                        )
                    )

                    if needs_rebuild:
                        save_combined_playlist(cregions)

            except KeyboardInterrupt:
                return

            wait = REFRESH_INTERVAL
            while wait > 0:
                if FORCE_REFRESH.is_set():
                    break
                time.sleep(1)
                wait -= 1

    except KeyboardInterrupt:
        return

def pre_fetch_manifests(session_obj, items_list):
    def fetch_manifest(item):
        if not item.get("resolved_url"):
            return item["id"], None
        try:
            r = session_obj.get(item["resolved_url"], timeout=8, headers=HEADERS)
            r.raise_for_status()
            return item["id"], r.text
        except:
            return item["id"], None
    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_item = {executor.submit(fetch_manifest, item): item for item in items_list}
        for future in as_completed(future_to_item):
            cid, manifest = future.result()
            for i in items_list:
                if i["id"] == cid:
                    i["manifest_cache"] = manifest
                    break
    return items_list
    

app = Flask(__name__)
app.secret_key = os.urandom(32)
SEGMENT_SESSION = requests.Session()
SEGMENT_SESSION.headers.update({
    "User-Agent": HEADERS["user-agent"],
    "Accept": "*/*"
})
adapter = requests.adapters.HTTPAdapter(
    pool_connections=30,
    pool_maxsize=150,
    max_retries=2,
    pool_block=False
)
SEGMENT_SESSION.mount('http://', adapter)
SEGMENT_SESSION.mount('https://', adapter)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            error = "Username and password required"
        else:
            stored_user = CONFIG.get("WEB_USER", "")
            stored_hash = CONFIG.get("WEB_PASS_HASH", "")

            # ───── FIRST LOGIN: CREATE USER ─────
            if not stored_user or not stored_hash:
                CONFIG["WEB_USER"] = username
                CONFIG["WEB_PASS_HASH"] = generate_password_hash(password)
                save_config_to_disk()

                session["logged_in"] = True
                session["user"] = username
                return redirect("/")

            # ───── NORMAL LOGIN ─────
            if (
                username == stored_user
                and check_password_hash(stored_hash, password)
            ):
                session["logged_in"] = True
                session["user"] = username
                return redirect("/")

            error = "Invalid username or password"

    return f"""
    <html>
    <head>
        <title>Vavoo Login</title>
        <style>
            body {{
                font-family: sans-serif;
                background:#111;
                color:#fff;
                display:flex;
                align-items:center;
                justify-content:center;
                height:100vh;
            }}
            form {{
                background:#222;
                padding:30px;
                border-radius:8px;
                width:320px;
            }}
            input {{
                width:100%;
                padding:10px;
                margin:10px 0;
            }}
            button {{
                width:100%;
                padding:10px;
                background:#667eea;
                color:#fff;
                border:none;
                cursor:pointer;
                font-weight:700;
            }}
            .err {{ color:#ff6b6b; }}
            .hint {{ font-size:12px; opacity:.7; margin-top:10px; }}
        </style>
    </head>
    <body>
        <form method="post">
            <h2>🔐 Vavoo Login</h2>
            {"<p class='err'>" + error + "</p>" if error else ""}
            <input name="username" placeholder="Username">
            <input name="password" type="password" placeholder="Password">
            <button type="submit">Login</button>
            <div class="hint">
                First login creates credentials if none exist.
            </div>
        </form>
    </body>
    </html>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/static/<path:filename>")
def serve_static(filename):
    """Serve static files (CSS, JS, images) for MacReplayXC theme integration."""
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    return send_from_directory(static_dir, filename)
    
@app.route("/api/config", methods=["GET"])
@login_required
def api_get_config():
    return {
        "RES": bool(CONFIG.get("RES", False)),
        "PLAYLIST_REBUILD_ON_START": bool(CONFIG.get("PLAYLIST_REBUILD_ON_START", True)),
        "FILTER_ENABLED": bool(CONFIG.get("FILTER_ENABLED", False)),
        "FILTER_KEYWORDS": list(CONFIG.get("FILTER_KEYWORDS", [])),
        "STREAM_MODE": bool(CONFIG.get("STREAM_MODE", True)),
        "LOCALES": [
            {"lang": l, "region": r}
            for l, r in list(CONFIG.get("LOCALES", []))
        ],
        "COMBINED_PLAYLISTS": list(CONFIG.get("COMBINED_PLAYLISTS", [])),
    }

@app.route("/api/config", methods=["POST"])
@login_required
def api_set_config():
    data = request.json or {}

    if "RES" in data:
        new_res = bool(data["RES"])
        old_res = bool(CONFIG.get("RES", False))
        CONFIG["RES"] = new_res

        if new_res and not old_res:
            shared_state.res_expected.value = 0
            shared_state.res_done.value = 0
            RES_READY.set()
            try:
                while True:
                    RES_QUEUE.get_nowait()
            except:
                pass

            workers = min(4, multiprocessing.cpu_count())
            for _ in range(workers):
                p = multiprocessing.Process(
                    target=resolution_worker,
                    args=(RES_QUEUE,),
                    daemon=True
                )
                p.start()

    if "PLAYLIST_REBUILD_ON_START" in data:
        CONFIG["PLAYLIST_REBUILD_ON_START"] = bool(data["PLAYLIST_REBUILD_ON_START"])

    if "FILTER_ENABLED" in data:
        CONFIG["FILTER_ENABLED"] = bool(data["FILTER_ENABLED"])

    if "FILTER_KEYWORDS" in data:
        CONFIG["FILTER_KEYWORDS"] = [
            x.strip() for x in data["FILTER_KEYWORDS"]
            if isinstance(x, str) and x.strip()
        ]

    if "STREAM_MODE" in data:
        CONFIG["STREAM_MODE"] = bool(data["STREAM_MODE"])

    new_combined = []
    for c in data.get("COMBINED_PLAYLISTS", []):
        name = c.get("name")
        regions = [r.upper() for r in c.get("regions", []) if r]
        if name and len(regions) >= 2:
            new_combined.append({
                "name": name,
                "regions": regions
            })

    new_locales = []
    for x in data.get("LOCALES", []):
        lang = (x.get("lang") or "").strip()
        region = (x.get("region") or "").strip().upper()
        if lang and region:
            new_locales.append((lang, region))

    seen = set()
    uniq_locales = []
    for l, r in new_locales:
        if r not in seen:
            uniq_locales.append((l, r))
            seen.add(r)

    seen = set()
    uniq_combined = []
    for c in new_combined:
        if c["name"] not in seen:
            uniq_combined.append(c)
            seen.add(c["name"])

    CONFIG["LOCALES"] = uniq_locales
    CONFIG["COMBINED_PLAYLISTS"] = uniq_combined

    save_config_to_disk()
    return {"status": "ok"}

@app.route("/api/rebuild", methods=["POST"])
def api_rebuild():
    for _, region in list(CONFIG.get("LOCALES", [])):
        shared_state.items_by_region.pop(region, None)
        shared_state.last_refresh.pop(region, None)
        shared_state.refresh_in_progress[region] = False

    FORCE_REFRESH.set()

    return {"status": "rebuild scheduled"}

@app.route("/api/refresh/*", methods=["POST"])
def api_refresh_all_star():
    request_refresh("*", rebuild=False)
    return {"status": "refresh scheduled", "region": "*"}


@app.route("/logos/<path:filename>")
def logos(filename):
    logo_dir = "logos"
    if not os.path.exists(logo_dir):
        os.makedirs(logo_dir)
    return send_from_directory(logo_dir, filename)
    
@app.route("/vavoo")
def vavoo():
    cid = request.args.get("channel")
    region = request.args.get("region")

    if not cid or not region:
        abort(400)

    region = region.upper()
    items = shared_state.items_by_region.get(region)
    if not items:
        abort(503)

    req_item = next((x for x in items if x["id"] == cid), None)
    if not req_item:
        abort(404)

    def fk(i):
        return canonical_channel_key(clean_display_name(i["name"]))

    def alive(url):
        try:
            r = requests.get(
                url,
                timeout=(1.2, 1.2),
                stream=True,
                headers={
                    "User-Agent": HEADERS["user-agent"],
                    "Accept": "*/*",
                }
            )
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=256):
                if chunk:
                    return True
            return False
        except:
            return False

    cache_key = (region, fk(req_item))
    now = time.time()

    item = None
    u = None

    cached = FALLBACK_CACHE.get(cache_key)
    if cached and now - cached["ts"] < FALLBACK_TTL:
        item = cached["item"]
        u = item.get("resolved_url")
    else:
        for cand in items:
            if not cand.get("resolved_url"):
                continue
            if fk(cand) != fk(req_item):
                continue
            ru = cand.get("resolved_url")
            if alive(ru):
                FALLBACK_CACHE[cache_key] = {
                    "item": cand,
                    "ts": now
                }
                item = cand
                u = ru
                break

    if not u:
        abort(503)

    try:
        r = requests.get(
            u,
            timeout=6,
            headers={
                "User-Agent": HEADERS["user-agent"],
                "Accept": "*/*",
                "Accept-Language": LANGUAGE,
            }
        )
        r.raise_for_status()
        text = r.text
    except:
        abort(502)

    ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0]
        or request.remote_addr
    )

    now = time.time()
    channel_name = clean_display_name(item["name"])
    mode = "proxy" if CONFIG.get("STREAM_MODE", True) else "direct"

    old = shared_state.connections.get(ip)
    shared_state.connections[ip] = {
        "ip": ip,
        "region": region,
        "channel": channel_name,
        "mode": mode,
        "connected_at": old["connected_at"] if old else now,
        "last_seen": now,
        "last_segment": old.get("last_segment") if old else None,
    }

    base = u.rsplit("/", 1)[0] + "/"
    host = public_host()

    patched = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            patched.append(line)
        else:
            abs_url = urljoin(base, line)
            if mode == "proxy":
                patched.append(f"http://{host}:{public_port()}/segment?u={abs_url}")
            else:
                patched.append(abs_url)

    resp = Response(
        "\n".join(patched),
        mimetype="application/vnd.apple.mpegurl"
    )
    resp.headers["X-Vavoo-CID"] = item["id"]
    return resp


@app.route("/api/connections")
def api_connections():
    now = time.time()
    out = []

    for ip, c in list(shared_state.connections.items()):
        mode = c.get("mode", "proxy")

        if mode == "proxy":
            ref = c.get("last_segment") or c["last_seen"]
        else:
            ref = c["last_seen"]

        delta = now - ref
        if delta > CONNECTION_TIMEOUT:
            shared_state.connections.pop(ip, None)
            continue

        idle = 0
        if delta > SEGMENT_GRACE:
            idle = int(delta - SEGMENT_GRACE)

        out.append({
            "ip": ip,
            "region": c["region"],
            "channel": c["channel"],
            "mode": mode.upper(),
            "connected": int(now - c["connected_at"]),
            "idle": idle,
        })

    return {"connections": out}

@app.route("/vavoo_variant")
def vavoo_variant():
    u = request.args.get("u")
    if not u:
        abort(400)

    is_playlist = u.lower().endswith(".m3u8")

    try:
        r = requests.get(
            u,
            stream=not is_playlist,
            timeout=6,
            headers={
                "User-Agent": HEADERS["user-agent"],
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "Accept-Language": LANGUAGE,
            }
        )
        r.raise_for_status()
    except:
        abort(502)

    if not is_playlist:
        return Response(
            r.iter_content(chunk_size=8192),
            status=r.status_code,
            content_type="video/mp2t",
            headers={
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": "*"
            }
        )

    text = r.text
    base = u.rsplit("/", 1)[0] + "/"

    patched = []
    for line in text.splitlines():
        s = line.strip()

        if not s or s.startswith("#"):
            patched.append(line)
            continue

        if s.startswith(("http://", "https://")):
            patched.append(
                f"http://{public_host()}:{public_port()}/vavoo_variant?u={s}"
            )
        else:
            patched.append(
                f"http://{public_host()}:{public_port()}/vavoo_variant?u={urljoin(base, s)}"
            )

    return Response(
        "\n".join(patched),
        mimetype="application/vnd.apple.mpegurl"
    )

@app.route("/segment")
def segment():
    url = request.args.get("u")
    if not url or not url.startswith(("http://", "https://")):
        abort(400)

    ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0]
        or request.remote_addr
    )

    now = time.time()
    if ip in shared_state.connections:
        c = shared_state.connections[ip]
        c["last_seen"] = now
        c["last_segment"] = now

    try:
        r = SEGMENT_SESSION.get(url, stream=True, timeout=(2, 8))
        r.raise_for_status()

        def generate():
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        return Response(
            generate(),
            status=r.status_code,
            content_type=r.headers.get("Content-Type", "video/mp2t"),
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    except requests.exceptions.Timeout:
        abort(504)
    except:
        abort(502)
        
@app.route("/playlist/<region>.m3u")
def playlist_region(region):
    region = region.upper()

    valid_regions = [r for _, r in CONFIG["LOCALES"]]
    if region not in valid_regions:
        abort(404, description="Unknown region")

    last_update = shared_state.last_refresh.get(region, 0)
    if not last_update:
        abort(503, description="Playlist not generated yet")

    if (time.time() - last_update) > (REFRESH_INTERVAL + 120):
        abort(503, description="Playlist stale")

    filename = f"vavoo_playlist_{region}.m3u"
    path = os.path.join(PLAYLIST_DIR, filename) if PLAYLIST_DIR else filename

    if not os.path.exists(path):
        abort(500, description="Playlist file missing")

    return Response(
        open(path, "r", encoding="utf-8").read(),
        mimetype="application/x-mpegURL"
    )
@app.route("/health")
def health():
    total = sum(len(shared_state.items_by_region.get(r, [])) for _, r in get_locales())
    resolved = sum(
        sum(1 for i in shared_state.items_by_region.get(r, []) if i.get("resolved_url"))
        for _, r in get_locales()
    )
    return Response(
        f"OK\nChannels: {total}\nResolved: {resolved}\n",
        status=200,
        mimetype="text/plain"
    )

@app.route("/stats")
def stats():
    total = sum(len(shared_state.items_by_region.get(r, [])) for _, r in get_locales())
    resolved = sum(
        sum(1 for i in shared_state.items_by_region.get(r, []) if i.get("resolved_url"))
        for _, r in get_locales()
    )
    by_group = defaultdict(int)

    for _, region in get_locales():
        for i in shared_state.items_by_region.get(region, []):
            by_group[i["group"]] += 1

    stats_text = f"Vavoo Proxy Statistics\n"
    stats_text += f"{'='*40}\n"
    stats_text += f"Total Channels: {total}\n"
    stats_text += f"Resolved URLs: {resolved}\n"
    stats_text += f"Resolution Scan: {res_status()}\n"

    for group, count in sorted(by_group.items()):
        stats_text += f"{group}: {count}\n"

    return Response(stats_text, status=200, mimetype="text/plain")
@app.route("/api/refresh/<region>", methods=["POST"])
def api_refresh_region(region):
    region = region.upper()
    request_refresh(region, rebuild=False)
    return {"status": "refresh scheduled", "region": region}

@app.route("/api/rebuild/<region>", methods=["POST"])
def api_rebuild_region(region):
    region = region.upper()
    shared_state.items_by_region.pop(region, None)
    shared_state.last_refresh.pop(region, None)
    request_refresh(region, rebuild=True)

    return {"status": "rebuild scheduled", "region": region}
    
@app.route("/api/status", methods=["GET"])
def api_status():
    now = time.time()
    regions = []

    locales = list(CONFIG.get("LOCALES", []))
    combined = list(CONFIG.get("COMBINED_PLAYLISTS", []))

    for lang, region in locales:
        region = region.upper()

        items = list(shared_state.items_by_region.get(region, []))
        last_update_ts = float(shared_state.last_refresh.get(region, 0) or 0)
        refreshing = bool(shared_state.refresh_in_progress.get(region, False))

        total = len(items)
        resolved = sum(1 for i in items if i.get("resolved_url"))

        if last_update_ts > 0:
            age_seconds = int(now - last_update_ts)
            age = f"{age_seconds//60}m {age_seconds%60}s"
            if age_seconds < (REFRESH_INTERVAL + 120):
                status_icon, status_text, status_class = "✅", "FRESH", "status-fresh"
            else:
                status_icon, status_text, status_class = "⚠️", "STALE", "status-stale"
        else:
            age = "never"
            status_icon, status_text, status_class = "❌", "NO DATA", "status-error"

        if refreshing:
            status_icon, status_text, status_class = "🔄", "REFRESHING", "status-refreshing"

        filename = f"vavoo_playlist_{region}.m3u"
        path = os.path.join(PLAYLIST_DIR, filename) if PLAYLIST_DIR else filename
        exists = os.path.exists(path)
        size = f"{os.path.getsize(path)/1024:.1f} KB" if exists else "N/A"

        regions.append({
            "lang": lang,
            "region": region,
            "channels": total,
            "resolved": resolved,
            "age": age,
            "status_icon": status_icon,
            "status_text": status_text,
            "status_class": status_class,
            "exists": exists,
            "size": size
        })

    for c in combined:
        name = c.get("name")
        cregions = [r.upper() for r in c.get("regions", [])]

        items = []
        last_updates = []
        refreshing = False

        for r in cregions:
            items.extend(shared_state.items_by_region.get(r, []))
            ts = shared_state.last_refresh.get(r)
            if ts:
                last_updates.append(ts)
            if shared_state.refresh_in_progress.get(r):
                refreshing = True

        total = len(items)
        resolved = sum(1 for i in items if i.get("resolved_url"))

        if last_updates:
            newest = max(last_updates)
            age_seconds = int(now - newest)
            age = f"{age_seconds//60}m {age_seconds%60}s"
            if age_seconds < (REFRESH_INTERVAL + 120):
                status_icon, status_text, status_class = "✅", "FRESH", "status-fresh"
            else:
                status_icon, status_text, status_class = "⚠️", "STALE", "status-stale"
        else:
            age = "never"
            status_icon, status_text, status_class = "❌", "NO DATA", "status-error"

        if refreshing:
            status_icon, status_text, status_class = "🔄", "REFRESHING", "status-refreshing"

        filename = f"vavoo_playlist_{name}.m3u"
        path = os.path.join(PLAYLIST_DIR, filename) if PLAYLIST_DIR else filename
        exists = os.path.exists(path)
        size = f"{os.path.getsize(path)/1024:.1f} KB" if exists else "N/A"

        regions.append({
            "lang": "—",
            "region": name,
            "channels": total,
            "resolved": resolved,
            "age": age,
            "status_icon": status_icon,
            "status_text": status_text,
            "status_class": status_class,
            "exists": exists,
            "size": size
        })

    return {"regions": regions}

@app.route("/api/delete/<region>", methods=["POST"])
@login_required
def api_delete_region(region):
    region = region.upper()

    for c in list(CONFIG.get("COMBINED_PLAYLISTS", [])):
        if c.get("name") == region:
            CONFIG["COMBINED_PLAYLISTS"] = [
                x for x in CONFIG["COMBINED_PLAYLISTS"]
                if x.get("name") != region
            ]

            fn = f"vavoo_playlist_{region}.m3u"
            path = os.path.join(PLAYLIST_DIR, fn) if PLAYLIST_DIR else fn
            if os.path.exists(path):
                os.remove(path)

            save_config_to_disk()
            return {"status": "deleted-combined", "name": region}

    CONFIG["LOCALES"] = [
        (l, r) for l, r in CONFIG.get("LOCALES", [])
        if r.upper() != region
    ]

    shared_state.items_by_region.pop(region, None)
    shared_state.last_refresh.pop(region, None)
    shared_state.refresh_in_progress.pop(region, None)

    fn = f"vavoo_playlist_{region}.m3u"
    path = os.path.join(PLAYLIST_DIR, fn) if PLAYLIST_DIR else fn
    if os.path.exists(path):
        os.remove(path)

    save_config_to_disk()

    return {"status": "deleted", "region": region}

@app.route("/api/download_full_hls")
@login_required
def download_full_hls_playlist():
    import requests
    import re

    def get_auth_signature():
        headers = {
            "user-agent": "okhttp/4.11.0",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "content-length": "1106",
            "accept-encoding": "gzip"
        }

        payload = {
            "token": "tosFwQCJMS8qrW_AjLoHPQ41646J5dRNha6ZWHnijoYQQQoADQoXYSo7ki7O5-CsgN4CH0uRk6EEoJ0728ar9scCRQW3ZkbfrPfeCXW2VgopSW2FWDqPOoVYIuVPAOnXCZ5g",
            "reason": "app-blur",
            "locale": "de",
            "theme": "dark",
            "metadata": {
                "device": {
                    "type": "Handset",
                    "os": "Android",
                    "osVersion": "10",
                    "model": "Pixel 4",
                    "brand": "Google"
                }
            }
        }

        response = requests.post(
            "https://vavoo.to/mediahubmx-signature.json",
            json=payload,
            headers=headers,
            timeout=10
        )

        return response.json().get("signature")

    def clean_channel_name(name):
        return re.sub(
            r'\s*\.(a|b|c|s|d|e|f|g|h|i|j|k|l|m|n|o|p|q|r|t|u|v|w|x|y|z)\s*$',
            '',
            name,
            flags=re.IGNORECASE
        ).strip()

    def get_channels():
        signature = get_auth_signature()

        headers = {
            "user-agent": "okhttp/4.11.0",
            "accept": "application/json",
            "content-type": "application/json; charset=utf-8",
            "accept-encoding": "gzip",
            "mediahubmx-signature": signature
        }

        all_channels = []
        cursor = 0

        while True:
            payload = {
                "language": "de",
                "region": "AT",
                "catalogId": "iptv",
                "id": "iptv",
                "adult": False,
                "search": "",
                "sort": "name",
                "filter": {"group": ""},
                "cursor": cursor,
                "clientVersion": "3.0.2"
            }

            response = requests.post(
                "https://vavoo.to/mediahubmx-catalog.json",
                json=payload,
                headers=headers,
                timeout=10
            )

            data = response.json()
            items = data.get("items", [])
            all_channels.extend(items)

            cursor = data.get("nextCursor")
            if not cursor:
                break

        return all_channels

    channels = get_channels()

    output = ["#EXTM3U"]
    name_counts = {}

    for channel in channels:
        name = clean_channel_name(channel.get("name", "NoName"))
        url = channel.get("url")
        if not url:
            continue

        name_counts[name] = name_counts.get(name, 0) + 1
        final_name = name if name_counts[name] == 1 else f"{name} ({name_counts[name]})"

        output.append(f'#EXTINF:-1,{final_name}')
        output.append(url)

    return Response(
        "\n".join(output),
        mimetype="application/x-mpegURL",
        headers={
            "Content-Disposition": "attachment; filename=vavoo_full_hls_playlist.m3u"
        }
    )

@app.route("/playlist/combined/<name>.m3u")
def playlist_combined(name):
    filename = f"vavoo_playlist_{name}.m3u"
    path = os.path.join(PLAYLIST_DIR, filename) if PLAYLIST_DIR else filename

    if not os.path.exists(path):
        abort(404)

    return Response(
        open(path, "r", encoding="utf-8").read(),
        mimetype="application/x-mpegURL"
    )


@app.route("/")
@login_required
def index():
    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Vavoo IPTV Proxy</title>
<meta name="viewport" content="width=device-width, initial-scale=1">

<style>
*{box-sizing:border-box}
body{
font-family:'Segoe UI',Tahoma,sans-serif;
background:linear-gradient(135deg,#667eea,#764ba2);
min-height:100vh;
padding:20px;
margin:0
}
.container{max-width:1200px;margin:auto}
h1{color:#fff;text-align:center;margin-bottom:5px}
.subtitle{color:#eee;text-align:center;margin-bottom:30px}
.section-title{
color:#fff;
font-size:1.8em;
margin:40px 0 20px;
border-bottom:3px solid rgba(255,255,255,.3);
padding-bottom:6px
}
.box{
background:#fff;
border-radius:12px;
padding:20px;
box-shadow:0 4px 6px rgba(0,0,0,.15);
margin-bottom:30px
}
table{width:100%;border-collapse:collapse}
th{
background:#667eea;
color:#fff;
padding:12px;
text-align:left
}
td{
padding:12px;
border-bottom:1px solid #e2e8f0
}
tr:last-child td{border-bottom:none}

.status-badge{
padding:5px 12px;
border-radius:20px;
color:#fff;
font-size:.85em;
font-weight:700
}
.status-fresh{background:#48bb78}
.status-stale{background:#ed8936}
.status-error{background:#f56565}
.status-refreshing{background:#4299e1}

button{
background:#667eea;
color:#fff;
border:none;
padding:6px 12px;
border-radius:6px;
cursor:pointer;
font-weight:600
}
button.danger{background:#e53e3e}
button.gray{background:#6b7280}

input,textarea{
width:100%;
padding:6px;
margin-top:6px
}
textarea{resize:vertical}

a{color:#667eea;font-weight:700;text-decoration:none}
a.disabled{color:#aaa;pointer-events:none}
.row-actions button{margin-right:5px}


.config-grid{
display:grid;
grid-template-columns:1fr 1fr;
column-gap:40px
}
.config-block{
display:flex;
flex-direction:column
}
.config-title{
font-weight:700;
margin-bottom:10px
}
.config-row{
display:flex;
align-items:center;
gap:10px;
margin-bottom:8px
}
.config-row input{
margin:0;
width:16px;
height:16px
}

/* SAVE STATUS */
#saveStatus{
display:none;
margin-bottom:10px;
padding:8px 12px;
border-radius:6px;
font-weight:700;
background:#48bb78;
color:#fff
}

:root {
  --tooltip-enabled: 0;
}

body.hide-tooltips {
  --tooltip-enabled: 0;
}

[data-tooltip] {
  position: relative;
  cursor: help;
}

[data-tooltip]::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: 125%;
  left: 50%;
  transform: translateX(-50%) translateY(4px);

  background: #f8fafc;
  color: #1a202c;

  padding: 12px 16px;
  border-radius: 10px;

  min-width: 320px;
  max-width: 520px;
  white-space: pre-line;     /* keeps line breaks but allows wrapping */
  text-align: left;

  font-size: 13.5px;
  line-height: 1.55;
  font-weight: 500;

  z-index: 1000;
  opacity: 0;
  pointer-events: none;

  transition: opacity 0.15s ease, transform 0.15s ease;

  box-shadow:
    0 10px 25px rgba(0,0,0,.18),
    0 2px 6px rgba(0,0,0,.08);

  border: 1px solid #e2e8f0;
}

[data-tooltip]::before {
  content: "";
  position: absolute;
  bottom: 112%;
  left: 50%;
  transform: translateX(-50%);
  border: 7px solid transparent;
  border-top-color: #f8fafc;
  opacity: 0;
  transition: opacity 0.15s ease;
}

[data-tooltip]:hover::after,
[data-tooltip]:hover::before {
  opacity: calc(var(--tooltip-enabled));
  transform: translateX(-50%) translateY(0);
}

</style>
<link rel="stylesheet" href="/static/macreplay-theme.css">
</head>

<body>
<div class="container">

<div style="display:flex;justify-content:space-between;align-items:center">
  <div>
    <h1>🚀 Vavoo IPTV Proxy</h1>
    <p class="subtitle">Multiprocessing Edition – Live Control Panel</p>
  </div>

  <div>
<div
  style="display:inline-block"
  data-tooltip="Log out from the admin interface. You will need to log in again to access settings."
>
  <a href="/logout"
     style="
       background:#e53e3e;
       color:#fff;
       padding:8px 14px;
       border-radius:6px;
       font-weight:700;
       text-decoration:none;
       display:inline-block;
     ">
    🚪 Logout
  </a>
</div>

  </div>
</div>

<h2 class="section-title">📺 Region Status</h2>
<div class="box">
<table>
<thead>
<tr>
<th>Lang</th>
<th>Region</th>
<th>Channels</th>
<th>Resolved</th>
<th>Age</th>
<th>Status</th>
<th>Playlist</th>
<th>Size</th>
<th>Action</th>
</tr>
</thead>
<tbody id="regionsBody"></tbody>
</table>
</div>
<h2 class="section-title">🌍 Region Management</h2>
<div class="box">

<div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap">
  <select
  id="regionSelect"
  multiple
  size="6"
  data-tooltip="
Region selection:

• Select ONE country
  → Creates ONE single playlist

• Select MULTIPLE countries
  → Creates ONE combined playlist
  → Name like: FR_IT_ES

Rules:
• Combined playlists NEVER auto-create singles
• Singles and combined can coexist
• Deleting one never affects the other
"
>
  <option value="">Select region…</option>
</select>

<button id="addBtn"
data-tooltip="
Add & Build region

• Adds the selected country to the system
• Fetches the full IPTV catalog from Vavoo
• Resolves all stream URLs
• Generates the playlist file

⚠ First build may take several minutes
">
➕ Add & Build
</button>
<th>(multiselect possible)</th>
<div
  style="display:inline-block"
  data-tooltip="
Download FULL HLS playlist

• Downloads ALL available channels
• Includes all countries & groups
• Raw HLS URLs (no proxy, no filtering)
• Independent from your configured regions

⚠ Large file – generation may take time
"
>
  <button
    id="downloadBtn"
    onclick="downloadFullHLS()"
    style="background:#38a169"
  >
    ⬇️ Download full HLS playlist
  </button>
</div>

<th>(all available countries)</th>

<span
  id="downloadInfo"
  style="
    display:none;
    margin-left:12px;
    font-weight:600;
    color:#22543d;
  "
>
  ⏳ This may take a while…
</span>


</div>

<br>
</div>

<h2 class="section-title">📡 Live Connections</h2>
<div class="box">
<table>
<thead>
<tr>
<th>IP</th>
<th>Channel</th>
<th>Region</th>
<th>Connected</th>
<th>Idle</th>
</tr>
</thead>
<tbody id="connBody"></tbody>
</table>
</div>

<h2 class="section-title">⚙️ Configuration</h2>
<div class="box">

<div id="saveStatus">✔ Configuration saved successfully</div>

<div class="config-grid">

<div class="config-block">
<div class="config-title">Streaming mode</div>

<div class="config-row">
<input type="radio" name="streammode" id="mode_proxy">
<label for="mode_proxy"
data-tooltip="
Proxy mode:
• Server downloads video segments
• Works over internet and LAN
• Hides source URLs from clients
• Slightly higher CPU usage
(RECOMMENDED)
">
Proxy streaming mode (Proxy is streaming segments) Local & Internet
</label>
</div>

<div class="config-row">
<input type="radio" name="streammode" id="mode_direct">
<label for="mode_direct"
data-tooltip="
Direct mode:
• Client connects directly to the stream source
• Lowest server load
• Only works reliably inside your local network
• Exposes source URLs to the client
">
Direct mode (client connects to source) Only local!
</label>

</div>
</div>

<div class="config-block">
<div class="config-title">Options</div>

<div class="config-row">
<input type="checkbox" id="res">
<label for="res"
data-tooltip="
Resolution Scan (RES):
• Probes every stream using FFmpeg
• Detects real resolution & FPS
• Locks the BEST working variant (e.g. 1080p50)
• Removes broken or low-quality variants

⚠ First build can take several minutes
">
Resolution scan (RES) may take a while!
</label>
</div>

<div class="config-row">
<input type="checkbox" id="rebuild">
<label for="rebuild"
data-tooltip="
Rebuild playlist on refresh:
• Forces a full catalog fetch
• Re-runs grouping & filtering logic
• Useful after Vavoo backend changes
• Slower than a normal refresh
">
Rebuild playlist on refresh
</label>
</div>

<div class="config-row">
<input type="checkbox" id="filter">
<label for="filter"
data-tooltip="
Enable filter:
• Only affects the FIRST configured region
• Keeps channels matching filter keywords
• Everything else is removed from playlist
• Useful for sport-only or custom lists
• Using own group-titles
">
Enable filter (FIRST region only)
</label>
</div>
<div class="config-row">
 <label
  data-tooltip="Enable on-screen help tooltips explaining buttons and options."
>
  <input type="checkbox" id="showTooltips">
  Show help tooltips
</label>
</div>
</div>

</div>

<br>

<div class="config-title">Filter keywords (one per line) part after ":" is the new group title for m3u</div>
<div
  data-tooltip="
Filter keywords (FIRST region only)

• Channel name must contain the keyword
• Case-insensitive matching
• Non-matching channels are removed

Group override:
• keyword:GroupName → overrides M3U group-title

Examples:
bundesliga:Bundesliga
sky sport:Sport
f1:Formula 1
uhd:UHD
">
  <textarea id="keywords" rows="7"
    placeholder="example:
bundesliga:Bundesliga
sky sport:Sport
f1:Formula 1
uhd:UHD"></textarea>
</div>

<br><br>
<button id="saveBtn"
data-tooltip="
Save & Apply:
• Saves configuration to disk
• Applies changes immediately
• May trigger playlist rebuild
">
💾 Save & Apply
</button>
<button class="gray"
onclick="refreshAll()"
data-tooltip="
Refresh all regions

• Re-fetches stream URLs
• Keeps existing playlists
• Fast operation
• Does NOT rebuild catalog

Use this when:
✓ Streams stop working
✓ Playlist is marked STALE
">
🔄 Refresh all
</button>

</div>

</div>

<script>
const tooltipToggle = document.getElementById("showTooltips");

function applyTooltipState() {
  if (tooltipToggle && tooltipToggle.checked) {
    document.body.classList.remove("hide-tooltips");
    document.documentElement.style.setProperty("--tooltip-enabled", "1");
  } else {
    document.body.classList.add("hide-tooltips");
    document.documentElement.style.setProperty("--tooltip-enabled", "0");
  }
}

applyTooltipState();

tooltipToggle.addEventListener("change", applyTooltipState);

applyTooltipState();
function downloadFullHLS() {
  const info = document.getElementById("downloadInfo");
  const btn  = document.getElementById("downloadBtn");

  info.style.display = "inline";
  btn.disabled = true;
  btn.style.opacity = "0.7";

  setTimeout(() => {
    window.location.href = "/api/download_full_hls";
  }, 50);

  setTimeout(() => {
    btn.disabled = false;
    btn.style.opacity = "1";
    info.style.display = "none";
  }, 8000); // 8 seconds – adjust if needed
}
const VAVOO_REGIONS = {
  "Albania":        { lang: "al", region: "AL" },
  "Bulgaria":       { lang: "bg", region: "BG" },
  "France":         { lang: "fr", region: "FR" },
  "Germany":        { lang: "de", region: "DE" },
  "Italy":          { lang: "it", region: "IT" },
  "Netherlands":    { lang: "nl", region: "NL" },
  "Poland":         { lang: "pl", region: "PL" },
  "Portugal":       { lang: "pt", region: "PT" },
  "Romania":        { lang: "ro", region: "RO" },
  "Spain":          { lang: "es", region: "ES" },
  "Turkey":         { lang: "tr", region: "TR" },
  "United Kingdom": { lang: "gb", region: "GB" } 
};

const regionSelect = document.getElementById("regionSelect");

for (const name of Object.keys(VAVOO_REGIONS)) {
  const opt = document.createElement("option");
  opt.value = name;
  opt.textContent = name;
  regionSelect.appendChild(opt);
}
function esc(s){
 return String(s).replace(/[&<>"']/g,function(m){
  return {"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}[m];
 });
}

async function loadConfig(){
 const c = await fetch('/api/config').then(r=>r.json());
 document.getElementById('res').checked = !!c.RES;
 document.getElementById('rebuild').checked = !!c.PLAYLIST_REBUILD_ON_START;
 document.getElementById('filter').checked = !!c.FILTER_ENABLED;
 document.getElementById('keywords').value = (c.FILTER_KEYWORDS||[]).join("\\n");
 if(c.STREAM_MODE===false){
  document.getElementById('mode_direct').checked = true;
 }else{
  document.getElementById('mode_proxy').checked = true;
 }
}

async function saveConfig(){
 const streamMode = document.getElementById('mode_proxy').checked;

 await fetch('/api/config',{
  method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({
   STREAM_MODE:streamMode,
   RES:document.getElementById('res').checked,
   PLAYLIST_REBUILD_ON_START:document.getElementById('rebuild').checked,
   FILTER_ENABLED:document.getElementById('filter').checked,
   FILTER_KEYWORDS:document.getElementById('keywords').value
    .split("\\n").map(x=>x.trim()).filter(Boolean)
  })
 });

 const s=document.getElementById('saveStatus');
 s.style.display="block";
 setTimeout(function(){s.style.display="none";},3000);
}

async function refreshCombined(name){
  const cfg = await fetch('/api/config').then(r => r.json());
  const combo = (cfg.COMBINED_PLAYLISTS || []).find(c => c.name === name);
  if (!combo) return;

  for (const r of combo.regions) {
    await fetch('/api/refresh/' + encodeURIComponent(r), { method: 'POST' });
  }
}

async function refreshRegion(r){
 await fetch('/api/refresh/'+encodeURIComponent(r),{method:'POST'});
}

async function refreshAll(){
 await fetch('/api/refresh/*',{method:'POST'});
}

async function addRegion(){
  const selected = [...regionSelect.selectedOptions];
  if (!selected.length) return;

  const cfg = await fetch('/api/config').then(r => r.json());

  cfg.LOCALES = cfg.LOCALES || [];
  cfg.COMBINED_PLAYLISTS = cfg.COMBINED_PLAYLISTS || [];

  const regions = selected.map(o => VAVOO_REGIONS[o.value].region.toUpperCase());
  const langs   = selected.map(o => VAVOO_REGIONS[o.value].lang);

  if (regions.length > 1) {
    const name = regions.join("_");

    if (!cfg.COMBINED_PLAYLISTS.some(c => c.name === name)) {
      cfg.COMBINED_PLAYLISTS.push({ name, regions });
    }
  } else {
    const r = regions[0];
    if (!cfg.LOCALES.some(x => x.region === r)) {
      cfg.LOCALES.push({ lang: langs[0], region: r });
    }
  }

  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cfg)
  });

  regions.forEach(r => {
    fetch('/api/rebuild/' + encodeURIComponent(r), { method: 'POST' });
  });
}

async function removeRegion(r){
 if(!confirm("Delete region "+r+" ?")) return;

 await fetch('/api/delete/'+encodeURIComponent(r), {
  method: 'POST'
 });

 renderStatus();
}

async function renderStatus(){
 const data = await fetch('/api/status').then(r=>r.json());
 const body = document.getElementById('regionsBody');
 let html="";

 for(const x of data.regions){
  const badge =
   '<span class="status-badge '+esc(x.status_class)+'">'+
   esc(x.status_icon)+' '+esc(x.status_text)+
   '</span>';

  const playlist = x.exists
   ? '<a class="playlist-link" href="/playlist/'+esc(x.region)+'.m3u">📥 Download</a><br><small>'+
     esc(location.protocol+'//'+location.host+'/playlist/'+x.region+'.m3u')+
     '</small>'
   : '<span class="disabled playlist-wait">⏳ Generating…</span>';

  let refreshBtn;
  if (x.lang === "—") {
    refreshBtn =
      '<button class="btn-refresh" data-type="combined" data-region="'+esc(x.region)+'">🔄</button>';
  } else {
    refreshBtn =
      '<button class="btn-refresh" data-type="single" data-region="'+esc(x.region)+'">🔄</button>';
  }

  const deleteBtn =
   '<button class="danger btn-delete" data-region="'+esc(x.region)+'">❌</button>';

  html +=
   '<tr>'+
    '<td>'+esc(x.lang)+'</td>'+
    '<td><b>'+esc(x.region)+'</b></td>'+
    '<td>'+x.channels+'</td>'+
    '<td>'+x.resolved+'</td>'+
    '<td>'+esc(x.age)+'</td>'+
    '<td>'+badge+'</td>'+
    '<td>'+playlist+'</td>'+
    '<td>'+esc(x.size)+'</td>'+
    '<td class="row-actions">'+refreshBtn+' '+deleteBtn+'</td>'+
   '</tr>';
 }

 body.innerHTML = html;

 applyTooltipsAndActions();
}

function applyTooltipsAndActions(){
 try {

  document.querySelectorAll(".playlist-link").forEach(el=>{
   el.setAttribute("data-tooltip","Download playlist");
  });

  document.querySelectorAll(".playlist-wait").forEach(el=>{
   el.setAttribute("data-tooltip","Playlist is being generated");
  });

  document.querySelectorAll(".btn-refresh").forEach(btn=>{
   const r = btn.dataset && btn.dataset.region;
   const t = btn.dataset && btn.dataset.type;
   if(!r) return;

   if(t === "combined"){
    btn.setAttribute(
     "data-tooltip",
     "Refresh combined playlist (refreshes all regions)"
    );
    btn.onclick = function(){ refreshCombined(r); };
   } else {
    btn.setAttribute(
     "data-tooltip",
     "Refresh this region only"
    );
    btn.onclick = function(){ refreshRegion(r); };
   }
  });

  document.querySelectorAll(".btn-delete").forEach(btn=>{
   const r = btn.dataset && btn.dataset.region;
   if(!r) return;

   btn.setAttribute(
    "data-tooltip",
    "Delete this playlist only"
   );
   btn.onclick = function(){ removeRegion(r); };
  });

  const dlBtn = document.getElementById("downloadBtn");
  if (dlBtn) {
   dlBtn.setAttribute(
    "data-tooltip",
    "Download full HLS playlist (all channels)"
   );
  }

 } catch(e) {
  console.error("applyTooltipsAndActions error:", e);
 }
}

async function renderConnections(){
 const data=await fetch('/api/connections').then(r=>r.json());
 const body=document.getElementById('connBody');
 let html="";

 for(const c of data.connections){
  html+='<tr>'+
   '<td>'+esc(c.ip)+'</td>'+
   '<td><b>'+esc(c.channel)+'</b></td>'+
   '<td>'+esc(c.region)+'</td>'+
   '<td>'+c.connected+'s</td>'+
   '<td>'+c.idle+'s</td>'+
   '</tr>';
 }
 body.innerHTML=html||'<tr><td colspan="5">No active connections</td></tr>';
}

document.getElementById('saveBtn').onclick=saveConfig;
document.getElementById('addBtn').onclick=addRegion;

loadConfig();
renderStatus();
renderConnections();
setInterval(renderStatus,2000);
setInterval(renderConnections,2000);
</script>

</body>
</html>
"""
    return html

if __name__ == "__main__":

    clear_screen()
    print_overview_banner()

    load_config_from_disk()
    load_mappings()

    RES_QUEUE = multiprocessing.Queue()

    if bool(CONFIG.get("RES", False)):
        RES_WORKERS = min(4, multiprocessing.cpu_count())
        for _ in range(RES_WORKERS):
            p = multiprocessing.Process(
                target=resolution_worker,
                args=(RES_QUEUE,),
                daemon=True
            )
            p.start()
        print(f"🎯 {RES_WORKERS} Resolution workers started\n")

    refresh_process = multiprocessing.Process(
        target=refresh_worker,
        daemon=True
    )
    refresh_process.start()
    print("✅ Refresh worker process started\n")

    request_refresh("*", rebuild=True)

    try:
        from waitress import serve

        print("🚀 Starting Waitress server (production-ready)...")
        print(f"📡 Server URL: http://{public_host()}:{public_port()}")
        print("📺 Playlists:")

        for _, region in get_locales():
            print(f"   http://{public_host()}:{public_port()}/playlist/{region}.m3u")

        if CONFIG.get("RES"):
            print("\n⏳ NOTE: First playlist generation waits for FFmpeg resolution scan")

        print("\nPress Ctrl+C to stop\n")
        print(f"{'=' * 60}\n")

        serve(
            app,
            host="0.0.0.0",
            port=PORT,
            threads=32,
            channel_timeout=120,
            cleanup_interval=30,
            connection_limit=1000
        )

    except ImportError:
        print("⚠️  'waitress' not installed – using Flask dev server")

        app.run(
            host="0.0.0.0",
            port=PORT,
            threaded=True,
            debug=False
        )  
