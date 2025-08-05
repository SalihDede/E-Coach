import speech_recognition as sr
import pyaudio
import wave
import time
import os
import threading
import queue
import re
from datetime import datetime
import numpy as np

class SystemAudioToText:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.audio_queue = queue.Queue()
        self.text_queue = queue.Queue()
        self.is_recording = False
        self.is_processing = False
        self.stop_recording = None
        self.output_file = "sistem_metinleri.txt"
        
        # Ses yakalama ayarları
        self.format = pyaudio.paInt16
        self.channels = 1  # Mono kayıt için kanalları 1 olarak ayarladık
        self.rate = 44100
        self.chunk = 1024
        self.record_seconds = 5  # Her kayıt periyodunun süresi
        
        # Cümle oluşturma için ek özellikler
        self.current_sentence = ""
        self.last_audio_time = None
        self.sentence_timeout = 2.5
        self.sentence_end_pattern = re.compile(r'[.!?]')
        
        # PyAudio nesnesi
        self.audio = pyaudio.PyAudio()
        
        # En uygun ses çıkış cihazını otomatik olarak bul
        self.output_device_index = self.find_best_output_device()
        self.input_device_index = self.find_best_input_device()  # Eklenen kod: Giriş cihazını bul
        
        if self.input_device_index is not None:
            device_info = self.audio.get_device_info_by_index(self.input_device_index)
            print(f"Otomatik olarak seçilen ses giriş cihazı: {device_info.get('name')}")
            print("VB-Cable kurulumu tespit edildi!")
            print("\nSesi hem duyabilmek hem de kaydetmek için:")
            print("1. Windows Ses Ayarları > Ses Denetim Masası'nı açın")
            print("2. 'Kayıt' sekmesinde 'CABLE Output' veya 'Stereo Mix' cihazını bulun")
            print("3. Bu cihaza sağ tıklayın > 'Özellikler' > 'Dinle' sekmesi")
            print("4. 'Bu cihazı dinle' seçeneğini işaretleyin")
            print("5. 'Oynatma cihazı' olarak kulaklığınızı seçin")
            print("6. Windows ses çıkışını 'CABLE Input' olarak ayarlayın")
            print("7. Bu şekilde hem kulaklığınızdan duyar hem de script'e kaydettirebilirsiniz\n")
        else:
            print("Uygun ses giriş cihazı bulunamadı. VB-Cable kurulumu gerekli olabilir.")
    
    def find_best_output_device(self):
        """En uygun ses çıkış cihazını otomatik olarak bulur"""
        info = self.audio.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')
        
        # Önce CABLE Input veya VB-Audio gibi sanal ses cihazlarını ara
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            device_name = device_info.get('name', '').lower()
            
            # Tipik sanal ses cihazı isimleri
            if (device_info.get('maxInputChannels') > 0 and 
                ('cable' in device_name or 'virtual' in device_name or 'vb-audio' in device_name)):
                print(f"Sanal ses cihazı bulundu: {device_info.get('name')}")
                return i
        
        # Sanal cihaz bulunamazsa, varsayılan giriş cihazını dene
        try:
            default_input_info = self.audio.get_default_input_device_info()
            return default_input_info['index']
        except:
            pass
        
        # Yine bulunamazsa, herhangi bir giriş cihazını dene
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            if device_info.get('maxInputChannels') > 0:
                return i
        
        return None
    
    def find_best_input_device(self):
        """En uygun ses giriş cihazını otomatik olarak bulur"""
        info = self.audio.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')

        # Önce VB-Cable Output cihazını ara (ses kaydı için)
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            device_name = device_info.get('name', '').lower()

            if (device_info.get('maxInputChannels') > 0 and 
                ('cable output' in device_name or 'cable-output' in device_name or 'vb-audio virtual cable' in device_name)):
                print(f"VB-Cable Output cihazı bulundu: {device_info.get('name')}")
                return i

        # VB-Cable Output bulunamazsa, genel Cable cihazlarını ara
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            device_name = device_info.get('name', '').lower()

            if (device_info.get('maxInputChannels') > 0 and 
                ('cable' in device_name or 'virtual' in device_name or 'vb-audio' in device_name)):
                print(f"Sanal ses giriş cihazı bulundu: {device_info.get('name')}")
                return i

        # Hiçbir sanal cihaz bulunamazsa, Stereo Mix'i ara
        for i in range(0, numdevices):
            device_info = self.audio.get_device_info_by_host_api_device_index(0, i)
            device_name = device_info.get('name', '').lower()

            if (device_info.get('maxInputChannels') > 0 and 
                ('stereo mix' in device_name or 'stereo karışımı' in device_name or 'what u hear' in device_name)):
                print(f"Stereo Mix cihazı bulundu: {device_info.get('name')}")
                return i

        return None

    def record_audio(self):
        """Bilgisayarın ses çıkışını ve girişini otomatik olarak kaydeder"""
        print("Sistem seslerini kaydetmeye başlıyorum...")

        try:
            # Seçilen veya varsayılan ses cihazıyla bağlantı kur
            stream = self.audio.open(
                format=self.format,
                channels=self.channels,  # Kanalları mono olarak ayarladık
                rate=self.rate,
                input=True,  # Sadece giriş modunda çalışıyoruz
                input_device_index=self.input_device_index,  # Bulunan giriş cihazını kullan
                output=False,  # Çıkış modunu kapatıyoruz
                frames_per_buffer=self.chunk
            )

            print("Sistem sesleri kaydediliyor. Durdurmak için CTRL+C tuşlarına basın.")
            print("Şimdi sistemden gelen herhangi bir sesi (video, müzik, vb.) oynatabilirsiniz.")
            
            self.is_recording = True
            frames = []
            
            while self.is_recording:
                frames = []
                for i in range(0, int(self.rate / self.chunk * self.record_seconds)):
                    if not self.is_recording:
                        break
                    data = stream.read(self.chunk, exception_on_overflow=False)
                    frames.append(data)
                
                if frames and self.is_recording:
                    # Ses verisini kaydedip işlemeye gönder
                    audio_data = b''.join(frames)
                    self.process_audio_chunk(audio_data)
                
                # Her 5 saniyede bir tekrarla
            
            stream.stop_stream()
            stream.close()
            
        except Exception as e:
            print(f"Ses kaydı sırasında hata: {e}")
            print("İpucu: Bilgisayarınızda bir sanal ses cihazı kurulu değilse, sistem sesleri algılanamayabilir.")
            print("VB-Cable kurulumu için: https://vb-audio.com/Cable/")
            self.is_recording = False
    
    def process_audio_chunk(self, audio_data):
        """Kaydedilen ses parçasını işler ve tanıma için kuyruğa ekler"""
        try:
            # Ses verisini geçici bir WAV dosyasına kaydet
            with wave.open("temp_audio.wav", 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(self.audio.get_sample_size(self.format))
                wf.setframerate(self.rate)
                wf.writeframes(audio_data)
            
            # Ses dosyasını yükle
            with sr.AudioFile("temp_audio.wav") as source:
                audio = self.recognizer.record(source)
            
            # Ses kuyruğuna ekle
            self.audio_queue.put(audio)
            self.last_audio_time = datetime.now()
            
        except Exception as e:
            print(f"Ses işleme hatası: {e}")
    
    def process_audio_queue(self):
        """Kuyruktaki ses verilerini işleyerek metne çevirir"""
        self.is_processing = True
        
        while self.is_processing:
            try:
                if not self.audio_queue.empty():
                    audio = self.audio_queue.get()
                    
                    try:
                        # Google Speech Recognition ile Türkçe tanıma
                        text = self.recognizer.recognize_google(audio, language="tr-TR")
                        
                        if text:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Algılanan: {text}")
                            self.process_text_fragment(text)
                    except sr.UnknownValueError:
                        # Konuşma algılanamadıysa, sessizlik olabilir
                        pass
                    except sr.RequestError as e:
                        print(f"Google Speech Recognition servisi hatası: {e}")
                
                # Zaman aşımı kontrolü
                self.check_sentence_timeout()
                
                time.sleep(0.1)
            except Exception as e:
                print(f"Ses tanıma işlemi sırasında hata: {e}")
    
    def process_text_fragment(self, text):
        """Algılanan metin parçalarını işleyerek cümle oluşturur"""
        # Büyük harfle başlat (eğer bu yeni bir cümle başlangıcıysa)
        if not self.current_sentence:
            text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
        
        # Metni mevcut cümle tamponuna ekle
        self.current_sentence += " " + text if self.current_sentence else text
        
        # Eğer metinde cümle bitirme işareti varsa, cümleyi tamamla
        if self.sentence_end_pattern.search(text):
            self.complete_sentence()
        # Veya eğer cümle uzunsa
        elif len(self.current_sentence.split()) > 15:
            self.complete_sentence(add_period=True)
    
    def complete_sentence(self, add_period=False):
        """Mevcut cümleyi tamamlar ve kuyruğa ekler"""
        if not self.current_sentence:
            return
        
        # Cümleyi tamamla
        sentence = self.current_sentence.strip()
        if add_period and not self.sentence_end_pattern.search(sentence):
            sentence += "."
        
        # Cümleyi kuyruğa ekle ve buffer'ı temizle
        self.text_queue.put(sentence)
        print(f"[CÜMLE TAMAMLANDI] {sentence}")
        self.current_sentence = ""
    
    def check_sentence_timeout(self):
        """Belirli bir süre ses algılanmazsa mevcut cümleyi tamamlar"""
        if (self.current_sentence and self.last_audio_time and 
            (datetime.now() - self.last_audio_time).total_seconds() > self.sentence_timeout):
            self.complete_sentence(add_period=True)
    
    def save_to_file(self, text):
        """Tanınan metni dosyaya kaydeder"""
        with open(self.output_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    
    def start(self):
        """Ses yakalama ve tanıma işlemini başlatır"""
        # Eğer çıktı dosyası yoksa oluştur
        if not os.path.exists(self.output_file):
            with open(self.output_file, "w", encoding="utf-8") as f:
                f.write(f"=== Sistem Sesleri Tanıma Metinleri - {datetime.now().strftime('%Y-%m-%d')} ===\n\n")
        
        print("\nSistem otomatik olarak başlatılıyor...")
        print("Bilgisayarınızdan herhangi bir ses çalmaya başlayın (video, müzik, vs).")
        print("Algılanan sesler otomatik olarak metne çevrilecektir.")
        print("Durdurmak için CTRL+C tuşlarına basın.")
        
        # Ses yakalama ve işleme thread'lerini başlat
        recording_thread = threading.Thread(target=self.record_audio)
        processing_thread = threading.Thread(target=self.process_audio_queue)
        
        try:
            # Thread'leri başlat
            recording_thread.start()
            processing_thread.start()
            
            # Ana döngü - metin kuyruğunu kontrol et ve dosyaya kaydet
            while True:
                if not self.text_queue.empty():
                    text = self.text_queue.get()
                    self.save_to_file(text)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nProgram sonlandırılıyor...")
            self.is_recording = False
            self.is_processing = False
            
            # Thread'lerin kapanmasını bekle
            recording_thread.join()
            processing_thread.join()
            
            # Son cümleyi tamamla
            if self.current_sentence:
                self.complete_sentence(add_period=True)
                if not self.text_queue.empty():
                    text = self.text_queue.get()
                    self.save_to_file(text)
            
            print(f"Tanınan metinler '{self.output_file}' dosyasına kaydedildi.")
        finally:
            # PyAudio nesnesini kapat
            self.audio.terminate()

if __name__ == "__main__":
    print("=== Sistem Ses Tanıma Uygulaması ===")
    print("\nBu uygulama, bilgisayarınızdan gelen sesleri (hoparlör veya kulaklık) otomatik olarak")
    print("yakalayıp metne çevirir.")
    
    # Doğrudan başlat
    app = SystemAudioToText()
    app.start()
