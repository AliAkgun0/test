import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time
import random

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TIME_WINDOW_HOURS = 4  # Son 4 saate bak (Sabah'ı kaçırmamak için genişlettik)

# --- TARAYICI KİMLİKLERİ HAVUZU (Rastgele Seçilecek) ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://news.google.com/"
    }

# --- SİTE YAPILANDIRMASI ---
# Not: Fotomaç ve Fanatik için Google News RSS kullanıyoruz (Engeli aşmak için)
SITES = [
    {
        "name": "Sabah Spor", 
        "rss": "https://www.sabah.com.tr/rss/spor.xml",
        "type": "direct",
        "selector": "div.newsDetail"
    },
    {
        "name": "Hürriyet Spor", 
        "rss": "https://www.hurriyet.com.tr/rss/spor",
        "type": "direct",
        "selector": "div.news-content"
    },
    {
        "name": "Fotomaç (G-News)", 
        "rss": "https://news.google.com/rss/search?q=site:fotomac.com.tr/futbol&hl=tr-TR&gl=TR&ceid=TR:tr",
        "type": "google",
        "selector": "div.detail-text-content"
    },
    {
        "name": "Fanatik (G-News)", 
        "rss": "https://news.google.com/rss/search?q=site:fanatik.com.tr/futbol&hl=tr-TR&gl=TR&ceid=TR:tr",
        "type": "google",
        "selector": "div.article-body"
    },
    {
        "name": "NTV Spor (G-News)", 
        "rss": "https://news.google.com/rss/search?q=site:ntvspor.net/futbol&hl=tr-TR&gl=TR&ceid=TR:tr",
        "type": "google",
        "selector": "div.content-text"
    }
]

# Hafıza Dosyası (Geçici)
SENT_LINKS = set()

def resolve_google_url(url):
    """Google News şifreli linkini gerçek linke çevirir"""
    try:
        # Google redirect'ini çöz
        r = requests.head(url, allow_redirects=True, timeout=5)
        return r.url
    except:
        return url

def check_time(entry):
    """Haberin zamanını kontrol et"""
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = now - pub_time
            # Son X saat içindeyse al
            if diff <= timedelta(hours=TIME_WINDOW_HOURS):
                return True
    except:
        return True # Tarih yoksa yeni kabul et
    return False

def get_content(url, selector):
    """Siteye gir, metni ve resmi al"""
    try:
        session = requests.Session()
        r = session.get(url, headers=get_headers(), timeout=15)
        soup = BeautifulSoup(r.content, "html.parser")
        
        # Resim
        img = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        img_url = img["content"] if img else None

        # Metin
        text = ""
        # 1. Öncelik: Özel Seçici
        if selector:
            box = soup.select_one(selector)
            if box:
                for p in box.find_all(['p', 'h2']):
                    t = p.get_text().strip()
                    if len(t) > 30 and "tıklayın" not in t.lower():
                        text += t + "\n\n"
        
        # 2. Öncelik: Genel Arama (Yedek)
        if not text:
            for p in soup.find_all("p"):
                t = p.get_text().strip()
                if len(t) > 50 and "abone" not in t.lower():
                    text += t + "\n\n"
        
        if len(text) > 950: text = text[:950] + "..."
        if not text: text = "Detaylar haber linkindedir."

        return img_url, text
    except:
        return None, "İçerik çekilemedi."

def send_telegram(title, text, image_url, site_name, link):
    caption = f"📣 <b>{site_name}</b>\n\n🔹 <b>{title}</b>\n\n{text}\n\n🔗 <a href='{link}'>Kaynağa Git</a>"
    
    try:
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {"chat_id": CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "HTML"}
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": False}
        
        r = requests.post(url, data=payload, timeout=10)
        
        # Resim hatası verirse sadece metin at
        if r.status_code != 200:
             requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                          data={"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"})
        return True
    except:
        return False

def main():
    print(f"🚀 Bot Devrede (Zaman Penceresi: {TIME_WINDOW_HOURS} saat)")
    
    for site in SITES:
        print(f"🔎 {site['name']} taranıyor...")
        try:
            # RSS İsteği
            resp = requests.get(site['rss'], headers=get_headers(), timeout=20)
            if resp.status_code != 200:
                print(f"   ⚠️ RSS Erişimi Yok: {resp.status_code}")
                continue

            feed = feedparser.parse(resp.content)
            
            # Her siteden en yeni 3 haberi al
            count = 0
            for entry in feed.entries[:3]:
                if check_time(entry):
                    # Google linki ise çöz, değilse olduğu gibi al
                    real_link = resolve_google_url(entry.link) if site['type'] == 'google' else entry.link
                    
                    # Aynı linki tekrar atma (Basit hafıza)
                    if real_link in SENT_LINKS:
                        continue
                    
                    print(f"   🆕 Haber: {entry.title}")
                    
                    img_url, full_text = get_content(real_link, site.get('selector'))
                    
                    if send_telegram(entry.title, full_text, img_url, site['name'], real_link):
                        print("      ✅ Gönderildi")
                        SENT_LINKS.add(real_link)
                        count += 1
                        time.sleep(5)
            
            if count == 0:
                print("   💤 Uygun haber bulunamadı.")

        except Exception as e:
            print(f"   ❌ Hata: {e}")

if __name__ == "__main__":
    main()
