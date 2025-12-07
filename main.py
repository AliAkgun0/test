import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# DİKKAT: Tekrarı önlemek için süreyi kıstım. 
# Bot 20 dk'da bir çalışıyor, biz son 30 dk'ya bakacağız.
TIME_WINDOW_MINUTES = 30 

# --- KAMUFLAJ ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com.tr/"
}

# --- SİTE YAPILANDIRMASI (METİN NEREDE SAKLI?) ---
SITES = [
    {
        "name": "Sabah Spor", 
        "rss": "https://www.sabah.com.tr/rss/spor.xml",
        "selector": "div.newsDetail" # Sabah'ın metin kutusu
    },
    {
        "name": "Hürriyet Spor", 
        "rss": "https://www.hurriyet.com.tr/rss/spor",
        "selector": "div.news-content" # Hürriyet'in metin kutusu
    },
    {
        "name": "Milliyet Spor", 
        "rss": "https://www.milliyet.com.tr/rss/rssNew/skorerRss.xml",
        "selector": "div.article-content" # Milliyet'in metin kutusu
    },
    {
        "name": "Fotomaç", 
        "rss": "https://www.fotomac.com.tr/rss/rssNew/futbolRss.xml",
        "selector": "div.detail-text-content" # Fotomaç'ın metin kutusu
    },
    {
        "name": "Fanatik", 
        "rss": "https://www.fanatik.com.tr/rss/futbol",
        "selector": "div.article-body" # Fanatik'in metin kutusu
    }
]

def check_time(entry):
    """Haber son 30 dakika içinde mi?"""
    try:
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = now - pub_time
            # Sadece son 30 dakikadaki haberleri al (Tekrarı önler)
            if diff <= timedelta(minutes=TIME_WINDOW_MINUTES):
                return True
    except:
        pass
    return False

def get_news_details(url, selector):
    """Siteye gir, özel kutudan metni ve resmi çek"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.content, "html.parser")
        
        # 1. RESİM
        img = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        img_url = img["content"] if img else None

        # 2. METİN (Nokta Atışı)
        text_content = ""
        
        # Sitenin özel metin kutusunu bul
        content_div = soup.select_one(selector)
        
        if content_div:
            # Sadece paragrafları al
            paragraphs = content_div.find_all(['p', 'h2', 'h3'])
            for p in paragraphs:
                text = p.get_text().strip()
                if len(text) > 30 and "tıklayın" not in text.lower() and "abone" not in text.lower():
                    text_content += text + "\n\n"
        
        # Eğer özel kutu boşsa veya bulunamadıysa JSON-LD dene (Yedek)
        if not text_content:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                if 'articleBody' in script.text:
                    try:
                        data = json.loads(script.text)
                        if isinstance(data, list): data = data[0]
                        text_content = data.get('articleBody', '')
                        break
                    except: pass

        # Yine boşsa RSS özetini al
        if not text_content:
            return img_url, "Detaylar haber linkindedir."

        # Telegram sınırı (1000 karakter)
        if len(text_content) > 950:
            text_content = text_content[:950] + "..."

        return img_url, text_content

    except Exception as e:
        print(f"      Hata: {e}")
        return None, None

def send_telegram(title, text, image_url, site_name):
    # Kaynak Linki Yok, Sadece Metin
    caption = f"📣 <b>{site_name}</b>\n\n🔹 <b>{title}</b>\n\n{text}"
    
    try:
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {"chat_id": CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "HTML"}
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"}
        
        r = requests.post(url, data=payload)
        if r.status_code == 200:
            print(f"      ✅ Kanala Gönderildi.")
            return True
        elif r.status_code == 400 and "IMAGE_PROCESS_FAILED" in r.text:
             # Resim hatası verirse resimsiz dene
             print("      ⚠️ Resim hatası, metin olarak deneniyor...")
             requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                          data={"chat_id": CHAT_ID, "text": caption, "parse_mode": "HTML"})
             return True
    except:
        pass
    return False

def main():
    print(f"🚀 Bot Başlatıldı (Son {TIME_WINDOW_MINUTES} dakika)")
    
    for site in SITES:
        print(f"🔎 {site['name']} kontrol ediliyor...")
        try:
            resp = requests.get(site['rss'], headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                print(f"   ⚠️ Erişim Engellendi: {resp.status_code}")
                continue

            feed = feedparser.parse(resp.content)
            
            # İlk 5 haberi kontrol et
            yeni_yok = True
            for entry in feed.entries[:5]:
                if check_time(entry):
                    print(f"   🆕 Haber: {entry.title}")
                    
                    # Özel seçiciyi (selector) fonksiyona gönder
                    img_url, full_text = get_news_details(entry.link, site['selector'])
                    
                    if send_telegram(entry.title, full_text, img_url, site['name']):
                        time.sleep(5)
                        yeni_yok = False
            
            if yeni_yok:
                print("   💤 Yeni haber yok.")
                
        except Exception as e:
            print(f"   ❌ Hata: {e}")

if __name__ == "__main__":
    main()
