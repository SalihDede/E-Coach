import { useState, useEffect, useRef } from 'react';
import { useActiveTools } from './useActiveTools';
import type { ActiveToolResult } from './useActiveTools';
import './App.css';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import Lottie from 'lottie-react';
import robotFaceAnimation from './assets/ROBOT-THINK.json';
import { speak } from './utils/tts';

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

// Klavye/Mouse verileri için arayüz
interface KeyboardMouseData {
  keyboard_activity: boolean;
  mouse_activity: boolean;
  status: number;
  tab_changed: boolean;
  target_tab: string | null;
  selected_targets: string[];
  targets_count: number;
  current_active_target: string | null;
  time_spent: { [key: string]: number };
}

// Pencere listesi için arayüz
interface WindowInfo {
  title: string;
  is_active: boolean;
  is_browser: boolean;
  is_selected: boolean;
}

// API yanıt arayüzleri
interface WindowsResponse {
  windows: WindowInfo[];
  total_count: number;
  selected_count: number;
}

// Sohbet mesajları için arayüz
interface ChatMessage {
  id: string;
  question: string;
  answer: string;
  timestamp: Date;
  isAutoMessage?: boolean; // Otomatik mesajlar için
  alertType?: string; // Alert tipi
}

// Last response API yanıtı için arayüz
interface LastResponseData {
  last_response: string;
  answer?: string;
  alert?: {
    type: string;
    message: string;
  };
}

function App() {
  // Göz takibi verilerini ve API durumunu tutmak için state'ler
  // Aktif tool ve efekt durumu
  const [activeTool, setActiveTool] = useState<ActiveToolResult | null>(null);
  const [showRedEffect, setShowRedEffect] = useState(false);

  // Aktif tool değiştiğinde efekt ve uyarı tetikle
  useActiveTools((toolResult) => {
    setActiveTool(toolResult);
    if (toolResult?.tool === 'DikkatUyarisi') {
      setShowRedEffect(true);
      speak('Dikkat uyarısı aktif!');
      setTimeout(() => setShowRedEffect(false), 2000);
    }
  });
  const [attentionData, setAttentionData] = useState<AttentionData | null>(null);
  const [isAttentionApiActive, setIsAttentionApiActive] = useState(false);
  const [attentionHistory, setAttentionHistory] = useState<number[]>([]);
  const [focusScore, setFocusScore] = useState<number>(0);
  const [soundIntensityHistory, setSoundIntensityHistory] = useState<number[]>([]);
  const [isVoiceApiActive, setIsVoiceApiActive] = useState(false);
  
  // AI Agent için state'ler
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [currentQuestion, setCurrentQuestion] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Ses kontrolü için state'ler
  const [isVoiceRecording, setIsVoiceRecording] = useState<boolean>(false);
  const [isCalibrating, setIsCalibrating] = useState<boolean>(false);
  const [calibrationThreshold, setCalibrationThreshold] = useState<number | null>(null);
  const [calibrationStatus, setCalibrationStatus] = useState<string>('idle'); // idle, running, completed, error
  const [calibrationCountdown, setCalibrationCountdown] = useState<number>(0); // Geri sayım için

  // Klavye/Mouse için state'ler
  const [keyboardMouseData, setKeyboardMouseData] = useState<KeyboardMouseData | null>(null);
  const [isKeyboardMouseApiActive, setIsKeyboardMouseApiActive] = useState(false);

  // Hedef seçimi için state'ler
  const [availableWindows, setAvailableWindows] = useState<WindowInfo[]>([]);
  const [showWindowSelector, setShowWindowSelector] = useState(false);
  const [selectedTargets, setSelectedTargets] = useState<string[]>([]);
  const [isLoadingWindows, setIsLoadingWindows] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  // Yeni mesaj geldiğinde scroll'u en alta kaydır
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages]);

  // Debug için state değişikliklerini takip et
  useEffect(() => {
    console.log("isVoiceApiActive değişti:", isVoiceApiActive);
  }, [isVoiceApiActive]);

  // Ses kontrol durumunu başlangıçta kontrol et
  useEffect(() => {
    checkVoiceStatus();
  }, []);

  // AI Agent'a soru gönderme fonksiyonu
  const sendQuestionToAgent = async (question: string) => {
    if (!question.trim()) return;
    
    setIsLoading(true);
    console.log("AI Agent'a soru gönderiliyor:", question.trim()); // Debug
    
    try {
      const response = await fetch('http://localhost:8005/ask', {
        method: 'POST',
        mode: 'cors',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify({ question: question.trim() }),
      });
      
      console.log("AI Agent API yanıt durumu:", response.status, response.statusText); // Debug
      
      if (!response.ok) {
        throw new Error(`AI Agent API hatası: ${response.status} ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log("AI Agent'tan gelen veri:", data); // Debug
      
      // Yeni mesajı chat geçmişine ekle
      const newMessage: ChatMessage = {
        id: Date.now().toString(),
        question: question.trim(),
        answer: data.answer || 'Cevap alınamadı',
        timestamp: new Date(),
      };
      
      setChatMessages(prev => [...prev, newMessage]);
      setCurrentQuestion(''); // Input'u temizle
      
    } catch (error) {
      console.error("AI Agent'a soru gönderilemedi:", error);
      
      // Hata türüne göre farklı mesajlar
      let errorMessage = 'Üzgünüm, şu anda bir sorun yaşıyorum. Lütfen daha sonra tekrar deneyin.';
      
      if (error instanceof Error) {
        console.error("Hata detayı:", error.message);
        if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
          errorMessage = 'AI Agent servisine bağlanılamıyor. Lütfen http://localhost:8005 servisinin çalıştığından emin olun.';
        } else if (error.message.includes('404')) {
          errorMessage = 'AI Agent endpoint\'i bulunamadı. /ask endpoint\'inin mevcut olduğundan emin olun.';
        } else if (error.message.includes('500')) {
          errorMessage = 'AI Agent servisinde bir hata oluştu. Lütfen sunucu loglarını kontrol edin.';
        }
      }
      
      // Hata durumunda da bir mesaj ekle
      const errorChatMessage: ChatMessage = {
        id: Date.now().toString(),
        question: question.trim(),
        answer: errorMessage,
        timestamp: new Date(),
      };
      setChatMessages(prev => [...prev, errorChatMessage]);
      setCurrentQuestion('');
    } finally {
      setIsLoading(false);
    }
  };

  // Mevcut pencereleri getirme fonksiyonu
  const fetchAvailableWindows = async () => {
    setIsLoadingWindows(true);
    try {
      const response = await fetch('http://localhost:5001/api/windows', {
        method: 'GET',
        mode: 'cors',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      });
      
      if (!response.ok) {
        throw new Error(`Windows API hatası: ${response.status}`);
      }
      
      const data = await response.json();
      setAvailableWindows(data.windows || []);
      setSelectedTargets(data.windows.filter((w: WindowInfo) => w.is_selected).map((w: WindowInfo) => w.title));
      
    } catch (error) {
      console.error("Pencere listesi alınamadı:", error);
      setAvailableWindows([]);
    } finally {
      setIsLoadingWindows(false);
    }
  };

  // Hedef seçme fonksiyonu
  const selectTargets = async (targets: string[]) => {
    try {
      const response = await fetch('http://localhost:5001/api/select-targets', {
        method: 'POST',
        mode: 'cors',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ targets }),
      });
      
      if (!response.ok) {
        throw new Error(`Select targets API hatası: ${response.status}`);
      }
      
      const data = await response.json();
      setSelectedTargets(data.selected_targets || []);
      console.log(`${data.count} hedef seçildi`);
      
    } catch (error) {
      console.error("Hedefler seçilemedi:", error);
    }
  };

  // Hedefleri temizleme fonksiyonu
  const clearTargets = async () => {
    try {
      const response = await fetch('http://localhost:5001/api/clear-targets', {
        method: 'POST',
        mode: 'cors',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      });
      
      if (!response.ok) {
        throw new Error(`Clear targets API hatası: ${response.status}`);
      }
      
      setSelectedTargets([]);
      console.log("Tüm hedefler temizlendi");
      
    } catch (error) {
      console.error("Hedefler temizlenemedi:", error);
    }
  };

  // Hedef seçim modalını açma
  const openWindowSelector = () => {
    setShowWindowSelector(true);
    fetchAvailableWindows();
  };

  // Ses tanımayı başlatma/durdurma fonksiyonu
  const toggleVoiceRecording = async () => {
    try {
      if (isVoiceRecording) {
        // Ses tanımayı durdur
        const response = await fetch('http://127.0.0.1:5002/api/voice_control/stop', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
          const data = await response.json();
          setIsVoiceRecording(false);
          console.log('Ses tanıma durduruldu:', data.message);
        }
      } else {
        // Ses tanımayı başlat
        const response = await fetch('http://127.0.0.1:5002/api/voice_control/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        
        if (response.ok) {
          const data = await response.json();
          setIsVoiceRecording(true);
          console.log('Ses tanıma başlatıldı:', data.message);
        }
      }
    } catch (error) {
      console.error('Ses tanıma kontrolü hatası:', error);
    }
  };

  // Kalibrasyon fonksiyonu
  const startCalibration = async () => {
    try {
      setIsCalibrating(true);
      setCalibrationStatus('countdown');
      
      // 5 saniye geri sayım
      for (let i = 5; i > 0; i--) {
        setCalibrationCountdown(i);
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      
      // Geri sayım bitti, kalibrasyon başla
      setCalibrationCountdown(0);
      setCalibrationStatus('running');
      
      const response = await fetch('http://127.0.0.1:5002/api/voice_control/calibrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      if (response.ok) {
        // Kalibrasyon durumunu kontrol et
        const checkStatus = setInterval(async () => {
          try {
            const statusResponse = await fetch('http://127.0.0.1:5002/api/voice_control/calibrate/status');
            if (statusResponse.ok) {
              const statusData = await statusResponse.json();
              setCalibrationStatus(statusData.calibration_status);
              
              if (statusData.calibration_status === 'completed') {
                clearInterval(checkStatus);
                setIsCalibrating(false);
                
                if (statusData.calibration_result) {
                  setCalibrationThreshold(statusData.calibration_result.new_threshold);
                  console.log('Kalibrasyon tamamlandı:', statusData.calibration_result);
                }
              } else if (statusData.calibration_status === 'error') {
                clearInterval(checkStatus);
                setIsCalibrating(false);
                setCalibrationStatus('error');
              }
            }
          } catch (error) {
            console.error('Kalibrasyon durumu kontrol hatası:', error);
          }
        }, 1000);
        
        // 10 saniye sonra timeout
        setTimeout(() => {
          clearInterval(checkStatus);
          if (isCalibrating) {
            setIsCalibrating(false);
            setCalibrationStatus('error');
          }
        }, 10000);
        
      }
    } catch (error) {
      console.error('Kalibrasyon başlatma hatası:', error);
      setIsCalibrating(false);
      setCalibrationStatus('error');
    }
  };

  // Ses durumunu kontrol etme
  const checkVoiceStatus = async () => {
    try {
      const response = await fetch('http://127.0.0.1:5002/api/voice_control/status');
      if (response.ok) {
        const data = await response.json();
        setIsVoiceRecording(data.is_active);
        if (data.energy_threshold) {
          setCalibrationThreshold(data.energy_threshold);
        }
      }
    } catch (error) {
      console.error('Ses durumu kontrol hatası:', error);
    }
  };

  // Last response endpoint'ini kontrol etme - otomatik mesajlar için
  const checkLastResponse = async () => {
    try {
      const response = await fetch('http://localhost:8005/last_response', {
        method: 'GET',
        mode: 'cors',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      });
      
      if (response.ok) {
        const data: LastResponseData = await response.json();
        
        // Eğer alert varsa ve henüz eklenmemişse ekle
        if (data.alert && data.alert.message) {
          const lastMessage = chatMessages[chatMessages.length - 1];
          
          // Son mesajın aynı olup olmadığını kontrol et
          if (!lastMessage || lastMessage.answer !== data.alert.message) {
            const autoMessage: ChatMessage = {
              id: `auto_${Date.now()}`,
              question: '', // Otomatik mesajlarda soru yok
              answer: data.alert.message,
              timestamp: new Date(),
              isAutoMessage: true,
              alertType: data.alert.type
            };
            
            setChatMessages(prev => [...prev, autoMessage]);
            console.log(`🤖 Otomatik mesaj alındı [${data.alert.type}]:`, data.alert.message);
          }
        }
        
        // Eğer sadece answer varsa ve henüz eklenmemişse ekle
        else if (data.answer) {
          const lastMessage = chatMessages[chatMessages.length - 1];
          
          if (!lastMessage || lastMessage.answer !== data.answer) {
            const autoMessage: ChatMessage = {
              id: `auto_${Date.now()}`,
              question: '',
              answer: data.answer,
              timestamp: new Date(),
              isAutoMessage: true
            };
            
            setChatMessages(prev => [...prev, autoMessage]);
            console.log('🤖 Otomatik cevap alındı:', data.answer);
          }
        }
      }
    } catch (error) {
      // Sessizce geç, log spam'ını önlemek için
      // console.error('Last response kontrol hatası:', error);
    }
  };

  // Endpoint'ten veri çekmek için useEffect
  useEffect(() => {
    const ENDPOINT_ATTENTION = "http://127.0.0.1:8001/attention";
    const ENDPOINT_SCRIPT = "http://localhost:5002/get_texts";
    const ENDPOINT_KEYBOARD_MOUSE = "http://localhost:5001/api/status";

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
        console.log("Ses analizi API'sine istek gönderiliyor...", ENDPOINT_SCRIPT); // Debug
        const response = await fetch(ENDPOINT_SCRIPT, {
          method: 'GET',
          mode: 'cors',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
        });
        console.log("API yanıt durumu:", response.status, response.statusText); // Debug
        
        if (!response.ok) {
          throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
        }
        const data = await response.json();
        console.log("Ses analizi verisi alındı:", data); // Debug

        // Gelen veriyi state'e ata
        setFocusScore(data.focus_score || 0);
        
        // sound_intensity yoksa focus_score'u kullan veya varsayılan değer ata
        const soundValue = data.sound_intensity !== undefined ? data.sound_intensity : data.focus_score || 0;
        setSoundIntensityHistory(prev => {
          const updated = [...prev, soundValue];
          return updated.length > 30 ? updated.slice(updated.length - 30) : updated;
        });
        
        console.log("Ses API'si aktif olarak işaretleniyor..."); // Debug
        setIsVoiceApiActive(true); // API aktif
      } catch (error) {
        console.error("Ses analizi verisi alınamadı:", error);
        if (error instanceof Error) {
          console.error("Hata detayı:", error.message); // Daha detaylı hata
        }
        setIsVoiceApiActive(false); // API aktif değil
      }
    };

    const fetchKeyboardMouseData = async () => {
      try {
        console.log("Klavye/Mouse API'sine istek gönderiliyor...", ENDPOINT_KEYBOARD_MOUSE); // Debug
        const response = await fetch(ENDPOINT_KEYBOARD_MOUSE, {
          method: 'GET',
          mode: 'cors',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
        });
        console.log("Klavye/Mouse API yanıt durumu:", response.status, response.statusText); // Debug
        
        if (!response.ok) {
          throw new Error(`Network response was not ok: ${response.status} ${response.statusText}`);
        }
        const data = await response.json();
        console.log("Klavye/Mouse verisi alındı:", data); // Debug

        // Gelen veriyi state'e ata
        const newKeyboardMouseData = {
          keyboard_activity: data.keyboard_activity || false,
          mouse_activity: data.mouse_activity || false,
          status: data.status || 0,
          tab_changed: data.tab_changed || false,
          target_tab: data.target_tab || null,
          selected_targets: data.selected_targets || [],
          targets_count: data.targets_count || 0,
          current_active_target: data.current_active_target || null,
          time_spent: data.time_spent || {},
        };
        setKeyboardMouseData(newKeyboardMouseData);
        
        console.log("Klavye/Mouse API'si aktif olarak işaretleniyor..."); // Debug
        setIsKeyboardMouseApiActive(true); // API aktif
      } catch (error) {
        console.error("Klavye/Mouse verisi alınamadı:", error);
        if (error instanceof Error) {
          console.error("Hata detayı:", error.message); // Daha detaylı hata
        }
        setIsKeyboardMouseApiActive(false); // API aktif değil
      }
    };

    // Bileşen yüklendiğinde hemen ve ardından her 1 saniyede bir veri çek
    fetchAttentionData();
    fetchVoiceAnalysisData();
    fetchKeyboardMouseData();
    checkLastResponse(); // İlk kez otomatik mesaj kontrolü
    
    const intervalId = setInterval(() => {
      fetchAttentionData();
      fetchVoiceAnalysisData();
      fetchKeyboardMouseData();
      checkLastResponse(); // Her saniye otomatik mesaj kontrolü
    }, 1000);

    // Bileşen kaldırıldığında interval'ı temizle
    return () => clearInterval(intervalId);
  }, [chatMessages]); // chatMessages'ı bağımlılık olarak ekle

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
          canvasCtx.strokeStyle = '#FF8C00'; // Orange color for center line
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

            canvasCtx.strokeStyle = '#FF8C00'; // Change wave color to orange
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
    <div className="app-container" style={showRedEffect ? { animation: 'red-flash 0.2s alternate 10' } : {}}>
      <header className="app-header">
        <h1>Anlık Durum İzleme Sistemi</h1>
        {/* Aktif tool uyarısı */}
        {activeTool?.tool === 'DikkatUyarisi' && (
          <div style={{
            background: 'linear-gradient(90deg, #ff1744, #ff8c00)',
            color: 'white',
            fontWeight: 'bold',
            fontSize: '1.2em',
            padding: '10px 24px',
            borderRadius: '12px',
            margin: '12px auto',
            boxShadow: '0 2px 12px rgba(255,0,0,0.2)',
            textAlign: 'center',
            maxWidth: '500px',
            animation: 'red-flash 0.2s alternate 10'
          }}>
            ⚠️ Dikkatin dağılıyor, odaklanmaya çalış!
          </div>
        )}
        {activeTool?.tool === 'MolaOnerisi' && (
          <div style={{
            background: 'linear-gradient(90deg, #ff9800, #ffe0b2)',
            color: '#6d4c41',
            fontWeight: 'bold',
            fontSize: '1.15em',
            padding: '10px 24px',
            borderRadius: '12px',
            margin: '12px auto',
            boxShadow: '0 2px 12px rgba(255,140,0,0.15)',
            textAlign: 'center',
            maxWidth: '500px'
          }}>
            🧘 Biraz mola vermek sana iyi gelecek, sakinleş kafanı dağıt sonra kaldığımız yerden devam edelim.
          </div>
        )}
        {activeTool?.tool === 'ZihinYorgunluguTahmini' && (
          <div style={{
            background: 'linear-gradient(90deg, #607d8b, #b0bec5)',
            color: '#263238',
            fontWeight: 'bold',
            fontSize: '1.15em',
            padding: '10px 24px',
            borderRadius: '12px',
            margin: '12px auto',
            boxShadow: '0 2px 12px rgba(96,125,139,0.15)',
            textAlign: 'center',
            maxWidth: '500px'
          }}>
            🧠 Bugünlük sanki bu kadar yeter, kafanı buraya veremiyorsun.
          </div>
        )}
        {activeTool?.tool === 'SoruyaGoreAnalizYap' && (
          <div style={{
            background: 'linear-gradient(90deg, #00bcd4, #b2ebf2)',
            color: '#006064',
            fontWeight: 'bold',
            fontSize: '1.15em',
            padding: '10px 24px',
            borderRadius: '12px',
            margin: '12px auto',
            boxShadow: '0 2px 12px rgba(0,188,212,0.15)',
            textAlign: 'center',
            maxWidth: '500px'
          }}>
            🤖 Sorunu cevaplamaya çalışacağım (sesli yanıt veriliyor).
          </div>
        )}
        <style>{`
          @keyframes red-flash {
            0% { background: #fff; }
            100% { background: #ff1744; }
          }
        `}</style>
      </header>
      
      <div className="container" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div style={{ display: 'flex', gap: '15px', width: '100%' }}>
          {/* Dashboard Box - sol taraf */}
          <div className="outer-box" style={{ backgroundColor: 'transparent', padding: '35px', borderRadius: '12px', width: '50%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', border: 'none', minHeight: '530px' }}>
            <div style={{ textAlign: 'center', width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
              <div style={{ 
                width: '100%', 
                flex: 1, 
                backgroundColor: 'transparent', 
                borderRadius: '15px', 
                boxShadow: 'none', 
                border: 'none', 
                display: 'flex', 
                flexDirection: 'column',
                padding: '20px',
                overflow: 'hidden'
              }}>
                <div style={{ 
                  flex: 1, 
                  overflowY: 'auto', 
                  marginBottom: '10px',
                  maxHeight: '350px',
                  paddingRight: '8px',
                  scrollbarWidth: 'thin',
                  scrollbarColor: '#FF8C00 rgba(255, 140, 0, 0.1)'
                }}>
                  <style>{`
                    div::-webkit-scrollbar {
                      width: 8px;
                    }
                    div::-webkit-scrollbar-track {
                      background: rgba(255, 140, 0, 0.1);
                      border-radius: 4px;
                    }
                    div::-webkit-scrollbar-thumb {
                      background: #FF8C00;
                      border-radius: 4px;
                    }
                    div::-webkit-scrollbar-thumb:hover {
                      background: #ff7700;
                    }
                  `}</style>
                  {chatMessages.length === 0 ? (
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'center', 
                      height: '100%',
                      color: '#999',
                      fontSize: '1.1em'
                    }}>
                      AI Agent ile konuşmaya başlayın...
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                      {chatMessages.map((message) => (
                        <div key={message.id} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                          {/* Kullanıcı sorusu - sadece manuel mesajlarda göster */}
                          {!message.isAutoMessage && message.question && (
                            <div style={{ 
                              display: 'flex', 
                              justifyContent: 'flex-end',
                              alignItems: 'flex-end'
                            }}>
                              <div style={{
                                backgroundColor: 'rgba(255, 140, 0, 0.8)',
                                color: 'white',
                                padding: '12px 16px',
                                borderRadius: '18px 18px 5px 18px',
                                maxWidth: '70%',
                                fontSize: '0.95em',
                                lineHeight: '1.4'
                              }}>
                                {message.question}
                              </div>
                            </div>
                          )}
                          
                          {/* AI cevabı */}
                          <div style={{ 
                            display: 'flex', 
                            justifyContent: 'flex-start',
                            alignItems: 'flex-end'
                          }}>
                            <div style={{
                              backgroundColor: message.isAutoMessage 
                                ? (message.alertType === 'attention' ? 'rgba(255, 193, 7, 0.1)' : 'rgba(13, 202, 240, 0.1)')
                                : 'rgba(240, 240, 240, 0.8)',
                              color: message.isAutoMessage 
                                ? (message.alertType === 'attention' ? '#e65100' : '#fafafaff')
                                : '#333',
                              padding: '12px 16px',
                              borderRadius: '18px 18px 18px 5px',
                              maxWidth: '80%',
                              fontSize: '0.95em',
                              lineHeight: '1.4',
                              border: message.isAutoMessage 
                                ? (message.alertType === 'attention' ? '2px solid rgba(255, 193, 7, 0.4)' : '2px solid rgba(13, 202, 240, 0.4)')
                                : '1px solid rgba(224, 224, 224, 0.5)',
                              boxShadow: message.isAutoMessage 
                                ? '0 4px 12px rgba(0, 0, 0, 0.1)' 
                                : 'none',
                              position: 'relative'
                            }}>
                              {/* Otomatik mesaj ikonu */}
                              {message.isAutoMessage && (
                                <span style={{
                                  position: 'absolute',
                                  top: '-8px',
                                  left: '-8px',
                                  backgroundColor: message.alertType === 'attention' ? '#ff9800' : '#03a9f4',
                                  color: 'white',
                                  borderRadius: '50%',
                                  width: '24px',
                                  height: '24px',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  fontSize: '0.8em',
                                  fontWeight: 'bold',
                                  border: '2px solid white',
                                  boxShadow: '0 2px 6px rgba(0, 0, 0, 0.2)'
                                }}>
                                  {message.alertType === 'attention' ? '⚠️' : '🤖'}
                                </span>
                              )}
                              {message.answer}
                            </div>
                          </div>
                          
                          {/* Zaman damgası */}
                          <div style={{ 
                            fontSize: '0.75em', 
                            color: '#999', 
                            textAlign: message.isAutoMessage ? 'left' : 'center',
                            marginTop: '5px',
                            paddingLeft: message.isAutoMessage ? '16px' : '0',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px'
                          }}>
                            {message.isAutoMessage && (
                              <span style={{
                                fontSize: '0.9em',
                                color: message.alertType === 'attention' ? '#ff9800' : '#03a9f4',
                                fontWeight: 'bold'
                              }}>
                                🤖 Otomatik
                              </span>
                            )}
                            <span>
                              {message.timestamp.toLocaleTimeString('tr-TR', { 
                                hour: '2-digit', 
                                minute: '2-digit' 
                              })}
                            </span>
                          </div>
                        </div>
                      ))}
                      <div ref={chatEndRef} /> {/* Scroll odaklanma için */}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* AI Agent Box - sağ taraf */}
          <div className="outer-box" style={{ backgroundColor: 'transparent', padding: '35px', borderRadius: '12px', width: '50%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', border: 'none', minHeight: '530px' }}>
            {/* AI Agent kutusu */}
            <div className="ai-logo" style={{ width: '210px', height: '210px', marginBottom: '45px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '6px solid #6a11cb', borderRadius: '50%' }}>
              <Lottie animationData={robotFaceAnimation} loop={true} style={{ width: '100%', height: '100%' }} />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: '100%' }}>
              {/* Loading Bar */}
              {isLoading && (
                <div style={{ 
                  width: '90%', 
                  height: '4px', 
                  backgroundColor: 'rgba(106, 17, 203, 0.2)', 
                  borderRadius: '2px', 
                  marginBottom: '15px',
                  overflow: 'hidden'
                }}>
                  <div style={{
                    height: '100%',
                    background: 'linear-gradient(90deg, #6a11cb, #2575fc)',
                    borderRadius: '2px',
                    animation: 'loading-bar 1.5s ease-in-out infinite',
                    width: '30%',
                    transform: 'translateX(-100%)'
                  }} />
                  <style>{`
                    @keyframes loading-bar {
                      0% { transform: translateX(-100%); }
                      50% { transform: translateX(200%); }
                      100% { transform: translateX(300%); }
                    }
                  `}</style>
                </div>
              )}
              
              {/* Textarea Container with Button Inside */}
              <div style={{ position: 'relative', width: '90%', marginBottom: '22px' }}>
                <textarea 
                  placeholder="AI Agent'a sorunuzu yazın..." 
                  value={currentQuestion}
                  onChange={(e) => setCurrentQuestion(e.target.value)}
                  disabled={isLoading}
                  style={{ 
                    width: '100%', 
                    height: '125px', 
                    padding: '22px 120px 22px 22px', // Sağ tarafta buton için alan bırak
                    borderRadius: '15px', 
                    border: '2px solid rgba(106, 17, 203, 0.3)', 
                    resize: 'none', 
                    fontSize: '1.15em',
                    opacity: isLoading ? 0.6 : 1,
                    backgroundColor: 'rgba(248, 245, 255, 0.9)',
                    color: '#4a148c',
                    outline: 'none',
                    transition: 'all 0.3s ease',
                    boxShadow: '0 4px 12px rgba(106, 17, 203, 0.1)',
                    boxSizing: 'border-box'
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = '#6a11cb';
                    e.target.style.boxShadow = '0 6px 20px rgba(106, 17, 203, 0.2)';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'rgba(106, 17, 203, 0.3)';
                    e.target.style.boxShadow = '0 4px 12px rgba(106, 17, 203, 0.1)';
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && e.ctrlKey && !isLoading) {
                      sendQuestionToAgent(currentQuestion);
                    }
                  }}
                />
                
                {/* Button Inside Textarea - Bottom Left */}
                <button 
                  onClick={() => sendQuestionToAgent(currentQuestion)} 
                  disabled={isLoading || !currentQuestion.trim()}
                  style={{ 
                    position: 'absolute',
                    bottom: '12px',
                    right: '12px',
                    padding: '8px 16px', 
                    background: isLoading || !currentQuestion.trim() 
                      ? 'linear-gradient(45deg, #ccc, #ddd)' 
                      : 'linear-gradient(45deg, #6a11cb, #2575fc)', 
                    color: 'white', 
                    border: 'none', 
                    borderRadius: '10px', 
                    cursor: isLoading || !currentQuestion.trim() ? 'not-allowed' : 'pointer', 
                    boxShadow: isLoading || !currentQuestion.trim() 
                      ? '0 2px 4px rgba(0, 0, 0, 0.1)' 
                      : '0 4px 12px rgba(106, 17, 203, 0.3)', 
                    transition: 'all 0.3s ease', 
                    fontSize: '0.9em', 
                    fontWeight: 'bold',
                    textShadow: '0 1px 2px rgba(0, 0, 0, 0.1)',
                    minWidth: '80px',
                    height: '36px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 10
                  }}
                  onMouseDown={(e) => {
                    if (!isLoading && currentQuestion.trim()) {
                      e.currentTarget.style.transform = 'scale(0.95)';
                    }
                  }}
                  onMouseUp={(e) => {
                    if (!isLoading && currentQuestion.trim()) {
                      e.currentTarget.style.transform = 'scale(1)';
                    }
                  }}
                  onMouseEnter={(e) => {
                    if (!isLoading && currentQuestion.trim()) {
                      e.currentTarget.style.boxShadow = '0 6px 16px rgba(106, 17, 203, 0.4)';
                      e.currentTarget.style.transform = 'translateY(-1px)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isLoading && currentQuestion.trim()) {
                      e.currentTarget.style.boxShadow = '0 4px 12px rgba(106, 17, 203, 0.3)';
                      e.currentTarget.style.transform = 'translateY(0)';
                    }
                  }}
                >
                  {isLoading ? (
                    <span style={{
                      width: '14px',
                      height: '14px',
                      border: '2px solid rgba(255, 255, 255, 0.3)',
                      borderTop: '2px solid white',
                      borderRadius: '50%',
                      animation: 'spin 1s linear infinite'
                    }} />
                  ) : (
                    '🚀'
                  )}
                  <style>{`
                    @keyframes spin {
                      0% { transform: rotate(0deg); }
                      100% { transform: rotate(360deg); }
                    }
                  `}</style>
                </button>
              </div>
            </div>
          </div>
        </div>
        
        <div className="outer-box" style={{ backgroundColor: 'transparent', padding: '10px', borderRadius: '8px', width: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', alignItems: 'stretch', border: 'none' }}>
          {/* Data box - alta taşındı */}
          <div className="data-box" style={{ width: '100%', margin: '0', flex: 1 }}>
            <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-end', height: '100%' }}>
              {/* Göz Takibi */}
              <div className="status-card eye-tracking" style={{ flex: 1, minHeight: '400px', maxHeight: '400px' }}>
                <div className="card-header">
                  <h3>👁️ Göz Takibi</h3>
                  <span className={`status-indicator ${isAttentionApiActive ? 'active' : 'inactive'}`}></span>
                </div>
                <div className="card-content" style={{ flexDirection: 'column', alignItems: 'stretch', height: '100%', overflow: 'hidden' }}>
                  {/* Attention skorunu grafik olarak göster */}
                  {isAttentionApiActive && attentionData ? (
                    <>
                      <ResponsiveContainer width="100%" height={200}>
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
                            stroke="#FF8C00"
                            strokeWidth={2}
                            dot={{ r: 5, fill: '#FF8C00' }}
                            activeDot={{ r: 8, fill: '#FF8C00', stroke: '#555', strokeWidth: 2 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                      <div className="attention-subtitles" style={{ marginTop: 16, display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', padding: '10px', backgroundColor: '#f0f4f8', borderRadius: '12px', boxShadow: '0 4px 8px rgba(0, 0, 0, 0.1)' }}>
                        <div style={{ textAlign: 'center', padding: '8px', backgroundColor: '#ffffff', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.8em', color: '#555' }}>Ekrana Bakıyor</div>
                          <div style={{ fontSize: '1.1em', fontWeight: 'bold', color: attentionData.screen ? '#4caf50' : '#f44336' }}>
                            {attentionData.screen ? 'Evet' : 'Hayır'}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '8px', backgroundColor: '#ffffff', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.8em', color: '#555' }}>Sol Göz</div>
                          <div style={{ fontSize: '1.1em', fontWeight: 'bold', color: attentionData.eye_left ? '#4caf50' : '#f44336' }}>
                            {attentionData.eye_left ? 'Açık' : 'Kapalı'}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '8px', backgroundColor: '#ffffff', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.8em', color: '#555' }}>Sağ Göz</div>
                          <div style={{ fontSize: '1.1em', fontWeight: 'bold', color: attentionData.eye_right ? '#4caf50' : '#f44336' }}>
                            {attentionData.eye_right ? 'Açık' : 'Kapalı'}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '8px', backgroundColor: '#ffffff', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.8em', color: '#555' }}>1dk Ort</div>
                          <div style={{ fontSize: '1.1em', fontWeight: 'bold', color: '#2196f3' }}>
                            {attentionData.att_1min.toFixed(2)}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '8px', backgroundColor: '#ffffff', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.8em', color: '#555' }}>5dk Ort</div>
                          <div style={{ fontSize: '1.1em', fontWeight: 'bold', color: '#2196f3' }}>
                            {attentionData.att_5min.toFixed(2)}
                          </div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '8px', backgroundColor: '#ffffff', borderRadius: '8px', boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)', border: '1px solid #e0e0e0' }}>
                          <div style={{ fontSize: '0.8em', color: '#555' }}>20dk Ort</div>
                          <div style={{ fontSize: '1.1em', fontWeight: 'bold', color: '#2196f3' }}>
                            {attentionData.att_20min.toFixed(2)}
                          </div>
                        </div>
                      </div>
                    </>
                  ) : (
                    <p>Göz takibi verisi bekleniyor veya servis aktif değil...</p>
                  )}
                </div>
              </div>

              {/* Ses Analizi */}
              <div className="status-card voice-analysis" style={{ flex: 1, minHeight: '400px', maxHeight: '400px' }}>
                <div className="card-header">
                  <h3>🎤 Ses Analizi</h3>
                  <span className={`status-indicator ${isVoiceApiActive ? 'active' : 'inactive'}`} style={{ marginLeft: 'auto' }}></span>
                  
                  {/* Kalibrasyon butonları */}
                  <div style={{ display: 'flex', gap: '8px', marginLeft: '15px' }}>
                    {/* Kalibrasyon butonu */}
                    <button
                      onClick={startCalibration}
                      disabled={isCalibrating}
                      style={{
                        padding: '6px 12px',
                        fontSize: '0.8em',
                        background: isCalibrating 
                          ? 'linear-gradient(45deg, #9ca3af, #6b7280)' 
                          : 'linear-gradient(45deg, #f59e0b, #d97706)',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: isCalibrating ? 'not-allowed' : 'pointer',
                        fontWeight: '600',
                        boxShadow: isCalibrating 
                          ? '0 2px 6px rgba(156, 163, 175, 0.3)' 
                          : '0 2px 6px rgba(245, 158, 11, 0.3)',
                        transition: 'all 0.3s ease',
                        minWidth: '120px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '4px'
                      }}
                      onMouseEnter={(e) => {
                        if (!isCalibrating) {
                          e.currentTarget.style.transform = 'translateY(-1px)';
                          e.currentTarget.style.boxShadow = '0 4px 8px rgba(245, 158, 11, 0.4)';
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!isCalibrating) {
                          e.currentTarget.style.transform = 'translateY(0)';
                          e.currentTarget.style.boxShadow = '0 2px 6px rgba(245, 158, 11, 0.3)';
                        }
                      }}
                    >
                      {calibrationStatus === 'countdown' ? (
                        <>
                          <span style={{
                            width: '16px',
                            height: '16px',
                            border: '2px solid rgba(255, 140, 0, 0.3)',
                            borderTop: '2px solid #FF8C00',
                            borderRadius: '50%',
                            animation: 'spin 1s linear infinite'
                          }} />
                          <span style={{ fontWeight: 'bold', fontSize: '1em' }}>{calibrationCountdown}</span>
                        </>
                      ) : calibrationStatus === 'running' ? (
                        <>
                          <span style={{
                            width: '12px',
                            height: '12px',
                            border: '2px solid rgba(255, 255, 255, 0.3)',
                            borderTop: '2px solid white',
                            borderRadius: '50%',
                            animation: 'spin 1s linear infinite'
                          }} />
                          Kalibrasyon...
                        </>
                      ) : (
                        <>🎯 Kalibre Et</>
                      )}
                    </button>
                    
                    {/* Ses tanıma başlat/durdur butonu */}
                    <button
                      onClick={toggleVoiceRecording}
                      style={{
                        padding: '6px 12px',
                        fontSize: '0.8em',
                        background: isVoiceRecording 
                          ? 'linear-gradient(45deg, #ef4444, #dc2626)' 
                          : 'linear-gradient(45deg, #10b981, #059669)',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontWeight: '600',
                        boxShadow: isVoiceRecording 
                          ? '0 2px 6px rgba(239, 68, 68, 0.3)' 
                          : '0 2px 6px rgba(16, 185, 129, 0.3)',
                        transition: 'all 0.3s ease',
                        minWidth: '90px'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = 'translateY(-1px)';
                        e.currentTarget.style.boxShadow = isVoiceRecording 
                          ? '0 4px 8px rgba(239, 68, 68, 0.4)' 
                          : '0 4px 8px rgba(16, 185, 129, 0.4)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = 'translateY(0)';
                        e.currentTarget.style.boxShadow = isVoiceRecording 
                          ? '0 2px 6px rgba(239, 68, 68, 0.3)' 
                          : '0 2px 6px rgba(16, 185, 129, 0.3)';
                      }}
                    >
                      {isVoiceRecording ? '⏹️ Durdur' : '🎤 Başlat'}
                    </button>
                  </div>
                </div>
                <div className="card-content" style={{ flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'center', position: 'relative' }}>
                  {/* Skor göstergesi - sağ üst */}
                  <div style={{
                    position: 'absolute',
                    top: '10px',
                    right: '10px',
                    fontSize: '1.2em',
                    fontWeight: 'bold',
                    color: '#FF8C00',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-end',
                    gap: '2px',
                    zIndex: 15
                  }}>
                    <div>Skor: {focusScore.toFixed(2)}</div>
                    {calibrationThreshold && (
                      <div style={{ fontSize: '0.8em', color: '#0369a1' }}>
                        Eşik: {calibrationThreshold}
                      </div>
                    )}
                  </div>
                  
                  {/* Kalibrasyon sonucu ve desibel göstergesi */}
                  
                  {/* Kalibrasyon durumu göstergesi */}
                  {calibrationStatus === 'countdown' && calibrationCountdown > 0 && (
                    <div style={{
                      position: 'absolute',
                      top: '50%',
                      left: '50%',
                      transform: 'translate(-50%, -50%)',
                      background: 'linear-gradient(135deg, #ff8c00 0%, #ff6b00 100%)',
                      padding: '20px 30px',
                      borderRadius: '15px',
                      border: '3px solid #ff6b00',
                      fontSize: '1.20rm',
                      fontWeight: '700',
                      color: 'white',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: '8px',
                      zIndex: 20,
                      boxShadow: '0 8px 24px rgba(255, 140, 0, 0.4)',
                      textAlign: 'center',
                      minWidth: '200px'
                    }}>
                      <div style={{ 
                        fontSize: '2em', 
                        fontWeight: '900',
                        textShadow: '2px 2px 4px rgba(0,0,0,0.3)'
                      }}>
                        {calibrationCountdown}
                      </div>
                      <div style={{ 
                        fontSize: '0.9em',
                        textShadow: '1px 1px 2px rgba(0,0,0,0.3)'
                      }}>
                        Hazırlanın...
                      </div>
                      <div style={{ 
                        fontSize: '0.8em',
                        opacity: 0.9,
                        textShadow: '1px 1px 2px rgba(0,0,0,0.3)'
                      }}>
                        🎤 Normal sesle konuşmaya hazırlanın
                      </div>
                      
                      {/* Turuncu loading bar */}
                      <div style={{
                        width: '150px',
                        height: '6px',
                        backgroundColor: 'rgba(255, 255, 255, 0.3)',
                        borderRadius: '3px',
                        overflow: 'hidden',
                        marginTop: '8px'
                      }}>
                        <div style={{
                          width: `${((6 - calibrationCountdown) / 5) * 100}%`,
                          height: '100%',
                          background: 'linear-gradient(90deg, #fff, #ffe0b3)',
                          borderRadius: '3px',
                          transition: 'width 1s ease',
                          boxShadow: '0 0 10px rgba(255, 255, 255, 0.5)'
                        }} />
                      </div>
                    </div>
                  )}
                  
                  {calibrationStatus === 'running' && (
                    <div style={{
                      position: 'absolute',
                      top: '50%',
                      left: '50%',
                      transform: 'translate(-50%, -50%)',
                      background: 'linear-gradient(135deg, #ff8c00 0%, #ff6b00 100%)',
                      padding: '15px 25px',
                      borderRadius: '12px',
                      border: '2px solid #ff6b00',
                      fontSize: '1em',
                      fontWeight: '600',
                      color: 'white',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      zIndex: 20,
                      animation: 'pulse 2s infinite',
                      boxShadow: '0 6px 18px rgba(255, 140, 0, 0.4)'
                    }}>
                      <span style={{
                        width: '16px',
                        height: '16px',
                        border: '2px solid rgba(255, 255, 255, 0.3)',
                        borderTop: '2px solid white',
                        borderRadius: '50%',
                        animation: 'spin 1s linear infinite'
                      }} />
                      <span>🎤 Normal sesle konuşun...</span>
                    </div>
                  )}
                  
                  {calibrationStatus === 'running' && (
                    <div style={{
                      position: 'absolute',
                      top: '120px',
                      right: '20px',
                      background: 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)',
                      padding: '6px 10px',
                      borderRadius: '6px',
                      border: '1px solid #f59e0b',
                      fontSize: '0.75em',
                      fontWeight: '600',
                      color: '#92400e',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      zIndex: 10,
                      animation: 'pulse 2s infinite'
                    }}>
                      <span>⚡</span>
                      <span>Kalibrasyon Yapılıyor...</span>
                    </div>
                  )}
                  
                  {calibrationStatus === 'completed' && (
                    <div style={{
                      position: 'absolute',
                      top: '120px',
                      right: '20px',
                      background: 'linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%)',
                      padding: '6px 10px',
                      borderRadius: '6px',
                      border: '1px solid #10b981',
                      fontSize: '0.75em',
                      fontWeight: '600',
                      color: '#059669',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      zIndex: 10
                    }}>
                      <span>✅</span>
                      <span>Kalibrasyon Tamamlandı</span>
                    </div>
                  )}
                  
                  <canvas ref={canvasRef} style={{ width: '100%', height: '200px', borderRadius: '8px' }}></canvas>
                </div>
              </div>

              {/* Klavye/Mouse Takibi */}
              <div className="status-card keyboard-mouse" style={{ flex: 1, minHeight: '400px', maxHeight: '400px' }}>
                <div className="card-header">
                  <h3>⌨️ Klavye/Mouse İzleme</h3>
                  <span className={`status-indicator ${isKeyboardMouseApiActive ? 'active' : 'inactive'}`}></span>
                  {isKeyboardMouseApiActive && (
                    <button
                      onClick={openWindowSelector}
                      style={{
                        padding: '6px 12px',
                        fontSize: '0.8em',
                        background: 'linear-gradient(45deg, #3b82f6, #1d4ed8)',
                        color: 'white',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontWeight: '600',
                        boxShadow: '0 2px 6px rgba(59, 130, 246, 0.3)',
                        transition: 'all 0.3s ease',
                        marginLeft: '10px'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.transform = 'translateY(-1px)';
                        e.currentTarget.style.boxShadow = '0 4px 8px rgba(59, 130, 246, 0.4)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.transform = 'translateY(0)';
                        e.currentTarget.style.boxShadow = '0 2px 6px rgba(59, 130, 246, 0.3)';
                      }}
                    >
                      🎯 Hedef Seç
                    </button>
                  )}
                </div>
                <div className="card-content" style={{ flexDirection: 'column', alignItems: 'stretch', height: '100%', overflow: 'hidden' }}>
                  {isKeyboardMouseApiActive && keyboardMouseData ? (
                    <>
                      {Object.keys(keyboardMouseData.time_spent).length > 0 ? (
                        <div style={{ 
                          flex: 1,
                          overflowY: 'auto',
                          paddingRight: '8px'
                        }}>
                          {Object.entries(keyboardMouseData.time_spent)
                            .sort(([,a], [,b]) => b - a)
                            .map(([target, timeSpent]) => {
                              const minutes = Math.floor(timeSpent / 60);
                              const seconds = Math.floor(timeSpent % 60);
                              const hours = Math.floor(minutes / 60);
                              const displayMinutes = minutes % 60;
                              const isActive = target === keyboardMouseData.current_active_target;
                              const totalTime = Object.values(keyboardMouseData.time_spent).reduce((a, b) => a + b, 0);
                              const percentage = Math.round((timeSpent / totalTime) * 100);
                              
                              return (
                                <div key={target} style={{ 
                                  marginBottom: '8px',
                                  padding: '12px',
                                  background: isActive 
                                    ? 'linear-gradient(45deg, #dbeafe, #bfdbfe)' 
                                    : 'linear-gradient(45deg, #ffffff, #f8fafc)',
                                  borderRadius: '8px',
                                  border: isActive 
                                    ? '2px solid #3b82f6' 
                                    : '1px solid #e2e8f0',
                                  boxShadow: isActive 
                                    ? '0 4px 12px rgba(59, 130, 246, 0.2)'
                                    : '0 2px 6px rgba(0,0,0,0.06)',
                                  transition: 'all 0.3s ease'
                                }}>
                                  <div style={{ 
                                    display: 'flex', 
                                    justifyContent: 'space-between', 
                                    alignItems: 'center',
                                    marginBottom: '8px'
                                  }}>
                                    <div style={{ 
                                      flex: 1, 
                                      overflow: 'hidden', 
                                      textOverflow: 'ellipsis', 
                                      whiteSpace: 'nowrap',
                                      fontWeight: isActive ? '700' : '600',
                                      color: isActive ? '#1e40af' : '#374151',
                                      fontSize: '0.9em'
                                    }}>
                                      {isActive && (
                                        <span style={{ 
                                          marginRight: '6px',
                                          animation: 'pulse 2s infinite',
                                          fontSize: '1em'
                                        }}>🔵</span>
                                      )}
                                      {target.length > 30 ? target.substring(0, 30) + '...' : target}
                                    </div>
                                    <div style={{ 
                                      fontSize: '1em', 
                                      fontWeight: '800', 
                                      color: isActive ? '#1e40af' : '#4b5563',
                                      marginLeft: '10px',
                                      minWidth: '70px',
                                      textAlign: 'right',
                                      fontFamily: 'monospace'
                                    }}>
                                      {hours > 0 ? `${hours}:${displayMinutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}` : `${displayMinutes}:${seconds.toString().padStart(2, '0')}`}
                                    </div>
                                  </div>
                                  
                                  {/* Progress Bar */}
                                  <div style={{
                                    width: '100%',
                                    height: '4px',
                                    backgroundColor: '#e5e7eb',
                                    borderRadius: '2px',
                                    overflow: 'hidden',
                                    marginBottom: '6px'
                                  }}>
                                    <div style={{
                                      width: `${percentage}%`,
                                      height: '100%',
                                      background: isActive 
                                        ? 'linear-gradient(90deg, #3b82f6, #1d4ed8)'
                                        : 'linear-gradient(90deg, #6b7280, #4b5563)',
                                      transition: 'width 0.3s ease',
                                      borderRadius: '2px'
                                    }} />
                                  </div>
                                  
                                  <div style={{
                                    fontSize: '0.75em',
                                    color: '#6b7280',
                                    fontWeight: '600',
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center'
                                  }}>
                                    <span>%{percentage} toplam</span>
                                    <span style={{
                                      color: isActive ? '#1e40af' : '#9ca3af',
                                      fontWeight: '500'
                                    }}>
                                      {isActive ? '🔄 Aktif' : '⏸️ Pasif'}
                                    </span>
                                  </div>
                                </div>
                              );
                            })}
                        </div>
                      ) : (
                        <div style={{ 
                          flex: 1,
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: '#6b7280',
                          textAlign: 'center',
                          padding: '20px'
                        }}>
                          <div style={{ fontSize: '2.5em', marginBottom: '12px', opacity: 0.5 }}>📊</div>
                          <p style={{ 
                            margin: '0 0 6px 0', 
                            fontWeight: '600',
                            fontSize: '1em',
                            color: '#374151'
                          }}>
                            Henüz veri yok
                          </p>
                          <p style={{ 
                            margin: 0, 
                            fontSize: '0.85em',
                            opacity: 0.8,
                            color: '#6b7280'
                          }}>
                            Hedef seçtikten sonra süre takibi başlayacak
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    <p>Klavye/Mouse izleme verisi bekleniyor veya servis aktif değil...</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Modern Hedef Seçim Modalı */}
      {showWindowSelector && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          backdropFilter: 'blur(8px)',
          animation: 'fadeIn 0.3s ease-out'
        }}>
          <div style={{
            backgroundColor: 'white',
            borderRadius: '20px',
            padding: '0',
            maxWidth: '700px',
            width: '90%',
            maxHeight: '85vh',
            overflow: 'hidden',
            boxShadow: '0 20px 60px rgba(0, 0, 0, 0.4)',
            animation: 'slideUp 0.3s ease-out',
            border: '1px solid rgba(255, 255, 255, 0.2)'
          }}>
            {/* Modern Header */}
            <div style={{
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              padding: '24px 32px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              borderTopLeftRadius: '20px',
              borderTopRightRadius: '20px'
            }}>
              <div>
                <h3 style={{ 
                  margin: '0 0 4px 0', 
                  color: 'white', 
                  fontSize: '1.5em',
                  fontWeight: '600',
                  textShadow: '0 2px 4px rgba(0,0,0,0.3)'
                }}>
                  🎯 Hedef Sekmeler Seçin
                </h3>
                <p style={{
                  margin: 0,
                  color: 'rgba(255, 255, 255, 0.8)',
                  fontSize: '0.9em'
                }}>
                  İzlemek istediğiniz pencereleri seçin
                </p>
              </div>
              <button
                onClick={() => setShowWindowSelector(false)}
                style={{
                  background: 'rgba(255, 255, 255, 0.2)',
                  border: 'none',
                  fontSize: '20px',
                  cursor: 'pointer',
                  color: 'white',
                  width: '40px',
                  height: '40px',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'all 0.3s ease',
                  backdropFilter: 'blur(10px)'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.3)';
                  e.currentTarget.style.transform = 'scale(1.1)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.2)';
                  e.currentTarget.style.transform = 'scale(1)';
                }}
              >
                ✕
              </button>
            </div>

            {/* Content Area */}
            <div style={{ padding: '24px 32px' }}>
              {isLoadingWindows ? (
                <div style={{ textAlign: 'center', padding: '60px 20px' }}>
                  <div style={{
                    width: '50px',
                    height: '50px',
                    border: '4px solid #f3f3f3',
                    borderTop: '4px solid #667eea',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                    margin: '0 auto 20px'
                  }} />
                  <p style={{ 
                    fontSize: '1.1em', 
                    color: '#4b5563',
                    margin: '0 0 8px 0',
                    fontWeight: '500'
                  }}>
                    Pencereler Taranıyor...
                  </p>
                  <p style={{ 
                    fontSize: '0.9em', 
                    color: '#9ca3af',
                    margin: 0
                  }}>
                    Lütfen bekleyiniz
                  </p>
                </div>
              ) : (
                <>
                  {/* Search & Filter Area */}
                  <div style={{
                    marginBottom: '20px',
                    padding: '16px',
                    background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
                    borderRadius: '12px',
                    border: '1px solid #e2e8f0'
                  }}>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}>
                      <div style={{
                        fontSize: '0.9em',
                        color: '#475569',
                        fontWeight: '500'
                      }}>
                        📊 Toplam {availableWindows.length} pencere bulundu
                      </div>
                      <div style={{
                        display: 'flex',
                        gap: '8px',
                        alignItems: 'center'
                      }}>
                        <span style={{
                          fontSize: '0.8em',
                          color: '#64748b'
                        }}>
                          🌐 Tarayıcı
                        </span>
                        <span style={{
                          fontSize: '0.8em',
                          color: '#64748b'
                        }}>
                          🔴 Aktif
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Windows List */}
                  <div style={{
                    maxHeight: '400px',
                    overflowY: 'auto',
                    border: '1px solid #e5e7eb',
                    borderRadius: '12px',
                    padding: '8px',
                    background: '#fafafa'
                  }}>
                    {availableWindows.length === 0 ? (
                      <div style={{ 
                        textAlign: 'center', 
                        padding: '40px 20px',
                        color: '#6b7280'
                      }}>
                        <div style={{ fontSize: '3em', marginBottom: '12px' }}>🔍</div>
                        <p style={{ margin: '0 0 8px 0', fontWeight: '500' }}>
                          Hiç pencere bulunamadı
                        </p>
                        <p style={{ margin: 0, fontSize: '0.9em' }}>
                          Lütfen bazı uygulamaları açtıktan sonra tekrar deneyin
                        </p>
                      </div>
                    ) : (
                      availableWindows.map((window, index) => (
                        <div key={index} style={{
                          display: 'flex',
                          alignItems: 'center',
                          padding: '16px',
                          marginBottom: '8px',
                          background: window.is_selected || selectedTargets.includes(window.title)
                            ? 'linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%)'
                            : window.is_active 
                            ? 'linear-gradient(135deg, #fef3c7 0%, #fde68a 100%)'
                            : 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
                          borderRadius: '12px',
                          border: window.is_selected || selectedTargets.includes(window.title)
                            ? '2px solid #3b82f6'
                            : window.is_active 
                            ? '2px solid #f59e0b'
                            : '1px solid #e5e7eb',
                          cursor: 'pointer',
                          transition: 'all 0.3s ease',
                          boxShadow: window.is_selected || selectedTargets.includes(window.title)
                            ? '0 4px 12px rgba(59, 130, 246, 0.2)'
                            : window.is_active
                            ? '0 4px 12px rgba(245, 158, 11, 0.2)'
                            : '0 2px 4px rgba(0, 0, 0, 0.05)'
                        }}
                        onClick={() => {
                          const newSelection = window.is_selected || selectedTargets.includes(window.title)
                            ? selectedTargets.filter(t => t !== window.title)
                            : [...selectedTargets, window.title];
                          setSelectedTargets(newSelection);
                        }}
                        onMouseEnter={(e) => {
                          if (!(window.is_selected || selectedTargets.includes(window.title))) {
                            e.currentTarget.style.transform = 'translateY(-2px)';
                            e.currentTarget.style.boxShadow = '0 6px 16px rgba(0, 0, 0, 0.1)';
                          }
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.transform = 'translateY(0)';
                          if (!(window.is_selected || selectedTargets.includes(window.title))) {
                            e.currentTarget.style.boxShadow = window.is_active
                              ? '0 4px 12px rgba(245, 158, 11, 0.2)'
                              : '0 2px 4px rgba(0, 0, 0, 0.05)';
                          }
                        }}
                        >
                          <div style={{
                            width: '20px',
                            height: '20px',
                            borderRadius: '4px',
                            border: '2px solid #3b82f6',
                            backgroundColor: window.is_selected || selectedTargets.includes(window.title) ? '#3b82f6' : 'transparent',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            marginRight: '16px',
                            transition: 'all 0.3s ease'
                          }}>
                            {(window.is_selected || selectedTargets.includes(window.title)) && (
                              <span style={{ color: 'white', fontSize: '12px', fontWeight: 'bold' }}>✓</span>
                            )}
                          </div>
                          
                          <div style={{ flex: 1 }}>
                            <div style={{
                              fontWeight: window.is_active ? '700' : '500',
                              fontSize: '1em',
                              marginBottom: '4px',
                              color: window.is_active ? '#92400e' : '#1f2937',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px'
                            }}>
                              {window.is_browser && <span style={{ fontSize: '1.1em' }}>🌐</span>}
                              {window.is_active && <span style={{ fontSize: '1.1em', animation: 'pulse 2s infinite' }}>🔴</span>}
                              <span style={{
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }}>
                                {window.title}
                              </span>
                            </div>
                            <div style={{ 
                              fontSize: '0.85em', 
                              color: '#6b7280',
                              fontWeight: '400'
                            }}>
                              {window.is_browser ? '🌐 Tarayıcı Penceresi' : '📱 Uygulama'}
                              {window.is_active && ' • ⚡ Şu an aktif'}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>

                  {/* Action Buttons */}
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginTop: '24px',
                    padding: '16px',
                    background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
                    borderRadius: '12px',
                    border: '1px solid #e2e8f0'
                  }}>
                    <div style={{ 
                      fontSize: '0.95em', 
                      color: '#475569',
                      fontWeight: '500'
                    }}>
                      <span style={{ 
                        background: 'linear-gradient(45deg, #3b82f6, #1d4ed8)',
                        color: 'white',
                        padding: '4px 8px',
                        borderRadius: '6px',
                        fontSize: '0.9em',
                        marginRight: '8px'
                      }}>
                        {selectedTargets.length}
                      </span>
                      hedef seçildi
                    </div>
                    <div style={{ display: 'flex', gap: '12px' }}>
                      <button
                        onClick={() => setSelectedTargets([])}
                        style={{
                          padding: '10px 20px',
                          background: 'linear-gradient(45deg, #ef4444, #dc2626)',
                          color: 'white',
                          border: 'none',
                          borderRadius: '8px',
                          cursor: 'pointer',
                          fontWeight: '500',
                          fontSize: '0.9em',
                          boxShadow: '0 4px 12px rgba(239, 68, 68, 0.3)',
                          transition: 'all 0.3s ease'
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.transform = 'translateY(-2px)';
                          e.currentTarget.style.boxShadow = '0 6px 16px rgba(239, 68, 68, 0.4)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.transform = 'translateY(0)';
                          e.currentTarget.style.boxShadow = '0 4px 12px rgba(239, 68, 68, 0.3)';
                        }}
                      >
                        🗑️ Temizle
                      </button>
                      <button
                        onClick={() => {
                          selectTargets(selectedTargets);
                          setShowWindowSelector(false);
                        }}
                        style={{
                          padding: '10px 24px',
                          background: 'linear-gradient(45deg, #10b981, #059669)',
                          color: 'white',
                          border: 'none',
                          borderRadius: '8px',
                          cursor: 'pointer',
                          fontWeight: '600',
                          fontSize: '0.9em',
                          boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
                          transition: 'all 0.3s ease'
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.transform = 'translateY(-2px)';
                          e.currentTarget.style.boxShadow = '0 6px 16px rgba(16, 185, 129, 0.4)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.transform = 'translateY(0)';
                          e.currentTarget.style.boxShadow = '0 4px 12px rgba(16, 185, 129, 0.3)';
                        }}
                      >
                        💾 Kaydet
                      </button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
          
          <style>{`
            @keyframes fadeIn {
              from { opacity: 0; }
              to { opacity: 1; }
            }
            
            @keyframes slideUp {
              from { 
                opacity: 0;
                transform: translateY(30px) scale(0.95);
              }
              to { 
                opacity: 1;
                transform: translateY(0) scale(1);
              }
            }
            
            @keyframes spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
            
            @keyframes pulse {
              0%, 100% { opacity: 1; }
              50% { opacity: 0.5; }
            }
            
            @keyframes pulse {
              0%, 100% { opacity: 1; }
              50% { opacity: 0.5; }
            }
          `}</style>
        </div>
      )}
    </div>
  )
}

export default App
