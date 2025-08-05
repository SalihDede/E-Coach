from typing import List, Optional
import torch
from torch.nn import DataParallel
torch.backends.cudnn.benchmark = True

from models.eyenet import EyeNet
import os
import numpy as np
import cv2
import dlib
import imutils
import util.gaze
from imutils import face_utils
import threading
import time
import socket
from flask import Flask, jsonify

from util.eye_prediction import EyePrediction
from util.eye_sample import EyeSample

# Flask-CORS import'u - eğer yüklü değilse manuel başlık ekleyeceğiz
try:
    from flask_cors import CORS
    FLASK_CORS_AVAILABLE = True
except ImportError:
    FLASK_CORS_AVAILABLE = False

torch.backends.cudnn.enabled = True

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
print(device)

webcam = cv2.VideoCapture(0)
webcam.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
webcam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
webcam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
webcam.set(cv2.CAP_PROP_FPS, 60)

dirname = os.path.dirname(__file__)
face_cascade = cv2.CascadeClassifier(os.path.join(dirname, 'lbpcascade_frontalface_improved.xml'))
landmarks_detector = dlib.shape_predictor(os.path.join(dirname, 'shape_predictor_5_face_landmarks.dat'))

checkpoint = torch.load('checkpoint.pt', map_location=device, weights_only=False)
nstack = checkpoint['nstack']
nfeatures = checkpoint['nfeatures']
nlandmarks = checkpoint['nlandmarks']
eyenet = EyeNet(nstack=nstack, nfeatures=nfeatures, nlandmarks=nlandmarks).to(device)
eyenet.load_state_dict(checkpoint['model_state_dict'])

# HTTP endpoint URL
ATTENTION_ENDPOINT = "http://127.0.0.1:8000/attention"

# Global değerler - anlık güncel veri için
current_attention_value = 0.0
current_head_looking = False
current_left_eye_open = False
current_right_eye_open = False

# Zaman aralığı bazlı dikkat verileri için global değişkenler
all_attention_values = []  # Başlangıçtan itibaren tüm dikkat değerleri
all_timestamps = []        # Her dikkat değerinin zaman damgası
session_start_time = None  # Oturum başlangıç zamanı

def get_local_ip():
    """Yerel IP adresini otomatik olarak tespit eder"""
    try:
        # Geçici bir socket bağlantısı açarak yerel IP'yi tespit et
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Google DNS'ine bağlan (veri gönderilmez)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        return local_ip
    except Exception:
        # Hata durumunda localhost döndür
        return "127.0.0.1"

def get_current_attention():
    """Anlık güncel dikkat değeri ve durum bilgilerini döndürür"""
    current_time = time.time()
    
    # Farklı zaman aralıklarında ortalama dikkat hesapla
    one_min_avg = calculate_average_attention(60)      # 1 dakika
    five_min_avg = calculate_average_attention(300)    # 5 dakika  
    twenty_min_avg = calculate_average_attention(1200) # 20 dakika
    total_avg = calculate_total_average_attention()    # Toplam ortalama
    
    return {
        "attention": float(current_attention_value),
        "head_looking_at_screen": bool(current_head_looking),
        "left_eye_open": bool(current_left_eye_open),
        "right_eye_open": bool(current_right_eye_open),
        "attention_1min_avg": float(one_min_avg),
        "attention_5min_avg": float(five_min_avg), 
        "attention_20min_avg": float(twenty_min_avg),
        "attention_total_avg": float(total_avg)
    }

def calculate_average_attention(seconds):
    """Belirtilen saniye sayısı içindeki ortalama dikkati hesaplar"""
    if not all_timestamps or not all_attention_values:
        return 0.0
    
    current_time = time.time()
    cutoff_time = current_time - seconds
    
    # Belirtilen zaman aralığındaki değerleri filtrele
    recent_values = []
    for i, timestamp in enumerate(all_timestamps):
        if timestamp >= cutoff_time:
            recent_values.append(all_attention_values[i])
    
    return np.mean(recent_values) if recent_values else 0.0

def calculate_total_average_attention():
    """Oturum başlangıcından itibaren toplam ortalama dikkati hesaplar"""
    return np.mean(all_attention_values) if all_attention_values else 0.0

# Flask server için basit endpoint
app = Flask(__name__)

# CORS kısıtlamasını devre dışı bırak
if FLASK_CORS_AVAILABLE:
    CORS(app)
else:
    # Manuel CORS başlıkları ekle
    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response

@app.route('/attention', methods=['GET'])
def get_attention():
    """Anlık güncel dikkat verisi ve durum bilgilerini döndürür"""
    return jsonify(get_current_attention())

def start_server():
    """HTTP sunucusunu arka planda başlatır"""
    app.run(host='0.0.0.0', port=8001, debug=False, use_reloader=False)

def main():
    global current_attention_value, current_head_looking, current_left_eye_open, current_right_eye_open
    global all_attention_values, all_timestamps, session_start_time
    
    # HTTP sunucusunu arka planda başlat
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Dinamik IP adresini tespit et
    local_ip = get_local_ip()
    
    print("✓ HTTP sunucusu başlatıldı:")
    print(f"  - Yerel erişim: http://127.0.0.1:8001/attention")
    print(f"  - Ağ erişimi: http://{local_ip}:8001/attention")
    print(f"  - Dinamik IP: {local_ip}")
    
    import math
    import matplotlib.pyplot as plt
    import time
    
    # Oturum başlangıç zamanını kaydet
    session_start_time = time.time()
    current_face = None
    landmarks = None
    alpha = 0.95

    left_eye = None
    right_eye = None
    left_eye_img = None
    right_eye_img = None
    # MediaPipe Face Mesh
    import mediapipe as mp
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=True, min_detection_confidence=0.5, min_tracking_confidence=0.5)
    # EAR için göz landmark indeksleri
    LEFT_EYE_IDX = [33, 160, 158, 133, 153, 144, 163, 7, 246, 161, 159, 27, 23, 130, 243, 112, 26, 22, 35, 11, 12, 13, 14, 15, 16, 17]
    RIGHT_EYE_IDX = [263, 387, 385, 362, 380, 373, 390, 249, 466, 388, 386, 259, 255, 339, 463, 342, 260, 257, 288, 285, 295, 296, 334, 293, 300, 301]
    # solvePnP için 3D model noktaları
    model_points = np.array([
        [0.0, 0.0, 0.0],             # Nose tip
        [0.0, -330.0, -65.0],        # Chin
        [-225.0, 170.0, -135.0],     # Left eye left corner
        [225.0, 170.0, -135.0],      # Right eye right corner
        [-150.0, -150.0, -125.0],    # Left Mouth corner
        [150.0, -150.0, -125.0]      # Right mouth corner
    ])

    left_attention_values = []
    right_attention_values = []
    total_attention_values = []
    timestamps = []
    attention_window_sec = 10.0  # Son 10 saniyelik pencere
    start_time = time.time()
    frame_count = 0
    last_time = time.time()
    fps = 0
    latency_ms = 0
    pitch_samples = []
    pitch_offset = 0
    offset_calibrated = False
    offset_calibration_time = 5.0  # saniye
    offset_start_time = time.time()
    gaze_samples_left = []
    gaze_samples_right = []
    gaze_offset_left = np.array([0.0, 0.0])
    gaze_offset_right = np.array([0.0, 0.0])
    gaze_offset_calibrated = False
    prev_left_gaze = None
    prev_right_gaze = None
    # Gaze smoothing: göz vektörlerindeki ani değişimleri azaltır. 0.0: anlık, 1.0: tamamen önceki.
    gaze_smoothing = 0.7
    print(f"Gaze smoothing katsayısı: {gaze_smoothing} (0.0: anlık, 1.0: tamamen önceki)")
    # Hareketlilik için landmark geçmişi
    landmark_history = []
    mobility_values = []
    
    while True:
        start_loop = time.time()
        ret, frame_bgr = webcam.read()
        if not ret or frame_bgr is None:
            print("Webcam'den görüntü alınamıyor! Kamera bağlantısını kontrol edin.")
            break
        orig_frame = frame_bgr.copy()
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # MediaPipe Face Mesh ile yüz landmarkları
        results = face_mesh.process(frame_rgb)
        # Landmark vektörlerini topla (kafa hareketliliği için)
        if results.multi_face_landmarks:
            lm = results.multi_face_landmarks[0]
            h, w, _ = frame_bgr.shape
            # 468 landmark'ın x,y koordinatlarını topla
            lm_vec = np.array([[pt.x * w, pt.y * h] for pt in lm.landmark], dtype=np.float32)
            landmark_history.append(lm_vec)
            # Sadece son 20 frame'i tut
            if len(landmark_history) > 20:
                landmark_history.pop(0)
            # Hareketlilik metriği hesapla
            if len(landmark_history) > 1:
                from util.mediapipe_face import compute_head_mobility
                mobility = compute_head_mobility(landmark_history[-2:])[-1]
                mobility_values.append(mobility)
                # Son 20 frame'i tut
                if len(mobility_values) > 20:
                    mobility_values.pop(0)
            else:
                mobility = 0.0
        else:
            mobility = 0.0
        if not results.multi_face_landmarks:
            left_attention = 0.0
            right_attention = 0.0
            left_status = "Bakmıyor"
            right_status = "Bakmıyor"
            total_attention = 0.0
            left_attention_values.append(left_attention)
            right_attention_values.append(right_attention)
            total_attention_values.append(total_attention)
            timestamps.append(time.time() - start_time)
            cv2.imshow("Gaze Estimation", orig_frame)
            if cv2.waitKey(1) == ord('q'):
                break
            continue

        face_landmarks = results.multi_face_landmarks[0]
        h, w, _ = frame_bgr.shape
        # 2D image points for solvePnP (daha doğru noktalar)
        # Burun ucu, çene, sol/sağ göz dış köşe, sol/sağ ağız köşe
        image_points = np.array([
            [face_landmarks.landmark[1].x * w, face_landmarks.landmark[1].y * h],     # Nose tip
            [face_landmarks.landmark[152].x * w, face_landmarks.landmark[152].y * h], # Chin
            [face_landmarks.landmark[33].x * w, face_landmarks.landmark[33].y * h],   # Left eye left corner
            [face_landmarks.landmark[263].x * w, face_landmarks.landmark[263].y * h], # Right eye right corner
            [face_landmarks.landmark[61].x * w, face_landmarks.landmark[61].y * h],   # Left mouth corner
            [face_landmarks.landmark[291].x * w, face_landmarks.landmark[291].y * h]  # Right mouth corner
        ], dtype="double")

        # solvePnP ile kafa pozisyonu
        focal_length = w
        center = (w/2, h/2)
        camera_matrix = np.array(
            [[focal_length, 0, center[0]],
             [0, focal_length, center[1]],
             [0, 0, 1]], dtype = "double"
        )
        dist_coeffs = np.zeros((4,1))
        success, rotation_vector, translation_vector = cv2.solvePnP(model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE)
        yaw, pitch, roll = 0, 0, 0
        if success:
            rmat, _ = cv2.Rodrigues(rotation_vector)
            sy = math.sqrt(rmat[0,0] * rmat[0,0] + rmat[1,0] * rmat[1,0])
            singular = sy < 1e-6
            if not singular:
                pitch = math.atan2(-rmat[2,0], sy)
                yaw = math.atan2(rmat[1,0], rmat[0,0])
                roll = math.atan2(rmat[2,1], rmat[2,2])
            pitch = math.degrees(pitch)
            yaw = math.degrees(yaw)
            roll = math.degrees(roll)
            # Kafa yönünü çiz (burun ucu referans)
            nose_tip = tuple(np.round(image_points[0]).astype(int))
            # Kafa yön vektörü (Z ekseni)
            head_dir = np.array([0, 0, 100.0])  # 100px ileri
            head_dir2d, _ = cv2.projectPoints(head_dir, rotation_vector, translation_vector, camera_matrix, dist_coeffs)
            head_dir2d = head_dir2d[0][0]
            end_point = (int(nose_tip[0] + (head_dir2d[0] - nose_tip[0])), int(nose_tip[1] + (head_dir2d[1] - nose_tip[1])))
            cv2.arrowedLine(orig_frame, nose_tip, end_point, (0, 0, 255), 4, tipLength=0.3)
            # Kafa açısını burun ucunun hemen üstüne ve biraz sağına yaz
            angle_text = f"Yaw: {yaw:.1f}°  Pitch: {pitch:.1f}°  Roll: {roll:.1f}°"
            angle_x = min(nose_tip[0]+60, orig_frame.shape[1]-350)
            angle_y = max(nose_tip[1]-40, 30)
            cv2.putText(orig_frame, angle_text, (angle_x, angle_y), cv2.FONT_HERSHEY_DUPLEX, 1.0, (255,140,0), 2, cv2.LINE_AA)
        # Pitch offset kalibrasyonu (ilk 5 saniye)
        if not offset_calibrated:
            pitch_samples.append(pitch)
            if time.time() - offset_start_time > offset_calibration_time:
                pitch_offset = np.mean(pitch_samples)
                offset_calibrated = True
        # Kafa ekrana bakıyor mu? Mantık güncellendi
        # Doğal kafa pozisyonu (pitch_offset) referans alınır
        # Toleranslar: yaw ±25°, pitch ±40° (yukarı/aşağı bakışta da ekrana bakıyor kabul edilir)
        head_yaw_tol = 25.0  # Yatay tolerans (simetrik)
        head_pitch_tol_up = 40.0  # Yukarı bakış toleransı
        head_pitch_tol_down = 40.0  # Aşağı bakış toleransı
        # Kafa ekrana bakıyor mu?
        head_yaw_ok = abs(yaw) <= head_yaw_tol
        pitch_delta = pitch - pitch_offset
        head_pitch_ok = (-head_pitch_tol_down <= pitch_delta <= head_pitch_tol_up)
        head_ok = head_yaw_ok and head_pitch_ok

        # EAR ile göz açık/kapalı durumu
        def compute_ear(landmarks, idxs):
            eye = np.array([[landmarks.landmark[i].x * w, landmarks.landmark[i].y * h] for i in idxs])
            A = np.linalg.norm(eye[1] - eye[5])
            B = np.linalg.norm(eye[2] - eye[4])
            C = np.linalg.norm(eye[0] - eye[3])
            ear = (A + B) / (2.0 * C)
            return ear
        left_ear = compute_ear(face_landmarks, LEFT_EYE_IDX)
        right_ear = compute_ear(face_landmarks, RIGHT_EYE_IDX)
        left_eye_open = left_ear > 0.18
        right_eye_open = right_ear > 0.18

        # Göz segmentasyonu ve gaze tahmini
        mp_landmarks = np.zeros((5,2), dtype=np.float32)
        mp_landmarks[0] = [face_landmarks.landmark[33].x * w, face_landmarks.landmark[33].y * h]
        mp_landmarks[1] = [face_landmarks.landmark[133].x * w, face_landmarks.landmark[133].y * h]
        mp_landmarks[2] = [face_landmarks.landmark[263].x * w, face_landmarks.landmark[263].y * h]
        mp_landmarks[3] = [face_landmarks.landmark[362].x * w, face_landmarks.landmark[362].y * h]
        mp_landmarks[4] = [face_landmarks.landmark[1].x * w, face_landmarks.landmark[1].y * h]
        eyes = segment_eyes(gray, mp_landmarks)
        eyes_ok = len(eyes) == 2
        left_eye = None
        right_eye = None
        left_eye_img = None
        right_eye_img = None
        left_status = "Kapalı"
        right_status = "Kapalı"
        left_attention = 0.0
        right_attention = 0.0
        max_angle = 30.0  # Gaze toleransı daha dar
        if eyes_ok:
            preds = run_eyenet(eyes)
            if preds:
                left_eye = preds[0]
                right_eye = preds[1]
                left_eye_img = eyes[0].img
                right_eye_img = eyes[1].img
                # Gaze vektörü
                left_gaze = left_eye.gaze.copy()
                right_gaze = right_eye.gaze.copy()
                # Gaze offset kalibrasyonu (ilk 5 saniye)
                if not gaze_offset_calibrated:
                    gaze_samples_left.append(left_gaze)
                    gaze_samples_right.append(right_gaze)
                    if time.time() - offset_start_time > offset_calibration_time:
                        gaze_offset_left = np.mean(gaze_samples_left, axis=0)
                        gaze_offset_right = np.mean(gaze_samples_right, axis=0)
                        gaze_offset_calibrated = True
                # Offset uygula
                if gaze_offset_calibrated:
                    left_gaze -= gaze_offset_left
                    right_gaze -= gaze_offset_right
                # Dikeyde 10 derece aşağı offset uygula (radyan cinsinden)
                vertical_offset_rad = np.deg2rad(10)
                left_gaze[1] += vertical_offset_rad
                right_gaze[1] += vertical_offset_rad
                # Gaze smoothing (hareketli ortalama)
                if prev_left_gaze is not None:
                    left_gaze = gaze_smoothing * prev_left_gaze + (1 - gaze_smoothing) * left_gaze
                if prev_right_gaze is not None:
                    right_gaze = gaze_smoothing * prev_right_gaze + (1 - gaze_smoothing) * right_gaze
                prev_left_gaze = left_gaze.copy()
                prev_right_gaze = right_gaze.copy()
                # Ekran büyüklüğüne göre tolerans açıları (ör: 24" ekran, 60cm mesafe)
                # Ortalama: yatay tolerans ±15°, dikey tolerans ±10°
                horizontal_tol_deg = 15
                vertical_tol_deg = 10
                # Gaze vektörünün açısını hesapla
                left_yaw_deg = np.degrees(left_gaze[0])
                left_pitch_deg = np.degrees(left_gaze[1])
                right_yaw_deg = np.degrees(right_gaze[0])
                right_pitch_deg = np.degrees(right_gaze[1])
                # Tolerans içinde mi?
                left_in_screen = abs(left_yaw_deg) < horizontal_tol_deg and abs(left_pitch_deg) < vertical_tol_deg
                right_in_screen = abs(right_yaw_deg) < horizontal_tol_deg and abs(right_pitch_deg) < vertical_tol_deg
                # Dikkat skoru: tolerans içindeyse tam, değilse mesafeye göre
                left_attention = 1.0 if left_in_screen else max(0.0, 1.0 - (abs(left_yaw_deg)/horizontal_tol_deg + abs(left_pitch_deg)/vertical_tol_deg)/2)
                right_attention = 1.0 if right_in_screen else max(0.0, 1.0 - (abs(right_yaw_deg)/horizontal_tol_deg + abs(right_pitch_deg)/vertical_tol_deg)/2)
                left_status = "Açık" if left_eye_open else "Kapalı"
                right_status = "Açık" if right_eye_open else "Kapalı"
                # Vektör ve landmark çizimi
                if left_eye is not None:
                    for (x, y) in left_eye.landmarks[16:33]:
                        cv2.circle(orig_frame, (int(round(x)), int(round(y))), 1, (255, 0, 0), -1, lineType=cv2.LINE_AA)
                    gaze_draw = left_gaze.copy()
                    gaze_draw[1] = -gaze_draw[1]
                    util.gaze.draw_gaze(orig_frame, left_eye.landmarks[-2], gaze_draw, length=60.0, thickness=2)
                if right_eye is not None:
                    for (x, y) in right_eye.landmarks[16:33]:
                        cv2.circle(orig_frame, (int(round(x)), int(round(y))), 1, (0, 255, 0), -1, lineType=cv2.LINE_AA)
                    gaze_draw = right_gaze.copy()
                    util.gaze.draw_gaze(orig_frame, right_eye.landmarks[-2], gaze_draw, length=60.0, thickness=2)
        # Kümülatif dikkat skoru: head_ok, göz açık/kapalı, gaze vektörü, kafa hareketliliği
        # Hareketlilik düşükse (sabit kafa) odak yüksek, hareketlilik yüksekse dikkat düşük
        mobility_norm = np.clip(mobility / 10.0, 0, 1)  # 0-1 arası normalize
        mobility_score = 1.0 - mobility_norm  # Sabitlik = odak
        attention_weights = [0.2, 0.2, 0.4, 0.2] # head, eye open, gaze, mobility
        head_score = 1.0 if head_ok else 0.0
        eye_score = 0.5 * float(left_eye_open) + 0.5 * float(right_eye_open)
        gaze_score = 0.5 * left_attention + 0.5 * right_attention
        total_attention = (attention_weights[0]*head_score +
                          attention_weights[1]*eye_score +
                          attention_weights[2]*gaze_score +
                          attention_weights[3]*mobility_score)
        now_time = time.time()
        left_attention_values.append(left_attention)
        right_attention_values.append(right_attention)
        total_attention_values.append(total_attention)
        timestamps.append(now_time - start_time)
        # Sadece son attention_window_sec kadar veriyi tut
        while timestamps and now_time - start_time - timestamps[0] > attention_window_sec:
            left_attention_values.pop(0)
            right_attention_values.pop(0)
            total_attention_values.pop(0)
            timestamps.pop(0)

        # Modern UI: kutular, barlar, renkler
        if left_eye_img is not None and right_eye_img is not None:
            eyes_imgs = [left_eye_img, right_eye_img]
            eyes_combined = np.hstack(eyes_imgs)
            eyes_combined = cv2.cvtColor(eyes_combined, cv2.COLOR_GRAY2BGR)

            window_width = max(1200, orig_frame.shape[1], eyes_combined.shape[1])
            window_height = orig_frame.shape[0] + eyes_combined.shape[0] + 100

            # Üst bar: Modern tasarımlı bilgi panelleri
            top_bar = np.ones((80, window_width, 3), dtype=np.uint8) * 245
            cv2.rectangle(top_bar, (0,0), (window_width,79), (220,220,220), 2)

            # FPS ve Gecikme paneli - Sol taraf
            panel_padding = 15
            panel_height = 60
            panel_width = 180
            for i, (metric, value, unit) in enumerate([("FPS", f"{fps:.1f}", ""), ("Gecikme", f"{latency_ms:.0f}", "ms")]):
                panel_x = 20 + i * (panel_width + 20)
                cv2.rectangle(top_bar, (panel_x, 10), (panel_x + panel_width, 70), (235,235,235), -1)
                cv2.rectangle(top_bar, (panel_x, 10), (panel_x + panel_width, 70), (200,200,200), 1)
                # Metrik adı
                cv2.putText(top_bar, metric, (panel_x + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100,100,100), 1, cv2.LINE_AA)
                # Değer
                value_text = f"{value}{unit}"
                value_size = cv2.getTextSize(value_text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[0]
                value_x = panel_x + (panel_width - value_size[0]) // 2
                cv2.putText(top_bar, value_text, (value_x, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40,40,40), 2, cv2.LINE_AA)

            # Dikkat Skoru paneli - Sağ taraf
            att_panel_width = 300
            att_panel_x = window_width - att_panel_width - 20
            # Gradient arka plan
            att_color = (0,200,100) if total_attention > 0.7 else (0,128,255) if total_attention > 0.4 else (0,50,255)
            cv2.rectangle(top_bar, (att_panel_x, 10), (att_panel_x + att_panel_width, 70), (245,245,245), -1)
            cv2.rectangle(top_bar, (att_panel_x, 10), (att_panel_x + att_panel_width, 70), att_color, 2)
            # Başlık
            cv2.putText(top_bar, "Dikkat Skoru", (att_panel_x + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100,100,100), 1, cv2.LINE_AA)
            # Değer
            score_text = f"{total_attention*100:.1f}%"
            score_size = cv2.getTextSize(score_text, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 2)[0]
            score_x = att_panel_x + (att_panel_width - score_size[0]) // 2
            cv2.putText(top_bar, score_text, (score_x, 58), cv2.FONT_HERSHEY_SIMPLEX, 1.2, att_color, 2, cv2.LINE_AA)

            # Modern durum barı: Göz ve kafa durumu
            status_bar = np.ones((70, window_width, 3), dtype=np.uint8) * 245
            cv2.rectangle(status_bar, (0,0), (window_width,69), (220,220,220), 2)
            
            # Durum panelleri için genel ayarlar
            panel_height = 50
            panel_gap = 20
            panel_y = 10
            
            # Sol Göz Paneli
            left_panel_width = 280
            left_panel_x = 20
            left_status_color = (46,204,113) if left_status == "Açık" else (231,76,60)  # Yeşil / Kırmızı
            cv2.rectangle(status_bar, (left_panel_x, panel_y), (left_panel_x + left_panel_width, panel_y + panel_height), (235,235,235), -1)
            cv2.rectangle(status_bar, (left_panel_x, panel_y), (left_panel_x + left_panel_width, panel_y + panel_height), left_status_color, 2)
            cv2.putText(status_bar, "SOL GÖZ", (left_panel_x + 10, panel_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100,100,100), 1, cv2.LINE_AA)
            cv2.putText(status_bar, left_status.upper(), (left_panel_x + 10, panel_y + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, left_status_color, 2, cv2.LINE_AA)
            
            # Sağ Göz Paneli
            right_panel_x = window_width//2 - left_panel_width//2
            right_status_color = (46,204,113) if right_status == "Açık" else (231,76,60)
            cv2.rectangle(status_bar, (right_panel_x, panel_y), (right_panel_x + left_panel_width, panel_y + panel_height), (235,235,235), -1)
            cv2.rectangle(status_bar, (right_panel_x, panel_y), (right_panel_x + left_panel_width, panel_y + panel_height), right_status_color, 2)
            cv2.putText(status_bar, "SAĞ GÖZ", (right_panel_x + 10, panel_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100,100,100), 1, cv2.LINE_AA)
            cv2.putText(status_bar, right_status.upper(), (right_panel_x + 10, panel_y + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, right_status_color, 2, cv2.LINE_AA)
            
            # Kafa Pozisyonu Paneli
            head_panel_x = window_width - left_panel_width - 20
            head_status = "EKRANA BAKIYOR" if head_ok else "BAKMIYOR"
            head_status_color = (46,204,113) if head_ok else (231,76,60)
            cv2.rectangle(status_bar, (head_panel_x, panel_y), (head_panel_x + left_panel_width, panel_y + panel_height), (235,235,235), -1)
            cv2.rectangle(status_bar, (head_panel_x, panel_y), (head_panel_x + left_panel_width, panel_y + panel_height), head_status_color, 2)
            cv2.putText(status_bar, "KAFA YÖNÜ", (head_panel_x + 10, panel_y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100,100,100), 1, cv2.LINE_AA)
            cv2.putText(status_bar, head_status, (head_panel_x + 10, panel_y + 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, head_status_color, 2, cv2.LINE_AA)

            # Gözler barı
            eyes_pad = np.ones((eyes_combined.shape[0], window_width, 3), dtype=np.uint8) * 255
            x_offset = (window_width - eyes_combined.shape[1]) // 2
            eyes_pad[:, x_offset:x_offset+eyes_combined.shape[1]] = eyes_combined

            # Webcam görüntüsünü ortala ve genişlet
            webcam_pad = np.ones((orig_frame.shape[0], window_width, 3), dtype=np.uint8) * 255
            x_offset_webcam = (window_width - orig_frame.shape[1]) // 2
            webcam_pad[:, x_offset_webcam:x_offset_webcam+orig_frame.shape[1]] = orig_frame

            # Son pencereyi birleştir: üst bar, gözler, durum barı, webcam
            final_img = np.vstack([top_bar, eyes_pad, status_bar, webcam_pad])
            cv2.imshow("Gaze Estimation", final_img)
        else:
            # Sadece webcam ve üst bar
            window_width = max(1200, orig_frame.shape[1])
            top_bar = np.ones((60, window_width, 3), dtype=np.uint8) * 245
            cv2.rectangle(top_bar, (0,0), (window_width,59), (220,220,220), 2)
            cv2.putText(top_bar, f"FPS: {fps:.1f}", (30, 40), cv2.FONT_HERSHEY_DUPLEX, 1.0, (40,40,40), 2, cv2.LINE_AA)
            cv2.putText(top_bar, f"Gecikme: {latency_ms:.0f} ms", (220, 40), cv2.FONT_HERSHEY_DUPLEX, 1.0, (40,40,40), 2, cv2.LINE_AA)
            att_color = (0,128,255) if total_attention > 0.5 else (0,0,255)
            cv2.rectangle(top_bar, (window_width-420, 10), (window_width-30, 50), (255,255,255), -1)
            cv2.putText(top_bar, f"Dikkat Skoru: {total_attention*100:.1f} %", (window_width-410, 40), cv2.FONT_HERSHEY_DUPLEX, 1.1, att_color, 2, cv2.LINE_AA)

            webcam_pad = np.ones((orig_frame.shape[0], window_width, 3), dtype=np.uint8) * 255
            x_offset_webcam = (window_width - orig_frame.shape[1]) // 2
            webcam_pad[:, x_offset_webcam:x_offset_webcam+orig_frame.shape[1]] = orig_frame

            final_img = np.vstack([top_bar, webcam_pad])
            cv2.imshow("Gaze Estimation", final_img)

        # FPS ve gecikme hesapla
        frame_count += 1
        now = time.time()
        if now - last_time > 1.0:
            fps = frame_count / (now - last_time)
            frame_count = 0
            last_time = now
        latency_ms = (time.time() - start_loop) * 1000

        # Modern canlı dikkat grafiği
        graph_height = 120
        graph_width = 320
        graph_margin = 15
        graph_img = np.ones((graph_height+2*graph_margin, graph_width+2*graph_margin, 3), dtype=np.uint8) * 245
        
        # Grafik başlığı ve çerçeve
        cv2.rectangle(graph_img, (0,0), (graph_width+2*graph_margin, graph_height+2*graph_margin), (220,220,220), 2)
        cv2.putText(graph_img, "Dikkat Grafiği", (graph_margin, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100,100,100), 2, cv2.LINE_AA)
        
        # Izgara çizgileri
        for i in range(5):
            y = graph_margin + graph_height - (i * graph_height // 4)
            cv2.line(graph_img, (graph_margin, y), (graph_margin+graph_width, y), (230,230,230), 1)
            cv2.putText(graph_img, f"{i*25}%", (5, y+4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150,150,150), 1, cv2.LINE_AA)
            
        # Dikkat grafiği
        att_hist = total_attention_values[-graph_width:] if len(total_attention_values) > graph_width else total_attention_values
        points = []
        for i in range(len(att_hist)):
            x = graph_margin + i
            y = graph_margin + graph_height - int(att_hist[i] * graph_height)
            points.append([x, y])
            
        if len(points) > 1:
            # Grafik altı dolgu
            pts = np.array([*points, [points[-1][0], graph_margin+graph_height], [points[0][0], graph_margin+graph_height]], np.int32)
            cv2.fillPoly(graph_img, [pts], (240,248,255))
            # Grafik çizgisi
            points = np.array(points, np.int32)
            cv2.polylines(graph_img, [points], False, (52,152,219), 2, cv2.LINE_AA)
            
        # İstatistikler
        avg_attention = np.mean(total_attention_values) if total_attention_values else 0
        live_attention = total_attention_values[-1] if total_attention_values else 0
        
        # Modern istatistik kutuları
        stats_y = graph_height + graph_margin - 10
        # Anlık değer
        cv2.putText(graph_img, f"Anlık: {live_attention*100:.1f}%", (graph_margin, stats_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (52,152,219), 2, cv2.LINE_AA)
        # Ortalama
        avg_text = f"{attention_window_sec:.0f}s Ort: {avg_attention*100:.1f}%"
        avg_size = cv2.getTextSize(avg_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
        cv2.putText(graph_img, avg_text, (graph_width+graph_margin-avg_size[0], stats_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (52,152,219), 2, cv2.LINE_AA)

        # Dikkat grafiğini ana pencereye ekle
        if left_eye_img is not None and right_eye_img is not None:
            h, w, _ = final_img.shape
            gh, gw, _ = graph_img.shape
            if h > gh and w > gw:
                final_img[0:gh, w-gw:w] = graph_img
            cv2.imshow("Gaze Estimation", final_img)
        else:
            h, w, _ = orig_frame.shape
            gh, gw, _ = graph_img.shape
            if h > gh and w > gw:
                orig_frame[0:gh, w-gw:w] = graph_img
            cv2.imshow("Gaze Estimation", orig_frame)        # Final görüntüyü göster
        cv2.imshow("Gaze Estimation", final_img if (left_eye_img is not None and right_eye_img is not None) else orig_frame)

        # Global değerleri güncelle
        current_attention_value = total_attention
        current_head_looking = head_ok
        current_left_eye_open = left_eye_open
        current_right_eye_open = right_eye_open
        
        # Zaman aralığı bazlı dikkat verilerini güncelle
        current_time = time.time()
        all_attention_values.append(total_attention)
        all_timestamps.append(current_time)
        
        # Bellek kullanımını optimize et: 24 saatlik veriyi tut (yaklaşık 86400 frame)
        max_history = 86400  # 24 saat * 60 dakika * 60 saniye (yaklaşık)
        if len(all_attention_values) > max_history:
            all_attention_values.pop(0)
            all_timestamps.pop(0)

        key = cv2.waitKey(1)
        # Kişisel kalibrasyon iptal edildi. Artık 'c' tuşu ile gaze offset güncellenmiyor.
        if key == ord('q'):
            break

    # Program sonlandığında dikkat grafiğini ve dikkat yüzdesini göster
    plt.figure(figsize=(12,5))
    plt.plot(timestamps, total_attention_values, label='Toplam Dikkat', color='blue', linewidth=2)
    plt.ylim(-0.1, 1.1)
    plt.xlabel('Süre (saniye)')
    plt.ylabel('Dikkat (0-1)')
    plt.title('Ekrana Bakma Toplam Dikkat Grafiği')
    plt.legend()
    plt.grid(True)
    # Dikkat yüzdesi hesapla ve göster
    attention_percent = 100 * np.mean(total_attention_values) if total_attention_values else 0
    plt.figtext(0.5, 0.01, f"Dikkat Yüzdesi: %{attention_percent:.1f}", ha='center', fontsize=14, color='darkblue')
    plt.show()


def detect_landmarks(face, frame, scale_x=0, scale_y=0):
    (x, y, w, h) = (int(e) for e in face)
    rectangle = dlib.rectangle(x, y, x + w, y + h)
    face_landmarks = landmarks_detector(frame, rectangle)
    return face_utils.shape_to_np(face_landmarks)


def draw_cascade_face(face, frame):
    (x, y, w, h) = (int(e) for e in face)
    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)


def draw_landmarks(landmarks, frame):
    for (x, y) in landmarks:
        cv2.circle(frame, (int(x), int(y)), 2, (0, 255, 0), -1, lineType=cv2.LINE_AA)


def segment_eyes(frame, landmarks, ow=160, oh=96):
    eyes = []

    # Segment eyes
    for corner1, corner2, is_left in [(2, 3, True), (0, 1, False)]:
        x1, y1 = landmarks[corner1, :]
        x2, y2 = landmarks[corner2, :]
        eye_width = 1.5 * np.linalg.norm(landmarks[corner1, :] - landmarks[corner2, :])
        if eye_width == 0.0:
            return eyes

        cx, cy = 0.5 * (x1 + x2), 0.5 * (y1 + y2)

        # center image on middle of eye
        translate_mat = np.asmatrix(np.eye(3))
        translate_mat[:2, 2] = [[-cx], [-cy]]
        inv_translate_mat = np.asmatrix(np.eye(3))
        inv_translate_mat[:2, 2] = -translate_mat[:2, 2]

        # Scale
        scale = ow / eye_width
        scale_mat = np.asmatrix(np.eye(3))
        scale_mat[0, 0] = scale_mat[1, 1] = scale
        inv_scale = 1.0 / scale
        inv_scale_mat = np.asmatrix(np.eye(3))
        inv_scale_mat[0, 0] = inv_scale_mat[1, 1] = inv_scale

        estimated_radius = 0.5 * eye_width * scale

        # center image
        center_mat = np.asmatrix(np.eye(3))
        center_mat[:2, 2] = [[0.5 * ow], [0.5 * oh]]
        inv_center_mat = np.asmatrix(np.eye(3))
        inv_center_mat[:2, 2] = -center_mat[:2, 2]

        # Get rotated and scaled, and segmented image
        transform_mat = center_mat * scale_mat * translate_mat
        inv_transform_mat = (inv_translate_mat * inv_scale_mat * inv_center_mat)

        eye_image = cv2.warpAffine(frame, transform_mat[:2, :], (ow, oh))
        eye_image = cv2.equalizeHist(eye_image)

        if is_left:
            eye_image = np.fliplr(eye_image)
        # Gözler artık tek pencerede gösterilecek
        eyes.append(EyeSample(orig_img=frame.copy(),
                              img=eye_image,
                              transform_inv=inv_transform_mat,
                              is_left=is_left,
                              estimated_radius=estimated_radius))
    return eyes


def smooth_eye_landmarks(eye: EyePrediction, prev_eye: Optional[EyePrediction], smoothing=0.2, gaze_smoothing=0.4):
    if prev_eye is None:
        return eye
    return EyePrediction(
        eye_sample=eye.eye_sample,
        landmarks=smoothing * prev_eye.landmarks + (1 - smoothing) * eye.landmarks,
        gaze=gaze_smoothing * prev_eye.gaze + (1 - gaze_smoothing) * eye.gaze)


def run_eyenet(eyes: List[EyeSample], ow=160, oh=96) -> List[EyePrediction]:
    result = []
    for eye in eyes:
        with torch.no_grad():
            x = torch.tensor([eye.img], dtype=torch.float32).to(device)
            _, landmarks, gaze = eyenet.forward(x)
            landmarks = np.asarray(landmarks.cpu().numpy()[0])
            gaze = np.asarray(gaze.cpu().numpy()[0])
            assert gaze.shape == (2,)
            assert landmarks.shape == (34, 2)

            landmarks = landmarks * np.array([oh/48, ow/80])

            temp = np.zeros((34, 3))
            if eye.is_left:
                temp[:, 0] = ow - landmarks[:, 1]
            else:
                temp[:, 0] = landmarks[:, 1]
            temp[:, 1] = landmarks[:, 0]
            temp[:, 2] = 1.0
            landmarks = temp
            assert landmarks.shape == (34, 3)
            landmarks = np.asarray(np.matmul(landmarks, eye.transform_inv.T))[:, :2]
            assert landmarks.shape == (34, 2)
            result.append(EyePrediction(eye_sample=eye, landmarks=landmarks, gaze=gaze))
    return result


if __name__ == '__main__':
    main()