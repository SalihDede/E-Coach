export const speak = (text: string, lang = 'tr-TR') => {
  if ('speechSynthesis' in window) {
    // Önceki konuşmaları iptal et
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang;
    utterance.rate = 1.0; // Okuma hızı
    utterance.pitch = 1.0; // Ses tonu

    window.speechSynthesis.speak(utterance);
  } else {
    console.error('Tarayıcınız konuşma sentezini desteklemiyor.');
  }
};
