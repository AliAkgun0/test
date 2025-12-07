import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# DİKKAT: Süreyi 90 dakika yaptım (Gecikmeli haberleri de yakalasın diye)
TIME_WINDOW_MINUTES = 90 

# --- KAMUFLAJ ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

SITES = [
    {"name": "Fanatik", "rss": "https://www.fanatik.com.tr/rss/futbol"},
    {"name": "TRT Spor", "rss": "https://www.trtspor.com.tr/rss"},
    {"name": "NTV Spor", "rss": "https://www.ntvspor.net/rss"},
    {"name": "Sabah", "rss": "https://www.sabah.com.tr/rss/spor.xml"},
    {"name": "Fotomaç", "rss": "https://www.fotomac.com.tr/rss/rssNew/futbolRss.xml"}
]

def is_new(entry):
    """Haberin tarihini kontrol et"""
    try:
        if hasattr(entry, 'published_parsed'):
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            # Haberin üzerinden geçen süre
            fark = datetime.now(timezone.utc) - pub_time
            # Eğer süre sınırımızdan azsa YENİDİR
            if fark <= timedelta(minutes=TIME_WINDOW_MINUTES):
                return True
    except:
        return False
    return False

def get_content_and_image(url):
    """Haberin içine gir, resim ve metin al"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.content, "html.parser")
        
        # Resim
        img = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        img_url = img["content"] if img else None

        # Metin (Paragrafları birleştir)
        text_content = ""
        for p in soup.find_all("p"):
            text = p.get_text().strip()
            if len(text) > 40 and "tıklayın" not in text.lower():
                text_content += text + "\n\n"
        
        if len(text_content) < 50:
            desc = soup.find("meta", property="og:description")
            if desc: text_content = desc["content"]

        if len(text_content) > 900:
            text_content = text_content[:900] + "..."

        return img_url, text_content
    except:
        return None, ""

def send_telegram(title, text, image_url, site_name):
    # Mesaj Şablonu
    caption = f"📣 <b>{site_name}</b>\n\n🔹 <b>{title}</b>\n\n{text}"
    
    try:
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {"chat_id": CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "HTML"}
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
        
        requests.post(url, data=payload)
        return True
    except:
        return False

def main():
    print(f"🚀 Bot Başlatıldı (Süre Limiti: {TIME_WINDOW_MINUTES} dk)")
    
    for site in SITES:
        print(f"🔎 {site['name']} taranıyor...") # Hangi sitede olduğunu göreceğiz
        try:
            resp = requests.get(site['rss'], headers=HEADERS, timeout=15)
            feed = feedparser.parse(resp.content)
            
            yeni_bulundu = False
            for entry in feed.entries[:5]: # Son 5 habere bak
                if is_new(entry):
                    print(f"   🆕 YENİ: {entry.title}")
                    img_url, full_text = get_content_and_image(entry.link)
                    
                    if send_telegram(entry.title, full_text, img_url, site['name']):
                        print(f"   ✅ Kanala Gönderildi")
                        yeni_bulundu = True
                        time.sleep(3)
            
            if not yeni_bulundu:
                print(f"   💤 {site['name']} için yeni haber yok.")
                
        except Exception as e:
            print(f"   ❌ {site['name']} Hatası: {e}")

if __name__ == "__main__":
    main()
