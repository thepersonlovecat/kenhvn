import os
import sys
import ssl
import json
import urllib.request
import urllib.error
import http.cookiejar
from flask import Flask, render_template, request, jsonify, Response, redirect

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

app = Flask(__name__, template_folder='templates', static_folder='static')

BASE_URL = "https://fiml4k.fun"
CDN_BASE = "https://cdn.fiml4k.fun"
DEFAULT_EMAIL = "thepersonlovecat@gmail.com"
DEFAULT_PASS = "123123qwe"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    urllib.request.HTTPSHandler(context=ctx)
)

USER_AGENT = 'Mozilla/5.0 (Linux; Android 14; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36'

def ensure_login(email=DEFAULT_EMAIL, password=DEFAULT_PASS):
    login_url = f"{BASE_URL}/api/auth/signin"
    payload = json.dumps({"email": email, "password": password}).encode('utf-8')
    headers = {
        'User-Agent': USER_AGENT,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    req = urllib.request.Request(login_url, data=payload, headers=headers, method='POST')
    try:
        with opener.open(req, timeout=10) as resp:
            print("Đăng nhập thành công:", email)
            return resp.status == 200
    except Exception as e:
        print("Login failed:", e)
        return False

# Ensure initial login
ensure_login()

def proxy_request(endpoint, headers_extra=None):
    url = f"{BASE_URL}{endpoint}" if endpoint.startswith('/') else f"{BASE_URL}/{endpoint}"
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'application/json'
    }
    if headers_extra:
        headers.update(headers_extra)
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=12) as resp:
            return resp.status, resp.read(), resp.headers
    except urllib.error.HTTPError as e:
        if e.code == 401:
            ensure_login()
            with opener.open(req, timeout=12) as resp2:
                return resp2.status, resp2.read(), resp2.headers
        return e.code, e.read(), e.headers
    except Exception as e:
        return 500, json.dumps({"error": str(e)}).encode('utf-8'), {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/<path:subpath>')
def proxy_all_api(subpath):
    full_path = f"/api/{subpath}"
    if request.query_string:
        full_path += f"?{request.query_string.decode('utf-8')}"
    status, data, headers = proxy_request(full_path)
    content_type = headers.get('Content-Type', 'application/json') if isinstance(headers, dict) else 'application/json'
    return Response(data, status=status, mimetype=content_type, headers={'Access-Control-Allow-Origin': '*'})

# HLS Playlist Proxy: Globally rewrites /api/hls/ and cdn.fiml4k.fun/tt/
@app.route('/proxy/hls/<path:subpath>')
def proxy_hls(subpath):
    target_url = f"{BASE_URL}/api/hls/{subpath}"
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"
    headers = {'User-Agent': USER_AGENT, 'Accept': '*/*'}
    req = urllib.request.Request(target_url, headers=headers)
    try:
        with opener.open(req, timeout=15) as resp:
            content = resp.read()
            content_type = resp.headers.get('Content-Type', 'application/vnd.apple.mpegurl')
            
            # Rewrite all M3U8 playlists globally
            if subpath.endswith('.m3u8') or 'application/vnd.apple.mpegurl' in content_type:
                text = content.decode('utf-8', errors='replace')
                # 1. Replace all /api/hls/ with /proxy/hls/
                text = text.replace('/api/hls/', '/proxy/hls/')
                # 2. Replace all https://cdn.fiml4k.fun/tt/ with /proxy/cdn/tt/
                text = text.replace('https://cdn.fiml4k.fun/tt/', '/proxy/cdn/tt/')
                # 3. Replace any cdn.fiml4k.fun/tt/
                text = text.replace('http://cdn.fiml4k.fun/tt/', '/proxy/cdn/tt/')
                return Response(
                    text,
                    status=resp.status,
                    mimetype='application/vnd.apple.mpegurl',
                    headers={
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': '*',
                        'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
                        'Cache-Control': 'no-cache'
                    }
                )
            return Response(content, status=resp.status, mimetype=content_type, headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        return Response(f"#EXTM3U\n#ERROR: {e}", status=500, mimetype='text/plain')

# CDN Video Segment Proxy: Strips the 67-byte fake PNG header to reveal raw fMP4 video chunks
@app.route('/proxy/cdn/tt/<path:seg_path>')
def proxy_cdn_segment(seg_path):
    target_url = f"{CDN_BASE}/tt/{seg_path}"
    headers = {'User-Agent': USER_AGENT, 'Accept': '*/*'}
    req = urllib.request.Request(target_url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=25) as resp:
            data = resp.read()
            # If disguised as PNG image, strip the 67-byte PNG envelope
            if data.startswith(b'\x89PNG\r\n\x1a\n'):
                iend_pos = data.find(b'IEND')
                if iend_pos != -1:
                    data = data[iend_pos + 8:]
                else:
                    data = data[67:]
            
            # Handle Range header if requested
            range_header = request.headers.get('Range', None)
            if range_header and range_header.startswith('bytes='):
                try:
                    ranges = range_header[6:].split('-')
                    start = int(ranges[0]) if ranges[0] else 0
                    end = int(ranges[1]) if ranges[1] else len(data) - 1
                    sliced = data[start:end+1]
                    return Response(
                        sliced,
                        status=206,
                        mimetype='video/mp4',
                        headers={
                            'Content-Range': f'bytes {start}-{end}/{len(data)}',
                            'Accept-Ranges': 'bytes',
                            'Content-Length': str(len(sliced)),
                            'Access-Control-Allow-Origin': '*',
                            'Access-Control-Allow-Headers': '*',
                            'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS'
                        }
                    )
                except Exception:
                    pass

            return Response(
                data,
                status=200,
                mimetype='video/mp4',
                headers={
                    'Accept-Ranges': 'bytes',
                    'Content-Length': str(len(data)),
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': '*',
                    'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
                    'Cache-Control': 'public, max-age=3600'
                }
            )
    except Exception as e:
        print(f"Error fetching CDN segment {seg_path[:30]}...: {e}")
        return Response(b"", status=500)

# TV Stream proxy
@app.route('/proxy/tv/<path:subpath>')
def proxy_tv(subpath):
    target_url = f"{BASE_URL}/api/tv/{subpath}"
    if request.query_string:
        target_url += f"?{request.query_string.decode('utf-8')}"
    headers = {'User-Agent': USER_AGENT, 'Accept': '*/*'}
    req = urllib.request.Request(target_url, headers=headers)
    try:
        with opener.open(req, timeout=15) as resp:
            content = resp.read()
            # If the response is JSON containing {"url": "..."} and client expects video/m3u8, redirect
            if subpath.endswith('/stream') or 'application/json' in resp.headers.get('Content-Type', ''):
                try:
                    js = json.loads(content.decode('utf-8'))
                    if isinstance(js, dict) and 'url' in js:
                        stream_url = js['url']
                        if stream_url.startswith('/'):
                            stream_url = f"{BASE_URL}{stream_url}"
                        if request.args.get('format') != 'json':
                            return redirect(stream_url, code=302)
                except Exception:
                    pass
            return Response(
                content,
                status=resp.status,
                mimetype=resp.headers.get('Content-Type', 'application/vnd.apple.mpegurl'),
                headers={
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': '*',
                    'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS'
                }
            )
    except Exception as e:
        return Response(f"#EXTM3U\n#ERROR: {e}", status=500, mimetype='text/plain')

if __name__ == '__main__':
    print("================================================================")
    print("🚀 FILM4K WEB STREAMER & CATALOG SERVER IS RUNNING")
    print("👉 Mở trình duyệt tại: http://localhost:5000")
    print("👉 Đã kích hoạt giải mã PNG envelope cho toàn bộ Video 1080p & 4K")
    print("================================================================")
    app.run(host='0.0.0.0', port=5000, debug=False)
