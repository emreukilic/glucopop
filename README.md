<p align="center"><img src="assets/glucopop.png" width="96" alt="GlucoPop"></p>
<h1 align="center">GlucoPop</h1>
<p align="center"><b>Şekerin, her zaman gözünün önünde.</b> · <i>Your glucose, always on top.</i></p>
<p align="center"><b>Emre Kılıç</b> tarafından yapıldı · bir <b>TypeHealthy</b> projesi</p>
<p align="center">Ücretsiz, açık kaynak Windows widget'ı: CGM (sürekli glikoz sensörü) değerini masaüstünde her zaman üstte duran küçük bir pencerede gösterir, aralık dışına çıkınca renk değiştirir ve bildirim verir.</p>

---

## Türkçe

### Desteklenen sensörler

| Sensör | Nasıl bağlanır | Gereken |
|---|---|---|
| **Dexcom** G6 · G7 · ONE · ONE+ | Dexcom Share | Dexcom uygulamasında *Paylaşım* açık + en az 1 takipçi davet edilmiş; sensörü takan kişinin Dexcom hesabı |
| **FreeStyle Libre** 2 · 2 Plus · 3 · 3 Plus | LibreLinkUp | Libre uygulamasından kendini davet et (Paylaş → Bağlı uygulamalar → LibreLinkUp), o e-postayla LibreLinkUp hesabı aç |
| **Medtrum** TouchCare A6 · A7 · Nano | EasyView | Kendi EasyView hesabın **veya** EasyFollow takipçi hesabı |
| **Diğer her şey** (Guardian/GL4, LinX/AiDEX, Sibionics GS1, CareSens Air…) | Nightscout | xDrip+ / Juggluco / AAPS / Loop ile bir Nightscout sitesine yükle **veya** xDrip+ yerel web servisi (`http://telefon-ip:17580`) |

> Medtronic CareLink doğrudan girişi (tarayıcı + captcha gerektiriyor) ve Sibionics bulut girişi yol haritasında.

### Kurulum (kullanıcı)

1. [Releases](../../releases) sayfasından **GlucoPop.exe** indir. Kurulum yok, tek dosya.
2. Çalıştır. Windows SmartScreen uyarısı çıkarsa *Ek bilgi → Yine de çalıştır* (uygulama imzasız; kod açık, isteyen kendi derleyebilir).
3. Sihirbaz: **Dil → Sensör → Giriş (Bağlantıyı test et) → Widget ayarları → Bitir.**
4. Widget sağ üstte belirir; sürükle, sağ tıkla. Sistem tepsisindeki damla ikonundan ayarlar / gizle / çıkış.

Ayarlar `%APPDATA%\GlucoPop\config.json` içinde; şifreler Windows Kimlik Bilgisi Yöneticisi'nde saklanır.

### Kaynaktan çalıştırma / geliştirme

```bat
git clone https://github.com/<kullanici>/glucopop.git
cd glucopop
dev.bat            REM sanal ortam kurar, uygulamayı kaynaktan başlatır
dev.bat check      REM kayıtlı ayarlarla terminalde bağlantı testi
build\build.bat    REM dist\GlucoPop.exe üretir (PyInstaller)
```

GitHub'a `v*` etiketi atıldığında Actions otomatik olarak exe'yi derler ve Release'e ekler.

### Önemli

* **Tıbbi cihaz değildir.** Değerler resmi uygulamadan gecikmeli gelebilir; tedavi kararından önce mutlaka resmi uygulamayı/cihazı kontrol et.
* Kullanılan servislerin resmi bir API'si yoktur; uygulamaların kendi uç noktaları kullanılır (Nightscout / Home Assistant topluluğuyla aynı yöntem). Üretici tarafında değişiklik olursa bir kaynak geçici olarak çalışmayabilir; sorunları *Issues*'a yaz.

---

## English

**GlucoPop** is a free, open-source Windows widget that shows your CGM glucose in a small always-on-top window, colours it by range and sends Windows notifications on lows/highs.

**Sources:** Dexcom Share (G6/G7/ONE), LibreLinkUp (Libre 2/3), Medtrum EasyView (patient or EasyFollow account), and Nightscout / xDrip+ web service as a universal bridge for everything else (Guardian, LinX/AiDEX, Sibionics, CareSens…).

**Install:** download `GlucoPop.exe` from Releases, run it, follow the wizard (language → sensor → sign-in with *Test connection* → widget settings). Settings live in `%APPDATA%\GlucoPop`, passwords in Windows Credential Manager.

**Develop:** `dev.bat` runs from source, `dev.bat check` tests the saved connection in a terminal, `build\build.bat` produces `dist\GlucoPop.exe`. Tagging `v*` builds and publishes the exe via GitHub Actions.

**Not a medical device.** Always confirm with your official app or meter before treating.

### Credits
Endpoint knowledge comes from the community: [pydexcom](https://github.com/gagebenne/pydexcom), [libre-link-unofficial-api](https://github.com/DRFR0ST/libre-link-unofficial-api), [sapk/medtrum-easyview](https://github.com/sapk/medtrum-easyview), [nl-ruud/nightscout-easyview](https://github.com/nl-ruud/nightscout-easyview), [Nightscout](https://nightscout.github.io/).

Made by **Emre Kılıç** · a **TypeHealthy** project · License: MIT
