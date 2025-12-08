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

# KRİTİK AYAR: Bot 20 dk'da bir çalışıyor. 
# Biz 25 dk yapıyoruz ki arada kaçan olmasın ama eskileri de tekrar atmasın.
TIME_WINDOW_MINUTES = 40 

# --- KAMUFLAJ ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.google.com.tr/"
    }

SITES = [
    {
        "name": "Sabah Spor", 
        "rss": "https://www.sabah.com.tr/rss/spor.xml", 
        "selector": "div.newsDetail"
    },
    {
        "name": "Hürriyet", 
        "rss": "https://www.hurriyet.com.tr/rss/spor", 
        "selector": "div.news-content"
    },
    {
        "name": "Fotomaç", 
        "rss": "https://www.fotomac.com.tr/rss/rssNew/futbolRss.xml", 
        "selector": "div.detail-text-content"
    },
    {
        "name": "Fanatik", 
        "rss": "https://www.fanatik.com.tr/rss/futbol", 
        "selector": "div.article-body"
    },
    {
        "name": "NTV Spor", 
        "rss": "https://www.ntvspor.net/rss", 
        "selector": "div.content-text"
    }
]

def clean_title(title):
    """Başlıktaki site isimlerini temizler"""
    removals = [" - Fanatik", " - FOTOMAÇ", " - NTV Spor", " - Sabah", " - Hürriyet", "Son Dakika"]
    for r in removals:
        title = title.replace(r, "")
    return title.strip()

def smart_truncate(text, max_length=950):
    """Metni cümle ortasında kesmez"""
    if len(text) <= max_length:
        return text
    cut_text = text[:max_length]
    last_dot = cut_text.rfind('.')
    if last_dot > 100:
        return cut_text[:last_dot+1]
    return cut_text + "..."

def check_time(entry):
    """Haber tam olarak son 25 dakika içinde mi?"""
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            # RSS saatini al
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            
            # Şu anki saat
            now = datetime.now(timezone.utc)
            
            # Aradaki fark
            diff = now - pub_time
            
            # Eğer haber son 25 dakika içindeyse AL
            if diff <= timedelta(minutes=TIME_WINDOW_MINUTES):
                return True
    except:
        pass
    return False

def get_content(url, selector):
    """Siteye gir, metni ve resmi çek"""
    try:
        r = requests.get(url, headers=get_headers(), timeout=15)
        soup = BeautifulSoup(r.content, "html.parser")
        
        # Resim
        img = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        img_url = img["content"] if img else None

        # Metin
        text = ""
        if selector:
            box = soup.select_one(selector)
            if box:
                for p in box.find_all(['p', 'h2']):
                    t = p.get_text().strip()
                    if len(t) > 30 and "tıklayın" not in t.lower():
                        text += t + "\n\n"
        
        if not text:
            for p in soup.find_all("p"):
                t = p.get_text().strip()
                if len(t) > 50 and "abone" not in t.lower():
                    text += t + "\n\n"
        
        text = smart_truncate(text)
        return img_url, text
    except:
        return None, ""

def send_telegram(title, text, image_url, site_name):
    clean_t = clean_title(title)
    if text.strip() == clean_t: text = ""

    caption = f"📣 <b>{site_name}</b>\n\n🔹 <b>{clean_t}</b>\n\n{text}"
    
    try:
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {"chat_id": CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "HTML"}
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
        
        r = requests.post(url, data=payload, timeout=10)
        return r.status_code == 200
    except:
        return False

def main():
    print(f"🚀 Bot Devrede (Süre Sınırı: {TIME_WINDOW_MINUTES} dakika)")
    
    for site in SITES:
        print(f"🔎 {site['name']} kontrol ediliyor...")
        try:
            resp = requests.get(site['rss'], headers=get_headers(), timeout=20)
            if resp.status_code != 200: continue

            feed = feedparser.parse(resp.content)
            
            count = 0
            for entry in feed.entries[:5]: # İlk 5'e bak
                # Burası çok önemli: Sadece son 25 dk içindekileri al
                if check_time(entry):
                    print(f"   🆕 Taze Haber: {entry.title}")
                    
                    img_url, full_text = get_content(entry.link, site.get('selector'))
                    if not full_text: full_text = entry.get('summary', '')
                    full_text = BeautifulSoup(full_text, "html.parser").get_text()

                    if send_telegram(entry.title, full_text, img_url, site['name']):
                        print("      ✅ Gönderildi")
                        count += 1
                        time.sleep(5)
            
            if count == 0:
                print("   💤 Bu aralıkta yeni haber yok.")

        except Exception as e:
            print(f"   ❌ Hata: {e}")

if __name__ == "__main__":
    main()
