import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TIME_WINDOW_MINUTES = 45 # Son 45 dakikadaki haberler

# --- KAMUFLAJ ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

SITES = [
    {"name": "Fanatik", "rss": "https://www.fanatik.com.tr/rss/futbol"},
    {"name": "TRT Spor", "rss": "https://www.trtspor.com.tr/rss"},
    {"name": "NTV Spor", "rss": "https://www.ntvspor.net/rss"},
    {"name": "Sabah", "rss": "https://www.sabah.com.tr/rss/spor.xml"}
]

def is_new(entry):
    """Haber yeni mi?"""
    try:
        if hasattr(entry, 'published_parsed'):
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - pub_time) <= timedelta(minutes=TIME_WINDOW_MINUTES):
                return True
    except:
        pass # Tarih hatası olursa geç
    return False

def get_content_and_image(url):
    """Siteye gir, hem resmi hem de metni çek"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.content, "html.parser")
        
        # 1. RESİM BULMA
        img = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        img_url = img["content"] if img else None

        # 2. METİN BULMA (En zor kısım, sitelerin yapısı farklı)
        text_content = ""
        
        # Tüm paragrafları (<p>) topla
        paragraphs = soup.find_all("p")
        for p in paragraphs:
            text = p.get_text().strip()
            # Reklam veya gereksiz kısa yazıları filtrele
            if len(text) > 30 and "tıklayın" not in text.lower() and "abone ol" not in text.lower():
                text_content += text + "\n\n"
        
        # Eğer metin çok kısaysa (çekemediysek), özet (description) kullan
        if len(text_content) < 100:
            desc = soup.find("meta", property="og:description")
            if desc:
                text_content = desc["content"]

        # Telegram sınırı (4096 karakter) - Güvenlik için 1000 karakterde keselim
        if len(text_content) > 950:
            text_content = text_content[:950] + "..."

        return img_url, text_content

    except:
        return None, "Haber detayı alınamadı."

def send_telegram(title, text, image_url, site_name):
    # Mesaj Formatı: Site Adı (Kalın) + Başlık + İçerik
    caption = f"📣 <b>{site_name}</b>\n\n🔹 <b>{title}</b>\n\n{text}"
    
    try:
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {
                "chat_id": CHAT_ID, 
                "photo": image_url, 
                "caption": caption, 
                "parse_mode": "HTML"
            }
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": CHAT_ID, 
                "text": caption, 
                "parse_mode": "HTML"
            }
        
        requests.post(url, data=payload)
        print(f"✅ Kanala Atıldı: {title}")
    except Exception as e:
        print(f"❌ Hata: {e}")

def main():
    print("🚀 Kanal Botu Çalışıyor...")
    
    for site in SITES:
        try:
            resp = requests.get(site['rss'], headers=HEADERS, timeout=15)
            feed = feedparser.parse(resp.content)
            
            for entry in feed.entries[:5]:
                if is_new(entry):
                    print(f"🆕 Tespit Edildi: {entry.title}")
                    
                    # Siteye girip içeriği çek
                    img_url, full_text = get_content_and_image(entry.link)
                    
                    # Eğer içerik boşsa RSS özetini kullan
                    if not full_text or len(full_text) < 20:
                        full_text = entry.get('summary', 'Detay yok.')

                    send_telegram(entry.title, full_text, img_url, site['name'])
                    time.sleep(3) 
                else:
                    print(f"💤 Eski: {entry.title}")
                    
        except Exception as e:
            print(f"❌ {site['name']} Hatası: {e}")

if __name__ == "__main__":
    main()
