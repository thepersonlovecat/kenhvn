import os
import sys
import json
import time
import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_URL = os.environ.get("FILM4K_BASE_URL", "https://fiml4k.fun")
EMAIL = os.environ.get("FILM4K_EMAIL")
PASSWORD = os.environ.get("FILM4K_PASS")

# Tự động đọc từ config.json (cục bộ) nếu không có biến môi trường
if not EMAIL or not PASSWORD:
    cfg_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, 'r', encoding='utf-8') as f:
                _cfg = json.load(f)
                EMAIL = EMAIL or _cfg.get("email")
                PASSWORD = PASSWORD or _cfg.get("pass")
        except Exception:
            pass


session = requests.Session()
session.verify = False
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
    'Accept': 'application/json'
})

def login():
    login_url = f"{BASE_URL}/api/auth/signin"
    for attempt in range(5):
        try:
            resp = session.post(login_url, json={"email": EMAIL, "password": PASSWORD}, timeout=25)
            if resp.status_code == 200:
                print(f"[OK] Dang nhap thanh cong tai khoan: {EMAIL}")
                return True
            print(f"[WARN] Dang nhap status {resp.status_code}, thu lai...")
        except Exception as e:
            print(f"[WARN] Loi ket noi ({attempt+1}/5): {e}")
            time.sleep(1)
    return False

def fetch_channels():
    resp = session.get(f"{BASE_URL}/api/tv/channels", timeout=25)
    return resp.json().get('channels', [])

def fetch_events():
    try:
        resp = session.get(f"{BASE_URL}/api/tv/events", timeout=25)
        return resp.json().get('events', [])
    except Exception:
        return []

def fetch_stream_url(ch):
    cid = ch['id']
    url = f"{BASE_URL}/api/tv/{cid}/stream"
    for _ in range(3):
        try:
            r = session.get(url, timeout=12)
            if r.status_code == 200:
                data = r.json()
                surl = data.get('url', '')
                if surl.startswith('/'):
                    surl = f"{BASE_URL}{surl}"
                return {
                    "id": cid,
                    "name": ch['name'],
                    "category": ch.get('category') or 'KÊNH KHÁC',
                    "logo": ch.get('logo', '') or '',
                    "stream_url": surl,
                    "dash": data.get('dash', False),
                    "raw": data
                }
        except Exception:
            time.sleep(0.5)
    return {
        "id": cid,
        "name": ch['name'],
        "category": ch.get('category') or 'KÊNH KHÁC',
        "logo": ch.get('logo', '') or '',
        "stream_url": "",
        "dash": False,
        "raw": None
    }

def main():
    print("=" * 60)
    print("BAT DAU CAP NHAT DANH SACH KENH & TOKEN FILM4K")
    print("=" * 60)

    if not login():
        print("[ERROR] Dang nhap that bai! Vui long kiem tra email/password.")
        sys.exit(1)

    channels = fetch_channels()
    events = fetch_events()
    total_ch = len(channels)
    print(f"[INFO] Tim thay tong cong {total_ch} kenh va {len(events)} su kien.")

    results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_stream_url, ch): ch for ch in channels}
        done = 0
        for future in as_completed(futures):
            res = future.result()
            results[res['id']] = res
            done += 1
            if done % 30 == 0 or done == total_ch:
                print(f" -> Da lay token: {done}/{total_ch} kenh...")

    ordered = [results[ch['id']] for ch in channels if ch['id'] in results]

    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    with open(os.path.join(script_dir, 'direct_streams.json'), 'w', encoding='utf-8') as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)

    with open(os.path.join(script_dir, 'channels_live.json'), 'w', encoding='utf-8') as f:
        json.dump({"channels": channels, "events": events}, f, ensure_ascii=False, indent=2)

    # 1. Phân loại kênh
    # - Nhóm HLS mượt mà đưa lên đầu: VTV, Thiết yếu, Thể thao, Giải trí...
    # - Nhóm TV360+ (MPD DRM) và Ants đưa xuống phía dưới
    hls_channels = []
    mpd_channels = []
    ants_channels = []

    preferred_order = [
        'Kênh thiết yếu',
        'Kênh VTV',
        'Thể thao',
        'Giải trí',
        'Kênh quốc tế',
        'Kênh HTV',
        'Kênh VTV Cab',
        'Kênh SCTV',
        'Kênh Vĩnh Long',
        'Kênh địa phương',
        'Kênh FM',
        'Sự kiện trực tiếp',
        'KÊNH KHÁC'
    ]

    groups = defaultdict(list)
    for c in ordered:
        surl = c.get('stream_url', '')
        if not surl:
            continue
        if '.mpd' in surl:
            mpd_channels.append(c)
        elif 'api/tv/ants/' in surl:
            ants_channels.append(c)
        else:
            grp = c.get('category') or 'KÊNH KHÁC'
            groups[grp].append(c)

    for g in groups:
        if g not in preferred_order:
            preferred_order.append(g)

    # Đưa các kênh HLS sắp xếp theo chuyên mục lên trước
    for grp_name in preferred_order:
        if grp_name in groups:
            hls_channels.extend(groups[grp_name])

    # Danh sách tổng hợp toàn bộ 190 kênh theo thứ tự tối ưu
    all_ordered_channels = hls_channels + mpd_channels + ants_channels

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Tạo danh_sach_kenh_potplayer.m3u (Đầy đủ 190 kênh, 140 kênh HLS lên đầu, sau đó đến TV360+ MPD và Ants)
    m3u_pot = [
        f'#EXTM3U name="Film4K PotPlayer All {len(all_ordered_channels)} Channels" updated="{now_str}"'
    ]
    for c in all_ordered_channels:
        cid = str(c.get('id', '')).strip()
        cname = str(c.get('name', '')).strip()
        logo = c.get('logo', '') or ''
        surl = c.get('stream_url', '')
        grp = c.get('category') or 'KÊNH KHÁC'
        if '.mpd' in surl:
            grp = f"{grp} (DRM MPD)"
        elif 'api/tv/ants/' in surl:
            grp = f"{grp} (Ants)"
        m3u_pot.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}')
        m3u_pot.append(surl)

    m3u_pot_path = os.path.join(script_dir, 'danh_sach_kenh_potplayer.m3u')
    with open(m3u_pot_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(m3u_pot) + '\n')

    # 2. Tạo danh_sach_kenh_tivimate.m3u (Đầy đủ 190 kênh kèm Pipe Headers)
    m3u_tivi = [
        f'#EXTM3U name="Film4K TiviMate All {len(all_ordered_channels)} Channels" updated="{now_str}"'
    ]
    for c in all_ordered_channels:
        cid = str(c.get('id', '')).strip()
        cname = str(c.get('name', '')).strip()
        logo = c.get('logo', '') or ''
        surl = c.get('stream_url', '')
        grp = c.get('category') or 'KÊNH KHÁC'
        if '.mpd' in surl:
            grp = f"{grp} (DRM MPD)"
        elif 'api/tv/ants/' in surl:
            grp = f"{grp} (Ants)"
        m3u_tivi.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}')
        if 'tv360.vn' in surl:
            pipe_url = f"{surl}|User-Agent=Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36&Referer=https://tv360.vn/&Origin=https://tv360.vn"
        else:
            pipe_url = f"{surl}|User-Agent=Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36&Referer=https://fiml4k.fun/&Origin=https://fiml4k.fun"
        m3u_tivi.append(pipe_url)

    m3u_tivi_path = os.path.join(script_dir, 'danh_sach_kenh_tivimate.m3u')
    with open(m3u_tivi_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(m3u_tivi) + '\n')

    # 3. Tạo danh_sach_kenh_film4k.m3u (Đầy đủ 190 kênh chuẩn VLC)
    m3u_all = [
        f'#EXTM3U name="Film4K All {len(all_ordered_channels)} Channels" updated="{now_str}"'
    ]
    for c in all_ordered_channels:
        cid = str(c.get('id', '')).strip()
        cname = str(c.get('name', '')).strip()
        logo = c.get('logo', '') or ''
        surl = c.get('stream_url', '')
        grp = c.get('category') or 'KÊNH KHÁC'
        if '.mpd' in surl:
            grp = f"{grp} (DRM MPD)"
        elif 'api/tv/ants/' in surl:
            grp = f"{grp} (Ants)"
        m3u_all.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}')
        m3u_all.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36')
        m3u_all.append(surl)

    m3u_all_path = os.path.join(script_dir, 'danh_sach_kenh_film4k.m3u')
    with open(m3u_all_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(m3u_all) + '\n')

    print(f"[HOAN TAT] Da cap nhat day du {len(all_ordered_channels)} kenh vao:")
    print(f"  - danh_sach_kenh_potplayer.m3u ({len(all_ordered_channels)} kenh, 140 HLS len dau)")
    print(f"  - danh_sach_kenh_tivimate.m3u ({len(all_ordered_channels)} kenh)")
    print(f"  - danh_sach_kenh_film4k.m3u ({len(all_ordered_channels)} kenh)")
    print(f"  - direct_streams.json")

if __name__ == '__main__':
    main()
