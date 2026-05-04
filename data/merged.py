# -*- coding: utf-8 -*-
"""
Created on Tue Apr  7 01:45:45 2026

@author: Shree
"""

import pandas as pd
import re


# LOAD DATA
stock_df = pd.read_csv("stock_dataset.csv")
disaster_df = pd.read_csv("cleaned_disaster_data.csv")

# CLEAN STOCK DATA
stock_df['Date'] = pd.to_datetime(stock_df['Date'], errors='coerce')
stock_df = stock_df.dropna(subset=['Date'])


# CLEAN DISASTER DATA (CREATE FULL DATE)
def extract_date(row):
    year = row["Year"]
    date_str = str(row["Date"]).strip()

    try:
        full_date = pd.to_datetime(f"{date_str}-{int(year)}", errors='coerce')

        if pd.isna(full_date):
            match = re.search(r"([A-Za-z]+)[^\d]*(\d{1,2})", date_str)
            if match:
                month, day = match.groups()
                full_date = pd.to_datetime(f"{day} {month} {int(year)}", errors='coerce')

        return full_date
    except:
        return None

disaster_df["Full_Date"] = disaster_df.apply(extract_date, axis=1)

# Clean columns
disaster_df["Type"] = disaster_df["Type"].str.lower().str.strip()
disaster_df["Event"] = disaster_df["Event"].str.strip()
disaster_df["Country"] = disaster_df["Country"].str.strip()

# Remove invalid rows
disaster_df = disaster_df.dropna(subset=["Full_Date"])

# Rename columns
disaster_df.rename(columns={
    "Event": "Disaster",
    "Country": "Location"
}, inplace=True)

# MERGE LOGIC (CORE)
final_data = []

print("🚀 Processing merge...")

for _, d in disaster_df.iterrows():
    disaster_date = d['Full_Date']

    for company in stock_df['Company'].unique():
        company_data = stock_df[stock_df['Company'] == company]

        # Window (±5 days)
        window = company_data[
            (company_data['Date'] >= disaster_date - pd.Timedelta(days=5)) &
            (company_data['Date'] <= disaster_date + pd.Timedelta(days=5))
        ].sort_values('Date')

        if len(window) > 1:
            before = window.iloc[0]['Close']
            after = window.iloc[-1]['Close']

            change = ((after - before) / before) * 100

            # Impact classification
            if change < -5:
                impact = "High"
            elif change < -2:
                impact = "Medium"
            else:
                impact = "Low"

            final_data.append({
                "Company": company,
                "Sector": window.iloc[0]['Sector'],
                "Disaster": d['Disaster'],
                "Type": d['Type'],
                "Location": d['Location'],
                "Disaster_Date": disaster_date,
                "Before_Price": round(before, 2),
                "After_Price": round(after, 2),
                "Change (%)": round(change, 2),
                "Impact": impact
            })


# FINAL DATASET
final_df = pd.DataFrame(final_data)

# Sort nicely
final_df = final_df.sort_values(by=["Company", "Disaster_Date"])

# Save
final_df.to_csv("final_optimized_dataset.csv", index=False)

print("✅ FINAL OPTIMIZED DATASET CREATED!")