import os
import sys
import urllib.request
import urllib.parse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

INPUT_URL = "https://tivi.k-20.xyz/a"
PROXY_ENDPOINT = "https://fiml4k.fun/api/iptv/stream?url="
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "danh_sach_kenh_film4k_proxy.m3u")

def wrap_playlist(content):
    lines = content.splitlines()
    wrapped_lines = []
    count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("http://") or stripped.startswith("https://"):
            # Nếu URL đã bọc proxy rồi thì không bọc lại
            if stripped.startswith(PROXY_ENDPOINT):
                wrapped_lines.append(stripped)
                continue
            if "|" in stripped:
                url_part, pipe_part = stripped.split("|", 1)
                wrapped_url = f"{PROXY_ENDPOINT}{urllib.parse.quote(url_part, safe='')}|{pipe_part}"
            else:
                wrapped_url = f"{PROXY_ENDPOINT}{urllib.parse.quote(stripped, safe='')}"
            wrapped_lines.append(wrapped_url)
            count += 1
        else:
            wrapped_lines.append(line)
    return "\n".join(wrapped_lines) + "\n", count

def main():
    print(f"[*] Đang tải playlist từ: {INPUT_URL}")
    req = urllib.request.Request(INPUT_URL, headers={
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content = resp.read().decode("utf-8")
    except Exception as e:
        print(f"[!] Không thể tải playlist trực tiếp ({e}), sử dụng scratch_a.m3u nếu có...")
        with open("scratch_a.m3u", "r", encoding="utf-8") as f:
            content = f.read()

    wrapped_content, count = wrap_playlist(content)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(wrapped_content)

    print(f"[✓] Đã bọc thành công {count} luồng stream qua proxy Film4K!")
    print(f"[✓] File danh sách đã lưu tại: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
