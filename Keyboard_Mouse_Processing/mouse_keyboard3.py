import time
import threading
from pynput import keyboard, mouse
from screeninfo import get_monitors
import psutil
import pygetwindow as gw
from flask import Flask, jsonify, request
from flask_cors import CORS

# Flask app
app = Flask(__name__)
CORS(app)  # CORS politikalarını etkinleştir

# Global değişkenler
current_status = 0
selected_targets = []  # Seçilen hedef sekme/pencereler listesi
time_tracking = {}  # Her hedef için harcanan süre takibi
current_active_target = None  # Şu anda aktif olan hedef
last_activity_time = time.time()  # Son aktivite zamanı

# Sistem bilgileri
def check_monitors():
    monitors = get_monitors()
    return len(monitors)

# Klavye dinleyicisi
class ActivityListener:
    def __init__(self, target_window=None, browser_only=False):
        self.last_activity_time = time.time()
        self.monitor_count = check_monitors()
        self.last_window = ""
        self.current_monitor = 0
        self.activity_detected = False
        self.target_window = target_window
        self.browser_only = browser_only
        self.browser_keywords = ['chrome', 'firefox', 'edge', 'opera', 'safari', 'brave']
        self.initial_target_tab = None
        self.target_found = False
        self.tab_changed = False
        self.mouse_activity = False
        self.keyboard_activity = False
        self.selected_targets = []  # Seçilen hedefler listesi

    def on_press(self, key):
        if self.target_found and not self.is_target_window_active():
            self.activity_detected = True
        self.keyboard_activity = True

    def on_move(self, x, y):
        if self.target_found and not self.is_target_window_active():
            self.activity_detected = True
        self.mouse_activity = True

    def is_target_window_active(self):
        global selected_targets, time_tracking, current_active_target, last_activity_time
        active_window = gw.getActiveWindow()
        if not active_window:
            return False

        current_title = active_window.title
        current_time = time.time()

        # Eğer manuel seçim yapılmışsa, o listeyi kullan
        if selected_targets:
            # Önceki aktif hedefin süresini güncelle
            if current_active_target and current_active_target != current_title:
                if current_active_target in time_tracking:
                    time_tracking[current_active_target] += current_time - last_activity_time
                else:
                    time_tracking[current_active_target] = current_time - last_activity_time

            # Sekme değişimini kontrol et (ilk seçilen hedef ile karşılaştır)
            if selected_targets and current_title != selected_targets[0]:
                self.tab_changed = True
            else:
                self.tab_changed = False
            
            # Mevcut sekme seçilen hedefler arasında mı?
            is_target_active = current_title in selected_targets
            
            if is_target_active:
                # Yeni aktif hedefi güncelle
                if current_active_target != current_title:
                    current_active_target = current_title
                    last_activity_time = current_time
                    # İlk kez görüyorsak time_tracking'e ekle
                    if current_title not in time_tracking:
                        time_tracking[current_title] = 0
            else:
                # Hedef olmayan bir penceredeyiz, önceki hedefin süresini güncelle
                if current_active_target:
                    if current_active_target in time_tracking:
                        time_tracking[current_active_target] += current_time - last_activity_time
                    current_active_target = None
                    last_activity_time = current_time
            
            return is_target_active

        # Sekme değişimini kontrol et
        if self.initial_target_tab and current_title != self.initial_target_tab:
            self.tab_changed = True
        else:
            self.tab_changed = False

        if self.browser_only:
            current_lower = current_title.lower()
            is_browser = any(browser in current_lower for browser in self.browser_keywords)

            if is_browser:
                if not self.target_found:
                    self.initial_target_tab = current_title
                    self.target_found = True
                    # İlk hedef için time tracking başlat
                    current_active_target = current_title
                    last_activity_time = current_time
                    if current_title not in time_tracking:
                        time_tracking[current_title] = 0
                    print(f"🎯 Hedef sekme belirlendi: {current_title}")
                    return True

                # Süre takibi güncelle
                if current_title == self.initial_target_tab:
                    if current_active_target != current_title:
                        current_active_target = current_title
                        last_activity_time = current_time
                    return True
                else:
                    # Başka bir sekmedeyiz, süreyi güncelle
                    if current_active_target:
                        if current_active_target in time_tracking:
                            time_tracking[current_active_target] += current_time - last_activity_time
                        current_active_target = None
                        last_activity_time = current_time
                    return False
            return False

        if self.target_window is not None:
            target_title = self.target_window.lower()
            return target_title in current_title.lower()

        return True

    def check_activity(self):
        global current_status, tab_changed, mouse_activity, keyboard_activity, current_active_target, time_tracking, last_activity_time

        while True:
            time.sleep(1)

            is_target_active = self.is_target_window_active()
            current_time = time.time()

            # Aktif hedefin süresini güncelle (eğer hala aktifse)
            if current_active_target and is_target_active:
                if current_active_target in time_tracking:
                    time_tracking[current_active_target] += current_time - last_activity_time
                last_activity_time = current_time

            # Her saniye başında aktiviteleri sıfırla
            tab_changed = self.tab_changed
            mouse_activity = self.mouse_activity
            keyboard_activity = self.keyboard_activity
            self.mouse_activity = False
            self.keyboard_activity = False

            if not self.target_found and not selected_targets:
                current_status = 0
                print("0")
                continue

            if is_target_active:
                current_status = 1
                print("1")
            else:
                current_status = 0
                print("0")

    def run(self):
        return self.check_activity()

tab_changed = False
mouse_activity = False
keyboard_activity = False

# Flask endpoint'leri
@app.route('/api/status')
def get_status():
    global current_active_target, time_tracking, last_activity_time
    
    # Aktif hedefin süresini güncelle
    current_time = time.time()
    if current_active_target and current_active_target in time_tracking:
        time_tracking[current_active_target] += current_time - last_activity_time
        last_activity_time = current_time
    
    active_targets = selected_targets if selected_targets else [listener.initial_target_tab] if listener.initial_target_tab else []
    
    response = jsonify({
        "status": current_status,
        "tab_changed": tab_changed,
        "mouse_activity": mouse_activity,
        "keyboard_activity": keyboard_activity,
        "target_tab": listener.initial_target_tab if listener.initial_target_tab else None,
        "selected_targets": active_targets,
        "targets_count": len(active_targets),
        "current_active_target": current_active_target,
        "time_spent": {target: round(time_val, 2) for target, time_val in time_tracking.items()}
    })
    
    # Manuel CORS header'ları (flask-cors alternatifi)
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    
    return response

# Süre istatistikleri endpoint'i
@app.route('/api/time-stats')
def get_time_stats():
    global current_active_target, time_tracking, last_activity_time
    
    # Aktif hedefin süresini güncelle
    current_time = time.time()
    if current_active_target and current_active_target in time_tracking:
        time_tracking[current_active_target] += current_time - last_activity_time
        last_activity_time = current_time
    
    # Süre istatistiklerini hesapla
    stats = []
    total_time = sum(time_tracking.values())
    
    for target, time_spent in time_tracking.items():
        percentage = (time_spent / total_time * 100) if total_time > 0 else 0
        stats.append({
            "target": target,
            "time_spent_seconds": round(time_spent, 2),
            "time_spent_minutes": round(time_spent / 60, 2),
            "time_spent_formatted": f"{int(time_spent // 3600):02d}:{int((time_spent % 3600) // 60):02d}:{int(time_spent % 60):02d}",
            "percentage": round(percentage, 2),
            "is_active": target == current_active_target
        })
    
    # Süreye göre sırala (en çok harcanan süre önce)
    stats.sort(key=lambda x: x["time_spent_seconds"], reverse=True)
    
    response = jsonify({
        "stats": stats,
        "total_time_seconds": round(total_time, 2),
        "total_time_minutes": round(total_time / 60, 2),
        "total_time_formatted": f"{int(total_time // 3600):02d}:{int((total_time % 3600) // 60):02d}:{int(total_time % 60):02d}",
        "active_targets_count": len([s for s in stats if s["is_active"]]),
        "tracked_targets_count": len(stats)
    })
    
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    
    return response

# Süre takibini sıfırlama endpoint'i
@app.route('/api/reset-time-tracking', methods=['POST'])
def reset_time_tracking():
    global time_tracking, current_active_target, last_activity_time
    
    time_tracking.clear()
    current_active_target = None
    last_activity_time = time.time()
    
    print("🕐 Süre takibi sıfırlandı")
    
    response = jsonify({
        "success": True,
        "message": "Süre takibi başarıyla sıfırlandı",
        "time_tracking": {}
    })
    
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    
    return response
@app.route('/api/windows')
def get_windows():
    try:
        windows = gw.getAllWindows()
        window_list = []
        
        for window in windows:
            if window.title and len(window.title.strip()) > 0:
                window_info = {
                    "title": window.title,
                    "is_active": window == gw.getActiveWindow(),
                    "is_browser": any(browser in window.title.lower() for browser in listener.browser_keywords),
                    "is_selected": window.title in selected_targets
                }
                window_list.append(window_info)
        
        # Tarayıcı pencereleri önce gelsin, sonra diğerleri
        window_list.sort(key=lambda x: (not x["is_browser"], not x["is_active"], x["title"]))
        
        response = jsonify({
            "windows": window_list,
            "total_count": len(window_list),
            "selected_count": len(selected_targets)
        })
        
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        
        return response
        
    except Exception as e:
        response = jsonify({"error": str(e), "windows": []})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

# Hedef sekmeler seçme endpoint'i
@app.route('/api/select-targets', methods=['POST'])
def select_targets():
    global selected_targets
    
    try:
        data = request.get_json()
        if not data or 'targets' not in data:
            return jsonify({"error": "targets listesi gerekli"}), 400
        
        new_targets = data['targets']
        
        # Geçerli pencere isimlerini kontrol et
        all_windows = [w.title for w in gw.getAllWindows() if w.title and len(w.title.strip()) > 0]
        valid_targets = [target for target in new_targets if target in all_windows]
        
        selected_targets = valid_targets
        
        # Listener'ın target_found durumunu güncelle
        if selected_targets:
            listener.target_found = True
            print(f"🎯 {len(selected_targets)} hedef seçildi: {', '.join(selected_targets[:2])}{'...' if len(selected_targets) > 2 else ''}")
        else:
            listener.target_found = False
            print("❌ Hiç hedef seçilmedi")
        
        response = jsonify({
            "success": True,
            "selected_targets": selected_targets,
            "count": len(selected_targets),
            "message": f"{len(selected_targets)} hedef başarıyla seçildi"
        })
        
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        
        return response
        
    except Exception as e:
        response = jsonify({"error": str(e), "success": False})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response, 500

# Hedef seçimini temizleme endpoint'i
@app.route('/api/clear-targets', methods=['POST'])
def clear_targets():
    global selected_targets, time_tracking, current_active_target, last_activity_time
    
    selected_targets = []
    listener.target_found = False
    listener.initial_target_tab = None
    
    # Süre takibini de temizle (isteğe bağlı)
    # time_tracking.clear()
    # current_active_target = None
    # last_activity_time = time.time()
    
    print("🗑️ Tüm hedefler temizlendi")
    
    response = jsonify({
        "success": True,
        "message": "Tüm hedefler temizlendi",
        "selected_targets": []
    })
    
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    
    return response

# OPTIONS endpoint for preflight requests
@app.route('/api/status', methods=['OPTIONS'])
@app.route('/api/windows', methods=['OPTIONS'])
@app.route('/api/select-targets', methods=['OPTIONS'])
@app.route('/api/clear-targets', methods=['OPTIONS'])
@app.route('/api/time-stats', methods=['OPTIONS'])
@app.route('/api/reset-time-tracking', methods=['OPTIONS'])
def handle_options():
    response = jsonify({})
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Dinleyici setup
listener = ActivityListener(browser_only=True)

def start_monitoring():
    try:
        with keyboard.Listener(on_press=listener.on_press) as listener_kb:
            with mouse.Listener(on_move=listener.on_move) as listener_mouse:
                listener.run()
    except KeyboardInterrupt:
        print("\n🛑 Program durduruldu")

def start_flask():
    app.run(debug=False, host='0.0.0.0', port=5001, use_reloader=False)

if __name__ == '__main__':
    # Flask'ı ayrı thread'de başlat
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    
    print("🔗 API endpoint: http://localhost:5001/api/status")
    print("📋 Terminal: 1/0 değerleri")
    print("🎯 Bir tarayıcı sekmesine geç!")
    
    # Ana monitoring'i başlat
    start_monitoring()
