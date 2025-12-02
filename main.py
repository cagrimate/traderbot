import os
import json
import time
import ccxt
import google.generativeai as genai
from dotenv import load_dotenv
import data_feed 

# --- KULLANICI AYARLARI (WOLF v3.1 - NET HEDEF MODU) ---
ISLEM_BASINA_YATIRIM = 20   # Her işlem için 20 Dolar
MAX_ACIK_ISLEM_SAYISI = 4   # Maksimum işlem sayısı
# --- BURASI SENİN İSTEDİĞİN AYARLAR ---
KAR_HEDEFI_YUZDE = 0.03     # %3 Kar görünce kapat (Otomatik)
ZARAR_STOP_YUZDE = 0.02     # %2 Zarar görünce kapat (Otomatik)
# -----------------------------------------------

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
binance_api = os.getenv("BINANCE_API_KEY")
binance_secret = os.getenv("BINANCE_SECRET_KEY")

SAHTE_ISLEM_MODU = False 

# --- BAĞLANTILAR ---
genai.configure(api_key=api_key)

print("🌍 Binance Futures Testnet (WOLF v3.1) Başlatılıyor...")

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
    Sen 'Wolf' kod adlı, hızlı sonuç alan bir 'Scalper' tradersın.
    Görevin: Küçük ve hızlı fiyat hareketlerini yakalamak.
    Felsefen: "Vur ve Kaç". %3 karı görünce affetme.
    
    ÇIKTI FORMATI (Sadece JSON): 
    [{"symbol": "BTC/USDT", "islem": "LONG", "sebep": "RSI uygun, trend yukarı."}]

    KURALLAR (SCALPER):
    1. VOLATİLİTE: ATR Yüzdesi %0.5 altındaysa İŞLEM AÇMA (Çok yavaş).
    
    2. LONG FIRSATI:
       - (RSI < 35) -> AL (Dip Tepkisi).
       - (Trend YUKSELIŞ ve RSI 40-60 arası) -> AL (Trend Devamı).
       
    3. SHORT FIRSATI:
       - (RSI > 65) -> SAT (Tepe Tepkisi).
       - (Trend DUSUS ve RSI 40-60 arası) -> SAT (Trend Devamı).
       
    4. Kararsızsan "YOK" dön.
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

        acik_pozisyonlar_listesi = [] 
        aktif_pozisyon_objeleri = []  
        
        for pos in positions_raw:
            amt = float(pos['positionAmt'])
            if amt != 0: 
                symbol = pos['symbol']
                entry_price = float(pos['entryPrice'])
                pnl = float(pos['unRealizedProfit'])
                yon = "LONG 🟢" if amt > 0 else "SHORT 🔴"
                
                acik_pozisyonlar_listesi.append(symbol.split(':')[0])
                aktif_pozisyon_objeleri.append({
                    'symbol': symbol,
                    'amt': amt,
                    'pnl': pnl,
                    'entry': entry_price
                })

                print(f"{symbol:<15} {yon:<8} {entry_price:<10.4f} {pnl:<10.4f}")

        if not aktif_pozisyon_objeleri:
            print("💤 Açık pozisyon yok. Nakitteyiz.")
        
        print("-" * 60)
        dolu_oran = len(aktif_pozisyon_objeleri)
        print(f"📊 Doluluk Oranı: {dolu_oran} / {MAX_ACIK_ISLEM_SAYISI} İşlem")
        print("=" * 60 + "\n")
        
        return acik_pozisyonlar_listesi, aktif_pozisyon_objeleri
        
    except Exception as e:
        print(f"⚠️ Cüzdan Hatası: {e}") 
        return [], []

def kar_supurucu(aktif_pozisyonlar):
    """
    Yedek Paraşüt: Hedef kârı geçmiş ama kapanmamış pozisyonları manuel kapatır.
    """
    if not aktif_pozisyonlar: return

    print("🧹 KAR SÜPÜRÜCÜ DEVREDE: Açık işlemler kontrol ediliyor...")
    
    # Hedef kazanç: %3 (Örn: 20$ * 0.03 = 0.6$)
    hedef_kazanc_usd = ISLEM_BASINA_YATIRIM * KAR_HEDEFI_YUZDE
    
    for pos in aktif_pozisyonlar:
        pnl = pos['pnl']
        symbol = pos['symbol']
        amt = pos['amt']
        
        # Eğer kar hedefe ulaştıysa (veya geçtiyse) kapat.
        if pnl >= hedef_kazanc_usd:
            print(f"🤑 FIRSAT YAKALANDI! {symbol} Kârda ({pnl:.2f} $). Hedef: {hedef_kazanc_usd:.2f}$. KAPATILIYOR!")
            try:
                side = 'SELL' if amt > 0 else 'BUY'
                params = {
                    'symbol': symbol, 'side': side, 'type': 'MARKET',
                    'quantity': abs(amt), 'reduceOnly': True, 'recvWindow': 60000
                }
                exchange.fapiPrivatePostOrder(params)
                print(f"✅ {symbol} BAŞARIYLA SÜPÜRÜLDÜ.")
            except Exception as e:
                print(f"❌ Kapatma Hatası ({symbol}): {e}")
        else:
            print(f"⏳ {symbol} izleniyor. PNL: {pnl:.2f}$ / Hedef: {hedef_kazanc_usd:.2f}$")
    print("-" * 60 + "\n")

def emir_gonder_tp_sl(symbol, islem, giris_fiyati):
    global kullanilabilir_bakiye
    
    if kullanilabilir_bakiye < ISLEM_BASINA_YATIRIM:
        print(f"❌ Yetersiz Bakiye! Gereken: {ISLEM_BASINA_YATIRIM}, Olan: {kullanilabilir_bakiye:.2f}")
        return False

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
    
    # --- 1. ANA İŞLEMİ AÇ ---
    try:
        params = {
            'symbol': symbol_clean, 'side': side, 'type': 'MARKET',
            'quantity': amount, 'recvWindow': 60000 
        }
        order = exchange.fapiPrivatePostOrder(params)
        print(f"   ✅ ANA POZİSYON AÇILDI! (ID: {order['orderId']})")
        kullanilabilir_bakiye -= ISLEM_BASINA_YATIRIM
        
    except Exception as e:
        print(f"   ❌ ANA İŞLEM HATASI: {e}")
        return False 

    # --- 2. STOP VE KAR AL EMİRLERİNİ KUR ---
    try:
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

        # TP Emri (Binance'e: Fiyat buraya gelirse KAR AL)
        tp_params = {
            'symbol': symbol_clean, 
            'side': kapatma_yonu, 
            'type': 'TAKE_PROFIT_MARKET',
            'stopPrice': tp_fiyat, 
            'closePosition': 'true',
            'workingType': 'CONTRACT_PRICE', 
            'recvWindow': 60000
        }
        exchange.fapiPrivatePostOrder(tp_params)
        print(f"   🎯 HEDEF KURULDU (TP): {tp_fiyat} (Fiyat buraya gelince +{tahmini_kazanc:.2f}$ alıp kapanacak)")

        # SL Emri (Binance'e: Fiyat buraya gelirse ZARARI DURDUR)
        sl_params = {
            'symbol': symbol_clean, 
            'side': kapatma_yonu, 
            'type': 'STOP_MARKET',
            'stopPrice': sl_fiyat, 
            'closePosition': 'true', 
            'workingType': 'CONTRACT_PRICE', 
            'recvWindow': 60000
        }
        exchange.fapiPrivatePostOrder(sl_params)
        print(f"   🛡️ STOP KURULDU (SL) : {sl_fiyat} (Fiyat buraya gelince -{tahmini_kayip:.2f}$ zararla kapanacak)")
        
    except Exception as e:
        print(f"   ⚠️ TP/SL GİRİLEMEDİ (Manuel ekle): {e}")

    return True

def botu_calistir():
    saati_esitle()
    
    # Cüzdanı çek
    acik_coin_isimleri, acik_pozisyon_objeleri = kar_zarar_raporu()
    
    # 1. KAR SÜPÜRÜCÜ (Açık işlemleri kontrol et)
    kar_supurucu(acik_pozisyon_objeleri)

    if len(acik_coin_isimleri) >= MAX_ACIK_ISLEM_SAYISI:
        print(f"🛑 KOTA BAŞLANGIÇTA DOLU! ({len(acik_coin_isimleri)}/{MAX_ACIK_ISLEM_SAYISI})")
        return 
    
    print(f"🐺 WOLF PİYASAYI KOKLUYOR... ({time.strftime('%H:%M:%S')})")
    
    piyasa_verileri = data_feed.piyasayi_tara()
    if not piyasa_verileri: return

    analiz_edilecekler = []
    
    for coin in piyasa_verileri:
        coin_temiz_ad = coin['symbol'].split(':')[0].replace('/', '')
        
        rsi_degeri = coin.get('rsi') 
        if rsi_degeri is None or rsi_degeri == 0: continue 

        zaten_var = False
        for acik in acik_coin_isimleri:
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
                if len(acik_coin_isimleri) >= MAX_ACIK_ISLEM_SAYISI:
                    print(f"⚠️ İŞLEM KOTASI DOLDU! Yeni işlem açılmayacak.")
                    break

                symbol = karar['symbol']
                islem = karar['islem']
                sebep = karar['sebep']
                
                print("🔹" * 20)
                print(f"📌 SEMBOL : {symbol}")
                print(f"🤖 KARAR  : {islem}")
                print(f"📝 SEBEP  : {sebep}")

                if islem in ["LONG", "SHORT"]:
                    ilgili_veri = next((item for item in piyasa_verileri if item["symbol"].split(':')[0] == symbol.split(':')[0]), None)
                    fiyat = ilgili_veri['fiyat'] if ilgili_veri else 0

                    if fiyat > 0:
                        gercek_sembol = ilgili_veri['symbol'] 
                        basarili = emir_gonder_tp_sl(gercek_sembol, islem, fiyat)
                        
                        if basarili:
                            acik_coin_isimleri.append(symbol.split(':')[0]) 
                            time.sleep(1)
                    else:
                        print(f"   ⚠️ Fiyat verisi bulunamadı. (Aranan: {symbol})")
                
                print("🔹" * 20 + "\n")
            
        else:
            print(f"❌ JSON Format Hatası: {text_response}")

    except Exception as e:
        print(f"Analiz Hatası: {e}")

if __name__ == "__main__":
    print("🚀 GitHub Actions Tetiklendi - Wolf v3.1 İş Başında...")
    try:
        botu_calistir()
        print("🏁 Tur Başarıyla Tamamlandı.")
    except Exception as e:
        print(f"❌ Kritik Hata: {e}")
        exit(1)
