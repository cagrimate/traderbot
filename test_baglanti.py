import os
import ccxt
from dotenv import load_dotenv

# 1. Ayarları Yükle
load_dotenv(override=True)

# .strip() komutu görünmez boşlukları siler
api_key = os.getenv("BINANCE_API_KEY", "").strip()
secret_key = os.getenv("BINANCE_SECRET_KEY", "").strip()

print(f"\n🔍 DENETİM BAŞLIYOR...")
print(f"🔑 Denenen API Key: {api_key[:5]}...{api_key[-5:] if len(api_key)>5 else ''}")
print(f"📏 Key Uzunluğu: {len(api_key)} karakter (Normalde 64 olmalı)")

if len(api_key) < 10:
    print("❌ HATA: API Key çok kısa veya okunamadı!")
    exit()

# --- TEST 1: GERÇEK BINANCE ---
print("\n🌍 TEST 1: GERÇEK BINANCE (Mainnet) Deneniyor...")
try:
    exchange_real = ccxt.binance({
        'apiKey': api_key,
        'secret': secret_key,
        'options': {'defaultType': 'future'}
    })
    balance = exchange_real.fetch_balance()
    print("✅ BAŞARILI! -> Bu bir GERÇEK Binance anahtarı.")
    print(f"💰 Bakiye: {balance['total'].get('USDT', 0)} USDT")
except Exception as e:
    print(f"❌ Gerçek Binance Başarısız: {str(e)}")

# --- TEST 2: TESTNET (Sanal) ---
print("\n🧪 TEST 2: BINANCE TESTNET (Futures) Deneniyor...")
try:
    exchange_test = ccxt.binance({
        'apiKey': api_key,
        'secret': secret_key,
        'options': {'defaultType': 'future'}
    })
    exchange_test.set_sandbox_mode(True) # Test modu aç
    balance = exchange_test.fetch_balance()
    print("✅ BAŞARILI! -> Bu bir TESTNET anahtarı.")
    print(f"💰 Sanal Bakiye: {balance['total'].get('USDT', 0)} USDT")
except Exception as e:
    print(f"❌ Testnet Başarısız: {str(e)}")

print("\n--- SONUÇ ---")