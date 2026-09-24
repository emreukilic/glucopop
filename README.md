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
| **Medtronic** MiniMed 780G · 770G · Simplera *(deneme)* | CareLink | Kişinin MiniMed Mobile ya da Simplera uygulaması CareLink'e yüklüyor olmalı. Kendi Medtronic hesabınla **veya** davet edildiğin care partner hesabıyla, GlucoPop'un açtığı pencerede Medtronic'in kendi sayfasından giriş yaparsın; şifreni GlucoPop görmez |
| **Diğer her şey** (LinX/AiDEX, Sibionics GS1, CareSens Air…) | Nightscout | xDrip+ / Juggluco / AAPS / Loop ile bir Nightscout sitesine yükle **veya** xDrip+ yerel web servisi (`http://telefon-ip:17580`) |

> Sibionics bulut girişi yol haritasında.

### Kurulum (kullanıcı)

1. [Releases](../../releases) sayfasından **GlucoPop-Setup-x.y.z.exe** indir ve çalıştır (İleri → İleri; "Windows ile başlat" ve masaüstü kısayolu seçenekleri kurulumda sorulur). Kurulum istemeyenler için taşınabilir sürüm de var: **GlucoPop-x.y.z-portable.zip**'i bir klasöre aç, içindeki **GlucoPop.exe**'yi çalıştır.
2. Windows SmartScreen uyarısı çıkarsa *Ek bilgi → Yine de çalıştır* (uygulama imzasız; kod açık, isteyen kendi derleyebilir).
3. Sihirbaz: **Dil → Sensör → Giriş (Bağlantıyı test et) → Widget ayarları → Bitir.**
4. Widget sağ üstte belirir; sürükle, sağ tıkla. Sistem tepsisindeki damla ikonundan ayarlar / gizle / çıkış.

Ayarlar `%APPDATA%\GlucoPop\config.json` içinde; şifreler (Medtronic'te şifre yerine Medtronic'in verdiği oturum anahtarı) Windows Kimlik Bilgisi Yöneticisi'nde saklanır.

### Kaynaktan çalıştırma / geliştirme

```bat
git clone https://github.com/emreukilic/glucopop.git
cd glucopop
dev.bat            REM sanal ortam kurar, uygulamayı kaynaktan başlatır
dev.bat check      REM kayıtlı ayarlarla terminalde bağlantı testi
build\build.bat    REM dist\GlucoPop\ klasörü + dist\GlucoPop-Setup-x.y.z.exe üretir (PyInstaller + Inno Setup 6)
```

GitHub'a `v*` etiketi atıldığında Actions otomatik olarak hem kurulum dosyasını hem taşınabilir zip'i derler ve Release'e ekler.

### Test edenler aranıyor 🙏

Geliştirici Medtrum kullanıyor; **Dexcom**, **Libre**, **Medtronic** ve **Nightscout** kaynakları gerçek API cevap örnekleriyle otomatik testlerden geçti ama henüz gerçek hesapla denenmedi. Bu sensörlerden birini kullanıyorsan: kur, "Bağlantıyı test et" sonucunu (çalıştı / hata metni) [Issues](../../issues) sayfasına yaz. Şifre paylaşma; hata metni yeterli.

Medtronic kaynağı yeni. Medtronic hesabında iki adımlı doğrulama açıksa giriş çalışmayabilir; bu durumda da hata metnini yazman çok işe yarar.

### Önemli

* **Tıbbi cihaz değildir.** Değerler resmi uygulamadan gecikmeli gelebilir; tedavi kararından önce mutlaka resmi uygulamayı/cihazı kontrol et.
* Kullanılan servislerin resmi bir API'si yoktur; uygulamaların kendi uç noktaları kullanılır (Nightscout / Home Assistant topluluğuyla aynı yöntem). Üretici tarafında değişiklik olursa bir kaynak geçici olarak çalışmayabilir; sorunları *Issues*'a yaz.

---

## English

**GlucoPop** is a free, open-source Windows widget that shows your CGM glucose in a small always-on-top window, colours it by range and sends Windows notifications on lows/highs.

**Sources:** Dexcom Share (G6/G7/ONE), LibreLinkUp (Libre 2/3), Medtrum EasyView (patient or EasyFollow account), Medtronic CareLink (MiniMed 780G/770G, Simplera; your own account or a care-partner one, signed in on Medtronic's own page in a GlucoPop window, so GlucoPop never sees the password; beta), and Nightscout / xDrip+ web service as a universal bridge for everything else (LinX/AiDEX, Sibionics, CareSens…).

**Install:** download `GlucoPop-Setup-x.y.z.exe` from Releases (or the portable `GlucoPop-x.y.z-portable.zip`: unzip it and run `GlucoPop.exe`), run it, follow the wizard (language → sensor → sign-in with *Test connection* → widget settings). Settings live in `%APPDATA%\GlucoPop`, passwords (and the Medtronic session) in Windows Credential Manager.

**Develop:** `dev.bat` runs from source, `dev.bat check` tests the saved connection in a terminal, `build\build.bat` produces the `dist\GlucoPop\` folder and the installer. Tagging `v*` builds and publishes both via GitHub Actions.

**Not a medical device.** Always confirm with your official app or meter before treating.

### Credits
Endpoint knowledge comes from the community: [pydexcom](https://github.com/gagebenne/pydexcom), [libre-link-unofficial-api](https://github.com/DRFR0ST/libre-link-unofficial-api), [sapk/medtrum-easyview](https://github.com/sapk/medtrum-easyview), [nl-ruud/nightscout-easyview](https://github.com/nl-ruud/nightscout-easyview), [Nightscout](https://nightscout.github.io/). Medtronic CareLink: the protocol as the open-source community around [xDrip+](https://github.com/NightscoutFoundation/xDrip), the Nightscout bridges and the Home Assistant CareLink integration has documented it; GlucoPop's code for it is its own.

Made by **Emre Kılıç** · a **TypeHealthy** project · License: MIT
