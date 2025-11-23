import os
import time
import ccxt
from dotenv import load_dotenv

# --- AYARLAR ---
load_dotenv()
binance_api = os.getenv("BINANCE_API_KEY")
binance_secret = os.getenv("BINANCE_SECRET_KEY")

print("🚨 ACİL DURUM PROTOKOLÜ BAŞLATILIYOR... 🚨")

# Bağlantı (Testnet - Raw Mod)
exchange = ccxt.binance({
    'apiKey': binance_api,
    'secret': binance_secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'adjustForTimeDifference': False, 
    },
})

# Testnet URL Ayarları
exchange.urls['api'] = {
    'fapiPublic': 'https://testnet.binancefuture.com/fapi/v1',
    'fapiPrivate': 'https://testnet.binancefuture.com/fapi/v1',
    'fapiPrivateV2': 'https://testnet.binancefuture.com/fapi/v2',
    'public': 'https://testnet.binancefuture.com/fapi/v1',
    'private': 'https://testnet.binancefuture.com/fapi/v1',
    'sapi': 'https://testnet.binancefuture.com/fapi/v1',
}

# Zaman Eşitleme
try:
    server_time = exchange.fapiPublicGetTime()['serverTime']
    offset = int(server_time) - int(time.time() * 1000)
    original_milliseconds = exchange.milliseconds
    exchange.milliseconds = lambda: original_milliseconds() + offset
    print("✅ Zaman senkronize edildi.")
except:
    pass

def her_seyi_kapat():
    try:
        # ---------------------------------------------------------
        # ADIM 1: AÇIK EMİRLERİ BUL VE İPTAL ET
        # ---------------------------------------------------------
        print("\n1️⃣ AÇIK EMİRLER TARANIYOR...")
        
        # Önce tüm açık emirleri çekiyoruz
        acik_emirler = exchange.fapiPrivateGetOpenOrders({'recvWindow': 60000})
        
        # Hangi coinlerde emir var? (Örn: ['BTCUSDT', 'ETHUSDT'])
        semboller = set([emir['symbol'] for emir in acik_emirler])
        
        if not semboller:
            print("💤 İptal edilecek açık emir yok.")
        else:
            for symbol in semboller:
                print(f"   🗑️ {symbol} emirleri iptal ediliyor...")
                try:
                    # O semboldeki tüm emirleri sil
                    exchange.fapiPrivateDeleteAllOpenOrders({
                        'symbol': symbol, 
                        'recvWindow': 60000
                    })
                    print(f"   ✅ {symbol} temizlendi.")
                except Exception as e:
                    print(f"   ❌ {symbol} hatası: {e}")

        # ---------------------------------------------------------
        # ADIM 2: AÇIK POZİSYONLARI BUL VE KAPAT
        # ---------------------------------------------------------
        print("\n2️⃣ AÇIK POZİSYONLAR KAPATILIYOR...")
        positions = exchange.fapiPrivateV2GetPositionRisk({'recvWindow': 60000})
        
        islem_var_mi = False
        for pos in positions:
            amt = float(pos['positionAmt'])
            symbol = pos['symbol']
            
            if amt != 0:
                islem_var_mi = True
                side = 'SELL' if amt > 0 else 'BUY' # Long ise Sat, Short ise Al
                
                print(f"   🔻 {symbol} KAPATILIYOR ({amt} adet)...")
                
                params = {
                    'symbol': symbol,
                    'side': side,
                    'type': 'MARKET',
                    'quantity': abs(amt), # Miktarın mutlak değeri
                    'reduceOnly': 'true', # Sadece pozisyon kapat
                    'recvWindow': 60000
                }
                try:
                    exchange.fapiPrivatePostOrder(params)
                    print(f"   ✅ {symbol} KAPATILDI.")
                except Exception as e:
                    print(f"   ❌ {symbol} kapatılamadı: {e}")
        
        if not islem_var_mi:
            print("💤 Zaten açık pozisyon yok.")
            
        print("\n🏁 --- SİSTEM GÜVENLİ, TAMAMEN NAKİTTESİN --- 🏁")

    except Exception as e:
        print(f"❌ GENEL HATA: {e}")

if __name__ == "__main__":
    confirm = input("!!! DİKKAT !!! TÜM İŞLEMLER KAPATILACAK. ONAYLIYOR MUSUN? (E/H): ")
    if confirm.lower() == 'e':
        her_seyi_kapat()
    else:
        print("İşlem iptal edildi.")