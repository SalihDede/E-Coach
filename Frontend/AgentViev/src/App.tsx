import { useState, useEffect, useRef } from 'react';
import './App.css';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import Lottie from 'lottie-react';
import robotFaceAnimation from './assets/ROBOT-THINK.json';

// Göz takibi verileri için arayüz (interface)
interface AttentionData {
  attention: number;
  screen: boolean;
  eye_left: boolean;
  eye_right: boolean;
  att_1min: number;
  att_5min: number;
  att_20min: number;
  att_total: number;
}

function App() {
  // Göz takibi verilerini ve API durumunu tutmak için state'ler
  const [attentionData, setAttentionData] = useState<AttentionData | null>(null);
  const [isAttentionApiActive, setIsAttentionApiActive] = useState(false);
  const [attentionHistory, setAttentionHistory] = useState<number[]>([]);
  const [focusScore, setFocusScore] = useState<number>(0);
  const [soundIntensityHistory, setSoundIntensityHistory] = useState<number[]>([]);
  const [isVoiceApiActive, setIsVoiceApiActive] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Endpoint'ten veri çekmek için useEffect
  useEffect(() => {
    const ENDPOINT_ATTENTION = "http://127.0.0.1:8001/attention";
    const ENDPOINT_SCRIPT = "http://localhost:5002/get_texts";

    const fetchAttentionData = async () => {
      try {
        const response = await fetch(ENDPOINT_ATTENTION);
        if (!response.ok) {
          // HTTP 2xx dışında bir yanıt gelirse hata fırlat
          throw new Error(`Network response was not ok: ${response.statusText}`);
        }
        const data = await response.json();
        
        // Gelen veriyi state'e ata
        const newAttentionData = {
          attention: data.attention || 0,
          screen: data.head_looking_at_screen || false,
          eye_left: data.left_eye_open || false,
          eye_right: data.right_eye_open || false,
          att_1min: data.attention_1min_avg || 0,
          att_5min: data.attention_5min_avg || 0,
          att_20min: data.attention_20min_avg || 0,
          att_total: data.attention_total_avg || 0,
        };
        setAttentionData(newAttentionData);
        setAttentionHistory(prev => {
          const updated = [...prev, newAttentionData.attention];
          // Son 30 değeri tut
          return updated.length > 30 ? updated.slice(updated.length - 30) : updated;
        });
        // API aktif
        setIsAttentionApiActive(true);
      } catch (error) {
        console.error("Göz takibi verisi alınamadı:", error);
        // API aktif değil
        setIsAttentionApiActive(false);
      }
    };

    const fetchVoiceAnalysisData = async () => {
      try {
        const response = await fetch(ENDPOINT_SCRIPT);
        if (!response.ok) {
          throw new Error(`Network response was not ok: ${response.statusText}`);
        }
        const data = await response.json();

        // Gelen veriyi state'e ata
        setFocusScore(data.focus_score || 0);
        setSoundIntensityHistory(prev => {
          const updated = [...prev, data.sound_intensity || 0];
          return updated.length > 30 ? updated.slice(updated.length - 30) : updated;
        });
        setIsVoiceApiActive(true); // API aktif
      } catch (error) {
        console.error("Ses analizi verisi alınamadı:", error);
        setIsVoiceApiActive(false); // API aktif değil
      }
    };

    // Bileşen yüklendiğinde hemen ve ardından her 1 saniyede bir veri çek
    fetchAttentionData();
    fetchVoiceAnalysisData();
    const intervalId = setInterval(() => {
      fetchAttentionData();
      fetchVoiceAnalysisData();
    }, 1000);

    // Bileşen kaldırıldığında interval'ı temizle
    return () => clearInterval(intervalId);
  }, []); // Boş bağımlılık dizisi, bu etkinin yalnızca bir kez çalışmasını sağlar

  useEffect(() => {
    const canvas = canvasRef.current;
    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    const canvasCtx = canvas?.getContext('2d');

    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);

      const draw = () => {
        requestAnimationFrame(draw);
        analyser.getByteFrequencyData(dataArray);

        if (canvasCtx && canvas) {
          const width = canvas.width;
          const height = canvas.height;
          const centerY = height / 2;
          const margin = 50; // Empty space on the edges
          const maxAmplitude = height / 4; // Maximum wave height is one-fourth of canvas height

          // Clear canvas with transparency
          canvasCtx.clearRect(0, 0, width, height);

          // Draw central line
          canvasCtx.beginPath();
          canvasCtx.moveTo(margin, centerY);
          canvasCtx.lineTo(width - margin, centerY);
          canvasCtx.strokeStyle = '#6a11cb'; // Purple color matching the 'Gönder' button
          canvasCtx.lineWidth = 2;
          canvasCtx.stroke();
          canvasCtx.closePath();

          if (isVoiceApiActive) {
            // Draw symmetrical wave pattern only if API is active
            const segmentWidth = (width - 2 * margin) / (dataArray.length - 1);
            canvasCtx.beginPath();

            for (let i = 0; i < dataArray.length; i++) {
              const amplitude = (dataArray[i] / 255) * maxAmplitude;
              const x = margin + i * segmentWidth;

              // Draw top wave
              canvasCtx.lineTo(x, centerY - amplitude);

              // Draw bottom wave
              canvasCtx.lineTo(x, centerY + amplitude);
            }

            canvasCtx.strokeStyle = '#6a11cb'; // Change wave color to purple
            canvasCtx.lineWidth = 2;
            canvasCtx.stroke();
            canvasCtx.closePath();
          }
        }
      };

      draw();
    });

    return () => {
      audioContext.close();
    };
  }, [isVoiceApiActive]);

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Anlık Durum İzleme Sistemi</h1>
      </header>
      
      <div className="container" style={{ display: 'flex', gap: '10px' }}>
        <div className="outer-box" style={{ backgroundColor: 'rgba(255, 255, 0, 0)', padding: '10px', borderRadius: '8px', width: '50%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', alignItems: 'stretch' }}>
          {/* Mevcut kutuları saracak şekilde bir box */}
          <div className="data-box" style={{ width: '100%', margin: '0', flex: 1 }}>
            <div className="dashboard-grid">
              {/* Sol üst - Göz Takibi */}
              <div className="status-card eye-tracking">
                <div className="card-header">
                  <h3>👁️ Göz Takibi</h3>
                  <span className={`status-indicator ${isAttentionApiActive ? 'active' : 'inactive'}`}></span>
                </div>
                <div className="card-content" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                  {/* Attention skorunu grafik olarak göster */}
                  {isAttentionApiActive && attentionData ? (
                    <>
                      <ResponsiveContainer width="100%" height={250}>
                        <LineChart
                          data={attentionHistory.map((value, index) => ({ name: `${index + 1}sn`, value }))}
                          margin={{ top: 20, right: 30, left: 20, bottom: 10 }}
                        >
                          <CartesianGrid strokeDasharray="3 3" stroke="#ccc" />
                          <XAxis
                            dataKey="name"
                            label={{ value: 'Zaman (sn)', position: 'insideBottom', offset: -5, style: { fontSize: '0.85em', fill: '#555' } }}
                            tick={{ fontSize: 12, fill: '#555' }}
                          />
                          <YAxis
                            domain={[0, 1]}
                            label={{ value: 'Dikkat Skoru', angle: -90, position: 'insideLeft', style: { fontSize: '0.85em', fill: '#555' } }}
                            tick={{ fontSize: 12, fill: '#555' }}
                          />
                          <Tooltip
                            contentStyle={{ backgroundColor: '#f5f5f5', border: '1px solid #ccc', borderRadius: '5px' }}
                            labelStyle={{ fontWeight: 'bold', color: '#333' }}
                            itemStyle={{ color: '#8884d8' }}
                          />
                          <Line
                            type="monotone"
                            dataKey="value"
                            stroke="#82ca9d"
                            strokeWidth={2}
                            dot={{ r: 5, fill: '#82ca9d' }}
                            activeDot={{ r: 8, fill: '#8884d8', stroke: '#555', strokeWidth: 2 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                      <div className="attention-subtitles" style={{ marginTop: 16, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '12px', padding: '15px', backgroundColor: '#f0f4f8', borderRadius: '12px', boxShadow: '0 4px 8px rgba(0, 0, 0, 0.1)' }}>
                        <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#ffffff', borderRadius: '10px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.9em', color: '#555' }}>Ekrana Bakıyor</div>
                          <div style={{ fontSize: '1.3em', fontWeight: 'bold', color: attentionData.screen ? '#4caf50' : '#f44336' }}>
                            {attentionData.screen ? 'Evet' : 'Hayır'}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#ffffff', borderRadius: '10px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.9em', color: '#555' }}>Sol Göz</div>
                          <div style={{ fontSize: '1.3em', fontWeight: 'bold', color: attentionData.eye_left ? '#4caf50' : '#f44336' }}>
                            {attentionData.eye_left ? 'Açık' : 'Kapalı'}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#ffffff', borderRadius: '10px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.9em', color: '#555' }}>Sağ Göz</div>
                          <div style={{ fontSize: '1.3em', fontWeight: 'bold', color: attentionData.eye_right ? '#4caf50' : '#f44336' }}>
                            {attentionData.eye_right ? 'Açık' : 'Kapalı'}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#ffffff', borderRadius: '10px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.9em', color: '#555' }}>1dk Ort</div>
                          <div style={{ fontSize: '1.3em', fontWeight: 'bold', color: '#2196f3' }}>
                            {attentionData.att_1min.toFixed(2)}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#ffffff', borderRadius: '10px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.9em', color: '#555' }}>5dk Ort</div>
                          <div style={{ fontSize: '1.3em', fontWeight: 'bold', color: '#2196f3' }}>
                            {attentionData.att_5min.toFixed(2)}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#ffffff', borderRadius: '10px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.9em', color: '#555' }}>20dk Ort</div>
                          <div style={{ fontSize: '1.3em', fontWeight: 'bold', color: '#2196f3' }}>
                            {attentionData.att_20min.toFixed(2)}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '12px', backgroundColor: '#ffffff', borderRadius: '10px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.9em', color: '#555' }}>Genel Ort</div>
                          <div style={{ fontSize: '1.3em', fontWeight: 'bold', color: '#2196f3' }}>
                            {attentionData.att_total.toFixed(2)}
                          </div>
                        </div>
                      </div>
                    </>
                  ) : (
                    <p>Göz takibi verisi bekleniyor veya servis aktif değil...</p>
                  )}
                </div>
              </div>

              {/* Sağ üst - Ses Analizi */}
              <div className="status-card voice-analysis">
                <div className="card-header">
                  <h3>🎤 Ses Analizi</h3>
                  <span className={`status-indicator ${isVoiceApiActive ? 'active' : 'inactive'}`} style={{ marginLeft: 'auto' }}></span>
                  <div style={{ fontSize: '1.2em', fontWeight: 'bold', color: '#FF9800', marginLeft: '10px' }}>
                    Skor: {focusScore.toFixed(2)}
                  </div>
                </div>
                <div className="card-content" style={{ flexDirection: 'column', alignItems: 'center' }}>
                  <canvas ref={canvasRef} style={{ width: '100%', height: '200px', borderRadius: '8px' }}></canvas>
                </div>
              </div>

              {/* Sol alt - Klavye/Mouse Takibi */}
              <div className="status-card keyboard-mouse">
                <div className="card-header">
                  <h3>⌨️ Klavye/Mouse</h3>
                  <span className="status-indicator active"></span>
                </div>
                <div className="card-content">
                  <p>Input monitoring aktif</p>
                </div>
              </div>

              {/* Sağ alt - Öğrenci Belleği */}
              <div className="status-card student-memory">
                <div className="card-header">
                  <h3>🧠 Öğrenci Belleği</h3>
                  <span className="status-indicator active"></span>
                </div>
                <div className="card-content">
                  <p>Bellek sistemi çalışıyor</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="outer-box" style={{ backgroundColor: 'rgba(0, 0, 0, 0)', padding: '10px', borderRadius: '8px', width: '50%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          {/* Yeni siyah kutu */}
          <div className="ai-logo" style={{ width: '180px', height: '180px', marginBottom: '50px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '5px solid #6a11cb', borderRadius: '50%' }}>
            <Lottie animationData={robotFaceAnimation} loop={true} style={{ width: '100%', height: '100%' }} />
          </div>

          <textarea placeholder="Prompt yazın..." style={{ width: '90%', height: '100px', padding: '10px', borderRadius: '5px', border: '1px solid #ccc', resize: 'none' }}></textarea>
          <button onClick={() => alert('AI Agent çalışıyor...')} style={{ marginTop: '10px', padding: '10px 20px', backgroundColor: '#6a11cb', color: '#fff', border: 'none', borderRadius: '5px', cursor: 'pointer', boxShadow: '0 4px 8px rgba(0, 0, 0, 0.2)', transition: 'transform 0.2s' }}
            onMouseDown={(e) => e.currentTarget.style.transform = 'scale(0.95)'}
            onMouseUp={(e) => e.currentTarget.style.transform = 'scale(1)'}>
            Gönder
          </button>
        </div>
      </div>
    </div>
  )
}

export default App
