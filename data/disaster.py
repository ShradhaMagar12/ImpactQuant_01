import pandas as pd
import requests
from io import StringIO

# --------------------------------------------
# Recreate cleaned_disaster_data.csv
# Same style as your OLD version
# --------------------------------------------

url = "https://en.wikipedia.org/wiki/List_of_natural_disasters_by_death_toll"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers)

# Read tables safely
tables = pd.read_html(StringIO(response.text))

# Select same table
df = tables[3]

# Rename columns
df.columns = ["Year", "Death_Toll", "Event", "Country", "Type", "Date"]

# --------------------------------------------
# Keep same year rows as old file
# --------------------------------------------
df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
df = df.dropna(subset=["Year"])
df["Year"] = df["Year"].astype(int)

df = df[(df["Year"] >= 2001) & (df["Year"] <= 2026)]

# --------------------------------------------
# CLEAN TO MATCH OLD FILE STYLE
# --------------------------------------------

# Remove weird symbols
for col in ["Death_Toll", "Event", "Country", "Type", "Date"]:
    df[col] = df[col].astype(str)

    df[col] = df[col].str.replace("Â", "", regex=False)
    df[col] = df[col].str.replace("â€“", " ", regex=False)
    df[col] = df[col].str.replace("–", " ", regex=False)
    df[col] = df[col].str.replace("+", "", regex=False)
    df[col] = df[col].str.replace("[", "", regex=False)
    df[col] = df[col].str.replace("]", "", regex=False)
    df[col] = df[col].str.strip()

# Type column lower case like old file
df["Type"] = df["Type"].str.lower()

# Remove duplicate rows
df = df.drop_duplicates()

# Reset index
df = df.reset_index(drop=True)


df.to_csv(
    "cleaned_disaster_data.csv",
    index=False,
    encoding="utf-8-sig"
)

print("Old style cleaned_disaster_data.csv recreated successfully ✅")
print("Total Rows:", len(df))