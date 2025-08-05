"""
Türkçe Ders/Toplantı Odak Analiz Sistemi

Bu sistem, öğrencinin konuşmalarının ders/toplantı konusuyla 
alakalı olup olmadığını tespit eder. Ana amaç:
- Ders scripti (system_texts): İzlenen ders/toplantının içeriği
- Öğrenci konuşması (user_texts): Öğrencinin söyledikleri
- Çıktı: Öğrenci ders konusuyla alakalı mı konuşuyor, alakasız mı?
"""

import requests
import json
from datetime import datetime, timedelta
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import pandas as pd
import time
import warnings
import re
import difflib
from collections import Counter

warnings.filterwarnings("ignore")

class LessonFocusAnalyzer:
    def __init__(self):
        """Ders/Toplantı Odak Analiz Sistemi - Öğrenci konuşması ders konusuyla alakalı mı?"""
        print("🎯 Ders/Toplantı Odak Analiz Sistemi Yükleniyor...")
        print("📚 Amaç: Öğrenci konuşmasının ders konusuyla alakasını tespit etmek")
        
        # Ana BERT modelini yükle
        self.load_model()
        
        # Metin işleme ve odak analizi araçları
        self.setup_focus_analysis_tools()
        
        self.api_url = "http://localhost:5002/get_texts"
        self.analysis_results = []
        
        print("✅ Odak Analiz Sistemi hazır!")
    
    def load_model(self):
        """Gelişmiş çok dilli BERT modelini yükler"""
        print("📚 Gelişmiş çok dilli BERT modeli yükleniyor...")
        try:
            # Önce güncel ve performanslı modeli dene
            self.bert_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-mpnet-base-v2')
            print("✅ Gelişmiş çok dilli BERT modeli yüklendi!")
        except Exception as e:
            print(f"⚠️ Ana model yüklenemedi, alternatif model deneniyor... ({e})")
            try:
                # Alternatif olarak daha hafif ama güçlü model
                self.bert_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
                print("✅ Alternatif çok dilli modeli yüklendi!")
            except Exception as e2:
                print(f"⚠️ Alternatif model de yüklenemedi, varsayılan modele geri dönülüyor... ({e2})")
                # Son çare olarak eski modeli kullan
                self.bert_model = SentenceTransformer('dbmdz/bert-base-turkish-cased')
                print("✅ Varsayılan BERT modeli yüklendi!")
    
    def setup_focus_analysis_tools(self):
        """Odak analizi için özel araçları kurar"""
        # Türkçe stopwords
        self.turkish_stopwords = set([
            'bir', 'bu', 'da', 'de', 'en', 've', 'ile', 'için', 'ki', 'mi', 'mu', 'mü',
            'olan', 'olarak', 'ama', 'ancak', 'çok', 'daha', 'gibi', 'kadar', 'sonra',
            'şey', 'şu', 'var', 'yok', 'ise', 'eğer', 'hem', 'ya', 'veya', 'bana',
            'beni', 'bunu', 'şunu', 'onun', 'bunun', 'şunun', 'o', 'ben', 'sen',
            'biz', 'siz', 'onlar', 'abi', 'ya', 'hocam', 'efendim'
        ])
        
        # Genişletilmiş eğitim/iş konuları anahtar kelimeleri
        self.topic_keywords = {
            'matematik': ['matematik', 'sayı', 'hesap', 'formül', 'denklem', 'geometri', 'algebra', 'trigonometri'],
            'teknoloji': ['bilgisayar', 'yazılım', 'program', 'kod', 'algoritma', 'veri', 'sistem', 'network'],
            'yapay_zeka': ['yapay', 'zeka', 'ai', 'makine', 'öğrenme', 'model', 'deep', 'neural'],
            'görüntü_işleme': ['resim', 'görüntü', 'piksel', 'filtre', 'çizgi', 'opencv', 'vision'],
            'web_geliştirme': ['html', 'css', 'javascript', 'react', 'node', 'backend', 'frontend'],
            'mobil_geliştirme': ['android', 'ios', 'flutter', 'swift', 'kotlin', 'mobile'],
            'veritabanı': ['database', 'sql', 'mysql', 'postgresql', 'mongodb', 'veritabanı'],
            'proje_yönetimi': ['proje', 'scrum', 'agile', 'sprint', 'kanban', 'planning'],
            'genel_eğitim': ['ders', 'öğren', 'anlat', 'açıkla', 'örnek', 'konu', 'kurs', 'eğitim'],
            'toplantı': ['toplantı', 'meeting', 'sunum', 'presentation', 'rapor', 'görüşme']
        }
        
        # Alakasız konular (kişisel, günlük hayat)
        self.irrelevant_keywords = {
            'kişisel': ['ailə', 'aile', 'anne', 'baba', 'kardeş', 'evli', 'sevgili', 'arkadaş'],
            'günlük_hayat': ['yemek', 'kahvaltı', 'akşam', 'sabah', 'uyku', 'yorgun', 'hasta'],
            'eğlence': ['film', 'dizi', 'müzik', 'oyun', 'tatil', 'parti', 'dans'],
            'spor': ['futbol', 'basketbol', 'tenis', 'yüzme', 'koşu', 'gym', 'spor'],
            'alışveriş': ['market', 'mağaza', 'alışveriş', 'para', 'ucuz', 'pahalı'],
            'hava_durumu': ['hava', 'yağmur', 'kar', 'güneş', 'soğuk', 'sıcak'],
            'siyaset': ['seçim', 'parti', 'hükümet', 'başkan', 'milletvekili', 'siyasi']
        }
    
    def preprocess_text(self, text):
        """Metni ön işleme tabi tutar"""
        if not text:
            return ""
        
        # Küçük harfe çevir
        text = text.lower().strip()
        
        # Özel karakterleri temizle ama kelimeler arası boşlukları koru
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        return text
    
    def extract_keywords(self, text):
        """Metinden anahtar kelimeleri çıkarır"""
        clean_text = self.preprocess_text(text)
        words = clean_text.split()
        
        # Stopwords'leri çıkar ve 2 harften uzun kelimeleri al
        keywords = [word for word in words 
                   if word not in self.turkish_stopwords and len(word) > 2]
        
        return keywords
    
    def analyze_lesson_focus(self, lesson_text, student_text):
        """
        Öğrenci konuşmasının ders konusuyla alakasını analiz eder
        
        Args:
            lesson_text: Ders/toplantı metni (system_texts)
            student_text: Öğrenci konuşması (user_texts)
            
        Returns:
            dict: Odak analiz sonuçları
        """
        results = {}
        
        # 1. BERT Semantic Relevance (Ana metrik)
        try:
            if not lesson_text.strip() or not student_text.strip():
                results['semantic_relevance'] = 0.0
            else:
                # Metinleri normalize et
                normalized_lesson = self.preprocess_text(lesson_text)
                normalized_student = self.preprocess_text(student_text)
                
                if len(normalized_lesson) < 3 or len(normalized_student) < 3:
                    results['semantic_relevance'] = self.calculate_simple_similarity(lesson_text, student_text)
                else:
                    # BERT embeddings ile alakayı hesapla
                    embeddings = self.bert_model.encode([normalized_lesson, normalized_student], 
                                                       normalize_embeddings=True,
                                                       show_progress_bar=False)
                    relevance_score = float(cosine_similarity([embeddings[0]], [embeddings[1]])[0][0])
                    results['semantic_relevance'] = max(0.0, relevance_score)
        except Exception as e:
            print(f"⚠️ BERT hesaplama hatası: {e}")
            results['semantic_relevance'] = self.calculate_simple_similarity(lesson_text, student_text)
        
        # 2. Topic Overlap Analysis (Konu çakışması)
        lesson_topics = self.detect_topics(lesson_text)
        student_topics = self.detect_topics(student_text)
        
        # Ortak konular var mı?
        common_topics = lesson_topics.intersection(student_topics)
        results['topic_overlap'] = len(common_topics) / max(len(lesson_topics.union(student_topics)), 1)
        results['common_topics'] = list(common_topics)
        
        # 3. Irrelevant Content Detection (Alakasız içerik tespiti)
        irrelevant_score = self.detect_irrelevant_content(student_text)
        results['irrelevant_score'] = irrelevant_score
        
        # 4. Keyword Relevance (Anahtar kelime alakası)
        lesson_keywords = set(self.extract_keywords(lesson_text))
        student_keywords = set(self.extract_keywords(student_text))
        
        if lesson_keywords and student_keywords:
            keyword_overlap = len(lesson_keywords.intersection(student_keywords)) / len(lesson_keywords.union(student_keywords))
        else:
            keyword_overlap = 0.0
        results['keyword_relevance'] = keyword_overlap
        
        # 5. FINAL FOCUS SCORE (Nihai odak skoru)
        # Alakasız içerik varsa penaltı
        irrelevant_penalty = irrelevant_score * 0.5
        
        # Odak skoru hesaplama
        focus_score = (
            results['semantic_relevance'] * 0.40 +      # BERT alakası (en önemli)
            results['topic_overlap'] * 0.25 +           # Konu çakışması
            results['keyword_relevance'] * 0.20 +       # Anahtar kelime alakası
            (1 - irrelevant_penalty) * 0.15             # Alakasız içerik penaltısı
        )
        
        results['focus_score'] = max(0.0, min(1.0, focus_score))
        
        # 6. Focus Grade and Category
        grade, category, emoji = self.get_focus_grade(results['focus_score'])
        results['focus_grade'] = grade
        results['focus_category'] = category
        results['focus_emoji'] = emoji
        
        return results
    
    def detect_topics(self, text):
        """Metindeki konuları tespit eder"""
        detected_topics = set()
        text_lower = text.lower()
        
        for topic_category, keywords in self.topic_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                detected_topics.add(topic_category)
        
        return detected_topics
    
    def detect_irrelevant_content(self, text):
        """Alakasız içerik oranını tespit eder"""
        text_lower = text.lower()
        irrelevant_count = 0
        total_categories = len(self.irrelevant_keywords)
        
        for category, keywords in self.irrelevant_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                irrelevant_count += 1
        
        return irrelevant_count / total_categories if total_categories > 0 else 0.0
    
    def get_focus_grade(self, score):
        """Odak skoruna göre not ve kategori verir"""
        if score >= 0.80:
            return "A+", "TAM ODAKLI", "🎯"
        elif score >= 0.70:
            return "A", "ÇOK İYİ ODAK", "💚"
        elif score >= 0.60:
            return "B+", "İYİ ODAK", "💛"
        elif score >= 0.50:
            return "B", "ORTA ODAK", "🧡"
        elif score >= 0.40:
            return "C+", "ZAYIF ODAK", "❤️"
        elif score >= 0.30:
            return "C", "ÇOK ZAYIF ODAK", "💔"
        elif score >= 0.20:
            return "D", "DAĞINIK", "⚠️"
    def calculate_simple_similarity(self, text1, text2):
        """Basit benzerlik hesaplama (BERT alternatifi)"""
        if not text1.strip() and not text2.strip():
            return 1.0
        if not text1.strip() or not text2.strip():
            return 0.0
        
        # Kelime tabanlı benzerlik
        words1 = set(self.extract_keywords(text1))
        words2 = set(self.extract_keywords(text2))
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
        
        jaccard = len(words1.intersection(words2)) / len(words1.union(words2))
        
        # Karakter benzerliği
        char_sim = difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
        
        # Basit ağırlıklı ortalama
        return (jaccard * 0.7) + (char_sim * 0.3)
    
    def calculate_advanced_similarity(self, text1, text2):
        """
        Gelişmiş benzerlik analizi - BERT odaklı ama dengeli
        
        Returns:
            dict: Farklı metriklerle hesaplanmış benzerlik skorları
        """
        results = {}
        
        # 1. BERT Semantic Similarity (Ana metrik) - İyileştirilmiş
        try:
            # Boş metinleri kontrol et
            if not text1.strip() or not text2.strip():
                results['bert_similarity'] = 0.0 if text1.strip() != text2.strip() else 1.0
            else:
                # Metinleri normalize et
                normalized_text1 = self.preprocess_text(text1)
                normalized_text2 = self.preprocess_text(text2)
                
                # Eğer normalize edilmiş metinler çok kısaysa, alternatif hesaplama
                if len(normalized_text1) < 3 or len(normalized_text2) < 3:
                    results['bert_similarity'] = self.calculate_simple_similarity(text1, text2)
                else:
                    # BERT embeddings hesapla
                    bert_embeddings = self.bert_model.encode([normalized_text1, normalized_text2], 
                                                           normalize_embeddings=True,
                                                           show_progress_bar=False)
                    bert_score = float(cosine_similarity([bert_embeddings[0]], [bert_embeddings[1]])[0][0])
                    results['bert_similarity'] = max(0.0, bert_score)  # Negatif skorları önle
        except Exception as e:
            print(f"⚠️ BERT hesaplama hatası: {e}")
            results['bert_similarity'] = self.calculate_simple_similarity(text1, text2)
        
        # 2. Topic Similarity (Konu benzerliği)
        results['topic_similarity'] = self.calculate_topic_similarity(text1, text2)
        
        # 3. Length Similarity (Uzunluk benzerliği)
        len1, len2 = len(text1.split()), len(text2.split())
        if len1 == 0 and len2 == 0:
            length_sim = 1.0
        elif len1 == 0 or len2 == 0:
            length_sim = 0.0
        else:
            length_sim = min(len1, len2) / max(len1, len2)
        results['length_similarity'] = length_sim
        
        # 4. Character Similarity (Karakter benzerliği)
        char_sim = difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
        results['character_similarity'] = char_sim
        
        # 5. Word Overlap (Kelime çakışması)
        words1 = set(self.extract_keywords(text1))
        words2 = set(self.extract_keywords(text2))
        
        if words1 or words2:
            word_overlap = len(words1.intersection(words2)) / len(words1.union(words2)) if words1.union(words2) else 0.0
        else:
            word_overlap = 1.0 if not text1.strip() and not text2.strip() else 0.0
        
        results['word_overlap'] = word_overlap
        
        # 6. Context Similarity (Bağlam benzerliği)
        # Eğitim bağlamında özel kontroller
        education_context_bonus = 0.0
        
        # Eğitim terimleri kontrolü
        education_terms = ['ders', 'öğren', 'anlat', 'açıkla', 'örnek', 'konu', 'kurs']
        text1_edu = any(term in text1.lower() for term in education_terms)
        text2_edu = any(term in text2.lower() for term in education_terms)
        
        if text1_edu and text2_edu:
            education_context_bonus = 0.2
        
        results['context_similarity'] = min(education_context_bonus + word_overlap, 1.0)
        
        # 7. SMART WEIGHTED COMBINATION (Akıllı Ağırlıklı Birleştirme)
        # BERT skoruna göre dinamik ağırlıklandırma
        
        bert_score = results['bert_similarity']
        
        if bert_score >= 0.8:
            # BERT çok yüksekse, ona daha fazla güven
            weights = {
                'bert_similarity': 0.70,
                'topic_similarity': 0.15,
                'word_overlap': 0.10,
                'context_similarity': 0.05
            }
        elif bert_score >= 0.6:
            # BERT ortaysa, dengeli yaklaşım
            weights = {
                'bert_similarity': 0.50,
                'topic_similarity': 0.25,
                'word_overlap': 0.15,
                'context_similarity': 0.10
            }
        else:
            # BERT düşükse, diğer metriklere daha fazla ağırlık ver
            weights = {
                'bert_similarity': 0.35,
                'topic_similarity': 0.35,
                'word_overlap': 0.20,
                'context_similarity': 0.10
            }
        
        # Ağırlıklı birleşik skor
        combined_score = sum(results.get(metric, 0) * weight for metric, weight in weights.items())
        results['smart_combined'] = combined_score
        
        # Kullanılan ağırlıkları da kaydet
        results['weights_used'] = weights
        
        return results
    
    def get_similarity_grade(self, score):
        """Benzerlik skoruna göre not ve açıklama verir"""
        if score >= 0.85:
            return "A+", "Mükemmel Uygunluk", "🏆"
        elif score >= 0.75:
            return "A", "Çok Yüksek Uygunluk", "💎"
        elif score >= 0.65:
            return "B+", "Yüksek Uygunluk", "💚"
        elif score >= 0.55:
            return "B", "İyi Uygunluk", "💛"
        elif score >= 0.45:
            return "C+", "Orta Uygunluk", "🧡"
        elif score >= 0.35:
            return "C", "Düşük Uygunluk", "❤️"
        elif score >= 0.25:
            return "D", "Zayıf Uygunluk", "💔"
        else:
            return "F", "Uygunsuz", "❌"
    
    def fetch_texts_from_api(self):
        """API'den metin verilerini çeker ve mevcut focus_score'u da alır"""
        try:
            response = requests.get(self.api_url)
            if response.status_code == 200:
                data = response.json()
                # API'den gelen focus_score'u da dahil et
                if 'focus_score' in data and data['focus_score'] is not None:
                    print(f"📊 API'den mevcut focus_score alındı: {data['focus_score']:.4f} ({data['focus_score']*100:.1f}%)")
                return data
            else:
                print(f"API hatası: {response.status_code}")
                return None
        except requests.exceptions.ConnectionError:
            print("API bağlantısı kurulamadı. Sunucunun çalıştığından emin olun.")
            return None
        except Exception as e:
            print(f"Veri çekme hatası: {e}")
            return None
    
    def parse_time(self, time_str):
        """Zaman string'ini datetime objesine çevirir"""
        try:
            return datetime.strptime(time_str, "%H:%M:%S").time()
        except ValueError:
            print(f"Geçersiz zaman formatı: {time_str}")
            return None
    
    def find_temporal_matches(self, system_texts, user_texts, time_window=20):
        """Zaman damgalarına göre eşleşen metinleri bulur - 20 saniye pencere"""
        matches = []
        
        for sys_text in system_texts:
            sys_time = self.parse_time(sys_text['time'])
            if sys_time is None:
                continue
                
            for user_text in user_texts:
                user_time = self.parse_time(user_text['time'])
                if user_time is None:
                    continue
                
                # Zaman farkını hesapla
                sys_datetime = datetime.combine(datetime.today(), sys_time)
                user_datetime = datetime.combine(datetime.today(), user_time)
                time_diff = abs((user_datetime - sys_datetime).total_seconds())
                
                if time_diff <= time_window:
                    matches.append({
                        'system_text': sys_text['text'],
                        'system_time': sys_text['time'],
                        'user_text': user_text['text'],
                        'user_time': user_text['time'],
                        'time_difference': time_diff
                    })
        
        return matches
    
    def analyze_lesson_focus_from_api(self, time_window=20):
        """API'den gelen verilerle odak analizi yapar - 20 saniye pencere"""
        print("📡 Ders ve öğrenci konuşmaları API'den çekiliyor...")
        data = self.fetch_texts_from_api()
        
        if data is None:
            print("❌ Veri çekilemedi!")
            return None
        
        print(f"📊 Ders metni: {data.get('total_system', 0)} | Öğrenci konuşması: {data.get('total_user', 0)}")
        print(f"🕒 Son güncelleme: {data.get('last_update', 'Bilinmiyor')}")
        
        # API'den gelen mevcut focus_score'u al
        api_focus_score = data.get('focus_score', None)
        if api_focus_score is not None:
            print(f"🎯 API'deki güncel focus_score: {api_focus_score:.4f} ({api_focus_score*100:.1f}%)")
        
        matches = self.find_temporal_matches(
            data['system_texts'], 
            data['user_texts'], 
            time_window
        )
        
        if not matches:
            print("⚠️ Zaman penceresi içinde eşleşen konuşma bulunamadı!")
            # Sadece API focus_score varsa onu göster
            if api_focus_score is not None:
                print(f"\n📊 API'DEN GELEN GÜNCEL ODAK SKORU: {api_focus_score:.4f} ({api_focus_score*100:.1f}%)")
                grade, category, emoji = self.get_focus_grade(api_focus_score)
                print(f"{emoji} DEĞERLENDİRME: {grade} - {category}")
                return {'api_focus_score': api_focus_score, 'focus_grade': grade, 'focus_category': category}
            return None
        
        print(f"\n🎯 {len(matches)} adet eşleştirme bulundu!")
        print("="*100)
        
        results = []
        
        for i, match in enumerate(matches, 1):
            print(f"\n� ODAK ANALİZİ {i}:")
            print(f"⏱️ Zaman Farkı: {match['time_difference']:.1f} saniye")
            print("-" * 60)
            print(f"🎓 DERS İÇERİĞİ ({match['system_time']}): {match['system_text']}")
            print(f"👨‍🎓 ÖĞRENCİ KONUŞMASI ({match['user_time']}): {match['user_text']}")
            print("-" * 60)
            
            # Odak analizi
            focus_analysis = self.analyze_lesson_focus(
                match['system_text'], 
                match['user_text']
            )
            
            # Ana odak skoru
            focus_score = focus_analysis['focus_score']
            grade = focus_analysis['focus_grade']
            category = focus_analysis['focus_category']
            emoji = focus_analysis['focus_emoji']
            
            print(f"🎯 ODAK SKORU: {focus_score:.4f} ({focus_score*100:.1f}%)")
            print(f"{emoji} DEĞERLENDİRME: {grade} - {category}")
            
            # API focus_score ile karşılaştırma
            if api_focus_score is not None:
                difference = abs(focus_score - api_focus_score)
                print(f"📊 API Focus Score: {api_focus_score:.4f} | Fark: {difference:.4f}")
            
            # Detaylı analiz
            print(f"\n📊 DETAYLI ODAK ANALİZİ:")
            print(f"   🤖 Semantik Alaka: {focus_analysis['semantic_relevance']:.3f} ({focus_analysis['semantic_relevance']*100:.1f}%)")
            print(f"   🎯 Konu Çakışması: {focus_analysis['topic_overlap']:.3f} ({focus_analysis['topic_overlap']*100:.1f}%)")
            print(f"   🔤 Anahtar Kelime Alakası: {focus_analysis['keyword_relevance']:.3f} ({focus_analysis['keyword_relevance']*100:.1f}%)")
            print(f"   ⚠️ Alakasız İçerik: {focus_analysis['irrelevant_score']:.3f} ({focus_analysis['irrelevant_score']*100:.1f}%)")
            
            # Ortak konular
            if focus_analysis['common_topics']:
                print(f"   📚 Ortak Konular: {', '.join(focus_analysis['common_topics'])}")
            else:
                print(f"   📚 Ortak Konular: Bulunamadı")
            
            # Odak durumu açıklaması
            if focus_score >= 0.70:
                explanation = "✅ Öğrenci ders konusuyla alakalı konuşuyor"
            elif focus_score >= 0.50:
                explanation = "⚡ Öğrenci kısmen ders konusuyla alakalı konuşuyor"
            elif focus_score >= 0.30:
                explanation = "⚠️ Öğrenci ders konusundan uzaklaşıyor"
            else:
                explanation = "❌ Öğrenci ders konusuyla alakasız konuşuyor"
            
            print(f"\n💡 SONUÇ: {explanation}")
            
            # Sonucu kaydet (API focus_score'u da dahil et)
            result = {
                'analysis_id': i,
                'lesson_content': match['system_text'],
                'lesson_time': match['system_time'],
                'student_speech': match['user_text'],
                'student_time': match['user_time'],
                'time_difference': match['time_difference'],
                'focus_score': focus_score,
                'focus_grade': grade,
                'focus_category': category,
                'explanation': explanation,
                'api_focus_score': api_focus_score,  # API'den gelen score
                **focus_analysis  # Tüm analiz detaylarını ekle
            }
            
            results.append(result)
            print("="*100)
        
        # Özet istatistikler (API score ile birlikte)
        if results:
            focus_scores = [r['focus_score'] for r in results]
            
            print(f"\n📈 ODAK ANALİZİ ÖZETİ:")
            print(f"🔢 Toplam Analiz: {len(results)}")
            print(f"🎯 Ortalama Odak Skoru: {np.mean(focus_scores):.4f} ({np.mean(focus_scores)*100:.1f}%)")
            
            # API score ile karşılaştırma
            if api_focus_score is not None:
                avg_calculated = np.mean(focus_scores)
                api_difference = abs(avg_calculated - api_focus_score)
                print(f"📊 API Focus Score: {api_focus_score:.4f} ({api_focus_score*100:.1f}%)")
                print(f"⚖️ Ortalama Fark: {api_difference:.4f}")
            
            print(f"📊 Standart Sapma: {np.std(focus_scores):.4f}")
            print(f"⬆️ En Yüksek Odak: {max(focus_scores):.4f} ({max(focus_scores)*100:.1f}%)")
            print(f"⬇️ En Düşük Odak: {min(focus_scores):.4f} ({min(focus_scores)*100:.1f}%)")
            
            # Odak dağılımı
            grades = [r['focus_grade'] for r in results]
            grade_counts = Counter(grades)
            print(f"\n🏆 ODAK DAĞILIMI:")
            for grade, count in sorted(grade_counts.items()):
                print(f"   {grade}: {count} adet")
            
            # Genel değerlendirme
            avg_score = np.mean(focus_scores)
            if avg_score >= 0.70:
                overall = "✅ ÖĞRENCİ GENEL OLARAK DERSİ TAKİP EDİYOR"
            elif avg_score >= 0.50:
                overall = "⚡ ÖĞRENCİ KISMEN DERSİ TAKİP EDİYOR"
            elif avg_score >= 0.30:
                overall = "⚠️ ÖĞRENCİ DERSTİN ODAĞINI KAYBEDEYOR"
            else:
                overall = "❌ ÖĞRENCİ DERSTEN KOPMUŞ DURUMDA"
            
            print(f"\n🎯 GENEL DEĞERLENDİRME: {overall}")
        
        self.analysis_results = results
        return results
    
    def analyze_recent_period(self, period_seconds=20):
        """Son X saniyedeki tüm verileri toplu analiz eder"""
        print(f"📡 Son {period_seconds} saniyenin tüm verileri analiz ediliyor...")
        data = self.fetch_texts_from_api()
        
        if data is None:
            print("❌ Veri çekilemedi!")
            return None
        
        print(f"📊 Sistem metni: {data.get('total_system', 0)} | Kullanıcı metni: {data.get('total_user', 0)}")
        print(f"🕒 Son güncelleme: {data.get('last_update', 'Bilinmiyor')}")
        
        # API'den gelen mevcut focus_score'u al
        api_focus_score = data.get('focus_score', None)
        if api_focus_score is not None:
            print(f"🎯 API'deki güncel focus_score: {api_focus_score:.4f} ({api_focus_score*100:.1f}%)")
        
        # Son X saniyedeki tüm verileri al
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(seconds=period_seconds)
        
        # Sistem ve kullanıcı metinlerini filtrele
        recent_system_texts = []
        recent_user_texts = []
        
        for sys_text in data['system_texts']:
            sys_time = self.parse_time(sys_text['time'])
            if sys_time:
                sys_datetime = datetime.combine(datetime.today(), sys_time)
                # Gün geçişi kontrolü için basit yaklaşım
                if (current_time - sys_datetime).total_seconds() <= period_seconds:
                    recent_system_texts.append(sys_text)
        
        for user_text in data['user_texts']:
            user_time = self.parse_time(user_text['time'])
            if user_time:
                user_datetime = datetime.combine(datetime.today(), user_time)
                # Gün geçişi kontrolü için basit yaklaşım
                if (current_time - user_datetime).total_seconds() <= period_seconds:
                    recent_user_texts.append(user_text)
        
        if not recent_system_texts and not recent_user_texts:
            print(f"⚠️ Son {period_seconds} saniyede veri bulunamadı!")
            # Sadece API focus_score varsa onu göster
            if api_focus_score is not None:
                print(f"\n📊 API'DEN GELEN GÜNCEL ODAK SKORU: {api_focus_score:.4f} ({api_focus_score*100:.1f}%)")
                grade, category, emoji = self.get_focus_grade(api_focus_score)
                print(f"{emoji} DEĞERLENDİRME: {grade} - {category}")
                return {'api_focus_score': api_focus_score, 'focus_grade': grade, 'focus_category': category}
            return None
        
        print(f"\n📊 SON {period_seconds} SANİYE ANALİZİ:")
        print(f"🎓 Ders metinleri: {len(recent_system_texts)} adet")
        print(f"👨‍🎓 Öğrenci konuşmaları: {len(recent_user_texts)} adet")
        print("="*100)
        
        # Tüm sistem metinlerini birleştir
        combined_system_text = " ".join([text['text'] for text in recent_system_texts])
        combined_user_text = " ".join([text['text'] for text in recent_user_texts])
        
        if not combined_system_text.strip() and not combined_user_text.strip():
            print("⚠️ Analiz edilecek metin bulunamadı!")
            if api_focus_score is not None:
                print(f"\n📊 API'DEN GELEN GÜNCEL ODAK SKORU: {api_focus_score:.4f} ({api_focus_score*100:.1f}%)")
                grade, category, emoji = self.get_focus_grade(api_focus_score)
                print(f"{emoji} DEĞERLENDİRME: {grade} - {category}")
                return {'api_focus_score': api_focus_score, 'focus_grade': grade, 'focus_category': category}
            return None
        
        # Detaylı metin gösterimi
        print(f"\n📝 BİRLEŞİK DERS İÇERİĞİ:")
        for i, text in enumerate(recent_system_texts, 1):
            print(f"   {i}. ({text['time']}) {text['text']}")
        
        print(f"\n👨‍🎓 BİRLEŞİK ÖĞRENCİ KONUŞMASI:")
        for i, text in enumerate(recent_user_texts, 1):
            print(f"   {i}. ({text['time']}) {text['text']}")
        
        print("-" * 100)
        
        # Odak analizi yap
        if combined_system_text.strip() and combined_user_text.strip():
            focus_analysis = self.analyze_lesson_focus(combined_system_text, combined_user_text)
            
            focus_score = focus_analysis['focus_score']
            grade = focus_analysis['focus_grade']
            category = focus_analysis['focus_category']
            emoji = focus_analysis['focus_emoji']
            
            print(f"\n🎯 TOPLAM ODAK SKORU: {focus_score:.4f} ({focus_score*100:.1f}%)")
            print(f"{emoji} DEĞERLENDİRME: {grade} - {category}")
            
            # API focus_score ile karşılaştırma
            if api_focus_score is not None:
                difference = abs(focus_score - api_focus_score)
                print(f"📊 API Focus Score: {api_focus_score:.4f} | Fark: {difference:.4f}")
                if difference < 0.1:
                    print("✅ Hesaplanan ve API skorları uyumlu")
                elif difference < 0.2:
                    print("⚡ Hesaplanan ve API skorları kısmen farklı")
                else:
                    print("⚠️ Hesaplanan ve API skorları önemli ölçüde farklı")
            
            print(f"\n📊 DETAYLI TOPLU ANALİZ:")
            print(f"   🤖 Semantik Alaka: {focus_analysis['semantic_relevance']:.3f} ({focus_analysis['semantic_relevance']*100:.1f}%)")
            print(f"   🎯 Konu Çakışması: {focus_analysis['topic_overlap']:.3f} ({focus_analysis['topic_overlap']*100:.1f}%)")
            print(f"   🔤 Anahtar Kelime Alakası: {focus_analysis['keyword_relevance']:.3f} ({focus_analysis['keyword_relevance']*100:.1f}%)")
            print(f"   ⚠️ Alakasız İçerik: {focus_analysis['irrelevant_score']:.3f} ({focus_analysis['irrelevant_score']*100:.1f}%)")
            
            if focus_analysis['common_topics']:
                print(f"   📚 Ortak Konular: {', '.join(focus_analysis['common_topics'])}")
            else:
                print(f"   📚 Ortak Konular: Bulunamadı")
            
            # Periyod sonucu
            if focus_score >= 0.70:
                period_result = f"✅ SON {period_seconds} SANİYEDE ÖĞRENCİ DERSİ TAKİP ETMİŞ"
            elif focus_score >= 0.50:
                period_result = f"⚡ SON {period_seconds} SANİYEDE ÖĞRENCİ KISMEN DERSİ TAKİP ETMİŞ"
            elif focus_score >= 0.30:
                period_result = f"⚠️ SON {period_seconds} SANİYEDE ÖĞRENCİ DERSTEN UZAKLAŞMIŞ"
            else:
                period_result = f"❌ SON {period_seconds} SANİYEDE ÖĞRENCİ DERSTEN KOPMUŞ"
            
            print(f"\n💡 PERİYOD SONUCU: {period_result}")
            
            # Sonucu kaydet (API score ile birlikte)
            result = {
                'analysis_time': current_time.strftime('%H:%M:%S'),
                'period_seconds': period_seconds,
                'system_texts_count': len(recent_system_texts),
                'user_texts_count': len(recent_user_texts),
                'combined_system_text': combined_system_text,
                'combined_user_text': combined_user_text,
                'focus_score': focus_score,
                'focus_grade': grade,
                'focus_category': category,
                'period_result': period_result,
                'api_focus_score': api_focus_score,  # API'den gelen score
                **focus_analysis
            }
            
            return result
        
        elif combined_system_text.strip():
            print(f"\n📚 Sadece ders içeriği var, öğrenci konuşması yok")
            result = {'analysis_time': current_time.strftime('%H:%M:%S'), 
                     'period_seconds': period_seconds,
                     'system_texts_count': len(recent_system_texts),
                     'user_texts_count': 0,
                     'api_focus_score': api_focus_score,
                     'result': 'only_system_content'}
            return result
        
        elif combined_user_text.strip():
            print(f"\n👨‍🎓 Sadece öğrenci konuşması var, ders içeriği yok")
            # Alakasız içerik kontrolü yap
            irrelevant_score = self.detect_irrelevant_content(combined_user_text)
            if irrelevant_score > 0.3:
                print(f"⚠️ Öğrenci büyük ihtimalle alakasız konular hakkında konuşuyor")
            result = {'analysis_time': current_time.strftime('%H:%M:%S'),
                     'period_seconds': period_seconds,
                     'system_texts_count': 0, 
                     'user_texts_count': len(recent_user_texts),
                     'irrelevant_score': irrelevant_score,
                     'api_focus_score': api_focus_score,
                     'result': 'only_user_content'}
            return result
        
        return None
    
    def save_results_to_csv(self, filename="lesson_focus_analysis_results.csv"):
        """Odak analizi sonuçlarını CSV dosyasına kaydeder"""
        if not self.analysis_results:
            print("⚠️ Kaydedilecek analiz sonucu bulunamadı!")
            return False
        
        try:
            df = pd.DataFrame(self.analysis_results)
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"💾 Odak analizi sonuçları {filename} dosyasına kaydedildi!")
            return True
        except Exception as e:
            print(f"❌ CSV kaydetme hatası: {e}")
            return False
    
    def test_focus_analysis_with_examples(self):
        """Odak analizi testini örnek verilerle yapar"""
        test_pairs = [
            # Yüksek odak beklenen (ders konusuyla alakalı)
            ("Python programlama dilinin temel özelliklerini öğreniyoruz", "Python gerçekten çok kullanışlı bir dil"),
            ("Makine öğrenmesi algoritmalarını inceliyoruz", "Bu algoritma nasıl çalışıyor hocam?"),
            ("Veritabanı tasarım prensiplerini açıklıyorum", "SQL sorguları çok karmaşık geliyor"),
            ("Proje yönetimi metodolojilerini tartışıyoruz", "Scrum methodology çok mantıklı"),
            
            # Orta odak (kısmen alakalı)
            ("JavaScript framework'leri hakkında konuşuyoruz", "Programlama zor ama güzel"),
            ("Ağ güvenliği protokollerini anlatıyorum", "Bilgisayarım çok yavaş çalışıyor"),
            
            # Düşük odak (alakasız)
            ("Algoritma karmaşıklığı analizi yapıyoruz", "Akşam ne yesek acaba?"),
            ("Frontend development teknikleri", "Futbol maçı çok heyecanlıydı"),
            ("Veritabanı normalizasyonu", "Annem bugün arara"),
            ("Yapay zeka etiği", "Hava çok soğuk bugün")
        ]
        
        print("\n🧪 ODAK ANALİZİ TEST SİSTEMİ:")
        print("="*80)
        
        total_time = 0
        for i, (lesson_text, student_text) in enumerate(test_pairs, 1):
            print(f"\nTest {i}:")
            print(f"🎓 Ders İçeriği: {lesson_text}")
            print(f"👨‍🎓 Öğrenci: {student_text}")
            
            start_time = time.time()
            focus_analysis = self.analyze_lesson_focus(lesson_text, student_text)
            end_time = time.time()
            
            processing_time = end_time - start_time
            total_time += processing_time
            
            focus_score = focus_analysis['focus_score']
            grade = focus_analysis['focus_grade']
            category = focus_analysis['focus_category']
            emoji = focus_analysis['focus_emoji']
            
            print(f"🎯 Odak Skoru: {focus_score:.4f} ({focus_score*100:.1f}%) - {grade} {emoji}")
            print(f"📊 Semantic: {focus_analysis['semantic_relevance']:.3f} | Konu: {focus_analysis['topic_overlap']:.3f} | Alakasız: {focus_analysis['irrelevant_score']:.3f}")
            if focus_analysis['common_topics']:
                print(f"📚 Ortak Konular: {', '.join(focus_analysis['common_topics'])}")
            print(f"⏱️ İşlem süresi: {processing_time:.3f}s")
            print("-" * 40)
        
        avg_time = total_time / len(test_pairs)
        print(f"\n📊 TEST ÖZETİ:")
        print(f"⏱️ Toplam süre: {total_time:.3f}s")
        print(f"⚡ Ortalama işlem süresi: {avg_time:.3f}s")
        print(f"🚀 Saniyede analiz: {1/avg_time:.1f} analiz/s")
    
    def continuous_monitoring(self, interval=30, time_window=20):
        """Sürekli odak izleme modu - 20 saniye pencere"""
        print(f"🔄 Sürekli odak izleme başlatıldı. Her {interval} saniyede bir kontrol edilecek...")
        print("💡 Öğrencinin ders odağı anlık olarak izleniyor...")
        print("Durdurmak için Ctrl+C tuşlarına basın.")
        
        try:
            while True:
                print(f"\n🔍 Kontrol zamanı: {datetime.now().strftime('%H:%M:%S')}")
                self.analyze_lesson_focus_from_api(time_window)
                
                print(f"⏳ {interval} saniye bekleniyor...")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Odak izleme durduruldu!")
        except Exception as e:
            print(f"❌ İzleme hatası: {e}")
    
    def continuous_period_monitoring(self, interval=20, period_seconds=20):
        """Sürekli periyodik analiz - Son X saniyedeki tüm verileri analiz eder"""
        print(f"📊 PERİYODİK ANALİZ MODU BAŞLATILDI")
        print(f"⏰ Her {interval} saniyede bir, son {period_seconds} saniyenin TÜM verileri analiz edilecek")
        print("💡 Bu modda zaman eşleştirmesi yerine toplu veri analizi yapılır")
        print("Durdurmak için Ctrl+C tuşlarına basın.")
        
        analysis_history = []
        
        try:
            while True:
                print(f"\n{'='*80}")
                print(f"🔍 PERİYODİK KONTROL: {datetime.now().strftime('%H:%M:%S')}")
                print(f"📊 Son {period_seconds} saniyedeki TÜM veriler analiz ediliyor...")
                
                result = self.analyze_recent_period(period_seconds)
                
                if result:
                    analysis_history.append(result)
                    
                    # Son 5 analizin trendini göster
                    if len(analysis_history) >= 2:
                        print(f"\n📈 TREND ANALİZİ:")
                        recent_scores = [r.get('focus_score', 0) for r in analysis_history[-5:] if 'focus_score' in r]
                        if len(recent_scores) >= 2:
                            trend = recent_scores[-1] - recent_scores[-2]
                            if trend > 0.1:
                                print(f"📈 Odak artıyor! (+{trend:.3f})")
                            elif trend < -0.1:
                                print(f"📉 Odak azalıyor! ({trend:.3f})")
                            else:
                                print(f"📊 Odak stabil ({trend:+.3f})")
                            
                            avg_recent = np.mean(recent_scores)
                            print(f"🎯 Son {len(recent_scores)} analiz ortalaması: {avg_recent:.3f} ({avg_recent*100:.1f}%)")
                
                print(f"\n⏳ {interval} saniye sonra tekrar analiz...")
                print("="*80)
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Periyodik analiz durduruldu!")
            
            # Özet rapor
            if analysis_history:
                focus_scores = [r.get('focus_score', 0) for r in analysis_history if 'focus_score' in r]
                if focus_scores:
                    print(f"\n📊 OTURUM ÖZETİ:")
                    print(f"🔢 Toplam analiz: {len(focus_scores)}")
                    print(f"🎯 Ortalama odak: {np.mean(focus_scores):.3f} ({np.mean(focus_scores)*100:.1f}%)")
                    print(f"⬆️ En yüksek odak: {max(focus_scores):.3f} ({max(focus_scores)*100:.1f}%)")
                    print(f"⬇️ En düşük odak: {min(focus_scores):.3f} ({min(focus_scores)*100:.1f}%)")
                    
        except Exception as e:
            print(f"❌ Periyodik analiz hatası: {e}")

def main():
    """Ana fonksiyon"""
    print("🎯 Ders/Toplantı Odak Analiz Sistemi v3.0")
    print("� Öğrenci Konuşmasının Ders Alakasını Tespit Eder")
    print("="*80)
    
    # Odak analiz sistemi
    try:
        analyzer = LessonFocusAnalyzer()
    except Exception as e:
        print(f"❌ Sistem başlatılamadı: {e}")
        print("💡 Gerekli kütüphaneleri yüklemek için: pip install -r requirements.txt")
        return
    
    while True:
        print("\n📋 DERS ODAK ANALİZ MENÜSÜ:")
        print("1. 🎯 Tek seferlik odak analizi (zaman eşleştirmeli)")
        print("2. 🔄 Sürekli odak izleme (zaman eşleştirmeli)")  
        print("3. 📊 Tek seferlik periyodik analiz (son 20 saniye)")
        print("4. ⏰ Sürekli periyodik izleme (20 saniyelik dönemler)")
        print("5. 💾 Analiz sonuçlarını CSV'ye kaydet")
        print("6. 🧪 Odak analizi testi (örnek verilerle)")
        print("7. 🚪 Çıkış")
        
        choice = input("\nSeçiminizi yapın (1-7): ").strip()
        
        if choice == "1":
            time_window = input("Zaman penceresi (saniye, varsayılan 10): ").strip()
            time_window = int(time_window) if time_window.isdigit() else 10
            
            analyzer.analyze_lesson_focus_from_api(time_window)
            
        elif choice == "2":
            interval = input("Kontrol aralığı (saniye, varsayılan 30): ").strip()
            interval = int(interval) if interval.isdigit() else 30
            
            time_window = input("Zaman penceresi (saniye, varsayılan 10): ").strip()
            time_window = int(time_window) if time_window.isdigit() else 10
            
            analyzer.continuous_monitoring(interval, time_window)
            
        elif choice == "3":
            period_seconds = input("Analiz periyodu (saniye, varsayılan 20): ").strip()
            period_seconds = int(period_seconds) if period_seconds.isdigit() else 20
            
            analyzer.analyze_recent_period(period_seconds)
            
        elif choice == "4":
            interval = input("Kontrol aralığı (saniye, varsayılan 20): ").strip()
            interval = int(interval) if interval.isdigit() else 20
            
            period_seconds = input("Analiz periyodu (saniye, varsayılan 20): ").strip()
            period_seconds = int(period_seconds) if period_seconds.isdigit() else 20
            
            analyzer.continuous_period_monitoring(interval, period_seconds)
            
        elif choice == "5":
            filename = input("Dosya adı (varsayılan: lesson_focus_analysis_results.csv): ").strip()
            filename = filename if filename else "lesson_focus_analysis_results.csv"
            
            analyzer.save_results_to_csv(filename)
            
        elif choice == "6":
            analyzer.test_focus_analysis_with_examples()
            
        elif choice == "7":
            print("👋 Ders odak analiz sistemi kapatılıyor...")
            break
            
        else:
            print("❌ Geçersiz seçim! Lütfen 1-7 arası bir sayı girin.")

if __name__ == "__main__":
    main()
