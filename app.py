import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# مسار تخزين مؤقت (يضيع عند إعادة التشغيل)
DATA_FILE = '/tmp/received_data.json'

def load_data():
    """تحميل البيانات المحفوظة"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_data(data_list):
    """حفظ البيانات"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data_list, f, ensure_ascii=False, indent=2)

@app.route('/')
def home():
    return "Server is running", 200

@app.route('/collect', methods=['POST'])
def collect():
    """استقبال البيانات من البرنامج"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    # تحميل البيانات السابقة
    all_data = load_data()

    # إضافة البيانات الجديدة مع وقت الاستلام
    entry = {
        "received_at": datetime.now().isoformat(),
        "ip": request.remote_addr,
        "data": data
    }
    all_data.append(entry)

    # الاحتفاظ بآخر 500 مدخل فقط (لتجنب امتلاء الملف)
    if len(all_data) > 500:
        all_data = all_data[-500:]

    save_data(all_data)

    return jsonify({"status": "ok", "received": len(str(data))}), 200

@app.route('/view')
def view():
    """صفحة عرض البيانات"""
    all_data = load_data()
    
    # عكس الترتيب (الأحدث أولاً)
    all_data = list(reversed(all_data))
    
    # قالب HTML بسيط
    html = """
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>البيانات المستلمة</title>
        <style>
            body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }
            h1 { color: #e94560; }
            .stats { background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
            .entry { background: #0f3460; padding: 15px; border-radius: 8px; margin-bottom: 10px; border-right: 4px solid #e94560; }
            .time { color: #f9a826; font-size: 12px; }
            .ip { color: #999; font-size: 12px; }
            pre { background: #000; padding: 10px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; color: #0f0; }
            .empty { color: #999; text-align: center; padding: 50px; }
            .refresh { background: #e94560; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <h1>📦 البيانات المستلمة</h1>
        <div class="stats">
            <strong>إجمالي المدخلات:</strong> {{ total }}
        </div>
        <a href="/view" class="refresh">🔄 تحديث</a>
        
        {% if data %}
            {% for entry in data %}
            <div class="entry">
                <div class="time">⏰ {{ entry.received_at }}</div>
                <div class="ip">🌐 {{ entry.ip }}</div>
                <pre>{{ entry.data | tojson(indent=2) }}</pre>
            </div>
            {% endfor %}
        {% else %}
            <div class="empty">لا توجد بيانات بعد. أرسل طلب POST إلى /collect</div>
        {% endif %}
    </body>
    </html>
    """
    
    return render_template_string(html, data=all_data, total=len(all_data))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
