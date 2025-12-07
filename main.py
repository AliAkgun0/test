import os
import time
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

# --- SADECE BU İKİSİ YETERLİ ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# --- AYARLAR ---
TIME_WINDOW_MINUTES = 45  # Son 45 dakikadaki haberleri getir
# Kamuflaj (Chrome Gibi Görün)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

SITES = [
    {"name": "Fanatik", "rss": "https://www.fanatik.com.tr/rss/futbol"},
    {"name": "TRT Spor", "rss": "https://www.trtspor.com.tr/rss"},
    {"name": "NTV Spor", "rss": "https://www.ntvspor.net/rss"},
    {"name": "Fotomaç", "rss": "https://www.fotomac.com.tr/rss/rssNew/futbolRss.xml"},
    {"name": "Sabah", "rss": "https://www.sabah.com.tr/rss/spor.xml"}
]

def get_image(url):
    """Haberin içine girip resim bulur"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.content, "html.parser")
        img = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        if img and img.get("content"):
            return img["content"]
    except:
        return None
    return None

def is_new(entry):
    """Haberin saati son 45 dakika içinde mi?"""
    try:
        # RSS zamanını al
        if hasattr(entry, 'published_parsed'):
            published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        else:
            return True # Tarih yoksa yeni kabul et (Riskli ama kaçırmaz)
        
        # Şu anki zaman (UTC)
        now = datetime.now(timezone.utc)
        
        # Farkı hesapla
        diff = now - published_time
        
        # Eğer haber son X dakikada yayınlandıysa "Yeni"dir
        if diff <= timedelta(minutes=TIME_WINDOW_MINUTES):
            return True
    except:
        return True # Hata çıkarsa yeni kabul et
    
    return False

def send_telegram(title, link, image_url, site_name):
    caption = f"<b>{site_name}</b>\n\n{title}\n\n<a href='{link}'>Haberi Oku 🔗</a>"
    try:
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {"chat_id": CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "HTML"}
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
        
        requests.post(url, data=payload)
        print(f"✅ Gönderildi: {title}")
    except:
        pass

def main():
    print("🚀 Bot Kontrol Ediyor...")
    
    for site in SITES:
        try:
            # RSS çek
            resp = requests.get(site['rss'], headers=HEADERS, timeout=20)
            feed = feedparser.parse(resp.content)
            
            # İlk 5 haberi kontrol et
            for entry in feed.entries[:5]:
                # Sadece ZAMANA bak, veritabanına değil
                if is_new(entry):
                    print(f"🆕 Taze Haber: {entry.title}")
                    img = get_image(entry.link)
                    send_telegram(entry.title, entry.link, img, site['name'])
                    time.sleep(2) # Spam yapma
                else:
                    print(f"💤 Eski Haber: {entry.title}")
                    
        except Exception as e:
            print(f"❌ {site['name']} Hatası: {e}")

if __name__ == "__main__":
    main()
