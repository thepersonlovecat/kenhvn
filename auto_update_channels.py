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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Cấu hình tài khoản Film4K để lấy token các kênh TV360+
BASE_URL = os.environ.get("FILM4K_BASE_URL", "https://fiml4k.fun")
EMAIL = os.environ.get("FILM4K_EMAIL")
PASSWORD = os.environ.get("FILM4K_PASS")

if not EMAIL or not PASSWORD:
    cfg_file = os.path.join(SCRIPT_DIR, 'config.json')
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, 'r', encoding='utf-8') as f:
                _cfg = json.load(f)
                EMAIL = EMAIL or _cfg.get("email")
                PASSWORD = PASSWORD or _cfg.get("pass")
        except Exception:
            pass

EMAIL = EMAIL or "thepersonlovecat@gmail.com"
PASSWORD = PASSWORD or "123123qwe"

session = requests.Session()
session.verify = False
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
    'Accept': 'application/json'
})

# Danh sách 15 kênh TV360+ với cấu hình mã Film4K & Broadpeak
TV360_MAP = {
    '1':  {'cid': 2554, 'bpk': '198', 'name': 'TV360+1',  'logo': 'https://vietanhtv.id.vn/logo/tv360plus1.png', 'is_dash': True},
    '2':  {'cid': 1,    'bpk': '199', 'name': 'TV360+2',  'logo': 'https://vietanhtv.id.vn/logo/tv360plus2.png', 'is_dash': True},
    '3':  {'cid': 148,  'bpk': '200', 'name': 'TV360+3',  'logo': 'https://vietanhtv.id.vn/logo/tv360plus3.png', 'is_dash': True},
    '4':  {'cid': 2458, 'bpk': '201', 'name': 'TV360+4',  'logo': 'https://vietanhtv.id.vn/logo/tv360plus4.png', 'is_dash': True},
    '5':  {'cid': 9867, 'bpk': '367', 'name': 'TV360+5',  'logo': 'https://vietanhtv.id.vn/logo/tv360plus5.png', 'is_dash': True},
    '6':  {'cid': 9868, 'bpk': '368', 'name': 'TV360+6',  'logo': 'https://vietanhtv.id.vn/logo/tv360plus6.png', 'is_dash': True},
    '7':  {'cid': 9869, 'bpk': '369', 'name': 'TV360+7',  'logo': 'https://vietanhtv.id.vn/logo/tv360plus7.png', 'is_dash': True},
    '8':  {'cid': 9870, 'bpk': '370', 'name': 'TV360+8',  'logo': 'https://vietanhtv.id.vn/logo/tv360plus8.png', 'is_dash': True},
    '9':  {'cid': 9887, 'bpk': '379', 'name': 'TV360+9',  'logo': 'https://vietanhtv.id.vn/logo/tv360plus9.png', 'is_dash': False},
    '10': {'cid': 9957, 'bpk': '449', 'name': 'TV360+10', 'logo': 'https://vietanhtv.id.vn/logo/tv360plus10.png', 'is_dash': False},
    '11': {'cid': 9958, 'bpk': '450', 'name': 'TV360+11', 'logo': 'https://vietanhtv.id.vn/logo/tv360plus11.png', 'is_dash': False},
    '12': {'cid': 10001,'bpk': '465', 'name': 'TV360+12', 'logo': 'https://vietanhtv.id.vn/logo/tv360plus12.png', 'is_dash': True},
    '13': {'cid': 10022,'bpk': '471', 'name': 'TV360+13', 'logo': 'https://img-zlr1.tv360.vn/image1/2026/05/15/01/1778782670293/dd4067f28084_480_270.png', 'is_dash': True},
    '14': {'cid': 10023,'bpk': '472', 'name': 'TV360+14', 'logo': 'https://img-zlr1.tv360.vn/image1/2026/05/15/01/177878325467/bbecb3ccb477_480_270.png', 'is_dash': True},
    '15': {'cid': 10024,'bpk': '473', 'name': 'TV360+15', 'logo': 'https://img-zlr1.tv360.vn/image1/2026/05/15/01/1778783528367/ddfa21d56253_480_270.png', 'is_dash': True},
}

def login_film4k():
    """Đăng nhập tài khoản Film4K để lấy quyền gọi stream TV360."""
    login_url = f"{BASE_URL}/api/auth/signin"
    for attempt in range(3):
        try:
            resp = session.post(login_url, json={"email": EMAIL, "password": PASSWORD}, timeout=15)
            if resp.status_code == 200:
                print(f"[OK] Đăng nhập Film4K thành công ({EMAIL})")
                return True
            print(f"[WARN] Đăng nhập Film4K trả về HTTP {resp.status_code}, đang thử lại...")
        except Exception as e:
            print(f"[WARN] Lỗi kết nối Film4K ({attempt+1}/3): {e}")
            time.sleep(1)
    return False

def parse_existing_tv360_m3u():
    """Đọc dữ liệu dự phòng từ file tv360.m3u hiện có."""
    tv360_path = os.path.join(SCRIPT_DIR, 'tv360.m3u')
    fallback_data = {}
    if not os.path.exists(tv360_path):
        return fallback_data

    try:
        with open(tv360_path, 'r', encoding='utf-8') as f:
            content = f.read()
        blocks = re.split(r'(?=#EXTINF:)', content)
        for b in blocks:
            if not b.strip().startswith('#EXTINF:'):
                continue
            m = re.search(r'tvg-id="tv360plus(\d+)"', b)
            if not m:
                continue
            ch_num = m.group(1)
            key_m = re.search(r'#KODIPROP:inputstream\.adaptive\.license_key=([^\r\n]+)', b)
            lines = [l.strip() for l in b.splitlines() if l.strip()]
            url = lines[-1] if lines and lines[-1].startswith('http') else ''
            fallback_data[ch_num] = {
                'url': url,
                'drm_key': key_m.group(1).strip() if key_m else '',
                'block': b.strip()
            }
    except Exception as e:
        print(f"[WARN] Lỗi đọc fallback tv360.m3u: {e}")
    return fallback_data

def fetch_fresh_tv360_channels():
    """Lấy luồng và DRM ClearKey tươi mới cho 15 kênh TV360+ từ Film4K API."""
    fallback_info = parse_existing_tv360_m3u()
    tv360_results = {}

    has_logged_in = login_film4k()
    if not has_logged_in:
        print("[WARN] Không đăng nhập được Film4K, sử dụng dữ liệu đã lưu trong tv360.m3u.")

    def fetch_single_tv360(ch_num, info):
        cid = info['cid']
        bpk = info['bpk']
        final_url = ""
        drm_key = ""

        if has_logged_in:
            for _ in range(3):
                try:
                    r = session.get(f"{BASE_URL}/api/tv/{cid}/stream", timeout=12)
                    if r.status_code == 200:
                        data = r.json()
                        stream_url = data.get('url', '')
                        ck = data.get('clearKey')
                        if ck and ck.get('keyId') and ck.get('key'):
                            drm_key = f"{ck['keyId']}:{ck['key']}"

                        # Phân giải redirect 307 cho luồng Broadpeak để lấy link bpk-token sạch
                        if 'fo-hlc' in stream_url:
                            try:
                                r_redir = requests.get(stream_url, allow_redirects=False, verify=False, timeout=6)
                                if 'Location' in r_redir.headers:
                                    loc = r_redir.headers['Location']
                                    m = re.search(r'(https://[^/]+/bpk-token/[^/]+/bpk-tv/' + bpk + r'/output/index\.(?:mpd|m3u8))', loc)
                                    if m:
                                        stream_url = m.group(1)
                            except Exception:
                                pass

                        final_url = stream_url
                        break
                except Exception:
                    time.sleep(0.5)

        # Nếu không lấy được qua API, dùng lại dữ liệu cũ từ tv360.m3u
        if not final_url and ch_num in fallback_info:
            final_url = fallback_info[ch_num].get('url', '')
        if not drm_key and ch_num in fallback_info:
            drm_key = fallback_info[ch_num].get('drm_key', '')

        return ch_num, {
            'name': info['name'],
            'logo': info['logo'],
            'bpk': bpk,
            'is_dash': info['is_dash'],
            'url': final_url,
            'drm_key': drm_key
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_single_tv360, ch_num, info) for ch_num, info in TV360_MAP.items()]
        for f in as_completed(futures):
            ch_num, res = f.result()
            tv360_results[ch_num] = res

    # Cập nhật và lưu lại file tv360.m3u
    tv360_m3u_lines = []
    for i in range(1, 16):
        ch_num = str(i)
        data = tv360_results.get(ch_num)
        if not data or not data['url']:
            continue

        cname = data['name']
        logo = data['logo']
        extinf = f'#EXTINF:-1 tvg-id="tv360plus{ch_num}" group-title="Sự Kiện TV360" tvg-logo="{logo}", {cname}'
        block = [extinf, '#EXTVLCOPT:http-user-agent=Dalvik/2.1.0']

        if data['is_dash']:
            block.append('#KODIPROP:inputstream.adaptive.manifest_type=mpd')
            if data['drm_key']:
                block.append('#KODIPROP:inputstream.adaptive.license_type=clearkey')
                block.append(f'#KODIPROP:inputstream.adaptive.license_key={data["drm_key"]}')

        block.append(data['url'])
        tv360_m3u_lines.append('\n'.join(block))

    tv360_full_text = '\n\n'.join(tv360_m3u_lines) + '\n'
    tv360_path = os.path.join(SCRIPT_DIR, 'tv360.m3u')
    with open(tv360_path, 'w', encoding='utf-8') as f:
        f.write(tv360_full_text)
    print(f"[OK] Đã cập nhật 15 kênh TV360+ vào {tv360_path}")

    return tv360_results

def fetch_vietnam_channels():
    """Bóc tách danh sách kênh Việt Nam từ nguồn VIP TV365 (FPT Play, VTVGo, vtvprime...)."""
    vip_url = "https://raw.githubusercontent.com/VIET-NAM-VIP/TOI-YEU-VIET-NAM/refs/heads/main/VIETNAM"
    codeberg_url = "https://codeberg.org/TV365/TV365-STREAM/raw/branch/main/VIETNAM.m3u"

    raw_text = ""
    try:
        r = requests.get(vip_url, timeout=12)
        if r.status_code == 200 and len(r.text) > 1000:
            raw_text = r.text
            print(f"[OK] Tải danh sách TV365 VIP từ GitHub ({len(raw_text)} bytes)")
    except Exception as e:
        print(f"[WARN] Không thể tải TV365 VIP từ GitHub: {e}")

    if not raw_text:
        try:
            r = requests.get(codeberg_url, timeout=12)
            if r.status_code == 200:
                raw_text = r.text
                print(f"[OK] Tải danh sách dự phòng từ Codeberg ({len(raw_text)} bytes)")
        except Exception as e:
            print(f"[WARN] Không thể tải TV365 từ Codeberg: {e}")

    cached_json = os.path.join(SCRIPT_DIR, "tv365_channels.json")
    if not raw_text and os.path.exists(cached_json):
        try:
            with open(cached_json, "r", encoding="utf-8") as f:
                channels = json.load(f)
                print(f"[OK] Sử dụng danh sách cache cục bộ ({len(channels)} kênh)")
                return channels
        except Exception:
            pass

    if not raw_text:
        print("[ERROR] Không tải được dữ liệu kênh Việt Nam!")
        return []

    lines = raw_text.splitlines()
    channels = []
    current = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            comma = line.rfind(",")
            name = line[comma + 1:].strip() if comma >= 0 else "Kênh không tên"
            logo_m = re.search(r'tvg-logo="([^"]*)"', line, re.I)
            group_m = re.search(r'group-title="([^"]*)"', line, re.I)
            id_m = re.search(r'tvg-id="([^"]*)"', line, re.I)

            # Lọc bỏ nếu kênh bị trùng tên TV360+ (để ưu tiên cụm TV360+ chính chủ)
            if "tv360+" in name.lower() or "tv360 plus" in name.lower():
                current = None
                continue

            current = {
                "name": name,
                "logo": logo_m.group(1) if logo_m else "",
                "group": group_m.group(1) if group_m else "KÊNH KHÁC",
                "id": id_m.group(1) if id_m else "",
                "drm_key": "",
                "license_type": "",
                "user_agent": "",
                "referer": "",
                "url": ""
            }
        elif line.startswith("#KODIPROP:inputstream.adaptive.license_key="):
            if current:
                current["drm_key"] = line.split("=", 1)[1].strip()
        elif line.startswith("#KODIPROP:inputstream.adaptive.license_type="):
            if current:
                current["license_type"] = line.split("=", 1)[1].strip()
        elif line.startswith("#EXTVLCOPT:http-user-agent="):
            if current:
                current["user_agent"] = line.split("=", 1)[1].strip()
        elif line.startswith("#EXTVLCOPT:http-referrer="):
            if current:
                current["referer"] = line.split("=", 1)[1].strip()
        elif not line.startswith("#") and current:
            current["url"] = line
            channels.append(current)
            current = None

    print(f"[OK] Bóc tách thành công {len(channels)} kênh Việt Nam từ TV365.")

    # Lưu lại file json
    with open(cached_json, "w", encoding="utf-8") as f:
        json.dump(channels, f, indent=2, ensure_ascii=False)

    return channels

def build_merged_playlists(tv360_data, vn_channels):
    """
    Ghép cụm 15 kênh Sự Kiện TV360+ và 252 kênh Việt Nam từ TV365.
    Xuất ra:
    - danh_sach_kenh_potplayer.m3u
    - danh_sach_kenh_tivimate.m3u
    - danh_sach_kenh_film4k.m3u
    - playlist.m3u
    - tv365_playlist.m3u
    """
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Phân loại nhóm kênh TV365 theo thứ tự ưu tiên hiển thị
    group_order = [
        'VTV',
        'Thiết yếu',
        'HTV',
        'VTVcab',
        'SCTV',
        'Thiếu Nhi',
        'Nghe nhạc',
        'Địa phương',
        'Quốc tế'
    ]

    grouped_vn = defaultdict(list)
    for c in vn_channels:
        grp = c.get('group', 'KÊNH KHÁC')
        grouped_vn[grp].append(c)

    # Thêm các nhóm khác chưa có trong danh sách
    for g in grouped_vn:
        if g not in group_order:
            group_order.append(g)

    # Khởi tạo danh sách các dòng M3U
    header = f'#EXTM3U url-tvg="https://vnepg.site/epg.xml" name="KenhVN IPTV" updated="{now_str}"'
    lines_pot = [header]
    lines_tivi = [header]
    lines_tv365_only = [header]

    # ==========================================
    # PHẦN 1: CỤM 15 KÊNH SỰ KIỆN THỂ THAO TV360+
    # ==========================================
    for i in range(1, 16):
        ch_num = str(i)
        info = tv360_data.get(ch_num)
        if not info or not info.get('url'):
            continue

        cname = info['name']
        logo = info['logo']
        surl = info['url']
        is_dash = info['is_dash']
        drm_key = info['drm_key']

        extinf = f'#EXTINF:-1 tvg-id="tv360plus{ch_num}" tvg-name="{cname}" tvg-logo="{logo}" group-title="Sự Kiện TV360",{cname}'

        # 1. Cho PotPlayer / VLC
        lines_pot.append(extinf)
        lines_pot.append('#EXTVLCOPT:http-user-agent=Dalvik/2.1.0')
        if is_dash:
            lines_pot.append('#KODIPROP:inputstream.adaptive.manifest_type=mpd')
            if drm_key:
                lines_pot.append('#KODIPROP:inputstream.adaptive.license_type=clearkey')
                lines_pot.append(f'#KODIPROP:inputstream.adaptive.license_key={drm_key}')
        lines_pot.append(surl)

        # 2. Cho TiviMate / Universal
        lines_tivi.append(extinf)
        lines_tivi.append('#EXTVLCOPT:http-user-agent=Dalvik/2.1.0')
        if is_dash:
            lines_tivi.append('#KODIPROP:inputstream.adaptive.manifest_type=mpd')
            if drm_key:
                lines_tivi.append('#KODIPROP:inputstream.adaptive.license_type=clearkey')
                lines_tivi.append(f'#KODIPROP:inputstream.adaptive.license_key={drm_key}')
        lines_tivi.append(surl)

    # ==========================================
    # PHẦN 2: CÁC KÊNH VIỆT NAM TỪ TV365 VIP
    # ==========================================
    for grp_name in group_order:
        channels_in_grp = grouped_vn.get(grp_name, [])
        for c in channels_in_grp:
            cname = c.get('name', '')
            cid = c.get('id', '')
            logo = c.get('logo', '')
            surl = c.get('url', '')
            drm_key = c.get('drm_key', '')
            ua = c.get('user_agent', '')
            referer = c.get('referer', '')

            # Tự động gán referer cho luồng vmttv nếu có
            if not referer and "vmttv.dpdns.org" in surl:
                referer = "https://vmttv.dpdns.org/VTVGo/"
                ua = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"

            extinf = f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp_name}",{cname}'

            # --- Dành cho PotPlayer / VLC ---
            lines_pot.append(extinf)
            if drm_key:
                lines_pot.append('#KODIPROP:inputstream.adaptive.license_type=clearkey')
                lines_pot.append(f'#KODIPROP:inputstream.adaptive.license_key={drm_key}')
            if ua:
                lines_pot.append(f'#EXTVLCOPT:http-user-agent={ua}')
            if referer:
                lines_pot.append(f'#EXTVLCOPT:http-referrer={referer}')
            lines_pot.append(surl)

            # --- Dành cho TiviMate / Android TV ---
            lines_tivi.append(extinf)
            if drm_key:
                lines_tivi.append('#KODIPROP:inputstream.adaptive.license_type=clearkey')
                lines_tivi.append(f'#KODIPROP:inputstream.adaptive.license_key={drm_key}')
            if ua:
                lines_tivi.append(f'#EXTVLCOPT:http-user-agent={ua}')
            if referer:
                lines_tivi.append(f'#EXTVLCOPT:http-referrer={referer}')

            # Định dạng Pipe headers cho TiviMate nếu cần gửi header riêng
            pipe_parts = []
            if ua:
                pipe_parts.append(f"User-Agent={ua}")
            if referer:
                pipe_parts.append(f"Referer={referer}")

            if pipe_parts and not ("|" in surl):
                tivi_stream_url = f"{surl}|{'&'.join(pipe_parts)}"
            else:
                tivi_stream_url = surl

            lines_tivi.append(tivi_stream_url)

            # --- Dành cho TV365 Only ---
            lines_tv365_only.append(extinf)
            if drm_key:
                lines_tv365_only.append('#KODIPROP:inputstream.adaptive.license_type=clearkey')
                lines_tv365_only.append(f'#KODIPROP:inputstream.adaptive.license_key={drm_key}')
            if ua:
                lines_tv365_only.append(f'#EXTVLCOPT:http-user-agent={ua}')
            if referer:
                lines_tv365_only.append(f'#EXTVLCOPT:http-referrer={referer}')
            lines_tv365_only.append(surl)

    # Ghi file danh_sach_kenh_potplayer.m3u
    file_pot = os.path.join(SCRIPT_DIR, 'danh_sach_kenh_potplayer.m3u')
    with open(file_pot, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines_pot) + '\n')

    # Ghi file danh_sach_kenh_tivimate.m3u
    file_tivi = os.path.join(SCRIPT_DIR, 'danh_sach_kenh_tivimate.m3u')
    with open(file_tivi, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines_tivi) + '\n')

    # Ghi file playlist.m3u & danh_sach_kenh_film4k.m3u (chuẩn dùng chung)
    file_main = os.path.join(SCRIPT_DIR, 'playlist.m3u')
    with open(file_main, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines_tivi) + '\n')

    file_film4k = os.path.join(SCRIPT_DIR, 'danh_sach_kenh_film4k.m3u')
    with open(file_film4k, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines_tivi) + '\n')

    # Ghi file tv365_playlist.m3u
    file_tv365 = os.path.join(SCRIPT_DIR, 'tv365_playlist.m3u')
    with open(file_tv365, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines_tv365_only) + '\n')

    total_channels = len(tv360_data) + len(vn_channels)
    print("\n" + "=" * 60)
    print("🎉 HOÀN TẤT TẠO PLAYLIST HỢP NHẤT:")
    print(f"  - ⚡ 15 Kênh TV360+ (kèm fresh token & ClearKey DRM)")
    print(f"  - 📺 {len(vn_channels)} Kênh Việt Nam chất lượng cao (từ TV365)")
    print(f"  - 🌟 Tổng cộng: {total_channels} kênh")
    print(f"  - 📁 Đã ghi: danh_sach_kenh_potplayer.m3u, danh_sach_kenh_tivimate.m3u, playlist.m3u, danh_sach_kenh_film4k.m3u, tv360.m3u")
    print("=" * 60)

def main():
    print("=" * 60)
    print("BẮT ĐẦU CẬP NHẬT KÊNH TV365 & TOKEN TV360+")
    print("=" * 60)

    start_time = time.time()
    # 1. Lấy token tươi mới cho 15 kênh TV360+
    print("\n[Bước 1/2] Lấy fresh token & ClearKey cho 15 kênh TV360+...")
    tv360_data = fetch_fresh_tv360_channels()

    # 2. Bóc tách 252 kênh Việt Nam từ TV365 VIP
    print("\n[Bước 2/2] Bóc tách danh sách kênh Việt Nam từ TV365...")
    vn_channels = fetch_vietnam_channels()

    # 3. Hợp nhất danh sách và xuất file M3U
    build_merged_playlists(tv360_data, vn_channels)

    elapsed = round(time.time() - start_time, 2)
    print(f"⚡ Thời gian thực hiện: {elapsed} giây.")

if __name__ == '__main__':
    main()
