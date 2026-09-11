"""Generate a realistic US housing-sales dataset for the Spark tutorial.

Produces two CSV files under data/:
  - housing_sales.csv   (~50,000 rows) one row per home sale
  - city_stats.csv      (~30 rows)     per-city median income + population (for join demos)

The data is synthetic but calibrated to plausible US market numbers so
aggregations and window functions produce sensible-looking results.
A fixed random seed makes the output reproducible.

Run:  .venv/Scripts/python.exe generate_data.py
"""
import csv
import os
import random
from datetime import date, timedelta

random.seed(42)

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT_DIR, exist_ok=True)

# city, state, base price ($/sqft), median household income, population
CITIES = [
    ("Austin",        "TX", 310, 86000, 974000),
    ("Dallas",        "TX", 245, 63000, 1300000),
    ("Houston",       "TX", 210, 60000, 2300000),
    ("San Antonio",   "TX", 185, 58000, 1450000),
    ("Seattle",       "WA", 560, 110000, 750000),
    ("Spokane",       "WA", 250, 62000, 230000),
    ("San Francisco", "CA", 980, 126000, 815000),
    ("Los Angeles",   "CA", 620, 76000, 3900000),
    ("San Diego",     "CA", 640, 89000, 1380000),
    ("Sacramento",    "CA", 380, 78000, 525000),
    ("Denver",        "CO", 420, 85000, 715000),
    ("Boulder",       "CO", 610, 94000, 105000),
    ("Phoenix",       "AZ", 290, 72000, 1650000),
    ("Tucson",        "AZ", 220, 55000, 545000),
    ("Miami",         "FL", 470, 54000, 450000),
    ("Orlando",       "FL", 280, 61000, 315000),
    ("Tampa",         "FL", 300, 62000, 400000),
    ("Atlanta",       "GA", 290, 74000, 500000),
    ("Nashville",     "TN", 320, 70000, 690000),
    ("Charlotte",     "NC", 270, 70000, 900000),
    ("Raleigh",       "NC", 280, 78000, 470000),
    ("Chicago",       "IL", 260, 71000, 2700000),
    ("New York",      "NY", 780, 76000, 8300000),
    ("Boston",        "MA", 690, 89000, 650000),
    ("Philadelphia",  "PA", 230, 57000, 1580000),
    ("Portland",      "OR", 400, 79000, 640000),
    ("Las Vegas",     "NV", 270, 66000, 660000),
    ("Salt Lake City","UT", 340, 81000, 210000),
    ("Minneapolis",   "MN", 250, 76000, 430000),
    ("Columbus",      "OH", 210, 62000, 910000),
]

PROPERTY_TYPES = [
    ("Single Family", 0.62),
    ("Condo",         0.18),
    ("Townhouse",     0.14),
    ("Multi-Family",  0.06),
]

def pick_property_type():
    r = random.random()
    acc = 0.0
    for name, w in PROPERTY_TYPES:
        acc += w
        if r < acc:
            return name
    return PROPERTY_TYPES[-1][0]

START = date(2021, 1, 1)
DAYS = (date(2024, 12, 31) - START).days

rows = []
for i in range(1, 50_001):
    city, state, ppsf, _income, _pop = random.choice(CITIES)
    ptype = pick_property_type()

    beds = random.choices([1, 2, 3, 4, 5, 6], weights=[6, 18, 34, 28, 11, 3])[0]
    baths = max(1.0, round(beds * random.uniform(0.5, 1.0) * 2) / 2)
    sqft = int(random.gauss(650 + beds * 480, 260))
    sqft = max(400, min(sqft, 7500))
    if ptype == "Condo":
        sqft = int(sqft * 0.75)
    lot_sqft = 0 if ptype == "Condo" else int(abs(random.gauss(sqft * 3.2, 2200)))

    year_built = random.choices(
        [random.randint(1900, 1959), random.randint(1960, 1989),
         random.randint(1990, 2009), random.randint(2010, 2024)],
        weights=[10, 28, 34, 28])[0]

    sale_date = START + timedelta(days=random.randint(0, DAYS))
    # mild market appreciation over the window + age discount + noise
    year_factor = 1.0 + 0.05 * (sale_date.year - 2021)
    age_factor = 1.0 - min(0.25, (2024 - year_built) * 0.002)
    noise = random.uniform(0.80, 1.25)
    price = int(sqft * ppsf * year_factor * age_factor * noise)
    price = max(60_000, price)

    hoa_fee = random.choice([0, 0, 0, 50, 120, 250, 400]) if ptype != "Condo" \
        else random.randint(150, 900)

    # sprinkle realistic nulls for the data-cleaning section
    garage = random.choice([0, 1, 2, 2, 3, None])
    year_renovated = random.choice([None] * 8 + [random.randint(max(year_built, 1980), 2024)] * 2)

    rows.append([
        i,                                   # sale_id
        f"{random.randint(100, 99999)} {random.choice(['Oak', 'Maple', 'Cedar', 'Main', 'Lake', 'Hill', 'Park', 'River'])} "
        f"{random.choice(['St', 'Ave', 'Dr', 'Ln', 'Blvd', 'Ct'])}",
        city, state, ptype, price, beds, baths, sqft, lot_sqft,
        year_built,
        year_renovated if year_renovated is not None else "",
        garage if garage is not None else "",
        hoa_fee,
        sale_date.isoformat(),
    ])

sales_path = os.path.join(OUT_DIR, "housing_sales.csv")
with open(sales_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["sale_id", "address", "city", "state", "property_type", "price",
                "bedrooms", "bathrooms", "sqft", "lot_sqft", "year_built",
                "year_renovated", "garage_spaces", "hoa_monthly", "sale_date"])
    w.writerows(rows)

stats_path = os.path.join(OUT_DIR, "city_stats.csv")
with open(stats_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["city", "state", "median_household_income", "population"])
    for city, state, _ppsf, income, pop in CITIES:
        w.writerow([city, state, income, pop])

print(f"wrote {len(rows):,} rows -> {sales_path}")
print(f"wrote {len(CITIES)} rows  -> {stats_path}")
