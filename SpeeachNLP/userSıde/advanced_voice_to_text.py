import speech_recognition as sr
import time
import threading
import queue
import os
import re
from datetime import datetime

class RealtimeVoiceToText:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        # Ses algılama hassasiyetini artır
        self.recognizer.energy_threshold = 300  # Varsayılan 300, düşük değer daha hassas algılama
        self.recognizer.dynamic_energy_threshold = True  # Dinamik enerji eşiği
        self.recognizer.pause_threshold = 0.8  # Konuşma duraksaması (düşük değer daha hızlı algılama)
        
        # Tüm mikrofon cihazlarını listele
        print("Kullanılabilir mikrofon cihazları:")
        for i, microphone_name in enumerate(sr.Microphone.list_microphone_names()):
            print(f"{i}: {microphone_name}")
        print("\nVarsayılan mikrofon kullanılıyor. Farklı bir mikrofon için kodu düzenleyin.")
        
        # Varsayılan mikrofonu kullan
        self.microphone = sr.Microphone()
        self.text_queue = queue.Queue()
        self.is_listening = False
        self.stop_listening_callback = None
        self.output_file = "tanınan_metinler.txt"
        
        # Cümle oluşturma için ek özellikler
        self.current_sentence = ""
        self.sentence_buffer = []
        self.last_speech_time = None
        self.sentence_timeout = 2.5  # saniye cinsinden cümle tamamlama zaman aşımı
        self.sentence_end_pattern = re.compile(r'[.!?]')
    
    def callback(self, recognizer, audio):
        try:
            # Google Speech Recognition kullanarak sesi metne çevir (Türkçe dil desteği ile)
            print("Ses işleniyor...")
            # Hata ayıklama için ses verisinin uzunluğunu göster
            print(f"Ses süresi: ~{len(audio.frame_data)/audio.sample_rate:.2f} saniye")
            
            text = recognizer.recognize_google(audio, language="tr-TR", show_all=False)
            current_time = datetime.now()
            
            if text:
                # Zamanı güncelle ve metni işle
                self.last_speech_time = current_time
                self.process_speech_fragment(text)
                
                # Debug çıktısı (son fragment)
                print(f"[{current_time.strftime('%H:%M:%S')}] Algılanan parça: {text}")
            else:
                print("Ses algılandı ancak metin çıkarılamadı.")
        except sr.UnknownValueError:
            print("[!] Ses anlaşılamadı - lütfen daha yüksek sesle veya daha net konuşun")
        except sr.RequestError as e:
            print(f"[!] Google Speech Recognition servisi hatası: {e}")
        except Exception as e:
            print(f"[!] Beklenmeyen hata: {e}")
            
    def process_speech_fragment(self, text):
        """Konuşma parçalarını işleyerek cümle oluşturur"""
        # Büyük harfle başlat (eğer bu yeni bir cümle başlangıcıysa)
        if not self.current_sentence:
            text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
            
        # Metni mevcut cümle tamponuna ekle
        self.current_sentence += " " + text if self.current_sentence else text
        
        # Eğer metinde cümle bitirme işareti varsa, cümleyi tamamla
        if self.sentence_end_pattern.search(text):
            self.complete_sentence()
        # Veya eğer cümle uzunsa (muhtemelen noktalama işareti eksik)
        elif len(self.current_sentence.split()) > 15:
            self.complete_sentence(add_period=True)
    
    def complete_sentence(self, add_period=False):
        """Mevcut cümleyi tamamlar ve kuyruğa ekler"""
        if not self.current_sentence:
            return
        
        # Cümleyi tamamla (gerekiyorsa nokta ekle)
        sentence = self.current_sentence.strip()
        if add_period and not self.sentence_end_pattern.search(sentence):
            sentence += "."
            
        # Cümleyi kuyruğa ekle ve buffer'ı temizle
        self.text_queue.put(sentence)
        print(f"[CÜMLE TAMAMLANDI] {sentence}")
        self.current_sentence = ""
    
    def check_sentence_timeout(self):
        """Belirli bir süre konuşma algılanmazsa mevcut cümleyi tamamlar"""
        if (self.current_sentence and self.last_speech_time and 
            (datetime.now() - self.last_speech_time).total_seconds() > self.sentence_timeout):
            self.complete_sentence(add_period=True)
    
    def adjust_for_noise(self):
        print("Gürültü eşiği ayarlanıyor, lütfen sessiz olun...")
        try:
            with self.microphone as source:
                # Gürültü ayarlaması için süreyi 3 saniyeye çıkar
                self.recognizer.adjust_for_ambient_noise(source, duration=3)
            print("Gürültü eşiği ayarlandı!")
            # Ayarlanan eşik değerini göster
            print(f"Ayarlanan enerji eşiği: {self.recognizer.energy_threshold}")
        except Exception as e:
            print(f"Gürültü eşiği ayarlanırken hata: {e}")
            print("Manuel enerji eşiği ayarlanıyor...")
            # Manuel olarak eşik değeri belirle
            self.recognizer.energy_threshold = 300
    
    def start_listening(self):
        if not self.is_listening:
            self.adjust_for_noise()
            print("Dinleme başlatılıyor...")
            self.stop_listening_callback = self.recognizer.listen_in_background(self.microphone, self.callback)
            self.is_listening = True
            self.last_speech_time = datetime.now()
            print("Dinleme aktif. Konuşmaya başlayabilirsiniz.")
            print("Çıkmak için CTRL+C tuşlarına basın.")
    
    def stop_listening(self):
        if self.is_listening and self.stop_listening_callback:
            # Son cümleyi tamamla
            if self.current_sentence:
                self.complete_sentence(add_period=True)
                
            self.stop_listening_callback(wait_for_stop=False)
            self.is_listening = False
            print("Dinleme durduruldu.")
    
    def save_to_file(self, text):
        with open(self.output_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
    
    def run(self):
        self.start_listening()
        
        try:
            while self.is_listening:
                # Zaman aşımı kontrolü - belirli bir süre konuşma yoksa cümleyi tamamla
                self.check_sentence_timeout()
                
                # Tamamlanan cümleleri dosyaya kaydet
                if not self.text_queue.empty():
                    text = self.text_queue.get()
                    self.save_to_file(text)
                    
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nProgram sonlandırılıyor...")
            self.stop_listening()
            print(f"Tanınan metinler '{self.output_file}' dosyasına kaydedildi.")

if __name__ == "__main__":
    print("=== Gerçek Zamanlı Türkçe Ses Tanıma Uygulaması ===")
    
    # Kullanıcıya mikrofon seçimi için prompt göster
    print("\nFarklı bir mikrofon seçmek ister misiniz? (E/H): ", end="")
    choice = input().strip().lower()
    
    app = RealtimeVoiceToText()
    
    if choice == "e" or choice == "evet":
        try:
            print("\nHangi mikrofonu kullanmak istiyorsunuz? (Numara girin): ", end="")
            device_index = int(input().strip())
            
            # Yeni mikrofon nesnesi oluştur
            print(f"\n{device_index} numaralı mikrofon seçildi. Değiştiriliyor...")
            app.microphone = sr.Microphone(device_index=device_index)
            print("Mikrofon değiştirildi!")
        except ValueError:
            print("Geçersiz değer. Varsayılan mikrofon kullanılacak.")
        except Exception as e:
            print(f"Mikrofon değiştirilirken hata oluştu: {e}")
            print("Varsayılan mikrofon kullanılacak.")
    
    # Eğer çıktı dosyası yoksa oluştur
    if not os.path.exists("tanınan_metinler.txt"):
        with open("tanınan_metinler.txt", "w", encoding="utf-8") as f:
            f.write(f"=== Tanınan Metinler - {datetime.now().strftime('%Y-%m-%d')} ===\n\n")
    
    # Uygulamayı başlat
    app.run()
