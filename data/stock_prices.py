# -*- coding: utf-8 -*-
"""
Stock Dataset Downloader for "Stocks Affected by Disasters" Project
Downloads historical NSE stock data using yfinance

Author: Data Science Project
"""

import yfinance as yf
import pandas as pd
import time

# COMPANY LIST — 20 Indian Companies (NSE)
# Format: "Company Name": ("TICKER.NS", "Sector")
companies = {
    "Reliance":       ("RELIANCE.NS",    "Oil & Gas"),
    "ONGC":           ("ONGC.NS",        "Oil & Gas"),
    "IOC":            ("IOC.NS",         "Oil & Gas"),
    "TCS":            ("TCS.NS",         "IT"),
    "Infosys":        ("INFY.NS",        "IT"),
    "Wipro":          ("WIPRO.NS",       "IT"),
    "HDFC Bank":      ("HDFCBANK.NS",    "Banking"),
    "ICICI Bank":     ("ICICIBANK.NS",   "Banking"),
    "SBI":            ("SBIN.NS",        "Banking"),
    "HUL":            ("HINDUNILVR.NS",  "FMCG"),
    "ITC":            ("ITC.NS",         "FMCG"),
    "L&T":            ("LT.NS",          "Infrastructure"),
    "Adani Ports":    ("ADANIPORTS.NS",  "Infrastructure"),
    "Maruti":         ("MARUTI.NS",      "Automobile"),
    "Tata Motors":    ("TATAMOTORS.NS",  "Automobile"),
    "Sun Pharma":     ("SUNPHARMA.NS",   "Pharma"),
    "Dr Reddy":       ("DRREDDY.NS",     "Pharma"),
    "Airtel":         ("BHARTIARTL.NS",  "Telecom"),
    "Vodafone Idea":  ("IDEA.NS",        "Telecom"),
    "Coal India":     ("COALINDIA.NS",   "Mining"),     # Added 20th company
}

all_data = []
failed = []

print("=" * 55)
print("  Downloading Stock Data (NSE) — 2000 to 2024")
print("=" * 55)

# ─────────────────────────────────────────────
# DOWNLOAD LOOP
# ─────────────────────────────────────────────
for company, (ticker, sector) in companies.items():
    print(f"\n⏳ Downloading: {company} ({ticker})...")

    try:
        # Download raw data
        raw = yf.download(
            ticker,
            start="2000-01-01",
            end="2024-01-01",
            auto_adjust=True,      # Adjusts for splits & dividends automatically
            progress=False         # Suppress yfinance progress bar
        )

        # ── FIX: yfinance may return MultiIndex columns ──
        # Flatten MultiIndex if present (happens with newer yfinance versions)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        # Check if we actually got data
        if raw.empty:
            print(f"  ⚠️  No data returned for {ticker}. Skipping.")
            failed.append(company)
            continue

        # Reset index so Date becomes a regular column
        raw.reset_index(inplace=True)

        # Select only needed columns (Close is adjusted close when auto_adjust=True)
        df = raw[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()

        # Add identifying columns
        df['Company'] = company
        df['Ticker']  = ticker        # ← ADDED: useful for merging/lookups later
        df['Sector']  = sector

        # Ensure Date is datetime
        df['Date'] = pd.to_datetime(df['Date'])

        # Round price columns to 2 decimal places
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = df[col].round(2)

        all_data.append(df)
        print(f"  ✅ {company}: {len(df)} rows downloaded "
              f"({df['Date'].min().date()} → {df['Date'].max().date()})")

    except Exception as e:
        print(f"  ❌ Failed to download {company}: {e}")
        failed.append(company)

    # Small delay to avoid hitting rate limits
    time.sleep(0.5)

# ─────────────────────────────────────────────
# COMBINE & SAVE
# ─────────────────────────────────────────────
if not all_data:
    print("\n❌ No data downloaded. Check your internet connection.")
else:
    stock_df = pd.concat(all_data, ignore_index=True)

    # Sort by Company and Date
    stock_df = stock_df.sort_values(by=['Company', 'Date']).reset_index(drop=True)

    # Reorder columns nicely
    stock_df = stock_df[['Date', 'Company', 'Ticker', 'Sector',
                          'Open', 'High', 'Low', 'Close', 'Volume']]

    # Save to CSV
    output_path = "stock_dataset.csv"
    stock_df.to_csv(output_path, index=False)

    print("\n" + "=" * 55)
    print(f"  ✅ Stock dataset saved to: {output_path}")
    print(f"  📊 Total rows     : {len(stock_df):,}")
    print(f"  🏢 Companies      : {stock_df['Company'].nunique()}")
    print(f"  📅 Date range     : {stock_df['Date'].min().date()} → {stock_df['Date'].max().date()}")
    if failed:
        print(f"  ⚠️  Failed tickers: {', '.join(failed)}")
    print("=" * 55)