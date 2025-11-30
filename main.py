import os
import json
import time
import ccxt
import google.generativeai as genai
from dotenv import load_dotenv
import data_feed 

# --- KULLANICI AYARLARI (WOLF AGRESİF MOD 🐺) ---
ISLEM_BASINA_YATIRIM = 20   # Her işlem için 20 Dolar
MAX_ACIK_ISLEM_SAYISI = 4   # Maksimum işlem sayısı
KAR_HEDEFI_YUZDE = 0.08     # %8 Kâr Hedefi
ZARAR_STOP_YUZDE = 0.05     # %5 Zarar Kes
# -----------------------------------------------

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
binance_api = os.getenv("BINANCE_API_KEY")
binance_secret = os.getenv("BINANCE_SECRET_KEY")

SAHTE_ISLEM_MODU = False 

# --- BAĞLANTILAR ---
genai.configure(api_key=api_key)

print("🌍 Binance Futures Testnet (WOLF v2.2 - Final Fix) Başlatılıyor...")

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
    'dapiPublic': 'https://testnet.binancefuture.com/dapi/v1',
    'dapiPrivate': 'https://testnet.binancefuture.com/dapi/v1',
    'dapiPrivateV2': 'https://testnet.binancefuture.com/dapi/v2',
}

# --- ZAMAN MAKİNESİ (Sync) ---
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

# --- WOLF'UN BEYNİ (STRATEJİ) ---
MODEL_ADI = "models/gemini-2.0-flash" 
model = genai.GenerativeModel(
    model_name=MODEL_ADI,
    generation_config={"temperature": 0.6},
    system_instruction="""
    Sen 'Wolf' kod adlı fırsatçı ve trend takipçisi bir kripto tradersın.
    Görevin: Verilen teknik verileri analiz edip karlılık ihtimali olan işlemleri seçmek.
    Korkak olma, trend yönündeysen tetiği çek.
    
    ÇIKTI FORMATI (Sadece JSON): 
    [{"symbol": "BTC/USDT", "islem": "LONG", "sebep": "Momentum yukarı, RSI uygun."}]

    KURALLAR (ÖNEMLİ):
    1. VOLATİLİTE KONTROLÜ: 'ATR Yüzdesi' %0.5'in altındaysa ASLA işlem açma (Ölü coin).
    
    2. LONG STRATEJİSİ:
       - (Trend YUKSELIŞ ve RSI < 70) -> AL (Trende katıl).
       - (RSI < 35) -> AL (Dip tepkisi).
       
    3. SHORT STRATEJİSİ:
       - (Trend DUSUS ve RSI > 30) -> SAT (Trende katıl).
       - (RSI > 65) -> SAT (Tepeden dönüş).
       
    4. Kararsızsan veya sinyaller çelişiyorsa "YOK" dön.
    """
)

kullanilabilir_bakiye = 0 

def kar_zarar_raporu():
    global kullanilabilir_bakiye 
    print("\n" + "="*60)
    print("💰 --- WOLF CÜZDAN DURUMU --- 💰".center(60))
    print("="*60)
    try:
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
        dolu_oran = len(acik_pozisyonlar)
        print(f"📊 Doluluk Oranı: {dolu_oran} / {MAX_ACIK_ISLEM_SAYISI} İşlem")
        print("=" * 60 + "\n")
        
        return acik_pozisyonlar
        
    except Exception as e:
        print(f"⚠️ Cüzdan Hatası: {e}") 
        return []

def emir_gonder_tp_sl(symbol, islem, giris_fiyati):
    global kullanilabilir_bakiye
    try:
        if kullanilabilir_bakiye < ISLEM_BASINA_YATIRIM:
            print(f"❌ Yetersiz Bakiye! Gereken: {ISLEM_BASINA_YATIRIM}, Olan: {kullanilabilir_bakiye:.2f}")
            return False

        # Sembolü temizle (Örn: BTC/USDT:USDT -> BTCUSDT)
        symbol_clean = symbol.split(':')[0].replace('/', '')
        amount = int(ISLEM_BASINA_YATIRIM / giris_fiyati) 

        tahmini_kazanc = ISLEM_BASINA_YATIRIM * KAR_HEDEFI_YUZDE
        tahmini_kayip = ISLEM_BASINA_YATIRIM * ZARAR_STOP_YUZDE

        if SAHTE_ISLEM_MODU:
            print(f"🛑 [SİMÜLASYON] {symbol} {islem} (Bakiye düşmedi)")
            return True

        print(f"\n   🎲 İŞLEM BAŞLIYOR ({ISLEM_BASINA_YATIRIM} $)")
        print(f"   ⏳ {symbol_clean} için {islem} emri giriliyor...")
        
        side = 'BUY' if islem == 'LONG' else 'SELL'
        
        # 1. ANA İŞLEMİ AÇ
        params = {
            'symbol': symbol_clean, 'side': side, 'type': 'MARKET',
            'quantity': amount, 'recvWindow': 60000 
        }
        order = exchange.fapiPrivatePostOrder(params)
        print(f"   ✅ ANA POZİSYON AÇILDI! (ID: {order['orderId']})")

        kullanilabilir_bakiye -= ISLEM_BASINA_YATIRIM

        # TP ve SL Fiyat Hesaplama
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

        # 2. TAKE PROFIT (KAR AL) - Reduce Only
        tp_params = {
            'symbol': symbol_clean, 
            'side': kapatma_yonu, 
            'type': 'TAKE_PROFIT_MARKET',
            'stopPrice': tp_fiyat, 
            'closePosition': 'true', 
            'recvWindow': 60000,
            'reduceOnly': True 
        }
        exchange.fapiPrivatePostOrder(tp_params)
        print(f"   🎯 HEDEF (TP): {tp_fiyat}  (Kazanç: +{tahmini_kazanc:.2f} $)")

        # 3. STOP LOSS (ZARAR DURDUR) - Reduce Only
        sl_params = {
            'symbol': symbol_clean, 
            'side': kapatma_yonu, 
            'type': 'STOP_MARKET',
            'stopPrice': sl_fiyat, 
            'closePosition': 'true', 
            'recvWindow': 60000,
            'reduceOnly': True 
        }
        exchange.fapiPrivatePostOrder(sl_params)
        print(f"   🛡️ STOP (SL) : {sl_fiyat}  (Kayıp : -{tahmini_kayip:.2f} $)")
        
        return True
            
    except Exception as e:
        print(f"   ❌ EMİR HATASI: {e}")
        return False

def botu_calistir():
    saati_esitle()
    
    acik_coinler = kar_zarar_raporu()
    if acik_coinler is None: acik_coinler = []
    
    su_anki_islem_sayisi = len(acik_coinler)
    if su_anki_islem_sayisi >= MAX_ACIK_ISLEM_SAYISI:
        print(f"🛑 KOTA TAMAMEN DOLU! ({su_anki_islem_sayisi}/{MAX_ACIK_ISLEM_SAYISI})")
        return 
    
    print(f"🐺 WOLF PİYASAYI KOKLUYOR... ({time.strftime('%H:%M:%S')})")
    
    piyasa_verileri = data_feed.piyasayi_tara()
    if not piyasa_verileri: return

    analiz_edilecekler = []
    
    for coin in piyasa_verileri:
        coin_temiz_ad = coin['symbol'].split(':')[0].replace('/', '')
        
        # Hatalı veri veya elde olan coin kontrolü
        rsi_degeri = coin.get('rsi') 
        if rsi_degeri is None or rsi_degeri == 0: continue 

        zaten_var = False
        for acik in acik_coinler:
            if coin_temiz_ad == acik:
                zaten_var = True
                break
        
        if not zaten_var:
            analiz_edilecekler.append(coin)
            
    if not analiz_edilecekler:
        print("\n🤷‍♂️ Liste boş veya uygun aday yok.")
        return

    # --- GEMINI PROMPT ---
    prompt = "Aşağıdaki teknik verileri analiz et. Özellikle 'ATR Yüzdesi'ne dikkat et (%0.5 altı ölüdür). Çıktı saf JSON olmalı.\n"
    for coin in analiz_edilecekler:
        atr_p = coin.get('atr_yuzde', 0)
        
        prompt += f"""
        COIN: {coin['symbol']}
        Fiyat: {coin['fiyat']}
        RSI (14): {coin['rsi']:.1f}
        TREND: {coin['trend']} 
        MACD: {coin['macd']}
        ATR Yüzdesi (Oynaklık): %{atr_p:.2f}
        Destek: {coin['destek']}
        Direnç: {coin['direnc']}
        -------------------
        """
    
    print(f"\n🧠 {len(analiz_edilecekler)} Coin Analiz Ediliyor... Bekleyin...\n")

    try:
        response = model.generate_content(prompt)
        text_response = response.text
        
        # --- JSON TEMİZLEME ---
        text_response = text_response.replace("```json", "").replace("```", "").strip()
        
        baslangic = text_response.find('[')
        bitis = text_response.rfind(']')
        
        if baslangic != -1 and bitis != -1:
            temiz_json = text_response[baslangic : bitis + 1]
            kararlar = json.loads(temiz_json)
            
            for karar in kararlar:
                if len(acik_coinler) >= MAX_ACIK_ISLEM_SAYISI:
                    print(f"⚠️ Kota doldu!")
                    break

                symbol = karar['symbol']
                islem = karar['islem']
                sebep = karar['sebep']
                
                print("🔹" * 20)
                print(f"📌 SEMBOL : {symbol}")
                print(f"🤖 KARAR  : {islem}")
                print(f"📝 SEBEP  : {sebep}")

                if islem in ["LONG", "SHORT"]:
                    # --- KRİTİK DÜZELTME BURADA ---
                    # Gemini'den gelen "PIPPIN/USDT" ile listedeki "PIPPIN/USDT:USDT"yi eşleştirmek için
                    # her ikisinin de sadece ilk kısmına (Split) bakıyoruz.
                    ilgili_veri = next((item for item in piyasa_verileri if
