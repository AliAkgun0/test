import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time
import random
import re

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
TIME_WINDOW_HOURS = 4

# --- KAMUFLAJ ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://news.google.com/"
    }

SITES = [
    {"name": "Sabah Spor", "rss": "https://www.sabah.com.tr/rss/spor.xml", "type": "direct", "selector": "div.newsDetail"},
    {"name": "Hürriyet Spor", "rss": "https://www.hurriyet.com.tr/rss/spor", "type": "direct", "selector": "div.news-content"},
    {"name": "Fotomaç", "rss": "https://news.google.com/rss/search?q=site:fotomac.com.tr/futbol&hl=tr-TR&gl=TR&ceid=TR:tr", "type": "google", "selector": "div.detail-text-content"},
    {"name": "Fanatik", "rss": "https://news.google.com/rss/search?q=site:fanatik.com.tr/futbol&hl=tr-TR&gl=TR&ceid=TR:tr", "type": "google", "selector": "div.article-body"},
    {"name": "NTV Spor", "rss": "https://news.google.com/rss/search?q=site:ntvspor.net/futbol&hl=tr-TR&gl=TR&ceid=TR:tr", "type": "google", "selector": "div.content-text"}
]

SENT_LINKS = set()

def resolve_google_url(url):
    """Google linkini gerçek site linkine dönüştürür"""
    try:
        # Google redirect'ini takip et
        r = requests.head(url, allow_redirects=True, timeout=5)
        real_url = r.url
        # Temizlik (bazen google parametreleri kalır)
        return real_url.split('?')[0]
    except:
        return url

def clean_title(title):
    """Başlıktaki site isimlerini temizler"""
    removals = [" - Fanatik", " - FOTOMAÇ", " - NTV Spor", " - Sabah", " - Hürriyet"]
    for r in removals:
        title = title.replace(r, "")
    return title

def check_time(entry):
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - pub_time) <= timedelta(hours=TIME_WINDOW_HOURS):
                return True
    except:
        return True
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
        
        # 2. Öncelik: Genel Arama
        if not text:
            for p in soup.find_all("p"):
                t = p.get_text().strip()
                if len(t) > 50 and "abone" not in t.lower():
                    text += t + "\n\n"
        
        # Temizlik
        if len(text) > 950: text = text[:950] + "..."
        if not text: text = ""

        return img_url, text
    except:
        return None, ""

def send_telegram(title, text, image_url, site_name):
    # Link Yok, G-News Yazısı Yok
    caption = f"📣 <b>{site_name}</b>\n\n🔹 <b>{clean_title(title)}</b>\n\n{text}"
    
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
    print(f"🚀 Bot Devrede (Zaman: {TIME_WINDOW_HOURS} saat)")
    
    for site in SITES:
        print(f"🔎 {site['name']} taranıyor...")
        try:
            resp = requests.get(site['rss'], headers=get_headers(), timeout=20)
            if resp.status_code != 200: continue

            feed = feedparser.parse(resp.content)
            
            for entry in feed.entries[:3]:
                if check_time(entry):
                    # Google linki ise gerçeğe çevir
                    real_link = resolve_google_url(entry.link) if site['type'] == 'google' else entry.link
                    
                    if real_link in SENT_LINKS: continue
                    
                    print(f"   🆕 Haber: {entry.title}")
                    
                    # Gerçek siteye git ve içeriği çek
                    img_url, full_text = get_content(real_link, site.get('selector'))
                    
                    if not full_text: 
                        full_text = entry.get('summary', 'Detaylar için siteyi ziyaret ediniz.')

                    # HTML etiketlerini temizle (Özet için)
                    full_text = BeautifulSoup(full_text, "html.parser").get_text()

                    if send_telegram(entry.title, full_text, img_url, site['name']):
                        print("      ✅ Gönderildi")
                        SENT_LINKS.add(real_link)
                        time.sleep(5)

        except Exception as e:
            print(f"   ❌ Hata: {e}")

if __name__ == "__main__":
    main()
