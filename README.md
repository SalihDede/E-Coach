# Proje Kurulum ve Çalıştırma Adımları

1. Kullanıcı sisteminde aşağıdaki yazılımlar kurulu olmalıdır:
   - Node.js
   - Python
   - VB-Audio

2. Backend altyapısını kurmak için:
   - `RUNBACKEND.bat` dosyasını çalıştırın.
   - Not: Conda ortamı kurulumu birkaç kez tekrarlanabilir. 3-4 kez çalıştırarak backend altyapısının sağlıklı kurulduğundan emin olun.

3. Sistemleri ve endpointleri başlatmak için:
   - `START.bat` dosyasını çalıştırın.

4. Frontend'i başlatmak için:
   - `Frontend\AgentViev\src\App.tsx` dizininde terminal açın.
   - `npm run dev` komutunu çalıştırın.
   - Artık tüm proje kullanıma hazırdır.

5. Gerekli modeli indirin:
   - [Bu linkten](https://drive.google.com/file/d/1znrWahVgTuJ8KonPSqbajfilapdVyw-l/view?usp=drive_link) `bert-base-multilingual-cased` modelini indirin.
   - İndirdiğiniz modeli `Vision_Process/models/bert-base-multilingual-cased` klasörüne yerleştirin.

## Önemli Not

- VB-Audio kurulumundan sonra, Windows + R ile "Çalıştır" menüsünü açın ve `mmsys.cpl` yazıp Enter'a basın.
- Açılan ses ayarları menüsünde, kaynak cihazı olarak "Cable Input"u seçin.
- Özellikler > Kayıt sekmesinden "Dinle" seçeneğini aktif edin ve mevcut kulaklığınızı seçin.
