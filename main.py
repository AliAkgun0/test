import os
import json
import time
import requests
import feedparser
from bs4 import BeautifulSoup

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# --- GELİŞMİŞ KAMUFLAJ ---
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/"
}

SITES = [
    {"name": "Fotomaç", "rss": "https://www.fotomac.com.tr/rss/rssNew/futbolRss.xml"},
    {"name": "Fanatik", "rss": "https://www.fanatik.com.tr/rss/futbol"},
    {"name": "TRT Spor", "rss": "https://www.trtspor.com.tr/rss"},
    {"name": "NTV Spor", "rss": "https://www.ntvspor.net/rss"},
    {"name": "Sabah Spor", "rss": "https://www.sabah.com.tr/rss/spor.xml"}
]

# --- HAFIZA SİSTEMİ (Basit Dosya) ---
# GitHub Actions her çalıştığında sıfırlanmasın diye basit bir mantık kuruyoruz.
# Ancak Actions'da kalıcı hafıza zordur, bu yüzden son gönderilenleri
# o anki çalışmada hafızada tutup tekrarı önleyeceğiz.
SENT_LINKS = set()

def get_news_details(url):
    """
    Sayfanın içine girer ve Google için hazırlanan 
    GİZLİ JSON verisini (ld+json) okur. En temiz yöntemdir.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(response.content, "html.parser")

        # 1. RESİM BULMA (Meta Etiketlerinden)
        img = soup.find("meta", property="og:image") or soup.find("meta", name="twitter:image")
        img_url = img["content"] if img else None

        # 2. İÇERİK BULMA (JSON-LD Yöntemi - Attığın kodlarda bu var!)
        text_content = ""
        scripts = soup.find_all('script', type='application/ld+json')
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                # Eğer veri bir listeyse döngüye al
                if isinstance(data, list):
                    for item in data:
                        if 'articleBody' in item:
                            text_content = item['articleBody']
                            break
                # Eğer veri sözlükse direkt bak
                elif isinstance(data, dict):
                    if 'articleBody' in data:
                        text_content = data['articleBody']
                        break
            except:
                continue
        
        # Eğer JSON'dan metin çıkmazsa klasik yönteme dön (<p> etiketleri)
        if not text_content:
            paragraphs = soup.find_all("p")
            for p in paragraphs:
                text = p.get_text().strip()
                if len(text) > 40 and "tıklayın" not in text.lower():
                    text_content += text + "\n\n"

        # Temizlik ve Kısaltma
        text_content = text_content.replace("&nbsp;", " ").strip()
        
        # HTML taglerini temizle (bazen json içinde html kalabiliyor)
        text_content = BeautifulSoup(text_content, "html.parser").get_text()

        # Çok uzunsa kes (Telegram limiti 1024 karakter resim altında)
        if len(text_content) > 900:
            text_content = text_content[:900] + "..."

        return img_url, text_content

    except Exception as e:
        print(f"      ❌ Detay Çekme Hatası: {e}")
        return None, None

def send_telegram(title, text, image_url, site_name):
    # Mesaj Şablonu
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
        
        r = requests.post(url, data=payload, timeout=20)
        if r.status_code == 200:
            return True
        else:
            print(f"      ⚠️ Telegram Hatası: {r.text}")
            return False
    except Exception as e:
        print(f"      ❌ Bağlantı Hatası: {e}")
        return False

def main():
    print("🚀 Bot Başlatılıyor... (JSON-LD Modu)")
    
    for site in SITES:
        print(f"🔎 {site['name']} taranıyor...")
        try:
            # RSS'i requests ile çekiyoruz
            resp = requests.get(site['rss'], headers=HEADERS, timeout=20)
            if resp.status_code != 200:
                print(f"   ⚠️ Siteye erişilemedi: {resp.status_code}")
                continue

            feed = feedparser.parse(resp.content)
            
            if not feed.entries:
                print("   ⚠️ RSS Boş döndü!")
                continue
            
            # Sitenin EN YENİ haberini al (Sadece 1. sıradaki)
            # Neden? Çünkü sürekli çalışacağı için en üsttekini alması yeterli.
            # Eski haberleri tekrar atmamak için basit bir mantık.
            entry = feed.entries[0]
            
            # Haber zaten hafızada mı? (GitHub Actions her çalıştığında bu sıfırlanır,
            # ama aynı çalışma döngüsü içinde tekrarı önler)
            if entry.link in SENT_LINKS:
                continue

            print(f"   👉 İnceleniyor: {entry.title}")
            
            # Detayları Çek
            img_url, full_text = get_news_details(entry.link)
            
            if not full_text:
                full_text = entry.get('summary', 'Detaylara ulaşılamadı.')

            # Telegram'a Gönder
            if send_telegram(entry.title, full_text, img_url, site['name']):
                print("      ✅ Kanala Gönderildi.")
                SENT_LINKS.add(entry.link)
                time.sleep(5) # Spam önleme
            else:
                print("      ⚠️ Gönderilemedi.")

        except Exception as e:
            print(f"   ❌ {site['name']} Kritik Hata: {e}")

if __name__ == "__main__":
    main()
