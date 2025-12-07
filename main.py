import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TIME_WINDOW_HOURS = 3  # Son 3 saatteki haberleri getir

# --- KAMUFLAJ (Anti-Blok) ---
# Bu ayarlar botu gerçek bir Windows bilgisayar gibi gösterir
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com.tr/"
}

# --- SİTELER (Daha Uyumlu Liste) ---
SITES = [
    {"name": "Sabah Spor", "rss": "https://www.sabah.com.tr/rss/spor.xml"},
    {"name": "Fotomaç", "rss": "https://www.fotomac.com.tr/rss/rssNew/futbolRss.xml"},
    {"name": "Fanatik", "rss": "https://www.fanatik.com.tr/rss/futbol"},
    {"name": "Hürriyet Spor", "rss": "https://www.hurriyet.com.tr/rss/spor"},
    {"name": "Milliyet Spor", "rss": "https://www.milliyet.com.tr/rss/rssNew/skorerRss.xml"}
]

def check_time(entry):
    """Haberin son 3 saat içinde olup olmadığını kontrol et"""
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = now - pub_time
            
            # Eğer haber son X saat içindeyse AL
            if diff <= timedelta(hours=TIME_WINDOW_HOURS):
                return True
    except:
        # Tarih okuyamazsak ve haber listesinin en başındaysa alalım
        return True
    return False

def get_news_details(url):
    """Haberin resmini ve özetini çeker"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.content, "html.parser")
        
        # Resim Bulma
        img = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        img_url = img["content"] if img else None

        # Özet Bulma (Description en temizi)
        desc = soup.find("meta", property="og:description") or soup.find("meta", name="description")
        text = desc["content"] if desc else "Detaylar için habere gidin."

        return img_url, text
    except:
        return None, "Detay çekilemedi."

def send_telegram(title, text, image_url, site_name, link):
    caption = f"📣 <b>{site_name}</b>\n\n🔹 <b>{title}</b>\n\n{text}"
    
    try:
        # Resim varsa resimli at, yoksa normal mesaj at
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {"chat_id": CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "HTML"}
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
            
        r = requests.post(url, data=payload, timeout=10)
        
        # Eğer Telegram "Resim formatı bozuk" derse, sadece yazıyı at (Yedek Plan)
        if r.status_code != 200:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                          data={"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"})
            
        return True
    except:
        return False

def main():
    print(f"🚀 Bot Başlatıldı (Son {TIME_WINDOW_HOURS} saat taranıyor)")
    
    for site in SITES:
        print(f"🔎 {site['name']} taranıyor...")
        try:
            # RSS çekme
            resp = requests.get(site['rss'], headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                print(f"   ⚠️ Erişim Engellendi (Kod: {resp.status_code})")
                continue
                
            feed = feedparser.parse(resp.content)
            
            if not feed.entries:
                print("   ⚠️ RSS Boş!")
                continue

            # Sitenin en yeni 5 haberini kontrol et
            count = 0
            for entry in feed.entries[:5]:
                if check_time(entry):
                    print(f"   🆕 Haber Bulundu: {entry.title}")
                    
                    img_url, summary = get_news_details(entry.link)
                    
                    # Eğer metin yoksa RSS'teki özeti kullan
                    if not summary or len(summary) < 10:
                        summary = entry.get('summary', 'Detay yok.')
                    
                    # Özeti temizle (HTML kodlarını sil)
                    summary = BeautifulSoup(summary, "html.parser").get_text()

                    send_telegram(entry.title, summary, img_url, site['name'], entry.link)
                    count += 1
                    time.sleep(5) # Spam olmasın diye bekle
            
            if count == 0:
                print("   💤 Bu sitede yeni haber yok.")
                
        except Exception as e:
            print(f"   ❌ Hata: {e}")

if __name__ == "__main__":
    main()
