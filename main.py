import os
import json
import time
import ccxt
import google.generativeai as genai
from dotenv import load_dotenv
import data_feed 

# --- KULLANICI AYARLARI (YÜKSEK RİSK MODU 🔥) ---
ISLEM_BASINA_YATIRIM = 10  # 10 yerine 100 Dolar basıyoruz! (Kazancı 10'a katlar)
MAX_ACIK_ISLEM_SAYISI = 5   # Aynı anda 5 işlem (Toplam 500$ risk)
BEKLEME_SURESI_DK = 40       
KAR_HEDEFI_YUZDE = 0.05   # %10 Kâr hedefle (Büyük vuruş)
ZARAR_STOP_YUZDE = 0.02    # %5 Stop (Erken patlamamak için geniş alan)
# -----------------------------------------------
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
binance_api = os.getenv("BINANCE_API_KEY")
binance_secret = os.getenv("BINANCE_SECRET_KEY")

SAHTE_ISLEM_MODU = False 

# --- BAĞLANTILAR ---
genai.configure(api_key=api_key)

print("🌍 Binance Futures Testnet (FİNAL SÜRÜM) Başlatılıyor...")

exchange = ccxt.binance({
    'apiKey': binance_api,
    'secret': binance_secret,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'future',
        'adjustForTimeDifference': False, 
    },
})

exchange.urls['api'] = {
    'fapiPublic': 'https://testnet.binancefuture.com/fapi/v1',
    'fapiPrivate': 'https://testnet.binancefuture.com/fapi/v1',
    'fapiPrivateV2': 'https://testnet.binancefuture.com/fapi/v2',
    'public': 'https://testnet.binancefuture.com/fapi/v1',
    'private': 'https://testnet.binancefuture.com/fapi/v1',
    'sapi': 'https://testnet.binancefuture.com/fapi/v1', 
}

# --- ZAMAN MAKİNESİ ---
def saati_esitle():
    try:
        server_time_req = exchange.fapiPublicGetTime()
        server_time = int(server_time_req['serverTime'])
        local_time = int(time.time() * 1000)
        time_offset = server_time - local_time
        original_milliseconds = exchange.milliseconds
        exchange.milliseconds = lambda: original_milliseconds() + time_offset
        return True
    except:
        return False

saati_esitle()

# --- WOLF'UN BEYNİ ---
MODEL_ADI = "models/gemini-2.5-pro" 
model = genai.GenerativeModel(
    model_name=MODEL_ADI,
    generation_config={"temperature": 0.6}, 
    system_instruction="""
    Sen 'Wolf' kod adlı agresif bir tradersın.
    Görevin: Volatiliteden yararlanıp işlem fırsatı çıkarmak.
    ÇIKTI FORMATI (JSON): [{"symbol": "BTC/USDT", "islem": "LONG/SHORT/YOK", "sebep": "..."}]
    KURALLAR:
    1. RSI < 35 ve Destek yakınsa -> LONG.
    2. RSI > 65 ve Direnç yakınsa -> SHORT.
    3. Trend Takibi: Fiyat destekten zıplamışsa -> LONG.
    """
)

# Global değişken
kullanilabilir_bakiye = 0 

def kar_zarar_raporu():
    global kullanilabilir_bakiye 
    
    print("\n" + "="*60)
    print("💰 --- WOLF CÜZDAN DURUMU --- 💰".center(60))
    print("="*60)
    try:
        # Bakiye Bilgisi
        account_info = exchange.fapiPrivateV2GetAccount({'recvWindow': 60000})
        toplam_varlik = float(account_info['totalMarginBalance'])
        kullanilabilir_bakiye = float(account_info['availableBalance'])
        
        print(f"💵 Toplam Varlık : {toplam_varlik:.2f} $")
        print(f"🔓 Harcanabilir  : {kullanilabilir_bakiye:.2f} USDT")
        print("-" * 60)

        positions_raw = exchange.fapiPrivateV2GetPositionRisk({'recvWindow': 60000})
        
        print(f"{'COIN':<15} {'YÖN':<8} {'GİRİŞ':<10} {'PNL ($)':<10}")
        print("-" * 60)

        acik_pozisyonlar = [] 
        aktif_pozisyon = False
        
        for pos in positions_raw:
            amt = float(pos['positionAmt'])
            if amt != 0: 
                aktif_pozisyon = True
                symbol = pos['symbol']
                acik_pozisyonlar.append(symbol) 
                entry_price = float(pos['entryPrice'])
                pnl = float(pos['unRealizedProfit'])
                yon = "LONG 🟢" if amt > 0 else "SHORT 🔴"
                print(f"{symbol:<15} {yon:<8} {entry_price:<10.4f} {pnl:<10.4f}")

        if not aktif_pozisyon:
            print("💤 Açık pozisyon yok. Nakitteyiz.")
        
        print("-" * 60)
        print(f"📊 Doluluk Oranı: {len(acik_pozisyonlar)} / {MAX_ACIK_ISLEM_SAYISI} İşlem")
        print("=" * 60 + "\n")
        
        return acik_pozisyonlar
        
    except Exception as e:
        # --- DÜZELTİLEN SATIR BURASI ---
        print(f"⚠️ Cüzdan Hatası: {e}") 
        return []

# --- EMİR GÖNDER ---
def emir_gonder_tp_sl(symbol, islem, giris_fiyati):
    global kullanilabilir_bakiye
    
    try:
        # Bakiye Yetersizse Dur
        if kullanilabilir_bakiye < ISLEM_BASINA_YATIRIM:
            print(f"❌ Yetersiz Bakiye! Gereken: {ISLEM_BASINA_YATIRIM}, Olan: {kullanilabilir_bakiye:.2f}")
            return False

        symbol_clean = symbol.split(':')[0].replace('/', '')
        amount = int(ISLEM_BASINA_YATIRIM / giris_fiyati) 

        tahmini_kazanc = ISLEM_BASINA_YATIRIM * KAR_HEDEFI_YUZDE
        tahmini_kayip = ISLEM_BASINA_YATIRIM * ZARAR_STOP_YUZDE

        if SAHTE_ISLEM_MODU:
            print(f"🛑 [SİMÜLASYON] {symbol} {islem}")
            return True

        print(f"\n   🎲 İŞLEM BAŞLIYOR ({ISLEM_BASINA_YATIRIM} $)")
        print(f"   ⏳ {symbol_clean} için {islem} emri giriliyor...")
        
        side = 'BUY' if islem == 'LONG' else 'SELL'
        
        # 1. ANA İŞLEM
        params = {
            'symbol': symbol_clean, 'side': side, 'type': 'MARKET',
            'quantity': amount, 'recvWindow': 60000 
        }
        order = exchange.fapiPrivatePostOrder(params)
        print(f"   ✅ POZİSYON AÇILDI! (ID: {order['orderId']})")

        # Sanal olarak bakiyeyi düş
        kullanilabilir_bakiye -= ISLEM_BASINA_YATIRIM

        # 2. HESAPLAMALAR
        if islem == "LONG":
            tp_fiyat = giris_fiyati * (1 + KAR_HEDEFI_YUZDE)
            sl_fiyat = giris_fiyati * (1 - ZARAR_STOP_YUZDE)
            kapatma_yonu = 'SELL'
        else: 
            tp_fiyat = giris_fiyati * (1 - KAR_HEDEFI_YUZDE)
            sl_fiyat = giris_fiyati * (1 + ZARAR_STOP_YUZDE)
            kapatma_yonu = 'BUY'

        tp_fiyat = float("{:.4f}".format(tp_fiyat))
        sl_fiyat = float("{:.4f}".format(sl_fiyat))

        # 3. TP EMRİ
        tp_params = {
            'symbol': symbol_clean, 'side': kapatma_yonu, 'type': 'TAKE_PROFIT_MARKET',
            'stopPrice': tp_fiyat, 'closePosition': 'true', 'recvWindow': 60000
        }
        exchange.fapiPrivatePostOrder(tp_params)
        print(f"   🎯 HEDEF (TP): {tp_fiyat}  (Kazanç: +{tahmini_kazanc:.2f} $)")

        # 4. SL EMRİ
        sl_params = {
            'symbol': symbol_clean, 'side': kapatma_yonu, 'type': 'STOP_MARKET',
            'stopPrice': sl_fiyat, 'closePosition': 'true', 'recvWindow': 60000
        }
        exchange.fapiPrivatePostOrder(sl_params)
        print(f"   🛡️ STOP (SL) : {sl_fiyat}  (Kayıp : -{tahmini_kayip:.2f} $)")
        return True
            
    except Exception as e:
        print(f"   ❌ HATA: {e}")
        return False

def botu_calistir():
    saati_esitle()
    acik_coinler = kar_zarar_raporu()
    if acik_coinler is None: acik_coinler = []
    
    # Kota Kontrolü
    su_anki_islem_sayisi = len(acik_coinler)
    if su_anki_islem_sayisi >= MAX_ACIK_ISLEM_SAYISI:
        print(f"🛑 KOTA DOLU! ({su_anki_islem_sayisi}/{MAX_ACIK_ISLEM_SAYISI})")
        print("   Yeni işlem açılmayacak, sadece mevcutlar izleniyor.")
        return 
    
    print(f"🐺 WOLF PİYASAYI KOKLUYOR... ({time.strftime('%H:%M:%S')})")
    
    piyasa_verileri = data_feed.piyasayi_tara()
    if not piyasa_verileri: return

    # Filtreleme (Cüzdanda olanı ele)
    analiz_edilecekler = []
    for coin in piyasa_verileri:
        coin_temiz_ad = coin['symbol'].split(':')[0].replace('/', '')
        zaten_var = False
        for acik in acik_coinler:
            if coin_temiz_ad == acik:
                zaten_var = True
                break
        if not zaten_var:
            analiz_edilecekler.append(coin)
            
    if not analiz_edilecekler:
        print("\n🤷‍♂️ Liste boş veya hepsi zaten cüzdanda.")
        return

    prompt = "Analiz et ve JSON formatında karar ver:\n"
    for coin in analiz_edilecekler:
        prompt += f"Symbol:{coin['symbol']}, Fiyat:{coin['fiyat']}, RSI:{coin['rsi']:.1f}, Destek:{coin['destek']}, Direnc:{coin['direnc']}\n"
    
    print(f"\n🧠 {len(analiz_edilecekler)} Coin Analiz Ediliyor... Bekleyin...\n")

    try:
        response = model.generate_content(prompt)
        text_response = response.text
        baslangic = text_response.find('[')
        bitis = text_response.rfind(']')
        
        if baslangic != -1 and bitis != -1:
            temiz_json = text_response[baslangic : bitis + 1]
            kararlar = json.loads(temiz_json)
            
            for karar in kararlar:
                # Döngü İçi Kota Kontrolü
                if len(acik_coinler) >= MAX_ACIK_ISLEM_SAYISI:
                    print(f"⚠️ İşlem sırasında kota doldu! Kalan analizler pas geçiliyor.")
                    break

                symbol = karar['symbol']
                islem = karar['islem']
                sebep = karar['sebep']
                
                print("🔹" * 20)
                print(f"📌 SEMBOL : {symbol}")
                print(f"🤖 KARAR  : {islem}")
                print(f"📝 SEBEP  : {sebep}")

                ilgili_veri = None
                for veri in piyasa_verileri:
                    veri_adi = veri["symbol"].split(':')[0] 
                    gemini_adi = symbol.split(':')[0]
                    if veri_adi == gemini_adi:
                        ilgili_veri = veri
                        break
                
                fiyat = ilgili_veri['fiyat'] if ilgili_veri else 0

                if islem in ["LONG", "SHORT"]:
                    if fiyat > 0:
                        basarili = emir_gonder_tp_sl(symbol, islem, fiyat)
                        if basarili:
                            acik_coinler.append(symbol.split(':')[0]) 
                    else:
                        print("   ⚠️ Fiyat verisi eşleşmedi.")
                
                print("🔹" * 20 + "\n")
            
        else:
            print("❌ JSON Alınamadı.")

    except Exception as e:
        print(f"Analiz Hatası: {e}")

if __name__ == "__main__":
    while True:
        try:
            botu_calistir()
            print(f"💤 Wolf {BEKLEME_SURESI_DK} dakika dinleniyor... (Durdurmak için CTRL+C)")
            time.sleep(BEKLEME_SURESI_DK * 60) 
        except KeyboardInterrupt:
            print("\n🛑 Bot durduruldu.")
            break
        except Exception as e:
            print(f"\n❌ Hata: {e}")
            time.sleep(60)