# GlucoPop — macOS sürümü

Kod ve derleme hattı hazır. Kalan iş bir kere yapılacak: sertifikayı üretmek, beş GitHub secret'ı
girmek ve ödünç aldığın Mac'te yarım saatlik testi yapmak.

## Neden imzalamak zorundayız

macOS Sequoia'dan (15) beri imzasız bir uygulamayı sağ tık → Aç ile açma yöntemi kaldırıldı.
Kullanıcının Sistem Ayarları → Gizlilik ve Güvenlik'e gidip "Yine de Aç"a basması gerekiyor.
Diyabetli birine "önce güvenlik ayarlarını kurcala" demek, uygulamayı hiç yayınlamamakla aynı
kapıya çıkar. Apple Developer hesabın olduğu için bu sorunu tamamen çözebiliyoruz: Developer ID
ile imzalanıp notarize edilmiş bir uygulama çift tıklayınca açılır.

Notarization Apple'ın uygulamayı tarayıp "içinde zararlı bir şey yok" diye onaylaması; ücretsiz,
otomatik, genelde birkaç dakika sürüyor. App Store incelemesiyle ilgisi yok.

---

## Mac başına oturduğunda: sertifika (15 dakika)

Bunu sadece bir kez yapacaksın; sertifika 5 yıl geçerli.

**1. Sertifika isteği üret.** Anahtar Zinciri Erişimi'ni aç → menüden Anahtar Zinciri Erişimi →
Sertifika Yardımcısı → Bir Sertifika Yetkilisinden Sertifika İste. E-postanı ve adını yaz,
"Diske kaydedildi" ve "Anahtar çiftini kendim belirteyim" seçeneklerini işaretle. Anahtar boyutu
2048 bit, algoritma RSA. `CertificateSigningRequest.certSigningRequest` dosyası masaüstüne düşer.

**2. Sertifikayı al.** developer.apple.com → Certificates, Identifiers & Profiles → Certificates →
`+` → **Developer ID Application** seç (Mac App Distribution değil; o App Store içindir). Az önceki
CSR dosyasını yükle, üretilen `.cer` dosyasını indir ve çift tıkla — Anahtar Zinciri'ne girer.

**3. `.p12` olarak dışa aktar.** Anahtar Zinciri Erişimi → Sertifikalarım → "Developer ID
Application: Emre Kılıç (X34U2J2H28)" satırını bul, sağ tık → Dışa Aktar. Biçim: Personal
Information Exchange (.p12). Bir parola belirle; bu parola secret olarak girilecek, sağlam olsun.

**4. base64'e çevir.** Terminal'de:

    base64 -i GlucoPop.p12 | pbcopy

Panoya kopyalanır.

**5. Uygulamaya özel parola.** appleid.apple.com → Oturum Açma ve Güvenlik → Uygulamaya Özel
Parolalar → `+` → "GlucoPop notarization". Çıkan `xxxx-xxxx-xxxx-xxxx` parolasını kaydet; bir daha
gösterilmez.

---

## GitHub secret'ları

github.com/emreukilic/glucopop → Settings → Secrets and variables → Actions → New repository secret.
Beşi de girilmeden imzalama adımı atlanır ve derleme imzasız devam eder (hata vermez).

| Secret | Değer |
|---|---|
| `MACOS_CERT_P12` | 4. adımdaki base64 metni |
| `MACOS_CERT_PASSWORD` | `.p12` dışa aktarırken belirlediğin parola |
| `APPLE_ID` | Apple Developer hesabının e-postası |
| `APPLE_APP_PASSWORD` | 5. adımdaki uygulamaya özel parola |
| `APPLE_TEAM_ID` | `X34U2J2H28` |

---

## Test (Mac'teyken, yarım saat)

Derlemeyi tetikle: GitHub → Actions → Build Windows exe → Run workflow. `mac` işi bitince
Artifacts'ten `GlucoPop-macos` indir, DMG'yi aç, uygulamayı Applications'a sürükle ve şunları
sırayla dene:

- [ ] Çift tıklayınca **uyarısız açılıyor** (imzalıysa). Uyarı çıkıyorsa notarization adımına bak.
- [ ] Menü çubuğunda değer görünüyor, rengi doğru (aralıkta yeşil, yüksek turuncu, düşük kırmızı).
- [ ] Kurulum sihirbazı açılıyor; Medtrum hesabınla giriş yapıp "Bağlantıyı test et" değer veriyor.
- [ ] Şifre Anahtar Zinciri'ne yazılıyor: Anahtar Zinciri Erişimi'nde "GlucoPop" araması sonuç veriyor.
- [ ] Widget ekranda duruyor, **her zaman üstte** kalıyor, sürüklenip bırakıldığı yerde kalıyor.
- [ ] Tam ekran bir uygulamanın (Safari) üstünde de görünüyor mu? Görünmüyorsa not al — macOS'ta
      Spaces davranışı ayrı bir ayar gerektirir, düzeltilebilir.
- [ ] Menü çubuğu menüsü açılıyor, Ayarlar ve "Hesaptan çık" çalışıyor.
- [ ] Aralık dışına çıkınca bildirim geliyor (Ayarlar → Bildirimler'de GlucoPop görünüyor).
- [ ] Ayarlar → "Bilgisayarla başlat" açılıp kapanıyor; açıkken
      `~/Library/LaunchAgents/com.typehealthy.glucopop.plist` dosyası oluşuyor.
- [ ] Uygulamayı kapatıp yeniden açınca hesap hatırlanıyor.
- [ ] Ayarlar → Kişiler → Ekle → Medtronic → "Medtronic ile giriş yap": giriş penceresi açılıyor ve
      Medtronic'in sayfası içinde görünüyor (boş/beyaz kalmıyor). Hesabın yoksa sayfanın açılması
      yeter. Bu pencere gömülü bir Chromium (Qt WebEngine); imzalı derlemede ilk kez burada
      denenmiş olacak, açılmazsa Console.app'te "QtWebEngineProcess" araması hata gösterir.

Ekran görüntüsü al: menü çubuğundaki değer ve masaüstündeki widget. Site için lazım olacak.

---

## Yayınlamak

Test tamamsa sürümü yükselt ve etiketle. `glucopop/config.py` ve `pyproject.toml` içindeki sürümü
bir üst sürüme çıkar (0.3.0 Windows'ta Medtronic sürümü olarak çıktı; Mac için sıradaki, örneğin
`0.3.1` ya da `0.4.0`), CHANGELOG'a macOS satırını ekle, commit'le, sonra (örnek 0.4.0 için):

    git tag v0.4.0
    git push origin v0.4.0

Etiket hem Windows hem Mac işini çalıştırır, ikisinin çıktısını aynı release'e koyar.
Site `releases/latest/download/GlucoPop.dmg` adresine bakacak — sabit ad, bir daha
değiştirmen gerekmez.

Yayından sonra sitede iki şey: indirme düğmesinin yanına Mac seçeneği, ve SSS'deki "Mac sürümü
var mı? Henüz yok" cevabının değişmesi. Onları ben hazırlarım, söyle yeter.

---

## Bilinen sınırlar

**Uygulama içi güncelleme Mac'te sessiz değil.** Windows'ta yeni sürüm kendini kurar; macOS'ta
çalışan bir `.app`'in kendi üstüne yazması Gatekeeper'ın açılışta doğruladığı imzayı bozar. Mac
sürümü bunun yerine DMG'yi indirip Finder'da açıyor, kullanıcı yeni sürümü üstüne sürüklüyor.
İki saniyelik bir iş, karşılığında imza anlamını koruyor.

**Dock'ta simge yok.** `LSUIElement` açık: uygulama menü çubuğunda yaşıyor, Dock'ta ve Cmd-Tab'de
görünmüyor — her zaman açık duran durum uygulamalarının standart davranışı. Kurulum sihirbazı yine
de normal bir pencere olarak açılıyor.

**Apple Silicon / Intel.** `macos-latest` runner'ı Apple Silicon; üretilen uygulama arm64. Intel
Mac'lerde çalışmaz. Talep gelirse universal2 derlemesi eklenebilir, ama PySide6'nın universal
tekerleği olmadığı için iki ayrı derleme birleştirmek gerekir — şimdilik gereksiz.
