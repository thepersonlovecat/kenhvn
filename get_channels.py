import sys
import os
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

BASE_URL = "https://fiml4k.fun"
DEFAULT_EMAIL = "thepersonlovecat@gmail.com"
DEFAULT_PASS = "123123qwe"

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
            resp = session.post(login_url, json={"email": DEFAULT_EMAIL, "password": DEFAULT_PASS}, timeout=25)
            if resp.status_code == 200:
                print(f" Đăng nhập thành công tài khoản: {DEFAULT_EMAIL}")
                return True
        except Exception as e:
            print(f"Lỗi kết nối ({attempt+1}/5): {e}")
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
    print("⏳ Đang kết nối tới máy chủ Film4K...")
    if not login():
        print("❌ Đăng nhập thất bại!")
        return

    channels = fetch_channels()
    events = fetch_events()
    print(f"✅ Đã tìm thấy {len(channels)} kênh và {len(events)} sự kiện.")

    print(f"⏳ Đang lấy link stream gốc cho {len(channels)} kênh...")
    results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_stream_url, ch): ch for ch in channels}
        done = 0
        for future in as_completed(futures):
            res = future.result()
            results[res['id']] = res
            done += 1
            if done % 30 == 0 or done == len(channels):
                print(f"   Đã xử lý {done}/{len(channels)} kênh...")

    ordered = [results[ch['id']] for ch in channels if ch['id'] in results]

    # 1. Lưu direct_streams.json
    with open('direct_streams.json', 'w', encoding='utf-8') as f:
        json.dump(ordered, f, ensure_ascii=False, indent=2)

    # 2. Lưu channels_live.json
    with open('channels_live.json', 'w', encoding='utf-8') as f:
        json.dump({"channels": channels, "events": events}, f, ensure_ascii=False, indent=2)

    preferred_order = [
        'KÊNH KHÁC',
        'Kênh thiết yếu',
        'Kênh VTV',
        'Sự kiện trực tiếp',
        'Giải trí',
        'Thể thao',
        'Kênh quốc tế',
        'Kênh Vĩnh Long',
        'Kênh HTV',
        'Kênh FM',
        'Kênh SCTV',
        'Kênh VTV Cab',
        'Kênh địa phương'
    ]

    groups = defaultdict(list)
    for c in ordered:
        grp = c.get('category') or 'KÊNH KHÁC'
        groups[grp].append(c)

    for g in groups:
        if g not in preferred_order:
            preferred_order.append(g)

    # 3. Tạo danh_sach_kenh_film4k.m3u
    m3u_lines = ['#EXTM3U']
    for grp_name in preferred_order:
        if grp_name not in groups:
            continue
        for c in groups[grp_name]:
            cid = str(c.get('id', '')).strip()
            cname = str(c.get('name', '')).strip()
            logo = c.get('logo', '') or ''
            stream_url = c.get('stream_url', '')
            if not stream_url:
                continue
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{cname}" tvg-logo="{logo}" group-title="{grp_name}",{cname}')
            m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36')
            m3u_lines.append(stream_url)

    with open('danh_sach_kenh_film4k.m3u', 'w', encoding='utf-8') as f:
        f.write('\n'.join(m3u_lines))

    # 4. Tạo danh_sach_kenh_truyen_hinh_film4k.txt
    lines = []
    lines.append('=' * 80)
    lines.append('            DANH SÁCH TOÀN BỘ KÊNH TRUYỀN HÌNH TRỰC TIẾP (FILM4K TV)')
    lines.append(f'Tài khoản: {DEFAULT_EMAIL}')
    lines.append(f'Tổng số kênh: {len(channels)} kênh (Kèm đầy đủ LINK STREAM GỐC M3U8)')
    lines.append(f'Thời gian cập nhật: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append('=' * 80)
    lines.append('')

    for grp_name in preferred_order:
        if grp_name not in groups:
            continue
        chs = groups[grp_name]
        lines.append('-' * 80)
        lines.append(f'★ NHÓM: {grp_name.upper()} ({len(chs)} kênh)')
        lines.append('-' * 80)
        for c in chs:
            cid = str(c.get('id', '')).strip()
            cname = str(c.get('name', '')).strip()
            surl = c.get('stream_url', '')
            lines.append(f'  • ID: {cid:<10} | {cname}')
            lines.append(f'    Link Stream gốc: {surl}')
        lines.append('')

    with open('danh_sach_kenh_truyen_hinh_film4k.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"\n🎉 Hoàn thành! Đã cập nhật 100% link stream gốc ({len(ordered)} kênh) vào:")
    print("   👉 danh_sach_kenh_film4k.m3u")
    print("   👉 danh_sach_kenh_truyen_hinh_film4k.txt")
    print("   👉 direct_streams.json")

if __name__ == '__main__':
    main()
