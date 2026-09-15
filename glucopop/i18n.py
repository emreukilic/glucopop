"""Tiny i18n: tr(key) looks up the active language, falls back to English, then the key."""

from __future__ import annotations

_LANG = "tr"

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "app": "GlucoPop",
        "tagline": "Your glucose, always on top.",
        # wizard
        "wz_title": "GlucoPop setup",
        "wz_welcome": "Welcome",
        "wz_welcome_text": "GlucoPop shows your CGM glucose in a small always-on-top window and warns you when it goes out of range.\n\nIt is free and open source. Your credentials are stored only on this computer.",
        "wz_language": "Language",
        "wz_source": "Which sensor do you use?",
        "wz_source_sub": "Pick the service that has your data. Not sure? Hover a card for details.",
        "wz_login": "Sign in",
        "wz_login_sub": "Enter the account that can see the sensor data.",
        "wz_test": "Test connection",
        "wz_testing": "Connecting…",
        "wz_test_ok": "Connected: {value} {unit} {arrow} ({age})",
        "wz_test_fail": "Could not connect: {err}",
        "wz_need_test": "Please test the connection before continuing.",
        "wz_settings": "Widget settings",
        "wz_settings_sub": "You can change these later from the tray icon.",
        "wz_done": "All set!",
        "wz_done_text": "GlucoPop will now sit in your system tray. Drag the widget wherever you like; right-click it for options.",
        "next": "Next", "back": "Back", "finish": "Finish", "cancel": "Cancel",
        # fields
        "f_email": "E-mail", "f_password": "Password",
        "f_dexcom_user": "Dexcom username / e-mail / phone",
        "h_dexcom_user": "The sensor wearer's Dexcom account. Share must be ON in the Dexcom app with at least one follower invited.",
        "f_region": "Region",
        "r_ous": "Outside USA (Türkiye, Europe…)", "r_us": "USA", "r_jp": "Japan",
        "h_libre_user": "Your LibreLinkUp account (not LibreView). In the Libre app: Share → Connected apps → LibreLinkUp → invite your own e-mail, then create the LibreLinkUp account with that e-mail.",
        "f_libre_patient": "Person to follow (optional)",
        "h_libre_patient": "Leave empty to use the first connection.",
        "f_medtrum_type": "Account type",
        "medtrum_patient": "My own EasyView account", "medtrum_follow": "EasyFollow follower account",
        "h_medtrum_type": "Patient = the account you use on easyview.medtrum.eu. Follower = an EasyFollow account that follows someone.",
        "f_server": "Server", "r_medtrum_eu": "Europe (easyview.medtrum.eu)", "r_medtrum_fr": "France", "r_medtrum_global": "Global",
        "f_medtrum_follow_user": "Followed username (optional)",
        "h_medtrum_follow_user": "Only if you follow more than one person.",
        "f_ns_url": "Nightscout URL", "h_ns_url": "e.g. https://myname.ns.10be.de  — or xDrip+ web service http://192.168.1.20:17580",
        "f_ns_secret": "API secret or token (optional)", "h_ns_secret": "Needed only if your site is not publicly readable.",
        # sources
        "src_sub_dexcom": "G6 · G7 · ONE · ONE+",
        "src_desc_dexcom": "Uses Dexcom Share. In the Dexcom app turn on Share and invite at least one follower, then sign in with the wearer's Dexcom account.",
        "src_sub_libre": "Libre 2 · 2 Plus · 3 · 3 Plus",
        "src_desc_libre": "Uses LibreLinkUp. Invite yourself from the Libre app (Share → LibreLinkUp), create a LibreLinkUp account, and sign in with it here.",
        "src_sub_medtrum": "TouchCare A6 · A7 · Nano",
        "src_desc_medtrum": "Uses EasyView. Sign in with your EasyView account, or with an EasyFollow follower account.",
        "src_sub_ns": "Any sensor via xDrip+, Juggluco, AAPS, Loop…",
        "src_desc_ns": "Guardian/GL4, LinX/AiDEX, Sibionics, CareSens and others: upload with xDrip+ or Juggluco to a Nightscout site (or use xDrip+'s local web service) and enter the URL here.",
        # settings
        "s_unit": "Unit", "s_low": "Low alert below", "s_high": "High alert above", "s_urgent_low": "Urgent low below",
        "s_refresh": "Refresh every", "s_sec": "s", "s_min": "min", "s_stale": "Mark data stale after",
        "s_notify": "Show Windows notifications", "s_sound": "Play sound on alerts", "s_repeat": "Repeat alert every",
        "s_opacity": "Opacity", "s_size": "Size", "s_small": "Small", "s_medium": "Medium", "s_large": "Large",
        "s_autostart": "Start with Windows", "s_show_delta": "Show change since last reading",
        "s_click_through": "Always on top", "s_theme": "Theme", "t_dark": "Dark", "t_light": "Light",
        "s_language": "Language",
        # widget / tray
        "connecting": "connecting…", "no_data": "no data", "stale": "stale",
        "ago_now": "just now", "ago_min": "{m} min ago", "ago_hr": "{h} h {m} min ago",
        "m_show": "Show widget", "m_hide": "Hide widget", "m_refresh": "Refresh now", "m_open": "Open {site}",
        "m_settings": "Settings…", "m_setup": "Change sensor / account…", "m_about": "About", "m_quit": "Quit",
        "n_low_title": "Low glucose!", "n_urgent_title": "URGENT LOW!", "n_high_title": "High glucose",
        "n_stale_title": "No fresh data", "n_stale_body": "Last reading {age}. Check the phone app / sensor.",
        "n_err_title": "GlucoPop connection problem",
        "about_text": "GlucoPop {ver}\nMade by Emre Kılıç · a TypeHealthy project\n\nFree, open-source glucose widget.\nNot a medical device – always confirm with your official app before treating.\n\nhttps://github.com/{repo}",
        "credit": "Made by Emre Kılıç · TypeHealthy",
        # errors
        "e_auth": "Sign-in rejected. Check username/password.",
        "e_net": "Network error: {err}",
        "e_no_data": "Signed in, but no sensor data was returned (sensor warming up, not sharing, or no follower set up).",
        "e_llu_terms": "LibreLinkUp asks you to accept new terms. Open the LibreLinkUp app once, accept, then retry.",
        "e_libre_no_connection": "This LibreLinkUp account follows nobody. Invite yourself from the Libre app first.",
        "e_medtrum_no_follow": "This EasyFollow account follows nobody.",
        "e_rate_limited": "Too many requests – the server asked us to slow down.",
    },
    "tr": {
        "app": "GlucoPop",
        "tagline": "Şekerin, her zaman gözünün önünde.",
        "wz_title": "GlucoPop kurulumu",
        "wz_welcome": "Hoş geldin",
        "wz_welcome_text": "GlucoPop, sensör (CGM) glikoz değerini masaüstünde her zaman üstte duran küçük bir pencerede gösterir ve aralık dışına çıkınca uyarır.\n\nÜcretsiz ve açık kaynaklıdır. Giriş bilgilerin yalnızca bu bilgisayarda saklanır.",
        "wz_language": "Dil",
        "wz_source": "Hangi sensörü kullanıyorsun?",
        "wz_source_sub": "Verinin bulunduğu servisi seç. Emin değilsen kartın üzerine gel, açıklama çıkar.",
        "wz_login": "Giriş",
        "wz_login_sub": "Sensör verisini görebilen hesabı gir.",
        "wz_test": "Bağlantıyı test et",
        "wz_testing": "Bağlanıyor…",
        "wz_test_ok": "Bağlandı: {value} {unit} {arrow} ({age})",
        "wz_test_fail": "Bağlanamadı: {err}",
        "wz_need_test": "Devam etmeden önce bağlantıyı test et.",
        "wz_settings": "Widget ayarları",
        "wz_settings_sub": "Bunları sonradan tepsi ikonundan değiştirebilirsin.",
        "wz_done": "Hazır!",
        "wz_done_text": "GlucoPop artık sistem tepsisinde. Widget'ı istediğin yere sürükle; seçenekler için sağ tıkla.",
        "next": "İleri", "back": "Geri", "finish": "Bitir", "cancel": "İptal",
        "f_email": "E-posta", "f_password": "Şifre",
        "f_dexcom_user": "Dexcom kullanıcı adı / e-posta / telefon",
        "h_dexcom_user": "Sensörü takan kişinin Dexcom hesabı. Dexcom uygulamasında Paylaşım (Share) AÇIK olmalı ve en az bir takipçi davet edilmiş olmalı.",
        "f_region": "Bölge",
        "r_ous": "ABD dışı (Türkiye, Avrupa…)", "r_us": "ABD", "r_jp": "Japonya",
        "h_libre_user": "LibreLinkUp hesabın (LibreView değil). Libre uygulamasında: Paylaş → Bağlı uygulamalar → LibreLinkUp → kendi e-postanı davet et; sonra o e-postayla LibreLinkUp hesabı aç.",
        "f_libre_patient": "Takip edilen kişi (isteğe bağlı)",
        "h_libre_patient": "Boş bırakılırsa ilk bağlantı kullanılır.",
        "f_medtrum_type": "Hesap türü",
        "medtrum_patient": "Kendi EasyView hesabım", "medtrum_follow": "EasyFollow takipçi hesabı",
        "h_medtrum_type": "Hasta = easyview.medtrum.eu'ya girdiğin hesap. Takipçi = birini takip eden EasyFollow hesabı.",
        "f_server": "Sunucu", "r_medtrum_eu": "Avrupa (easyview.medtrum.eu)", "r_medtrum_fr": "Fransa", "r_medtrum_global": "Global",
        "f_medtrum_follow_user": "Takip edilen kullanıcı adı (isteğe bağlı)",
        "h_medtrum_follow_user": "Sadece birden fazla kişiyi takip ediyorsan.",
        "f_ns_url": "Nightscout adresi", "h_ns_url": "örn. https://adim.ns.10be.de — veya xDrip+ web servisi http://192.168.1.20:17580",
        "f_ns_secret": "API secret veya token (isteğe bağlı)", "h_ns_secret": "Siten herkese açık okunamıyorsa gerekir.",
        "src_sub_dexcom": "G6 · G7 · ONE · ONE+",
        "src_desc_dexcom": "Dexcom Share kullanır. Dexcom uygulamasında Paylaşım'ı aç ve en az bir takipçi davet et; sonra sensörü takan kişinin Dexcom hesabıyla giriş yap.",
        "src_sub_libre": "Libre 2 · 2 Plus · 3 · 3 Plus",
        "src_desc_libre": "LibreLinkUp kullanır. Libre uygulamasından kendini davet et (Paylaş → LibreLinkUp), LibreLinkUp hesabı aç ve burada onunla giriş yap.",
        "src_sub_medtrum": "TouchCare A6 · A7 · Nano",
        "src_desc_medtrum": "EasyView kullanır. Kendi EasyView hesabınla ya da EasyFollow takipçi hesabıyla giriş yap.",
        "src_sub_ns": "xDrip+, Juggluco, AAPS, Loop ile her sensör",
        "src_desc_ns": "Guardian/GL4, LinX/AiDEX, Sibionics, CareSens ve diğerleri: xDrip+ veya Juggluco ile bir Nightscout sitesine yükle (ya da xDrip+ yerel web servisini kullan) ve adresi buraya gir.",
        "s_unit": "Birim", "s_low": "Düşük uyarısı (altında)", "s_high": "Yüksek uyarısı (üstünde)", "s_urgent_low": "Acil düşük (altında)",
        "s_refresh": "Yenileme sıklığı", "s_sec": "sn", "s_min": "dk", "s_stale": "Veri eski sayılsın",
        "s_notify": "Windows bildirimi göster", "s_sound": "Uyarılarda ses çal", "s_repeat": "Uyarıyı tekrarla",
        "s_opacity": "Saydamlık", "s_size": "Boyut", "s_small": "Küçük", "s_medium": "Orta", "s_large": "Büyük",
        "s_autostart": "Windows ile başlat", "s_show_delta": "Son ölçüme göre değişimi göster",
        "s_click_through": "Her zaman üstte", "s_theme": "Tema", "t_dark": "Koyu", "t_light": "Açık",
        "s_language": "Dil",
        "connecting": "bağlanıyor…", "no_data": "veri yok", "stale": "eski",
        "ago_now": "az önce", "ago_min": "{m} dk önce", "ago_hr": "{h} sa {m} dk önce",
        "m_show": "Widget'ı göster", "m_hide": "Widget'ı gizle", "m_refresh": "Şimdi yenile", "m_open": "{site} aç",
        "m_settings": "Ayarlar…", "m_setup": "Sensör / hesap değiştir…", "m_about": "Hakkında", "m_quit": "Çıkış",
        "n_low_title": "Düşük glikoz!", "n_urgent_title": "ACİL DÜŞÜK!", "n_high_title": "Yüksek glikoz",
        "n_stale_title": "Güncel veri yok", "n_stale_body": "Son ölçüm {age}. Telefon uygulamasını / sensörü kontrol et.",
        "n_err_title": "GlucoPop bağlantı sorunu",
        "about_text": "GlucoPop {ver}\nEmre Kılıç tarafından yapıldı · bir TypeHealthy projesi\n\nÜcretsiz, açık kaynak glikoz widget'ı.\nTıbbi cihaz değildir – tedavi kararından önce mutlaka resmi uygulamandan doğrula.\n\nhttps://github.com/{repo}",
        "credit": "Emre Kılıç tarafından yapıldı · TypeHealthy",
        "e_auth": "Giriş reddedildi. Kullanıcı adı/şifreyi kontrol et.",
        "e_net": "Ağ hatası: {err}",
        "e_no_data": "Giriş yapıldı ama sensör verisi gelmedi (sensör ısınıyor, paylaşım kapalı ya da takipçi ayarlanmamış olabilir).",
        "e_llu_terms": "LibreLinkUp yeni koşulları kabul etmeni istiyor. LibreLinkUp uygulamasını bir kez aç, kabul et, sonra tekrar dene.",
        "e_libre_no_connection": "Bu LibreLinkUp hesabı kimseyi takip etmiyor. Önce Libre uygulamasından kendini davet et.",
        "e_medtrum_no_follow": "Bu EasyFollow hesabı kimseyi takip etmiyor.",
        "e_rate_limited": "Çok fazla istek – sunucu yavaşlamamızı istedi.",
    },
}

LANGUAGES = [("tr", "Türkçe"), ("en", "English")]


def set_language(lang: str) -> None:
    global _LANG
    _LANG = lang if lang in STRINGS else "en"


def get_language() -> str:
    return _LANG


def tr(key: str, **kw) -> str:
    s = STRINGS.get(_LANG, {}).get(key) or STRINGS["en"].get(key) or key
    if kw:
        try:
            s = s.format(**kw)
        except (KeyError, IndexError):
            pass
    return s


def age_text(seconds: int) -> str:
    if seconds < 60:
        return tr("ago_now")
    m = seconds // 60
    if m < 60:
        return tr("ago_min", m=m)
    return tr("ago_hr", h=m // 60, m=m % 60)
