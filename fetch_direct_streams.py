import sys
import json
import time
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_URL = "https://fiml4k.fun"
EMAIL = "thepersonlovecat@gmail.com"
PASS = "123123qwe"

session = requests.Session()
session.verify = False
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
    'Accept': 'application/json'
})

print("1. Đang đăng nhập tài khoản...")
logged_in = False
for attempt in range(5):
    try:
        resp = session.post(
            f"{BASE_URL}/api/auth/signin",
            json={"email": EMAIL, "password": PASS},
            timeout=25
        )
        if resp.status_code == 200:
            print(" Đăng nhập thành công!")
            logged_in = True
            break
        else:
            print(f"Đăng nhập thất bại status: {resp.status_code}")
    except Exception as e:
        print(f"Lỗi kết nối ({attempt+1}/5): {e}")
        time.sleep(1)

if not logged_in:
    print("Không thể đăng nhập. Thoát.")
    sys.exit(1)

# Đọc danh sách 188 kênh từ channels_live.json
with open('channels_live.json', 'r', encoding='utf-8') as f:
    channels = json.load(f)['channels']

print(f"2. Bắt đầu lấy link stream gốc cho {len(channels)} kênh...")

def fetch_channel_stream(ch):
    cid = ch['id']
    name = ch['name']
    url = f"{BASE_URL}/api/tv/{cid}/stream"
    for _ in range(3):
        try:
            r = session.get(url, timeout=12)
            if r.status_code == 200:
                data = r.json()
                stream_url = data.get('url', '')
                if stream_url.startswith('/'):
                    stream_url = f"{BASE_URL}{stream_url}"
                return {
                    "id": cid,
                    "name": name,
                    "category": ch.get('category') or 'KÊNH KHÁC',
                    "logo": ch.get('logo', '') or '',
                    "stream_url": stream_url,
                    "dash": data.get('dash', False),
                    "raw": data,
                    "status": "success"
                }
        except Exception:
            time.sleep(0.5)
    return {
        "id": cid,
        "name": name,
        "category": ch.get('category') or 'KÊNH KHÁC',
        "logo": ch.get('logo', '') or '',
        "stream_url": "",
        "dash": False,
        "raw": None,
        "status": "failed"
    }

results = {}
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = {executor.submit(fetch_channel_stream, ch): ch for ch in channels}
    completed_count = 0
    for future in as_completed(futures):
        res = future.result()
        results[res['id']] = res
        completed_count += 1
        if completed_count % 30 == 0 or completed_count == len(channels):
            print(f"   Đã xử lý {completed_count}/{len(channels)} kênh...")

# Sắp xếp lại theo thứ tự ban đầu
ordered_results = [results[ch['id']] for ch in channels if ch['id'] in results]

# Lưu file JSON đầy đủ link stream gốc
with open('direct_streams.json', 'w', encoding='utf-8') as f:
    json.dump(ordered_results, f, ensure_ascii=False, indent=2)

success_channels = [r for r in ordered_results if r['stream_url']]
print(f"3. Hoàn tất: {len(success_channels)}/{len(channels)} kênh lấy được link stream gốc thành công.")
