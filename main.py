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
TIME_WINDOW_HOURS = 4  # Son 4 saatteki haberler

# --- SİTELER (Hepsi Orijinal Linkler) ---
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

# --- KAMUFLAJ (Bot Engeli Aşmak İçin) ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

SENT_LINKS = set()

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.google.com.tr/"
    }

def clean_title(title):
    """Başlıktaki site isimlerini temizler"""
    removals = [" - Fanatik", " - FOTOMAÇ", " - NTV Spor", " - Sabah", " - Hürriyet", "Son Dakika"]
    for r in removals:
        title = title.replace(r, "")
    return title.strip()

def smart_truncate(text, max_length=950):
    """Metni cümle ortasında kesmez, noktada bitirir"""
    if len(text) <= max_length:
        return text
    cut_text = text[:max_length]
    last_dot = cut_text.rfind('.')
    if last_dot > 100:
        return cut_text[:last_dot+1]
    return cut_text + "..."

def check_time(entry):
    """Haber zaman kontrolü"""
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - pub_time) <= timedelta(hours=TIME_WINDOW_HOURS):
                return True
    except:
        return True
    return False

def get_content(url, selector):
    """Siteye gir, metni ve resmi çek"""
    try:
        r = requests.get(url, headers=get_headers(), timeout=15)
        soup = BeautifulSoup(r.content, "html.parser")
        
        # 1. Resim Bulma
        img = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        img_url = img["content"] if img else None

        # 2. Metin Bulma
        text = ""
        # Önce özel kutuya bak
        if selector:
            box = soup.select_one(selector)
            if box:
                for p in box.find_all(['p', 'h2']):
                    t = p.get_text().strip()
                    if len(t) > 30 and "tıklayın" not in t.lower():
                        text += t + "\n\n"
        
        # Bulamazsa genel paragraflara bak
        if not text:
            for p in soup.find_all("p"):
                t = p.get_text().strip()
                if len(t) > 50 and "abone" not in t.lower():
                    text += t + "\n\n"
        
        # Temizlik
        text = smart_truncate(text)
        if not text: text = ""

        return img_url, text
    except:
        return None, ""

def send_telegram(title, text, image_url, site_name):
    clean_t = clean_title(title)
    
    # Metin başlıkla aynıysa metni boşalt (tekrar etmesin)
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
    print(f"🚀 Bot Devrede (Google News İptal - Direkt Bağlantı)")
    
    for site in SITES:
        print(f"🔎 {site['name']} taranıyor...")
        try:
            resp = requests.get(site['rss'], headers=get_headers(), timeout=20)
            
            # Eğer site engellerse loga yazıp geç
            if resp.status_code != 200:
                print(f"   ⚠️ Erişim Engellendi (Kod: {resp.status_code})")
                continue

            feed = feedparser.parse(resp.content)
            
            for entry in feed.entries[:3]:
                if check_time(entry):
                    if entry.link in SENT_LINKS: continue
                    
                    print(f"   🆕 Haber: {entry.title}")
                    
                    img_url, full_text = get_content(entry.link, site.get('selector'))
                    
                    if not full_text: 
                        full_text = entry.get('summary', '')

                    full_text = BeautifulSoup(full_text, "html.parser").get_text()

                    if send_telegram(entry.title, full_text, img_url, site['name']):
                        print("      ✅ Gönderildi")
                        SENT_LINKS.add(entry.link)
                        time.sleep(5)

        except Exception as e:
            print(f"   ❌ Hata: {e}")

if __name__ == "__main__":
    main()
