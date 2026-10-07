import os
import sys
import re
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

# Tu dong doc tu config.json neu khong co bien moi truong
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

def update_and_load_tv360_m3u(ordered, script_dir):
    """
    1. Cap nhat token moi vao file tv360.m3u (chua ClearKey).
    2. Trich xuat cac khoi kenh tu tv360.m3u de ghep vao playlist tong hop.
    """
    tv360_path = os.path.join(script_dir, 'tv360.m3u')
    if not os.path.exists(tv360_path):
        return []

    ch_map = {
        '201': 2458,  # TV360+ 4
        '368': 9868,  # TV360+ 6
        '369': 9869,  # TV360+ 7
        '465': 10001, # TV360+ 12
        '471': 10022, # TV360+ 13
        '472': 10023, # TV360+ 14
        '473': 10024  # TV360+ 15
    }

    fresh_bpk_urls = {}
    for ch_num, cid in ch_map.items():
        found = next((c for c in ordered if c['id'] == cid), None)
        if not found or not found.get('stream_url'):
            continue
        surl = found['stream_url']
        try:
            r2 = requests.get(surl, allow_redirects=False, verify=False, timeout=10)
            loc = r2.headers.get('Location', '')
            m = re.search(r'https://([^/:]+)(?::\d+)?/bpk-token/([^/]+)/bpk-tv/' + ch_num + r'/output/index\.mpd', loc)
            if m:
                host = m.group(1)
                token = m.group(2)
                # Cat sach truoc .mpd, bo query phia sau
                fresh_bpk_urls[ch_num] = f'https://{host}/bpk-token/{token}/bpk-tv/{ch_num}/output/index.mpd'
        except Exception as e:
            print(f"[WARN] Khong the lay redirect bpk-token cho kenh {ch_num}: {e}")

    try:
        with open(tv360_path, 'r', encoding='utf-8') as f:
            content = f.read()

        for ch_num, new_url in fresh_bpk_urls.items():
            pattern = r'https://[^\s]+/bpk-token/[^/\s]+/bpk-tv/' + ch_num + r'/output/index\.mpd[^\s]*'
            content = re.sub(pattern, new_url, content)
            print(f"  -> tv360.m3u: Da cap nhat bpk-token cho kenh {ch_num}")

        # Cap nhat TV360+ 9, 10, 11 (cac kenh HLS sach tu TV360)
        hls_map = {
            '9887': 'tv360plus9',
            '9957': 'tv360plus10',
            '9958': 'tv360plus11'
        }
        for cid_str, tag in hls_map.items():
            ch_found = next((c for c in ordered if str(c['id']) == cid_str), None)
            if ch_found and ch_found.get('stream_url'):
                clean_hls = ch_found['stream_url']
                pattern = r'(tvg-id="' + tag + r'".*?\n(?:#EXTVLCOPT:[^\n]+\n)?)(https://[^\s]+)'
                content = re.sub(pattern, r'\g<1>' + clean_hls, content, flags=re.DOTALL)

        with open(tv360_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("[OK] Da cap nhat toan bo token moi vao tv360.m3u!")

        # Doc cac khoi kenh da duoc format san trong tv360.m3u
        tv360_entries = []
        current = []
        for line in content.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith('#EXTINF:'):
                if current:
                    tv360_entries.append(current)
                    current = []
            current.append(line_str)
        if current:
            tv360_entries.append(current)

        # Loc bo hoan toan cac kenh / su kien VTVPrime neu co
        filtered_entries = []
        for entry in tv360_entries:
            entry_text = "\n".join(entry).lower()
            if "vtvprime" in entry_text or "onsport" in entry_text:
                continue
            filtered_entries.append(entry)

        return filtered_entries

    except Exception as e:
        print(f"[ERROR] Loi khi xu ly tv360.m3u: {e}")
        return []

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

    # 1. Cap nhat va lay toan bo cac kenh TV360+ da giai ma ClearKey tu tv360.m3u
    tv360_clearkey_entries = update_and_load_tv360_m3u(ordered, script_dir)
    print(f"[INFO] Da nap {len(tv360_clearkey_entries)} kenh giai ma ClearKey tu tv360.m3u")

    # 2. Loc va sap xep cac kenh tu Film4K
    # Loai bo cac kenh TV360+ cu trong Film4K de thay the bang ban ClearKey tu tv360.m3u
    hls_channels = []
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
        'Kênh FM'
    ]

    groups = defaultdict(list)
    for c in ordered:
        surl = c.get('stream_url', '')
        cname = c.get('name', '')
        if not surl:
            continue
        # Neu la kenh TV360+ (da co ban ClearKey trong tv360.m3u) thi bo qua o day de chen ban ClearKey vao sau
        if 'tv360+' in cname.lower():
            continue
        if 'api/tv/ants/' in surl:
            ants_channels.append(c)
        else:
            grp = c.get('category') or 'KÊNH KHÁC'
            groups[grp].append(c)

    for g in groups:
        if g not in preferred_order:
            preferred_order.append(g)

    for grp_name in preferred_order:
        if grp_name in groups:
            hls_channels.extend(groups[grp_name])

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 3. Tao danh_sach_kenh_potplayer.m3u & danh_sach_kenh_tivimate.m3u
    # Thu tu:
    # 1. 140 kenh HLS thong thuong (VTV1 len dau, HTV, VTC...)
    # 2. Toan bo kenh TV360+ tu tv360.m3u (Co san ClearKey & bpk-token moi)
    # 3. Cac kenh Ants quoc te
    
    m3u_tivi_lines = [
        f'#EXTM3U name="Film4K & TV360 ClearKey IPTV" updated="{now_str}"'
    ]
    m3u_pot_lines = [
        f'#EXTM3U name="Film4K & TV360 ClearKey IPTV" updated="{now_str}"'
    ]

    # Phần 1: Các kênh HLS & ClearKey thông thường
    for c in hls_channels:
        cid = str(c.get('id', '')).strip()
        cname = str(c.get('name', '')).strip()
        logo = c.get('logo', '') or ''
        surl = c.get('stream_url', '')
        grp = c.get('category') or 'KÊNH KHÁC'

        raw = c.get('raw') or {}
        clearkey = raw.get('clearKey') if isinstance(raw, dict) else None

        # Fix prv.film4k.net stream: Luồng thực tế từ prv.film4k.net là HLS m3u8, không phải DASH mpd
        if "prv.film4k.net" in surl:
            surl = surl.replace(".mpd", ".m3u8")
            is_dash = False
        else:
            is_dash = c.get('dash') or '.mpd' in surl

        if clearkey and clearkey.get('keyId') and clearkey.get('key'):
            kid = clearkey.get('keyId')
            key = clearkey.get('key')

            entry_pot = [
                f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}',
                '#EXTVLCOPT:http-user-agent=Dalvik/2.1.0',
                '#KODIPROP:inputstream.adaptive.manifest_type=mpd',
                '#KODIPROP:inputstream.adaptive.license_type=clearkey',
                f'#KODIPROP:inputstream.adaptive.license_key={kid}:{key}',
                surl
            ]
            m3u_pot_lines.extend(entry_pot)

            entry_tivi = [
                f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}',
                '#EXTVLCOPT:http-user-agent=Dalvik/2.1.0',
                '#KODIPROP:inputstream.adaptive.manifest_type=mpd',
                '#KODIPROP:inputstream.adaptive.license_type=clearkey',
                f'#KODIPROP:inputstream.adaptive.license_key={kid}:{key}',
                surl
            ]
            m3u_tivi_lines.extend(entry_tivi)

        elif is_dash:
            entry_pot = [
                f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}',
                '#EXTVLCOPT:http-user-agent=Dalvik/2.1.0',
                '#KODIPROP:inputstream.adaptive.manifest_type=mpd',
                surl
            ]
            m3u_pot_lines.extend(entry_pot)

            entry_tivi = [
                f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}',
                '#EXTVLCOPT:http-user-agent=Dalvik/2.1.0',
                '#KODIPROP:inputstream.adaptive.manifest_type=mpd',
                surl
            ]
            m3u_tivi_lines.extend(entry_tivi)

        else:
            # PotPlayer: Clean URL
            m3u_pot_lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}')
            m3u_pot_lines.append(surl)

            # TiviMate: Pipe URL
            m3u_tivi_lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}')
            if 'tv360.vn' in surl:
                pipe_url = f"{surl}|User-Agent=Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36&Referer=https://tv360.vn/&Origin=https://tv360.vn"
            else:
                pipe_url = f"{surl}|User-Agent=Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36&Referer=https://fiml4k.fun/&Origin=https://fiml4k.fun"
            m3u_tivi_lines.append(pipe_url)

    # Phần 2: Các kênh TV360+ (Đã có ClearKey & Token mới)
    for entry in tv360_clearkey_entries:
        # Giu nguyen toan bo the dinh dang (#EXTINF, #KODIPROP, stream url)
        for line in entry:
            m3u_tivi_lines.append(line)
            m3u_pot_lines.append(line)

    # Phần 3: Các kênh Ants
    for c in ants_channels:
        cid = str(c.get('id', '')).strip()
        cname = str(c.get('name', '')).strip()
        logo = c.get('logo', '') or ''
        surl = c.get('stream_url', '')
        grp = "Kênh Quốc Tế (Ants)"

        m3u_pot_lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}')
        m3u_pot_lines.append(surl)

        m3u_tivi_lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp}",{cname}')
        pipe_url = f"{surl}|User-Agent=Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36&Referer=https://fiml4k.fun/&Origin=https://fiml4k.fun"
        m3u_tivi_lines.append(pipe_url)

    # Ghi file
    with open(os.path.join(script_dir, 'danh_sach_kenh_potplayer.m3u'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(m3u_pot_lines) + '\n')

    with open(os.path.join(script_dir, 'danh_sach_kenh_tivimate.m3u'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(m3u_tivi_lines) + '\n')

    with open(os.path.join(script_dir, 'danh_sach_kenh_film4k.m3u'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(m3u_tivi_lines) + '\n')

    total_merged = len(hls_channels) + len(tv360_clearkey_entries) + len(ants_channels)
    print(f"\n🎉 [THANH CONG] Da chen thanh cong {len(tv360_clearkey_entries)} kenh ClearKey vao playlist:")
    print(f"  - Tong so kenh: {total_merged} kenh")
    print(f"  - 140 kenh HLS len dau")
    print(f"  - {len(tv360_clearkey_entries)} kenh TV360+ kem ClearKey & bpk-token moi")
    print(f"  - Da cap nhat danh_sach_kenh_potplayer.m3u, danh_sach_kenh_tivimate.m3u, tv360.m3u!")

if __name__ == '__main__':
    main()
