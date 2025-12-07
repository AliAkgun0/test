import os
import json
import time
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# --- AYARLAR ---
# GitHub Actions Secrets'tan okuyacak
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
GIST_TOKEN = os.environ.get("GIST_TOKEN")
GIST_ID = os.environ.get("GIST_ID")

# Takip Edilecek Siteler ve RSS Kaynakları
SITES = [
    {
        "name": "Fanatik",
        "rss": "https://www.fanatik.com.tr/rss/futbol",
        "logo": "Fanatik"
    },
    {
        "name": "TRT Spor",
        "rss": "https://www.trtspor.com.tr/rss",
        "logo": "TRT Spor"
    },
    {
        "name": "NTV Spor",
        "rss": "https://www.ntvspor.net/rss",
        "logo": "NTV Spor"
    },
    {
        "name": "Fotomaç",
        "rss": "https://www.fotomac.com.tr/rss/rssNew/futbolRss.xml",
        "logo": "Fotomaç"
    }
]

# --- FONKSİYONLAR ---

def get_sent_links_from_gist():
    """GitHub Gist'ten daha önce gönderilen linkleri okur (Hafıza)"""
    headers = {"Authorization": f"token {GIST_TOKEN}"}
    try:
        response = requests.get(f"https://api.github.com/gists/{GIST_ID}", headers=headers)
        response.raise_for_status()
        content = response.json()["files"]["haber_hafizasi.json"]["content"]
        return json.loads(content)
    except Exception as e:
        print(f"Gist Okuma Hatası: {e}")
        return []

def update_gist_memory(sent_links):
    """GitHub Gist'i günceller (Yeni haberleri hafızaya yazar)"""
    # Son 200 haberi tut, gerisini sil (Hafıza şişmesin)
    if len(sent_links) > 200:
        sent_links = sent_links[-200:]
    
    headers = {
        "Authorization": f"token {GIST_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "files": {
            "haber_hafizasi.json": {
                "content": json.dumps(sent_links)
            }
        }
    }
    try:
        requests.patch(f"https://api.github.com/gists/{GIST_ID}", headers=headers, json=data)
        print("✅ Hafıza (Gist) güncellendi.")
    except Exception as e:
        print(f"❌ Gist Güncelleme Hatası: {e}")

def get_high_res_image(url):
    """Haberin içine girip kaliteli kapak fotoğrafını (og:image) çeker"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Öncelik 1: og:image
        img_tag = soup.find("meta", property="og:image")
        if img_tag and img_tag.get("content"):
            return img_tag["content"]
        
        # Öncelik 2: twitter:image
        img_tag = soup.find("meta", name="twitter:image")
        if img_tag and img_tag.get("content"):
            return img_tag["content"]
            
        return None
    except Exception:
        return None

def send_telegram_message(title, link, image_url, site_name):
    """Telegram'a Resimli Mesaj Gönderir"""
    
    # HTML formatında mesaj metni
    caption = f"<b>{site_name}</b>\n\n{title}\n\n<a href='{link}'>Haberi Oku 🔗</a>"
    
    try:
        if image_url:
            # Resim varsa sendPhoto kullan
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {
                "chat_id": CHAT_ID,
                "photo": image_url,
                "caption": caption,
                "parse_mode": "HTML"
            }
        else:
            # Resim yoksa sadece sendMessage kullan
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": CHAT_ID,
                "text": caption,
                "parse_mode": "HTML",
                "disable_web_page_preview": False
            }

        r = requests.post(url, data=payload)
        if r.status_code == 200:
            print(f"📤 Gönderildi: {title}")
            return True
        else:
            print(f"⚠️ Telegram Hatası: {r.text}")
            return False
            
    except Exception as e:
        print(f"Bağlantı Hatası: {e}")
        return False

def main():
    print(f"🚀 Haber Botu Başlatılıyor... Zaman: {datetime.now()}")
    
    # 1. Hafızayı Yükle
    sent_links = get_sent_links_from_gist()
    print(f"📂 Hafızada {len(sent_links)} eski haber var.")
    
    new_links_count = 0
    
    # 2. Siteleri Gez
    for site in SITES:
        print(f"🔍 Taranıyor: {site['name']}...")
        try:
            feed = feedparser.parse(site['rss'])
            
            # Son 5 haberi kontrol et (RSS'teki en yeni haberler)
            for entry in feed.entries[:5]:
                link = entry.link
                title = entry.title
                
                # Eğer link daha önce gönderilmediyse
                if link not in sent_links:
                    print(f"🆕 Yeni Haber Bulundu: {title}")
                    
                    # Detaylı resim çekme işlemi
                    image_url = get_high_res_image(link)
                    
                    # Telegram'a gönder
                    success = send_telegram_message(title, link, image_url, site['name'])
                    
                    if success:
                        sent_links.append(link)
                        new_links_count += 1
                        time.sleep(2) # Spam yapmamak için bekle
                else:
                    pass # Zaten gönderilmiş
                    
        except Exception as e:
            print(f"❌ {site['name']} hatası: {e}")

    # 3. Hafızayı Güncelle
    if new_links_count > 0:
        update_gist_memory(sent_links)
        print(f"🏁 İşlem Tamam. {new_links_count} yeni haber gönderildi.")
    else:
        print("💤 Yeni haber yok.")

if __name__ == "__main__":
    main()