import time
import threading
from pynput import keyboard, mouse
from screeninfo import get_monitors
import psutil
import pygetwindow as gw
from flask import Flask, jsonify

# Flask app
app = Flask(__name__)

# Global değişkenler
current_status = 0

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

    def on_press(self, key):
        if self.target_found and not self.is_target_window_active():
            self.activity_detected = True
        self.keyboard_activity = True

    def on_move(self, x, y):
        if self.target_found and not self.is_target_window_active():
            self.activity_detected = True
        self.mouse_activity = True

    def is_target_window_active(self):
        active_window = gw.getActiveWindow()
        if not active_window:
            return False

        current_title = active_window.title

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
                    print(f"🎯 Hedef sekme belirlendi: {current_title}")
                    return True

                return current_title == self.initial_target_tab
            return False

        if self.target_window is not None:
            target_title = self.target_window.lower()
            return target_title in current_title.lower()

        return True

    def check_activity(self):
        global current_status, tab_changed, mouse_activity, keyboard_activity

        while True:
            time.sleep(1)

            is_target_active = self.is_target_window_active()

            # Her saniye başında aktiviteleri sıfırla
            tab_changed = self.tab_changed
            mouse_activity = self.mouse_activity
            keyboard_activity = self.keyboard_activity
            self.mouse_activity = False
            self.keyboard_activity = False

            if not self.target_found:
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

# Flask endpoint
@app.route('/api/status')
def get_status():
    return jsonify({
        "status": current_status,
        "tab_changed": tab_changed,
        "mouse_activity": mouse_activity,
        "keyboard_activity": keyboard_activity
    })

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
