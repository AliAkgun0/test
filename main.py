import os
import json
import time
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID = os.environ.get("GIST_ID")

# --- TARAYICI KİMLİĞİ (Anti-Blok) ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
}

SITES = [
    {"name": "Fanatik", "rss": "https://www.fanatik.com.tr/rss/futbol"},
    {"name": "TRT Spor", "rss": "https://www.trtspor.com.tr/rss"},
    {"name": "NTV Spor", "rss": "https://www.ntvspor.net/rss"},
    {"name": "Fotomaç", "rss": "https://www.fotomac.com.tr/rss/rssNew/futbolRss.xml"}
]

def get_sent_links():
    """Gist'ten hafızayı okur"""
    headers = {"Authorization": f"token {GIST_TOKEN}"}
    try:
        r = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers)
        if r.status_code == 200:
            content = r.json()["files"]["haber_hafizasi.json"]["content"]
            data = json.loads(content)
            print(f"✅ Hafıza yüklendi: {len(data)} kayıt var.")
            return data
        else:
            print(f"⚠️ Gist Bulunamadı (Hata Kodu: {r.status_code}). ID veya Token kontrol et.")
            return []
    except Exception as e:
        print(f"❌ Hafıza Hatası: {e}")
        return []

def save_sent_links(links):
    """Gist'e kaydeder"""
    if len(links) > 200: links = links[-200:]
    headers = {"Authorization": f"token {GIST_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    data = {"files": {"haber_hafizasi.json": {"content": json.dumps(links)}}}
    try:
        r = requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=data)
        if r.status_code == 200:
            print("💾 Hafıza başarıyla güncellendi.")
        else:
            print(f"⚠️ Hafıza Kaydedilemedi: {r.status_code}")
    except Exception as e:
        print(f"❌ Kayıt Hatası: {e}")

def get_image(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.content, "html.parser")
        img = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        if img and img.get("content"):
            return img["content"]
    except:
        return None
    return None

def send_telegram(title, link, image_url, site_name):
    caption = f"<b>{site_name}</b>\n\n{title}\n\n<a href='{link}'>Haberi Oku 🔗</a>"
    try:
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {"chat_id": CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "HTML"}
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
        
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code == 200:
            return True
        else:
            print(f"Telegram Hatası: {r.text}")
            return False
    except Exception as e:
        print(f"Gönderim Hatası: {e}")
        return False

def main():
    print(f"🚀 Bot Başladı: {datetime.now()}")
    sent_links = get_sent_links()
    new_count = 0
    
    for site in SITES:
        print(f"🔎 Taranıyor: {site['name']}...")
        try:
            # RSS'i özel header ile çekiyoruz (Önemli Değişiklik)
            response = requests.get(site['rss'], headers=HEADERS, timeout=15)
            feed = feedparser.parse(response.content)
            
            if not feed.entries:
                print(f"   ⚠️ {site['name']} RSS boş döndü! (Engel yemiş olabilir)")
                continue
                
            print(f"   ✅ {len(feed.entries)} haber bulundu.")
            
            for entry in feed.entries[:3]: # Sitenin en yeni 3 haberine bak
                link = entry.link
                title = entry.title
                
                if link not in sent_links:
                    print(f"   🆕 Yeni: {title}")
                    img_url = get_image(link)
                    if send_telegram(title, link, img_url, site['name']):
                        sent_links.append(link)
                        new_count += 1
                        time.sleep(3)
        except Exception as e:
            print(f"   ❌ {site['name']} Hatası: {e}")

    if new_count > 0:
        save_sent_links(sent_links)
        print(f"🏁 Toplam {new_count} yeni haber gönderildi.")
    else:
        print("💤 Yeni haber yok.")

if __name__ == "__main__":
    main()
