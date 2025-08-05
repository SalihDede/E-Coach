#!/usr/bin/env python3
"""
Flask Web API - Gaze Estimation Dikkat Verilerini Almak İçin
Port 8000'de /attention endpoint'ini dinler
"""

from flask import Flask, request, jsonify
import datetime
import json
import logging

app = Flask(__name__)

# Logging ayarları
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Gelen verileri saklamak için basit bir liste (gerçek uygulamada veritabanı kullanılır)
attention_data_history = []

@app.route('/')
def home():
    """Ana sayfa"""
    return {
        "status": "success",
        "message": "Gaze Estimation API aktif",
        "endpoints": {
            "POST /attention": "Dikkat verilerini alır",
            "GET /data": "Son 10 veriyi görüntüler",
            "GET /stats": "İstatistikleri görüntüler"
        },
        "data_count": len(attention_data_history),
        "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.route('/attention', methods=['POST'])
def receive_attention_data():
    """Dikkat verilerini alan ana endpoint"""
    try:
        # İstek verisini al
        data = request.get_json()
        
        if not data:
            return jsonify({
                "status": "error",
                "message": "JSON verisi bulunamadı"
            }), 400
        
        # Zaman damgası ekle
        data['received_at'] = datetime.datetime.now().isoformat()
        
        # Veriyi kaydet
        attention_data_history.append(data)
        
        # Son 100 veriyi tut (bellek tasarrufu için)
        if len(attention_data_history) > 100:
            attention_data_history.pop(0)
        
        # Konsola yazdır
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        logger.info(f"[{timestamp}] ✅ Dikkat Verisi Alındı:")
        logger.info(f"  📊 Toplam Dikkat: {data.get('total_attention', 0):.3f}")
        logger.info(f"  👁️  Sol Göz: {data.get('left_attention', 0):.3f} | Sağ Göz: {data.get('right_attention', 0):.3f}")
        logger.info(f"  🎯 Kafa OK: {data.get('head_ok', False)} | Sol Açık: {data.get('left_eye_open', False)} | Sağ Açık: {data.get('right_eye_open', False)}")
        logger.info(f"  ⚡ FPS: {data.get('fps', 0):.1f} | Gecikme: {data.get('latency_ms', 0):.0f}ms")
        
        if 'head_pose' in data:
            pose = data['head_pose']
            logger.info(f"  🧭 Kafa - Yaw: {pose.get('yaw', 0):.1f}° | Pitch: {pose.get('pitch', 0):.1f}° | Roll: {pose.get('roll', 0):.1f}°")
        
        logger.info(f"  🔄 Hareketlilik: {data.get('mobility', 0):.3f} | Ortalama: {data.get('average_attention', 0):.3f}")
        logger.info("-" * 50)
        
        # Başarılı yanıt
        return jsonify({
            "status": "success",
            "message": "Veri başarıyla alındı",
            "data_count": len(attention_data_history),
            "timestamp": data['received_at']
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Veri alma hatası: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Sunucu hatası: {str(e)}"
        }), 500

@app.route('/data', methods=['GET'])
def get_recent_data():
    """Son 10 veriyi döndür"""
    recent_data = attention_data_history[-10:] if attention_data_history else []
    return jsonify({
        "status": "success",
        "total_records": len(attention_data_history),
        "recent_data": recent_data
    })

@app.route('/stats', methods=['GET'])
def get_statistics():
    """İstatistikleri döndür"""
    if not attention_data_history:
        return jsonify({
            "status": "success",
            "message": "Henüz veri yok",
            "stats": {}
        })
    
    # İstatistikleri hesapla
    total_attentions = [d.get('total_attention', 0) for d in attention_data_history]
    left_attentions = [d.get('left_attention', 0) for d in attention_data_history]
    right_attentions = [d.get('right_attention', 0) for d in attention_data_history]
    
    stats = {
        "total_records": len(attention_data_history),
        "average_total_attention": sum(total_attentions) / len(total_attentions),
        "max_total_attention": max(total_attentions),
        "min_total_attention": min(total_attentions),
        "average_left_attention": sum(left_attentions) / len(left_attentions),
        "average_right_attention": sum(right_attentions) / len(right_attentions),
        "first_record_time": attention_data_history[0].get('received_at'),
        "last_record_time": attention_data_history[-1].get('received_at')
    }
    
    return jsonify({
        "status": "success",
        "stats": stats
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "status": "error",
        "message": "Endpoint bulunamadı"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "status": "error",
        "message": "Sunucu hatası"
    }), 500

if __name__ == '__main__':
    print("🚀 Flask API başlatılıyor...")
    print("📡 Endpoint: http://127.0.0.1:8000/attention")
    print("🌐 Ana sayfa: http://127.0.0.1:8000")
    print("📊 Veriler: http://127.0.0.1:8000/data")
    print("📈 İstatistikler: http://127.0.0.1:8000/stats")
    print("🛑 Durdurmak için Ctrl+C basın")
    print("=" * 60)
    
    # Flask uygulamasını başlat
    app.run(
        host='127.0.0.1',
        port=8000,
        debug=True,
        use_reloader=False  # Çoklu process sorunlarını önlemek için
    )
