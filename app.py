import os
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

@app.route('/collect', methods=['POST'])
def collect():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    # سجل بسيط للبيانات المستلمة
    with open('/tmp/received.log', 'a') as f:
        f.write(f"{datetime.now().isoformat()} | {data}\n")

    return jsonify({"status": "ok", "received": len(str(data))}), 200

@app.route('/')
def home():
    return "Server is running", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)