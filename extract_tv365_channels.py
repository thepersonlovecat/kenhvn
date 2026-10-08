import json
import os
import re
import sys
import requests

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def build_tv365_playlist():
    print("[*] TV365 Playlist Extractor starting...")

    # Primary URL for TV365 VIP channels
    vip_url = "https://raw.githubusercontent.com/VIET-NAM-VIP/TOI-YEU-VIET-NAM/refs/heads/main/VIETNAM"
    codeberg_url = "https://codeberg.org/TV365/TV365-STREAM/raw/branch/main/VIETNAM.m3u"

    raw_text = ""
    try:
        r = requests.get(vip_url, timeout=10)
        if r.status_code == 200 and len(r.text) > 1000:
            raw_text = r.text
            print(f"[+] Fetched VIP playlist from GitHub ({len(raw_text)} bytes)")
    except Exception as e:
        print(f"[!] Failed to fetch VIP GitHub playlist: {e}")

    if not raw_text:
        try:
            r = requests.get(codeberg_url, timeout=10)
            if r.status_code == 200:
                raw_text = r.text
                print(f"  Fetched backup playlist from Codeberg ({len(raw_text)} bytes)")
        except Exception as e:
            print(f"  Failed to fetch Codeberg playlist: {e}")

    if not raw_text and os.path.exists("tv365_extracted/VIETNAM_VIP.m3u"):
        with open("tv365_extracted/VIETNAM_VIP.m3u", "r", encoding="utf-8") as f:
            raw_text = f.read()
        print("  Using locally cached VIETNAM_VIP.m3u")

    if not raw_text:
        print("  No playlist data available.")
        return

    # Parse M3U
    lines = raw_text.splitlines()
    channels = []
    current = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            comma = line.rfind(",")
            name = line[comma + 1:].strip() if comma >= 0 else "K nh ch a r "
            logo_m = re.search(r'tvg-logo="([^"]*)"', line, re.I)
            group_m = re.search(r'group-title="([^"]*)"', line, re.I)
            id_m = re.search(r'tvg-id="([^"]*)"', line, re.I)

            current = {
                "name": name,
                "logo": logo_m.group(1) if logo_m else "",
                "group": group_m.group(1) if group_m else "KH C",
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

    print(f"  Parsed {len(channels)} channels.")

    # Save channels.json
    with open("tv365_channels.json", "w", encoding="utf-8") as f:
        json.dump(channels, f, indent=2, ensure_ascii=False)
    print("  Saved tv365_channels.json")

    # Generate enhanced M3U playlist
    m3u_lines = ['#EXTM3U url-tvg="https://vnepg.site/epg.xml"']
    for c in channels:
        extinf = f'#EXTINF:-1 tvg-id="{c["id"]}" tvg-name="{c["name"]}" tvg-logo="{c["logo"]}" group-title="{c["group"]}",{c["name"]}'
        m3u_lines.append(extinf)
        if c["drm_key"]:
            m3u_lines.append(f'#KODIPROP:inputstream.adaptive.license_type=clearkey')
            m3u_lines.append(f'#KODIPROP:inputstream.adaptive.license_key={c["drm_key"]}')
        if c["user_agent"]:
            m3u_lines.append(f'#EXTVLCOPT:http-user-agent={c["user_agent"]}')
        if c["referer"]:
            m3u_lines.append(f'#EXTVLCOPT:http-referrer={c["referer"]}')
        elif "vmttv.dpdns.org" in c["url"]:
            m3u_lines.append('#EXTVLCOPT:http-referrer=https://vmttv.dpdns.org/VTVGo/')
            m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36')
        m3u_lines.append(c["url"])

    with open("tv365_playlist.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_lines) + "\n")
    print("  Saved tv365_playlist.m3u")

if __name__ == "__main__":
    build_tv365_playlist()
    try:
        import auto_update_channels
        print("\n[*] Đang tự động cập nhật token TV360+ và hợp nhất vào playlist.m3u...")
        auto_update_channels.main()
    except Exception as e:
        print(f"[!] Không thể chạy hợp nhất auto_update_channels: {e}")

