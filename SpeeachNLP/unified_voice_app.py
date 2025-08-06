import speech_recognition as sr
import pyaudio
import wave
import time
import os
import threading
import queue
import re
from datetime import datetime, timedelta
import numpy as np
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import tkinter.font as tkFont
import requests
import json
from collections import deque
from flask import Flask, jsonify
from flask_cors import CORS
import warnings
from transformers import BertTokenizer, BertModel

# Numpy ve audio warning'lerini sustur
np.seterr(all='ignore')
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning)

class UnifiedVoiceApp:
    def __init__(self):
        # Speech Recognition ayarları - Dengeli ve gerçekçi eşik değerleri
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 200  # Orta seviye eşik - gerçekçi ses tanıma
        self.recognizer.dynamic_energy_threshold = False  # Dinamik eşik kapatıldı
        self.recognizer.pause_threshold = 0.8  # Konuşma arası beklemeler için uygun
        self.recognizer.phrase_threshold = 0.3  # Normal başlatma eşiği
        self.recognizer.non_speaking_duration = 0.5  # Sessizlik süresi
        
        # Streaming için ek ayarlar - Dengeli VB-Cable ayarları
        self.stream_chunk_duration = 1.0  # Dengeli chunk süresi
        self.min_audio_length = 0.3  # Minimum 200ms ses - gerçekçi
        
        # Ses ayarları - Dengeli sistem ayarları
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 44100  # Sistem ses cihazları için optimal (VB-Cable)
        self.chunk = 1024
        self.record_seconds = 2  # Dengeli kayıt periyodu
        
        # Streaming buffer ayarları
        self.stream_buffer_size = 8  # Çok küçük buffer
        self.max_concurrent_processing = 3  # Eşzamanlı işlem sayısı
        
        # PyAudio
        self.audio = pyaudio.PyAudio()
        
        # Cihaz tespiti
        self.output_device_index = self.find_best_output_device()
        self.input_device_index = self.find_best_input_device()
        self.microphone = sr.Microphone()
        
        # Queue'lar - Ultra hızlı streaming için optimize
        self.user_text_queue = queue.Queue(maxsize=100)  # Daha küçük queue
        self.system_text_queue = queue.Queue(maxsize=100)  # Daha küçük queue
        self.audio_queue = queue.Queue(maxsize=10)  # Çok küçük audio queue
        
        # Streaming için ek queue'lar
        self.user_stream_queue = queue.Queue()  # Ham streaming verisi
        self.system_stream_queue = queue.Queue()  # Ham streaming verisi
        
        # Gerçek zamanlı API gönderimi için
        self.api_send_queue = queue.Queue()  # Anında API gönderimi
        
        # Kontrol değişkenleri
        self.is_user_listening = False
        self.is_system_recording = False
        self.is_processing = False
        self.stop_user_listening = None
        
        # Cümle oluşturma - Streaming optimizasyonu
        self.user_current_sentence = ""
        self.system_current_sentence = ""
        self.last_user_speech_time = None
        self.last_system_audio_time = None
        self.sentence_timeout = 2.0  # 2 saniye bekleme (kullanıcı isteği)
        self.sentence_end_pattern = re.compile(r'[.!?]')
        self.max_sentence_words = 999  # Kelime limiti kaldırıldı (çok yüksek değer)
        
        # Streaming için gerçek zamanlı kelime tamponları
        self.user_word_buffer = []
        self.system_word_buffer = []
        self.word_buffer_max = 999  # Kelime limiti kaldırıldı (çok yüksek değer)
        
        # Processing control için
        self.processing_semaphore = threading.Semaphore(self.max_concurrent_processing)
        self.active_processing_count = 0
        
        # Session başlangıç zamanı
        self.session_start_time = datetime.now()
        session_timestamp = self.session_start_time.strftime("%Y%m%d_%H%M%S")
        
        # STT hata takibi
        self.stt_error_count = 0
        self.last_error_time = None
        self.max_consecutive_errors = 5
        
        # 10 saniyelik lifetime dosyalar (sürekli temizlenen)
        self.user_lifetime_file = "kullanici_10s_lifetime.txt"
        self.system_lifetime_file = "sistem_10s_lifetime.txt"
        
        # Session dosyalar (uygulama açık olduğu sürece tutulan)
        self.user_session_file = "kullanici_session_full.txt"
        self.system_session_file = "sistem_session_full.txt"
        
        # Eski dosya isimleri (uyumluluk için)
        self.user_output_file = "kullanici_metinleri.txt"
        self.system_output_file = "sistem_metinleri.txt"
        
        # Flask sunucu ayarları - Port 5002'ye güncellendi
        self.flask_url = "http://127.0.0.1:5002"
        self.flask_enabled = True
        
        # Flask sunucusu oluştur (URL tanımlandıktan sonra)
        self.setup_flask_server()
        
        # UI oluştur
        self.create_ui()
    
    def setup_flask_server(self):
        """Flask sunucusunu kurar ve başlatır"""
        # Flask uygulaması oluştur
        self.flask_app = Flask(__name__)
        
        # CORS desteği ekle
        CORS(self.flask_app)
        
        self.flask_app.config['JSON_AS_ASCII'] = False  # Türkçe karakter desteği
        self.flask_app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # Prettify kapatıldı - hız için
        # Ultra performans optimizasyonları
        self.flask_app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Cache yok
        self.flask_app.config['TEMPLATES_AUTO_RELOAD'] = False  # Template reload yok
        self.flask_app.config['EXPLAIN_TEMPLATE_LOADING'] = False  # Template debug yok
        self.flask_app.config['PROPAGATE_EXCEPTIONS'] = True  # Hızlı exception handling
        
        # 20 saniyelik veri için deque - performans iyileştirmesi
        self.user_texts_flask = deque(maxlen=2000)  # Daha fazla kapasite
        self.system_texts_flask = deque(maxlen=2000)  # Daha fazla kapasite
        self.flask_data_lock = threading.RLock()  # RLock performans iyileştirmesi
        
        # BERT analiz cache'i - HIZLANDIRMA (Eksik olan değişkenler)
        self.focus_analyzer = None  # Tek seferlik yükleme için
        self.last_focus_analysis_time = 0
        self.cached_focus_result = {'focus_score': None, 'focus_grade': None, 'focus_category': None, 'focus_emoji': None}
        self.focus_analysis_cooldown = 2.0  # 2 saniye cooldown
        
        # Kalibrasyon durumu değişkenleri
        self.calibration_status = 'idle'  # idle, running, completed, error
        self.calibration_result = None
        
        # Flask route'ları ekle
        self.setup_flask_routes()
        
        # Flask sunucusunu arka planda başlat
        self.start_flask_background()
        
        # Temizleme thread'ini başlat - 20 saniye
        cleanup_thread = threading.Thread(target=self.clean_old_flask_data, daemon=True)
        cleanup_thread.start()
        
        # Anında API gönderim thread'ini başlat
        api_sender_thread = threading.Thread(target=self.instant_api_sender, daemon=True)
        api_sender_thread.start()
    
    def setup_flask_routes(self):
        """Flask route'larını kurar - İyileştirilmiş ve performanslı"""
        
        @self.flask_app.route('/add_user_text', methods=['POST'])
        def add_user_text():
            from flask import request
            try:
                # JSON validasyonu ve hız iyileştirmesi
                if not request.is_json:
                    return jsonify({'status': 'error', 'message': 'Content-Type must be application/json'}), 400
                
                data = request.get_json(force=True)
                text = data.get('text', '').strip() if data else ''
                
                if not text:
                    return jsonify({'status': 'error', 'message': 'Empty or invalid text'}), 400
                
                # Performans için timestamp önce hesapla
                current_time = datetime.now()
                
                with self.flask_data_lock:
                    self.user_texts_flask.append({
                        'text': text,
                        'time': current_time.strftime("%H:%M:%S"),
                        'timestamp': current_time
                    })
                
                response = jsonify({'status': 'success', 'message': 'User text added successfully'})
                response.headers['Content-Type'] = 'application/json; charset=utf-8'
                return response
                
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

        @self.flask_app.route('/add_system_text', methods=['POST'])
        def add_system_text():
            from flask import request
            try:
                # JSON validasyonu ve hız iyileştirmesi
                if not request.is_json:
                    return jsonify({'status': 'error', 'message': 'Content-Type must be application/json'}), 400
                
                data = request.get_json(force=True)
                text = data.get('text', '').strip() if data else ''
                
                if not text:
                    return jsonify({'status': 'error', 'message': 'Empty or invalid text'}), 400
                
                # Performans için timestamp önce hesapla
                current_time = datetime.now()
                
                with self.flask_data_lock:
                    self.system_texts_flask.append({
                        'text': text,
                        'time': current_time.strftime("%H:%M:%S"),
                        'timestamp': current_time
                    })
                
                response = jsonify({'status': 'success', 'message': 'System text added successfully'})
                response.headers['Content-Type'] = 'application/json; charset=utf-8'
                return response
                
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500
        
        @self.flask_app.route('/get_texts')
        def get_texts():
            try:
                with self.flask_data_lock:
                    # Performans iyileştirmesi: list comprehension
                    user_list = [{'text': item['text'], 'time': item['time']} 
                                for item in self.user_texts_flask]
                    system_list = [{'text': item['text'], 'time': item['time']} 
                                  for item in self.system_texts_flask]
                
                # HIZLI Odak analizi - Cache'den kullan
                current_time = time.time()
                try:
                    # Cooldown kontrolü - 2 saniyede bir analiz
                    if (current_time - self.last_focus_analysis_time) > self.focus_analysis_cooldown:
                        # BERT analyzer'ı tek seferlik yükle
                        if self.focus_analyzer is None:
                            from optimized_voice_comparison import LessonFocusAnalyzer
                            self.focus_analyzer = LessonFocusAnalyzer()
                            print("🧠 BERT analyzer cache'den yüklendi")
                        
                        # Son sistem ve kullanıcı metinlerini birleştir
                        system_text = ' '.join([item['text'] for item in system_list if item['text']])
                        user_text = ' '.join([item['text'] for item in user_list if item['text']])
                        
                        # Sadece yeni metin varsa analiz et
                        if system_text or user_text:
                            focus_result = self.focus_analyzer.analyze_lesson_focus(system_text, user_text)
                            self.cached_focus_result = focus_result
                            self.last_focus_analysis_time = current_time
                        else:
                            focus_result = self.cached_focus_result
                    else:
                        # Cache'den sonucu kullan
                        focus_result = self.cached_focus_result
                        
                except Exception as focus_e:
                    print(f"⚠️ Odak analizi hatası: {focus_e}")
                    focus_result = self.cached_focus_result
                response_data = {
                    'user_texts': user_list,
                    'system_texts': system_list,
                    'total_user': len(user_list),
                    'total_system': len(system_list),
                    'last_update': datetime.now().strftime('%H:%M:%S'),
                    'data_retention_seconds': 20,
                    'focus_score': focus_result.get('focus_score', None)
                }
                response = jsonify(response_data)
                response.headers['Content-Type'] = 'application/json; charset=utf-8'
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return response
            except Exception as e:
                return jsonify({'error': f'Server error: {str(e)}'}), 500
        
        @self.flask_app.route('/api/stats')
        def api_stats():
            try:
                with self.flask_data_lock:
                    user_count = len(self.user_texts_flask)
                    system_count = len(self.system_texts_flask)
                    
                    response_data = {
                        'status': 'active',
                        'user_texts_count': user_count,
                        'system_texts_count': system_count,
                        'total_texts': user_count + system_count,
                        'data_retention_seconds': 20,
                        'max_capacity_per_type': 2000,
                        'timestamp': datetime.now().isoformat(),
                        'memory_usage': {
                            'user_usage_percent': (user_count / 2000) * 100,
                            'system_usage_percent': (system_count / 2000) * 100
                        }
                    }
                
                response = jsonify(response_data)
                response.headers['Content-Type'] = 'application/json; charset=utf-8'
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return response
                
            except Exception as e:
                return jsonify({'error': f'Server error: {str(e)}'}), 500
        
        @self.flask_app.route('/api/voice_control/start', methods=['POST'])
        def start_voice_recognition():
            """Ses tanımayı başlatma endpoint'i"""
            try:
                if not self.is_user_listening and not self.is_system_recording:
                    # Her ikisini de başlat
                    self.start_user_listening()
                    self.start_system_recording()
                    
                    return jsonify({
                        'status': 'success',
                        'message': 'Ses tanıma başlatıldı',
                        'is_user_listening': self.is_user_listening,
                        'is_system_recording': self.is_system_recording,
                        'action': 'started'
                    })
                else:
                    return jsonify({
                        'status': 'info',
                        'message': 'Ses tanıma zaten aktif',
                        'is_user_listening': self.is_user_listening,
                        'is_system_recording': self.is_system_recording,
                        'action': 'already_active'
                    })
                    
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Ses tanıma başlatılamadı: {str(e)}',
                    'is_user_listening': self.is_user_listening,
                    'is_system_recording': self.is_system_recording
                }), 500
        
        @self.flask_app.route('/api/voice_control/stop', methods=['POST'])
        def stop_voice_recognition():
            """Ses tanımayı durdurma endpoint'i"""
            try:
                # Her ikisini de durdur
                if self.is_user_listening:
                    self.stop_user_listening_func()
                if self.is_system_recording:
                    self.stop_system_recording()
                
                return jsonify({
                    'status': 'success',
                    'message': 'Ses tanıma durduruldu',
                    'is_user_listening': self.is_user_listening,
                    'is_system_recording': self.is_system_recording,
                    'action': 'stopped'
                })
                
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Ses tanıma durdurulamadı: {str(e)}',
                    'is_user_listening': self.is_user_listening,
                    'is_system_recording': self.is_system_recording
                }), 500
        
        @self.flask_app.route('/api/voice_control/status')
        def get_voice_status():
            """Ses tanıma durumunu kontrol etme endpoint'i"""
            try:
                return jsonify({
                    'status': 'success',
                    'is_user_listening': self.is_user_listening,
                    'is_system_recording': self.is_system_recording,
                    'is_active': self.is_user_listening or self.is_system_recording,
                    'energy_threshold': getattr(self.recognizer, 'energy_threshold', 200),
                    'input_device_index': self.input_device_index,
                    'device_info': {
                        'input_device_available': self.input_device_index is not None,
                        'microphone_available': hasattr(self, 'microphone')
                    }
                })
                
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Durum bilgisi alınamadı: {str(e)}'
                }), 500
        
        @self.flask_app.route('/api/voice_control/calibrate', methods=['POST'])
        def calibrate_microphone():
            """Mikrofon kalibrasyonu endpoint'i"""
            try:
                # Kalibrasyon thread'ini başlat
                def calibration_process():
                    try:
                        # Kalibrasyonu başlat
                        self.calibration_status = 'running'
                        self.calibration_result = None
                        
                        # 5 saniye ses toplama simülasyonu
                        import numpy as np
                        volume_samples = []
                        
                        # Gerçek kalibrasyon kodu burada olacak
                        # Şimdilik örnek değerler
                        start_time = time.time()
                        while time.time() - start_time < 3:  # 3 saniye kısa test
                            try:
                                with self.microphone as source:
                                    audio = self.recognizer.listen(source, timeout=0.5, phrase_time_limit=0.5)
                                    if audio:
                                        audio_data = audio.get_raw_data()
                                        if audio_data:
                                            audio_array = np.frombuffer(audio_data, dtype=np.int16)
                                            if len(audio_array) > 0:
                                                volume = np.sqrt(np.mean(audio_array.astype(np.float32)**2))
                                                volume_samples.append(volume)
                            except:
                                continue
                        
                        if volume_samples:
                            avg_volume = np.mean(volume_samples)
                            balanced_threshold = int(avg_volume * 0.5)
                            
                            # Eşik değerini uygula
                            self.recognizer.energy_threshold = balanced_threshold
                            
                            self.calibration_result = {
                                'avg_volume': float(avg_volume),
                                'new_threshold': balanced_threshold,
                                'samples_count': len(volume_samples),
                                'success': True
                            }
                        else:
                            # Varsayılan değer
                            self.recognizer.energy_threshold = 200
                            self.calibration_result = {
                                'new_threshold': 200,
                                'samples_count': 0,
                                'success': False,
                                'message': 'Ses algılanamadı, varsayılan değer kullanıldı'
                            }
                        
                        self.calibration_status = 'completed'
                        
                    except Exception as e:
                        self.calibration_status = 'error'
                        self.calibration_result = {
                            'success': False,
                            'error': str(e)
                        }
                
                # Kalibrasyon thread'ini başlat
                threading.Thread(target=calibration_process, daemon=True).start()
                
                return jsonify({
                    'status': 'success',
                    'message': 'Kalibrasyon başlatıldı',
                    'calibration_status': 'started',
                    'estimated_duration': 3
                })
                
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Kalibrasyon başlatılamadı: {str(e)}'
                }), 500
        
        @self.flask_app.route('/api/voice_control/calibrate/status')
        def get_calibration_status():
            """Kalibrasyon durumunu kontrol etme endpoint'i"""
            try:
                status = getattr(self, 'calibration_status', 'idle')
                result = getattr(self, 'calibration_result', None)
                
                response_data = {
                    'status': 'success',
                    'calibration_status': status,
                    'current_threshold': getattr(self.recognizer, 'energy_threshold', 200)
                }
                
                if result:
                    response_data['calibration_result'] = result
                
                return jsonify(response_data)
                
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Kalibrasyon durumu alınamadı: {str(e)}'
                }), 500
        
        @self.flask_app.route('/api/voice_control/clear_texts', methods=['POST'])
        def clear_all_texts():
            """Tüm metinleri temizleme endpoint'i"""
            try:
                with self.flask_data_lock:
                    self.user_texts_flask.clear()
                    self.system_texts_flask.clear()
                
                return jsonify({
                    'status': 'success',
                    'message': 'Tüm metinler temizlendi',
                    'user_texts_count': 0,
                    'system_texts_count': 0
                })
                
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Metinler temizlenemedi: {str(e)}'
                }), 500
    
    def start_flask_background(self):
        """Flask sunucusunu arka planda başlatır - Ultra hızlı optimizasyon"""
        def run_flask():
            try:
                print(f"🚀 Flask sunucu başlatılıyor: {self.flask_url}")
                # Ultra performans iyileştirmeleri
                self.flask_app.run(
                    host='127.0.0.1',  # localhost yerine 127.0.0.1 kullan
                    port=5002, 
                    debug=False, 
                    threaded=True, 
                    use_reloader=False,
                    processes=1,  # Tek process daha kararlı
                    request_handler=None,  # Varsayılan handler kullan
                    passthrough_errors=False,  # Hata yakalama optimizasyonu
                    ssl_context=None,  # SSL yok - hız için
                    load_dotenv=False  # .env dosyası yüklememe - hız için
                )
            except OSError as e:
                if "Address already in use" in str(e):
                    print("⚠️ Port 5002 kullanımda, Flask sunucu başlatılamadı")
                    print("💡 Çözüm: Başka bir terminal açın ve 'netstat -ano | findstr :5002' çalıştırın")
                else:
                    print(f"⚠️ Flask sunucu hatası: {e}")
            except Exception as e:
                print(f"⚠️ Flask başlatma hatası: {e}")
        
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # Flask'ın başlaması için daha uzun bekle ve test et
        for i in range(10):  # 10 saniye boyunca dene
            time.sleep(1.0)
            try:
                response = requests.get("http://127.0.0.1:5002/api/stats", timeout=1)
                if response.status_code == 200:
                    print("✅ Flask sunucu başarıyla çalışıyor!")
                    break
            except:
                if i == 9:  # Son deneme
                    print("❌ Flask sunucu 10 saniye içinde başlatılamadı!")
                continue
        
        print("✅ Flask sunucu thread başlatıldı")
    
    def clean_old_flask_data(self):
        """20 saniyeden eski Flask verilerini temizler - Optimized"""
        while True:
            try:
                current_time = datetime.now()
                cutoff_time = current_time - timedelta(seconds=20)  # 20 saniye olarak değiştirildi
                
                with self.flask_data_lock:
                    # Performans iyileştirmesi: batch silme
                    # Kullanıcı metinlerini temizle
                    while (self.user_texts_flask and 
                           len(self.user_texts_flask) > 0 and 
                           self.user_texts_flask[0]['timestamp'] < cutoff_time):
                        self.user_texts_flask.popleft()
                    
                    # Sistem metinlerini temizle
                    while (self.system_texts_flask and 
                           len(self.system_texts_flask) > 0 and 
                           self.system_texts_flask[0]['timestamp'] < cutoff_time):
                        self.system_texts_flask.popleft()
                
                # Performans: daha uzun aralıklarla kontrol
                time.sleep(2)  # 2 saniyede bir kontrol et (daha az CPU kullanımı)
                
            except Exception as e:
                print(f"⚠️ Flask veri temizleme hatası: {e}")
                time.sleep(5)  # Hata durumunda daha uzun bekle
    
    def instant_api_sender(self):
        """Anında API gönderim thread'i - Ultra hızlı"""
        print("🚀 API sender thread başlatıldı")
        while True:
            try:
                if not self.api_send_queue.empty():
                    data = self.api_send_queue.get_nowait()
                    text = data['text']
                    text_type = data['type']
                    
                    print(f"📤 Queue'den alındı: [{text_type}] {text[:30]}...")
                    
                    # Async HTTP request simulation (non-blocking)
                    threading.Thread(
                        target=self.send_to_flask_immediate, 
                        args=(text, text_type), 
                        daemon=True
                    ).start()
                
                time.sleep(0.1)  # 100ms check interval
                
            except queue.Empty:
                time.sleep(0.2)
            except Exception as e:
                print(f"⚠️ API sender hatası: {e}")
                time.sleep(0.5)
        
    def find_best_output_device(self):
        """En uygun ses çıkış cihazını bulur"""
        info = self.audio.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')
        
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            device_name = device_info.get('name', '').lower()
            
            if (device_info.get('maxInputChannels') > 0 and 
                ('cable' in device_name or 'virtual' in device_name or 'vb-audio' in device_name)):
                return i
        
        try:
            default_input_info = self.audio.get_default_input_device_info()
            return default_input_info['index']
        except:
            pass
        
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            if device_info.get('maxInputChannels') > 0:
                return i
        
        return None
    
    def find_best_input_device(self):
        """En uygun ses giriş cihazını bulur - VB-Cable optimize"""
        info = self.audio.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')

        # Önce CABLE Output'u ara (En güvenilir)
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            device_name = device_info.get('name', '').lower()

            if (device_info.get('maxInputChannels') > 0 and 
                'cable output' in device_name and 'vb-audio' in device_name):
                print(f"✅ CABLE Output bulundu: {device_info.get('name')}")
                return i

        # Sonra diğer VB-Audio cihazlarını ara
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            device_name = device_info.get('name', '').lower()

            if (device_info.get('maxInputChannels') > 0 and 
                ('voicemeeter' in device_name or 'vb-audio' in device_name)):
                print(f"✅ VB-Audio cihazı bulundu: {device_info.get('name')}")
                return i

        # Cable ve virtual cihazları ara
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            device_name = device_info.get('name', '').lower()

            if (device_info.get('maxInputChannels') > 0 and 
                ('cable' in device_name or 'virtual' in device_name)):
                print(f"✅ Virtual cihaz bulundu: {device_info.get('name')}")
                return i

        # Son seçenek: Stereo Mix
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            device_name = device_info.get('name', '').lower()

            if (device_info.get('maxInputChannels') > 0 and 
                ('stereo mix' in device_name or 'stereo karışımı' in device_name or 'what u hear' in device_name)):
                print(f"✅ Stereo Mix bulundu: {device_info.get('name')}")
                return i

        print("❌ VB-Cable veya sanal ses cihazı bulunamadı!")
        return None

    def create_ui(self):
        """Modern ve şık kullanıcı arayüzünü oluşturur"""
        self.root = tk.Tk()
        self.root.title("🎤 Akıllı Ses Tanıma Uygulaması")
        self.root.geometry("1400x900")
        self.root.configure(bg='#0d1117')
        
        # Modern stil ayarları
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Modern.TLabelframe', background='#161b22', foreground='#f0f6fc', 
                       borderwidth=2, relief='flat')
        style.configure('Modern.TLabelframe.Label', background='#161b22', foreground='#58a6ff', 
                       font=('Segoe UI', 10, 'bold'))
        
        # Ana çerçeve
        main_frame = tk.Frame(self.root, bg='#0d1117', padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Başlık çerçevesi
        header_frame = tk.Frame(main_frame, bg='#0d1117')
        header_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Ana başlık
        title_label = tk.Label(header_frame, text="🎤 Akıllı Ses Tanıma Uygulaması", 
                              font=("Segoe UI", 24, "bold"), bg='#0d1117', fg='#f0f6fc')
        title_label.pack()
        
        subtitle_label = tk.Label(header_frame, text="Gerçek zamanlı mikrofon ve sistem ses tanıma", 
                                 font=("Segoe UI", 12), bg='#0d1117', fg='#8b949e')
        subtitle_label.pack(pady=(5, 0))
        
        # Session bilgi etiketi
        session_timestamp = self.session_start_time.strftime("%Y%m%d_%H%M%S")
        session_info_label = tk.Label(header_frame, 
                                     text=f"📋 Session: {session_timestamp} | 🗂️ Dosyalar: 10s lifetime + session full + uyumluluk dosyaları", 
                                     font=("Segoe UI", 9), bg='#0d1117', fg='#58a6ff', wraplength=1300)
        session_info_label.pack(pady=(8, 0))
        
        # Kontrol paneli
        control_frame = tk.Frame(main_frame, bg='#161b22', relief='flat', bd=2)
        control_frame.pack(fill=tk.X, pady=(0, 20), padx=10, ipady=15)
        
        # Ana kontrol butonu
        self.main_button = tk.Button(control_frame, text="� Ses Tanımayı Başlat", 
                                    command=self.toggle_all_recording, font=("Segoe UI", 14, "bold"),
                                    bg='#238636', fg='white', width=25, height=2,
                                    relief='flat', cursor='hand2')
        self.main_button.pack(pady=15)
        
        # Yan butonlar çerçevesi
        side_buttons_frame = tk.Frame(control_frame, bg='#161b22')
        side_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Temizleme butonu
        clear_button = tk.Button(side_buttons_frame, text="🧹 Temizle", 
                                command=self.clear_displays, font=("Segoe UI", 10, "bold"),
                                bg='#f85149', fg='white', width=12, relief='flat', cursor='hand2')
        clear_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Kaydetme butonu
        save_button = tk.Button(side_buttons_frame, text="💾 Kaydet", 
                               command=self.save_all_texts, font=("Segoe UI", 10, "bold"),
                               bg='#1f6feb', fg='white', width=12, relief='flat', cursor='hand2')
        save_button.pack(side=tk.LEFT, padx=(10, 0))
        
        # API test butonu
        api_button = tk.Button(side_buttons_frame, text="🔗 API Test", 
                              command=self.test_api, font=("Segoe UI", 10, "bold"),
                              bg='#6f42c1', fg='white', width=12, relief='flat', cursor='hand2')
        api_button.pack(side=tk.LEFT, padx=(10, 0))
        
        # Kalibrasyon butonu
        calibrate_button = tk.Button(side_buttons_frame, text="🎯 Kalibre Et", 
                                   command=self.manual_calibration, font=("Segoe UI", 10, "bold"),
                                   bg='#fb8500', fg='white', width=12, relief='flat', cursor='hand2')
        calibrate_button.pack(side=tk.LEFT, padx=(10, 0))
        
        # Ses cihazları debug butonu
        debug_button = tk.Button(side_buttons_frame, text="🔍 Ses Cihazları", 
                                command=self.debug_audio_devices, font=("Segoe UI", 10, "bold"),
                                bg='#6f42c1', fg='white', width=12, relief='flat', cursor='hand2')
        debug_button.pack(side=tk.LEFT, padx=(10, 0))
        
        # Durum göstergesi
        self.status_label = tk.Label(control_frame, text="⚡ Sistem Hazır", 
                                    font=("Segoe UI", 11, "bold"), bg='#161b22', fg='#58a6ff')
        self.status_label.pack(pady=(15, 0))
        
        # Ana içerik alanı
        content_frame = tk.Frame(main_frame, bg='#0d1117')
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Sol panel - Kullanıcı sesleri
        user_frame = tk.Frame(content_frame, bg='#0d1117')
        user_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        user_header = tk.Frame(user_frame, bg='#1f2937', height=50)
        user_header.pack(fill=tk.X, pady=(0, 10))
        user_header.pack_propagate(False)
        
        user_title = tk.Label(user_header, text="👤 Mikrofon Sesleri", 
                             font=("Segoe UI", 14, "bold"), bg='#1f2937', fg='#10b981')
        user_title.pack(expand=True)
        
        self.user_text_display = scrolledtext.ScrolledText(user_frame, height=25, width=55,
                                                          font=("JetBrains Mono", 11), wrap=tk.WORD,
                                                          bg='#0d1117', fg='#10b981', insertbackground='#10b981',
                                                          relief='flat', bd=0, selectbackground='#1f2937')
        self.user_text_display.pack(fill=tk.BOTH, expand=True)
        
        # Sağ panel - Sistem sesleri
        system_frame = tk.Frame(content_frame, bg='#0d1117')
        system_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        system_header = tk.Frame(system_frame, bg='#1e3a8a', height=50)
        system_header.pack(fill=tk.X, pady=(0, 10))
        system_header.pack_propagate(False)
        
        system_title = tk.Label(system_header, text="🖥️ Sistem Sesleri", 
                               font=("Segoe UI", 14, "bold"), bg='#1e3a8a', fg='#3b82f6')
        system_title.pack(expand=True)
        
        self.system_text_display = scrolledtext.ScrolledText(system_frame, height=25, width=55,
                                                            font=("JetBrains Mono", 11), wrap=tk.WORD,
                                                            bg='#0d1117', fg='#3b82f6', insertbackground='#3b82f6',
                                                            relief='flat', bd=0, selectbackground='#1e3a8a')
        self.system_text_display.pack(fill=tk.BOTH, expand=True)
        
        # İlk mesajları ekle - sadece dosya kayıtları
        session_timestamp = self.session_start_time.strftime("%Y%m%d_%H%M%S")
        
        # Dosyalar oluştur
        self.create_output_files()
        
        # 10 saniyelik temizleme thread'ini başlat
        self.start_lifetime_cleaner()
        
        # UI güncelleme thread'ini başlat
        self.start_ui_updater()
        
        # Başlangıçta Flask durumunu kontrol et
        self.root.after(2000, self.check_flask_status)  # 2 saniye sonra kontrol et
    
    def toggle_all_recording(self):
        """Tek tıkla her iki sistemi de başlatır/durdurur"""
        if not self.is_user_listening and not self.is_system_recording:
            # Her ikisini de başlat
            self.start_user_listening()
            self.start_system_recording()
            self.main_button.config(text="⏹️ Ses Tanımayı Durdur", bg='#f85149')
            self.update_status("Tam otomatik mod aktif 🔥")
        else:
            # Her ikisini de durdur
            if self.is_user_listening:
                self.stop_user_listening_func()
            if self.is_system_recording:
                self.stop_system_recording()
            self.main_button.config(text="🚀 Ses Tanımayı Başlat", bg='#238636')
            self.update_status("Sistem durduruldu ⏸️")
    
    def create_output_files(self):
        """Çıktı dosyalarını oluşturur - Her başlangıçta sıfırdan yazılır"""
        # Tüm dosyaları sil ve sıfırdan oluştur
        all_files = [
            # 10 saniyelik lifetime dosyalar
            self.user_lifetime_file,        # kullanici_10s_lifetime.txt
            self.system_lifetime_file,      # sistem_10s_lifetime.txt
            # Session dosyalar (uygulama boyunca tutulan)
            self.user_session_file,         # kullanici_session_full.txt
            self.system_session_file,       # sistem_session_full.txt
            # Eski uyumluluk dosyalar
            self.user_output_file,          # kullanici_metinleri.txt
            self.system_output_file,        # sistem_metinleri.txt
        ]
        
        # Önce mevcut dosyaları sil
        for filename in all_files:
            try:
                if os.path.exists(filename):
                    os.remove(filename)
                    print(f"🗑️ Eski dosya silindi: {filename}")
            except Exception as e:
                print(f"⚠️ Dosya silinirken hata: {filename} - {e}")
        
        # 10 saniyelik lifetime dosyalarını oluştur
        lifetime_files = [
            (self.user_lifetime_file, "Kullanıcı 10s Lifetime"),
            (self.system_lifetime_file, "Sistem 10s Lifetime")
        ]
        
        for filename, file_type in lifetime_files:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"=== {file_type} Metinleri ===\n")
                f.write(f"Oluşturulma: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("NOT: Bu dosya 10 saniye boyunca veri tutar, sonra temizlenir.\n")
                f.write("=" * 50 + "\n\n")
            print(f"✅ Lifetime dosya oluşturuldu: {filename}")
        
        # Session dosyalarını oluştur
        session_files = [
            (self.user_session_file, "Kullanıcı Session Full"),
            (self.system_session_file, "Sistem Session Full")
        ]
        
        for filename, file_type in session_files:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"=== {file_type} Transkripti ===\n")
                f.write(f"Session Başlangıç: {self.session_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Dosya: {filename}\n")
                f.write("NOT: Bu dosya uygulama açık olduğu sürece tüm verileri tutar.\n")
                f.write("=" * 50 + "\n\n")
            print(f"✅ Session dosya oluşturuldu: {filename}")
        
        # Eski uyumluluk dosyalarını oluştur
        for filename in [self.user_output_file, self.system_output_file]:
            with open(filename, "w", encoding="utf-8") as f:
                file_type = "Kullanıcı" if "kullanici" in filename else "Sistem"
                f.write(f"=== {file_type} Sesleri Tanıma Metinleri - {datetime.now().strftime('%Y-%m-%d')} ===\n\n")
            print(f"✅ Uyumluluk dosya oluşturuldu: {filename}")
    
    def start_lifetime_cleaner(self):
        """10 saniyelik lifetime temizleyici thread'ini başlatır"""
        def lifetime_cleaner():
            print("🧹 10 saniyelik lifetime temizleyici başlatıldı")
            while True:
                try:
                    current_time = datetime.now()
                    cutoff_time = current_time - timedelta(seconds=10)  # 10 saniye
                    
                    # Kullanıcı lifetime dosyasını temizle
                    self.clean_lifetime_file(self.user_lifetime_file, cutoff_time, "Kullanıcı")
                    
                    # Sistem lifetime dosyasını temizle
                    self.clean_lifetime_file(self.system_lifetime_file, cutoff_time, "Sistem")
                    
                    time.sleep(2)  # 2 saniyede bir kontrol et
                    
                except Exception as e:
                    print(f"⚠️ Lifetime temizleme hatası: {e}")
                    time.sleep(5)
        
        # Thread'i başlat
        lifetime_thread = threading.Thread(target=lifetime_cleaner, daemon=True)
        lifetime_thread.start()
    
    def clean_lifetime_file(self, filename, cutoff_time, file_type):
        """Belirtilen dosyadaki 10 saniyeden eski verileri temizler"""
        try:
            if not os.path.exists(filename):
                return
            
            # Dosyayı oku
            with open(filename, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Header satırları (ilk 4 satır) koru
            header_lines = []
            content_lines = []
            
            for i, line in enumerate(lines):
                if i < 4 or line.startswith("===") or line.startswith("NOT:"):
                    header_lines.append(line)
                else:
                    content_lines.append(line)
            
            # 10 saniyeden yeni verileri filtrele
            new_content_lines = []
            for line in content_lines:
                try:
                    # [YYYY-MM-DD HH:MM:SS] formatını ara
                    if line.startswith("[") and "]" in line:
                        timestamp_str = line[1:line.index("]")]
                        try:
                            line_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            if line_time > cutoff_time:  # 10 saniyeden yeni
                                new_content_lines.append(line)
                        except ValueError:
                            # Timestamp parse edilemezse satırı koru
                            new_content_lines.append(line)
                    else:
                        # Timestamp yoksa satırı koru
                        new_content_lines.append(line)
                except:
                    # Hata durumunda satırı koru
                    new_content_lines.append(line)
            
            # Dosyayı yeniden yaz
            with open(filename, "w", encoding="utf-8") as f:
                f.writelines(header_lines)
                f.writelines(new_content_lines)
                
        except Exception as e:
            print(f"⚠️ {file_type} lifetime temizleme hatası: {e}")
    
    def is_real_speech_text(self, text):
        """Gerçek konuşma metni olup olmadığını kontrol eder"""
        if not text or len(text.strip()) < 2:
            return False
        
        # Sistem mesajlarını filtrele
        system_indicators = ['❌', '✅', '⚠️', '🔍', '💡', '🔧', '📊', '🎯', '⚡', '🚀']
        if any(indicator in text for indicator in system_indicators):
            return False
        
        # Çok kısa metinleri filtrele
        if len(text.strip()) < 3:
            return False
            
        return True
    
    def add_user_text(self, text):
        """Kullanıcı paneline sadece net cümleleri ekler - 3 dosya sistemli"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_text = f"[{timestamp}] {text}\n\n"
        formatted_full = f"[{full_timestamp}] {text}\n"
        
        # 1. Lifetime dosyasına kaydet (10 saniyelik)
        try:
            with open(self.user_lifetime_file, "a", encoding="utf-8") as f:
                f.write(formatted_full)
        except Exception as e:
            print(f"Lifetime kayıt hatası (user): {e}")
        
        # 2. Session dosyasına kaydet (uygulama boyunca)
        try:
            with open(self.user_session_file, "a", encoding="utf-8") as f:
                f.write(formatted_full)
        except Exception as e:
            print(f"Session kayıt hatası (user): {e}")
        
        # 3. Eski uyumluluk dosyasına kaydet
        try:
            with open(self.user_output_file, "a", encoding="utf-8") as f:
                f.write(formatted_full)
        except Exception as e:
            print(f"Uyumluluk kayıt hatası (user): {e}")
        
        # Flask API'ye gönder - ÖNEMLİ! (Sadece gerçek konuşma metinleri)
        if self.is_real_speech_text(text):
            self.send_to_flask(text, "user")
        
        def update_ui():
            self.user_text_display.config(state=tk.NORMAL)
            self.user_text_display.insert(tk.END, formatted_text)
            self.user_text_display.see(tk.END)
            self.user_text_display.config(state=tk.DISABLED)
        
        self.root.after(0, update_ui)
    
    def add_system_text(self, text):
        """Sistem paneline sadece net cümleleri ekler - 3 dosya sistemli"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_text = f"[{timestamp}] {text}\n\n"
        formatted_full = f"[{full_timestamp}] {text}\n"
        
        # 1. Lifetime dosyasına kaydet (10 saniyelik)
        try:
            with open(self.system_lifetime_file, "a", encoding="utf-8") as f:
                f.write(formatted_full)
        except Exception as e:
            print(f"Lifetime kayıt hatası (system): {e}")
        
        # 2. Session dosyasına kaydet (uygulama boyunca)
        try:
            with open(self.system_session_file, "a", encoding="utf-8") as f:
                f.write(formatted_full)
        except Exception as e:
            print(f"Session kayıt hatası (system): {e}")
        
        # 3. Eski uyumluluk dosyasına kaydet
        try:
            with open(self.system_output_file, "a", encoding="utf-8") as f:
                f.write(formatted_full)
        except Exception as e:
            print(f"Uyumluluk kayıt hatası (system): {e}")
        
        # Flask API'ye gönder - ÖNEMLİ! (Sadece gerçek konuşma metinleri)
        if self.is_real_speech_text(text):
            self.send_to_flask(text, "system")
        
        def update_ui():
            self.system_text_display.config(state=tk.NORMAL)
            self.system_text_display.insert(tk.END, formatted_text)
            self.system_text_display.see(tk.END)
            self.system_text_display.config(state=tk.DISABLED)
        
        self.root.after(0, update_ui)
    
    def update_status(self, status):
        """Durum etiketini günceller"""
        def update_ui():
            self.status_label.config(text=f"⚡ {status}")
        
        self.root.after(0, update_ui)
    
    def toggle_user_listening(self):
        """Kullanıcı ses tanımayı başlatır/durdurur (artık kullanılmıyor)"""
        pass
    
    def send_to_flask(self, text, text_type):
        """Flask sunucusuna metin gönderir - Hızlı queue sistemi"""
        if not self.flask_enabled or not text.strip():
            return
        
        # Debug çıktısı
        print(f"🔄 Flask queue'ye ekleniyor: [{text_type}] {text[:50]}...")
        
        # API gönderim queue'sine ekle (anında işlem)
        try:
            self.api_send_queue.put_nowait({
                'text': text.strip(),
                'type': text_type
            })
            print(f"✅ Queue'ye eklendi: [{text_type}]")
        except queue.Full:
            print(f"⚠️ Queue dolu, atlanıyor: [{text_type}]")
            pass  # Queue doluysa skip et (performans için)
    
    def send_to_flask_immediate(self, text, text_type):
        """Flask'a ultra hızlı veri gönderme fonksiyonu - Optimize edilmiş"""
        if text_type == "user":
            endpoint = f"{self.flask_url}/add_user_text"
        else:
            endpoint = f"{self.flask_url}/add_system_text"
        
        # Session'ı tekrar kullan - bağlantı pool'u için
        if not hasattr(self, '_session'):
            import requests
            self._session = requests.Session()
            # Keep-alive ve connection pooling
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=1,
                pool_maxsize=2,
                max_retries=0  # Retry'ı manuel yap
            )
            self._session.mount('http://', adapter)
            self._session.headers.update({'Content-Type': 'application/json'})
        
        max_retries = 2  # 3'ten 2'ye düşür - hız için
        for attempt in range(max_retries):
            try:
                response = self._session.post(
                    endpoint, 
                    json={"text": text}, 
                    timeout=2  # 5'ten 2'ye düşür - çok daha hızlı
                )
                if response.status_code == 200:
                    # Debug çıktısını azalt - performans için
                    if attempt == 0:  # Sadece ilk denemede log
                        print(f"✅ Flask OK ({text_type}): {text[:30]}...")
                    return  # Başarılı, fonksiyondan çık
                else:
                    print(f"❌ Flask yanıt hatası ({text_type}): {response.status_code}")
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ Bağlantı hatası, yeniden deneniyor... ({attempt + 1}/{max_retries})")
                    time.sleep(0.2)  # 0.5'ten 0.2'ye - çok daha hızlı
                else:
                    print(f"❌ Flask bağlantı hatası ({text_type}): {e}")
                    
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ Timeout hatası, yeniden deneniyor... ({attempt + 1}/{max_retries})")
                    time.sleep(0.1)  # 0.5'ten 0.1'e - çok daha hızlı
                else:
                    print(f"❌ Flask timeout hatası ({text_type}): {e}")
                    
            except Exception as e:
                print(f"❌ Flask genel hatası ({text_type}): {e}")
                break  # Diğer hatalar için yeniden deneme
    
    def handle_stt_error(self, error_type, error_msg):
        """STT hatalarını yönetir ve kullanıcıya bilgi verir"""
        current_time = datetime.now()
        
        # Hata sayacını artır
        if self.last_error_time and (current_time - self.last_error_time).total_seconds() < 10:
            self.stt_error_count += 1
        else:
            self.stt_error_count = 1  # Reset counter
        
        self.last_error_time = current_time
        
        # Hata tipine göre mesaj
        if error_type == "quota":
            self.update_status("⚠️ Google API limiti aşıldı - 24 saat bekleyin")
            if self.stt_error_count == 1:  # İlk hata mesajı
                self.add_system_text("⚠️ Google STT API günlük limiti aşıldı")
                self.add_system_text("💡 Çözüm: 24 saat bekleyin veya Google Cloud API key kullanın")
        elif error_type == "connection":
            self.update_status("🌐 İnternet bağlantısı kontrol edin")
            if self.stt_error_count == 1:
                self.add_system_text("🌐 Google STT bağlantı hatası")
                self.add_system_text("💡 İnternet bağlantınızı kontrol edin")
        else:
            self.update_status(f"⚠️ STT hatası: {error_msg}")
        
        # Çok fazla hata varsa uyar
        if self.stt_error_count >= self.max_consecutive_errors:
            self.update_status("❌ Çok fazla STT hatası - Ses tanıma geçici olarak durdurulabilir")
            self.add_system_text("❌ Ardışık STT hataları nedeniyle ses tanıma sorun yaşıyor")
            self.add_system_text("🔧 Öneriler: İnternet bağlantısı, mikrofon ayarları, Google API durumu")
    
    def open_web_interface(self):
        """Web arayüzünü tarayıcıda açar"""
        import webbrowser
        try:
            webbrowser.open(f"{self.flask_url}/get_texts")
            self.update_status("🔗 API endpoint açıldı!")
        except:
            self.update_status("❌ API endpoint açılamadı")
    
    def test_api(self):
        """API'yi test eder"""
        try:
            print("🔍 Flask API testi yapılıyor...")
            response = requests.get(f"{self.flask_url}/api/stats", timeout=5)
            if response.status_code == 200:
                data = response.json()
                total_user = data.get('user_texts_count', 0)
                total_system = data.get('system_texts_count', 0)
                total = total_user + total_system
                self.update_status(f"✅ API çalışıyor! User: {total_user}, System: {total_system}")
                print(f"✅ Flask API çalışıyor - User: {total_user}, System: {total_system}")
            else:
                self.update_status("⚠️ API yanıt vermiyor")
                print(f"⚠️ Flask API yanıt kodu: {response.status_code}")
        except requests.exceptions.ConnectionError:
            self.update_status("❌ Flask sunucu çalışmıyor")
            print("❌ Flask sunucusuna bağlanılamıyor!")
            print("💡 Çözüm: Uygulamayı yeniden başlatın")
        except Exception as e:
            self.update_status("❌ API bağlantısı başarısız")
            print(f"❌ Flask API test hatası: {e}")
    
    def check_flask_status(self):
        """Flask durumunu kontrol eder"""
        try:
            response = requests.get(f"{self.flask_url}/api/stats", timeout=2)
            if response.status_code == 200:
                print("✅ Flask sunucu başarıyla çalışıyor ve erişilebilir!")
                self.update_status("Flask API hazır ✅")
            else:
                print(f"⚠️ Flask yanıt kodu: {response.status_code}")
                self.update_status("Flask API sorunlu ⚠️")
        except:
            print("❌ Flask sunucusuna erişilemiyor!")
            self.update_status("Flask API erişilemiyor ❌")
            self.add_system_text("❌ Flask sunucu başlatılamadı!")
            self.add_system_text("💡 Çözüm: Uygulamayı kapatıp yeniden açın")
    
    def manual_calibration(self):
        """Manuel eşik ayarı - Kullanıcı ile etkileşimli kalibrasyon"""
        def calibration_thread():
            try:
                self.update_status("🎯 Manuel kalibrasyon başlatılıyor...")
                
                # Ses seviyelerini toplamak için
                volume_samples = []
                start_time = time.time()
                
                # 5 saniye ses toplama
                while time.time() - start_time < 5:
                    try:
                        with self.microphone as source:
                            # Kısa ses örnekleri al
                            audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=1)
                            audio_data = audio.get_raw_data()
                            
                            if audio_data:
                                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                                if len(audio_array) > 0:
                                    volume = np.sqrt(np.mean(audio_array.astype(np.float64)**2))
                                    volume_samples.append(volume)
                                    print(f"📊 Anlık ses seviyesi: {volume:.1f}")
                    except:
                        continue
                
                if volume_samples:
                    # İstatistikleri hesapla
                    avg_volume = np.mean(volume_samples)
                    max_volume = np.max(volume_samples)
                    min_volume = np.min(volume_samples)
                    
                    # Önerilen eşik değerleri
                    conservative_threshold = int(avg_volume * 0.3)  # Muhafazakar
                    balanced_threshold = int(avg_volume * 0.5)     # Dengeli
                    sensitive_threshold = int(avg_volume * 0.7)    # Hassas
                    
                    # Dengeli değeri otomatik uygula
                    self.recognizer.energy_threshold = balanced_threshold
                    self.update_status(f"✅ Kalibrasyon tamamlandı! Eşik: {balanced_threshold}")
                    
                else:
                    self.recognizer.energy_threshold = 200  # Varsayılan değer
                    self.update_status("⚠️ Kalibrasyon başarısız - varsayılan değer kullanılıyor")
                    
            except Exception as e:
                self.recognizer.energy_threshold = 200
                self.update_status("❌ Kalibrasyon hatası - varsayılan değer")
        
        # Kalibrasyon thread'ini başlat
        threading.Thread(target=calibration_thread, daemon=True).start()
    
    def debug_audio_devices(self):
        """Ses cihazlarını detaylı analiz eder"""
        def debug_thread():
            try:
                self.update_status("🔍 Ses cihazları taranıyor...")
                
                info = self.audio.get_host_api_info_by_index(0)
                numdevices = info.get('deviceCount')
                
                self.add_system_text("🔍 === SES CİHAZLARI ANALİZİ ===")
                self.add_system_text(f"📊 Toplam {numdevices} ses cihazı bulundu")
                
                input_devices = []
                output_devices = []
                
                for i in range(numdevices):
                    try:
                        device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
                        device_name = device_info.get('name', 'Bilinmeyen')
                        max_input = device_info.get('maxInputChannels', 0)
                        max_output = device_info.get('maxOutputChannels', 0)
                        
                        if max_input > 0:
                            input_devices.append((i, device_name, max_input))
                            
                        if max_output > 0:
                            output_devices.append((i, device_name, max_output))
                            
                    except Exception as e:
                        continue
                
                # Input cihazları listele
                self.add_system_text(f"\n🎤 GİRİŞ CİHAZLARI ({len(input_devices)} adet):")
                for idx, (device_idx, name, channels) in enumerate(input_devices):
                    status = "✅ AKTIF" if device_idx == self.input_device_index else "⚪"
                    is_vb = "🟢 VB-AUDIO" if any(x in name.lower() for x in ['vb-audio', 'cable', 'voicemeeter']) else ""
                    self.add_system_text(f"{status} [{device_idx}] {name} ({channels}ch) {is_vb}")
                
                # Output cihazları listele
                self.add_system_text(f"\n🔊 ÇIKIŞ CİHAZLARI ({len(output_devices)} adet):")
                for idx, (device_idx, name, channels) in enumerate(output_devices):
                    is_vb = "🟢 VB-AUDIO" if any(x in name.lower() for x in ['vb-audio', 'cable', 'voicemeeter']) else ""
                    self.add_system_text(f"⚪ [{device_idx}] {name} ({channels}ch) {is_vb}")
                
                # Aktif cihaz bilgisi
                if self.input_device_index is not None:
                    active_device = self.audio.get_device_info_by_index(self.input_device_index)
                    self.add_system_text(f"\n🎯 AKTİF SİSTEM CİHAZI:")
                    self.add_system_text(f"   📱 {active_device.get('name')}")
                    self.add_system_text(f"   📊 {active_device.get('maxInputChannels')} kanal")
                    self.add_system_text(f"   🔢 Örnek Rate: {active_device.get('defaultSampleRate', 'Bilinmiyor')}")
                else:
                    self.add_system_text(f"\n❌ AKTİF SİSTEM CİHAZI YOK!")
                    self.add_system_text("💡 VB-Audio Virtual Cable kurulumu gerekebilir")
                
                # Öneriler
                vb_input_devices = [d for d in input_devices if any(x in d[1].lower() for x in ['cable output', 'vb-audio'])]
                if not vb_input_devices:
                    self.add_system_text("\n⚠️ VB-Audio cihazı bulunamadı!")
                    self.add_system_text("🔧 Çözüm adımları:")
                    self.add_system_text("1. VB-Audio Virtual Cable indirin ve kurun")
                    self.add_system_text("2. Windows Ses ayarlarında varsayılan çıkışı 'CABLE Input' yapın")
                    self.add_system_text("3. Programı yeniden başlatın")
                else:
                    self.add_system_text(f"\n✅ {len(vb_input_devices)} VB-Audio cihazı mevcut")
                    self.add_system_text("💡 Sistem seslerini dinlemek için:")
                    self.add_system_text("   Windows ayarları → Ses → Çıkış → CABLE Input seçin")
                
                self.update_status("✅ Ses cihazları analizi tamamlandı")
                
            except Exception as e:
                self.add_system_text(f"❌ Cihaz analizi hatası: {e}")
                self.update_status("❌ Cihaz analizi başarısız")
        
        threading.Thread(target=debug_thread, daemon=True).start()
    
    def start_user_listening(self):
        """Kullanıcı ses tanımayı başlatır - Dengeli gerçekçi ayarlar"""
        try:
            # Gerçekçi eşik değeri kullan
            if not hasattr(self, 'calibrated') or not self.calibrated:
                self.recognizer.energy_threshold = 200  # Varsayılan dengeli değer
            
            # Dinlemeyi başlat
            self.stop_user_listening = self.recognizer.listen_in_background(self.microphone, self.user_audio_callback)
            self.is_user_listening = True
            self.last_user_speech_time = datetime.now()
            
        except Exception as e:
            self.add_user_text(f"❌ Mikrofon başlatılamadı: {e}")
    
    def stop_user_listening_func(self):
        """Kullanıcı ses tanımayı durdurur - Streaming cleanup"""
        if self.is_user_listening and self.stop_user_listening:
            # Son buffer'ı temizle
            if self.user_word_buffer:
                self.complete_user_sentence(add_period=True)
            
            self.stop_user_listening(wait_for_stop=False)
            self.is_user_listening = False
    
    def start_system_recording(self):
        """Sistem ses kaydını başlatır - VB-Cable optimized"""
        if self.input_device_index is None:
            self.add_system_text("⚠️ VB-Cable kurulumu gerekli!")
            self.add_system_text("🔧 Çözüm: VB-Audio Virtual Cable kurulumu yapın")
            self.add_system_text("💡 '🔍 Ses Cihazları' butonuna tıklayarak detaylı analiz yapın")
            print("❌ VB-Cable cihazı bulunamadı!")
            return
        
        # Device bilgisini göster - sadece console log
        try:
            device_info = self.audio.get_device_info_by_index(self.input_device_index)
            device_name = device_info.get('name', 'Bilinmeyen')
            sample_rate = device_info.get('defaultSampleRate', 'Bilinmiyor')
            print(f"🎤 Sistem ses kaydı cihazı: {device_name}")
            print(f"📊 Örnek rate: {sample_rate} Hz, Kanal: {self.channels}")
                
        except Exception as e:
            print(f"⚠️ Cihaz bilgisi alınamadı: {e}")
        
        self.is_system_recording = True
        self.is_processing = True
        
        # Threading ile sistem ses kaydını başlat
        self.system_recording_thread = threading.Thread(target=self.record_system_audio, daemon=True)
        self.system_processing_thread = threading.Thread(target=self.process_system_audio_queue, daemon=True)
        
        self.system_recording_thread.start()
        self.system_processing_thread.start()
        
        print("✅ Sistem ses tanıma başlatıldı")
    
    def stop_system_recording(self):
        """Sistem ses kaydını durdurur - Streaming cleanup"""
        self.is_system_recording = False
        self.is_processing = False
        
        # Son buffer'ı temizle
        if self.system_word_buffer:
            self.complete_system_sentence(add_period=True)
    
    def adjust_for_noise(self):
        """Basit eşik ayarı - Dengeli gerçekçi ayarlar"""
        try:
            self.update_status("⚡ Eşik değeri dengeli ayarlara sabitlendi: 200")
            # Gerçekçi eşik değeri
            self.recognizer.energy_threshold = 200
            self.update_status(f"✅ Mikrofon dengeli ayarlarla hazır (Eşik: 200)")
            
        except Exception as e:
            self.update_status("✅ Varsayılan dengeli eşik: 200")
            self.recognizer.energy_threshold = 200
    
    def user_audio_callback(self, recognizer, audio):
        """Kullanıcı ses callback - Ultra hızlı streaming"""
        try:
            # Anında processing başlat
            threading.Thread(
                target=self.process_user_audio_stream, 
                args=(recognizer, audio), 
                daemon=True
            ).start()
        except:
            pass
    
    def process_user_audio_stream(self, recognizer, audio):
        """User audio streaming processor"""
        try:
            with self.processing_semaphore:  # Concurrent processing control
                # Güvenli ses seviyesi kontrolü
                audio_data = audio.get_raw_data()
                
                # Audio data validation
                if not audio_data or len(audio_data) < 2:
                    return
                
                try:
                    audio_array = np.frombuffer(audio_data, dtype=np.int16)
                    
                    # Array validation
                    if len(audio_array) == 0:
                        return
                    
                    # Güvenli volume hesaplama
                    mean_square = np.mean(audio_array.astype(np.float64)**2)
                    if mean_square < 0 or not np.isfinite(mean_square):
                        return
                    
                    volume = np.sqrt(mean_square)
                    
                except (ValueError, TypeError, OverflowError):
                    return  # Invalid audio data, skip
                
                # Volume threshold check (dengeli eşik)
                if volume < 100:  # Gerçekçi eşik değeri - normal konuşma sesleri
                    return
                
                # Geliştirilmiş STT çağrısı
                try:
                    # Retry mechanism ile Google STT
                    text = None
                    max_retries = 2
                    
                    for attempt in range(max_retries):
                        try:
                            text = recognizer.recognize_google(audio, language="tr-TR", show_all=False)
                            break  # Başarılı ise döngüden çık
                            
                        except sr.RequestError as e:
                            if "recognition request failed" in str(e).lower():
                                if attempt < max_retries - 1:  # Son deneme değilse
                                    time.sleep(0.3)  # Kısa bekle
                                    continue
                            raise e
                        except sr.UnknownValueError:
                            return  # Anlaşılamayan ses - normal
                
                except sr.RequestError as e:
                    error_msg = str(e)
                    if "quota exceeded" in error_msg.lower():
                        self.handle_stt_error("quota", "API limiti aşıldı (Mikrofon)")
                    elif "recognition request failed" in error_msg.lower():
                        self.handle_stt_error("connection", "Bağlantı hatası (Mikrofon)")
                    return
                except Exception:
                    return
                
                if text and len(text.strip()) > 1:
                    current_time = datetime.now()
                    self.last_user_speech_time = current_time
                    
                    # Kelime buffer'a ekle (limit yok)
                    words = text.strip().split()
                    self.user_word_buffer.extend(words)
                    
                    # Sadece cümle sonu işaretleri ile buffer kontrolü
                    if any(word.endswith(('.', '!', '?')) for word in words):
                        sentence = ' '.join(self.user_word_buffer)
                        self.user_word_buffer.clear()
                        
                        # UI ve API güncellemesi
                        self.add_user_text(sentence)
                        self.send_to_flask(sentence, "user")
                        
        except sr.UnknownValueError:
            pass
        except sr.RequestError:
            pass
        except Exception:
            pass
    
    def record_system_audio(self):
        """Sistem ses kaydı - VB-Cable uyumlu versiyon"""
        try:
            print(f"🎤 Sistem ses kaydı başlatılıyor...")
            
            stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                input_device_index=self.input_device_index,
                output=False,
                frames_per_buffer=self.chunk
            )
            
            print(f"✅ Audio stream açıldı: {self.rate}Hz, {self.channels} kanal")
            
            while self.is_system_recording:
                try:
                    frames = []
                    
                    # Dengeli ses kaydı periyodu (2 saniye)
                    frames_to_read = int(self.rate / self.chunk * self.record_seconds)
                    
                    for i in range(frames_to_read):
                        if not self.is_system_recording:
                            break
                            
                        try:
                            data = stream.read(self.chunk, exception_on_overflow=False)
                            frames.append(data)
                        except (OSError, IOError):
                            time.sleep(0.01)
                            continue
                    
                    if frames and self.is_system_recording:
                        # Frames'i birleştir
                        audio_data = b''.join(frames)
                        
                        # Kaliteli ses kontrolü
                        try:
                            audio_array = np.frombuffer(audio_data, dtype=np.int16)
                            if len(audio_array) > 0:
                                volume = np.sqrt(np.mean(audio_array.astype(np.float64)**2))
                                
                                # Ses seviyesi loglaması (debug için)
                                if hasattr(self, 'last_volume_log_time'):
                                    if (datetime.now() - self.last_volume_log_time).total_seconds() > 5:
                                        print(f"🔊 Sistem ses seviyesi: {volume:.1f} (Threshold: 80)")
                                        self.last_volume_log_time = datetime.now()
                                else:
                                    self.last_volume_log_time = datetime.now()
                                
                                # Dengeli ses kontrolü - gerçekçi konuşma sesleri
                                if volume > 80 and len(audio_data) > 4000:  # Gerçekçi eşik değeri
                                    print(f"✅ Sistem ses işleniyor: Seviye={volume:.1f}, Boyut={len(audio_data)} bytes")
                                    # Ses kalitesi yeterli, processing'e gönder
                                    threading.Thread(
                                        target=self.process_system_audio_data,
                                        args=(audio_data,),
                                        daemon=True
                                    ).start()
                                elif volume > 30:  # Düşük ses seviyesi uyarısı
                                    print(f"⚠️ Düşük sistem ses seviyesi: {volume:.1f} (Min: 80 gerekli)")
                        except Exception as e:
                            continue
                
                except Exception as e:
                    print(f"⚠️ Kayıt hatası: {e}")
                    time.sleep(0.1)
                    continue
            
            stream.stop_stream()
            stream.close()
            print("🛑 Sistem ses kaydı durduruldu")
            
        except Exception as e:
            self.add_system_text(f"❌ Sistem ses hatası: {str(e)}")
            print(f"❌ Record system audio error: {e}")
            self.is_system_recording = False
    
    def process_system_audio_data(self, audio_data):
        """Sistem ses verisi işleme - Geliştirilmiş hata yönetimi"""
        try:
            with self.processing_semaphore:
                # Gerçekçi audio data validation
                if not audio_data or len(audio_data) < 4000:  # Gerçekçi minimum ses uzunluğu
                    return
                
                # Temporary WAV dosyası oluştur
                temp_wav_file = "temp_system_audio.wav"
                
                try:
                    # WAV dosyasını oluştur
                    with wave.open(temp_wav_file, 'wb') as wf:
                        wf.setnchannels(self.channels)
                        wf.setsampwidth(self.audio.get_sample_size(self.format))
                        wf.setframerate(self.rate)
                        wf.writeframes(audio_data)
                    
                    # Gerçekçi dosya boyutu kontrolü
                    if os.path.getsize(temp_wav_file) < 4000:  # Gerçekçi dosya boyutu
                        return
                    
                    # Speech Recognition ile metne çevir
                    with sr.AudioFile(temp_wav_file) as source:
                        # Ses seviyesi kontrolü
                        audio = self.recognizer.record(source)
                        
                        # Retry mechanism ile Google STT
                        text = None
                        max_retries = 2
                        
                        for attempt in range(max_retries):
                            try:
                                # Google STT ile çevir - daha uzun timeout
                                text = self.recognizer.recognize_google(
                                    audio, 
                                    language="tr-TR", 
                                    show_all=False
                                )
                                break  # Başarılı ise döngüden çık
                                
                            except sr.RequestError as e:
                                if "recognition request failed" in str(e).lower():
                                    print(f"🔄 STT yeniden deneniyor... ({attempt + 1}/{max_retries})")
                                    time.sleep(0.5)  # Kısa bekle
                                    continue
                                else:
                                    raise e
                            except sr.UnknownValueError:
                                # Anlaşılamayan ses - bu normal
                                return
                        
                        if text and len(text.strip()) > 1:
                            # Kelime buffer sistemini kullan (limit yok)
                            words = text.strip().split()
                            self.system_word_buffer.extend(words)
                            self.last_system_audio_time = datetime.now()
                            
                            # Sadece cümle sonu işaretleri ile buffer kontrolü
                            if any(word.endswith(('.', '!', '?')) for word in words):
                                sentence = ' '.join(self.system_word_buffer)
                                self.system_word_buffer.clear()
                                
                                # UI ve API güncellemesi
                                self.add_system_text(sentence)
                                self.send_to_flask(sentence, "system")
                                print(f"🔊 Sistem: {sentence}")
                
                except Exception as e:
                    error_msg = str(e)
                    if "recognition request failed" in error_msg.lower():
                        self.handle_stt_error("connection", "Bağlantı hatası")
                    elif "quota exceeded" in error_msg.lower():
                        self.handle_stt_error("quota", "API limiti aşıldı")
                    else:
                        self.handle_stt_error("general", error_msg)
                finally:
                    # Temporary dosyayı temizle
                    try:
                        if os.path.exists(temp_wav_file):
                            os.remove(temp_wav_file)
                    except:
                        pass
                        
        except sr.UnknownValueError:
            pass  # Anlaşılamayan ses - normal durum
        except sr.RequestError as e:
            error_msg = str(e)
            if "recognition request failed" in error_msg.lower():
                self.handle_stt_error("connection", "Google STT bağlantı hatası")
            elif "quota exceeded" in error_msg.lower():
                self.handle_stt_error("quota", "Google STT limit aşıldı")
            else:
                self.handle_stt_error("general", str(e))
        except Exception as e:
            self.handle_stt_error("general", f"Sistem ses işleme hatası: {e}")
    
    def process_system_audio_queue(self):
        """Sistem ses streaming kontrolü - Simplified"""
        while self.is_processing:
            try:
                # Word buffer timeout kontrolü
                current_time = datetime.now()
                
                # User buffer timeout
                if (self.user_word_buffer and self.last_user_speech_time and 
                    (current_time - self.last_user_speech_time).total_seconds() > self.sentence_timeout):
                    
                    sentence = ' '.join(self.user_word_buffer)
                    self.user_word_buffer.clear()
                    self.add_user_text(sentence)
                    self.send_to_flask(sentence, "user")
                
                # System buffer timeout
                if (self.system_word_buffer and self.last_system_audio_time and 
                    (current_time - self.last_system_audio_time).total_seconds() > self.sentence_timeout):
                    
                    sentence = ' '.join(self.system_word_buffer)
                    self.system_word_buffer.clear()
                    self.add_system_text(sentence)
                    self.send_to_flask(sentence, "system")
                
                time.sleep(0.1)  # 100ms check
                
            except Exception:
                time.sleep(0.5)
    
    def process_user_speech_fragment(self, text):
        """Kullanıcı konuşma parçası - Deprecated, streaming kullanılıyor"""
        pass  # Artık streaming kullanıyoruz
    
    def process_system_speech_fragment(self, text):
        """Sistem konuşma parçası - Deprecated, streaming kullanılıyor"""
        pass  # Artık streaming kullanıyoruz
    
    def complete_user_sentence(self, add_period=False):
        """Kullanıcı cümle tamamlama - Simplified"""
        if self.user_word_buffer:
            sentence = ' '.join(self.user_word_buffer)
            if add_period and not self.sentence_end_pattern.search(sentence):
                sentence += "."
            
            self.user_word_buffer.clear()
            self.add_user_text(sentence)  # Flask'a gönderim add_user_text içinde
    
    def complete_system_sentence(self, add_period=False):
        """Sistem cümle tamamlama - Simplified"""
        if self.system_word_buffer:
            sentence = ' '.join(self.system_word_buffer)
            if add_period and not self.sentence_end_pattern.search(sentence):
                sentence += "."
            
            self.system_word_buffer.clear()
            self.add_system_text(sentence)  # Flask'a gönderim add_system_text içinde
    
    def check_user_sentence_timeout(self):
        """Kullanıcı buffer timeout - Streaming ile entegre"""
        if (self.user_word_buffer and self.last_user_speech_time and 
            (datetime.now() - self.last_user_speech_time).total_seconds() > self.sentence_timeout):
            self.complete_user_sentence(add_period=True)
    
    def check_system_sentence_timeout(self):
        """Sistem buffer timeout - Streaming ile entegre"""
        if (self.system_word_buffer and self.last_system_audio_time and 
            (datetime.now() - self.last_system_audio_time).total_seconds() > self.sentence_timeout):
            self.complete_system_sentence(add_period=True)
    
    def save_to_file(self, filename, text):
        """Metni dosyaya kaydeder"""
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    
    def save_all_texts(self):
        """Tüm metinleri dosyalara kaydeder"""
        user_count = 0
        system_count = 0
        
        while not self.user_text_queue.empty():
            text = self.user_text_queue.get()
            self.save_to_file(self.user_output_file, text)
            user_count += 1
        
        while not self.system_text_queue.empty():
            text = self.system_text_queue.get()
            self.save_to_file(self.system_output_file, text)
            system_count += 1
        
        total = user_count + system_count
        if total > 0:
            self.update_status(f"💾 {total} cümle dosyalara kaydedildi!")
        else:
            self.update_status("📝 Kaydedilecek yeni cümle yok")
    
    def clear_displays(self):
        """Metin ekranlarını temizler"""
        self.user_text_display.config(state=tk.NORMAL)
        self.user_text_display.delete(1.0, tk.END)
        self.user_text_display.config(state=tk.DISABLED)
        
        self.system_text_display.config(state=tk.NORMAL)
        self.system_text_display.delete(1.0, tk.END)
        self.system_text_display.config(state=tk.DISABLED)
        
        self.add_user_text("Mikrofon ses tanıma hazır...")
        self.add_system_text("Sistem ses tanıma hazır...")
        self.update_status("🧹 Ekranlar temizlendi")
    
    def start_ui_updater(self):
        """UI güncelleme döngüsü - Ultra hızlı streaming"""
        def update_loop():
            while True:
                try:
                    if self.is_user_listening:
                        self.check_user_sentence_timeout()
                    
                    if self.is_system_recording:
                        self.check_system_sentence_timeout()
                    
                    # Streaming queue'leri işle (çok hızlı)
                    while not self.user_text_queue.empty():
                        try:
                            text = self.user_text_queue.get_nowait()
                            self.save_to_file(self.user_output_file, text)
                        except queue.Empty:
                            break
                    
                    while not self.system_text_queue.empty():
                        try:
                            text = self.system_text_queue.get_nowait()
                            self.save_to_file(self.system_output_file, text)
                        except queue.Empty:
                            break
                    
                    time.sleep(0.05)  # 50ms update cycle (çok hızlı)
                except:
                    time.sleep(0.5)
                    break
        
        updater_thread = threading.Thread(target=update_loop, daemon=True)
        updater_thread.start()
    
    def check_flask_status(self):
        """Flask sunucusunun durumunu kontrol eder"""
        try:
            response = requests.get(f"{self.flask_url}/api/stats", timeout=1)
            if response.status_code == 200:
                self.update_status("🌐 Flask API hazır (Port: 5000)")
            else:
                self.update_status("⚠️ Flask API sorunu")
        except:
            self.update_status("❌ Flask API bağlantı hatası")
    
    def on_closing(self):
        """Uygulama kapanırken temizlik - Streaming cleanup"""
        if self.is_user_listening:
            self.stop_user_listening_func()
        
        if self.is_system_recording:
            self.stop_system_recording()
        
        # Son buffer'ları kaydet
        if self.user_word_buffer:
            self.complete_user_sentence(add_period=True)
        if self.system_word_buffer:
            self.complete_system_sentence(add_period=True)
        
        # Kalan metinleri kaydet
        self.save_all_texts()
        
        # Session dosyalarını sonlandır
        self.finalize_session_files()
        
        # PyAudio'yu kapat
        self.audio.terminate()
        
        self.root.destroy()
    
    def finalize_session_files(self):
        """Session dosyalarını sonlandırır ve özet bilgiler ekler"""
        try:
            session_end_time = datetime.now()
            session_duration = session_end_time - self.session_start_time
            
            # Session özet bilgileri
            summary_info = f"\n" + "=" * 50 + "\n"
            summary_info += f"Session Bitiş: {session_end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            summary_info += f"Session Süresi: {str(session_duration).split('.')[0]}\n"  # Mikrosaniyeyi kaldır
            summary_info += f"Toplam Çalışma Zamanı: {session_duration.total_seconds():.0f} saniye\n"
            summary_info += "=" * 50 + "\n"
            
            # User session dosyasını sonlandır
            with open(self.user_session_file, "a", encoding="utf-8") as f:
                f.write(summary_info)
                f.write("Session tamamlandı - Kullanıcı sesleri kaydedildi.\n")
            
            # System session dosyasını sonlandır
            with open(self.system_session_file, "a", encoding="utf-8") as f:
                f.write(summary_info)
                f.write("Session tamamlandı - Sistem sesleri kaydedildi.\n")
            
            print(f"✅ Session dosyları tamamlandı:")
            print(f"   👤 Kullanıcı: {self.user_session_file}")
            print(f"   🖥️ Sistem: {self.system_session_file}")
            print(f"   ⏱️ Süre: {str(session_duration).split('.')[0]}")
            
        except Exception as e:
            print(f"⚠️ Session sonlandırma hatası: {e}")
    
    def run(self):
        """Uygulamayı çalıştırır"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()
    
    def load_bert_model(self):
        """BERT multilingual modelini yükler."""
        try:
            model_path = "c:/Users/Hp/Desktop/BTK_Heckaton/Vision_Process/models/bert-base-multilingual-cased"
            self.tokenizer = BertTokenizer.from_pretrained(model_path)
            self.bert_model = BertModel.from_pretrained(model_path)
            print("✅ BERT modeli başarıyla yüklendi.")
        except Exception as e:
            print(f"⚠️ BERT modeli yüklenemedi: {e}")
            self.bert_model = None
    
    def is_real_speech_text(self, text):
        """Gerçek konuşma metinlerini sistem mesajlarından ayırır"""
        if not text or len(text.strip()) < 3:
            return False
        
        # Sistem mesajları ve teknik metinler
        system_keywords = [
            "listening", "recording", "başlıyor", "stopping", "timeout",
            "error", "recognizing", "api", "connection", "debug",
            "log", "warning", "exception", "failed", "trying",
            "mikrofo", "kayıt", "dinleni", "başla", "durdur"
        ]
        
        text_lower = text.lower()
        
        # Sistem anahtar kelimeleri kontrolü
        for keyword in system_keywords:
            if keyword in text_lower:
                return False
        
        # Çok kısa metinler (muhtemelen gürültü)
        if len(text.strip()) < 5:
            return False
        
        # Sadece rakam veya özel karakter içeren metinler
        if not any(c.isalpha() for c in text):
            return False
        
        return True

if __name__ == "__main__":
    app = UnifiedVoiceApp()
    app.load_bert_model()
    app.run()
