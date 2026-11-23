"""
Generate the AutoBid sample data.

Input:  data/data.csv  (real Kaggle "Car Features and MSRP" data)
Output: data/generated/vehicles.csv        1,000 real cars + a vehicle_id and a fake VIN
        data/generated/auction_sales.csv   synthetic auction listings for those cars
        data/bad_batch/auction_sales_bad.csv  a few deliberately bad rows (dbt test demo)

The auction sales are SYNTHETIC: real auction data is not public.
A fixed random seed means every run produces exactly the same files.

Run from the repo root:  python scripts/generate_auction_data.py
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
SEED = 42
NUM_VEHICLES = 1000
SALE_YEAR = 2025                 # all sales happen during this year
MAX_LISTINGS = 3                 # an unsold car is relisted, up to 3 tries in total
DAYS_BETWEEN_LISTINGS = 14

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILE = REPO_ROOT / "data" / "data.csv"
GENERATED_DIR = REPO_ROOT / "data" / "generated"
BAD_BATCH_DIR = REPO_ROOT / "data" / "bad_batch"

# One row per damage type:
#   weight      how common the damage is (Front End is the most common)
#   value_share share of the car's age-adjusted value it still sells for
#   salvage_pct chance the car has a Salvage title (vs Clean)
#   sell_pct    chance a listing ends in a sale
DAMAGE_TYPES = {
    #                          weight  value_share  salvage_pct  sell_pct
    "Front End":              (30,     0.35,        0.60,        0.70),
    "Rear End":               (15,     0.50,        0.40,        0.75),
    "Side":                   (15,     0.45,        0.50,        0.70),
    "Hail":                   (10,     0.60,        0.30,        0.80),
    "Flood":                  (8,      0.20,        0.90,        0.50),
    "Mechanical":             (10,     0.40,        0.20,        0.60),
    "Minor Dents/Scratches":  (12,     0.75,        0.05,        0.85),
}

SALVAGE_DISCOUNT = 0.80          # a Salvage title sells for 20% less
YARD_STATES = ["TX", "CA", "FL", "GA", "NY", "IL", "PA", "OH", "NC", "AZ"]

# VINs never use the letters I, O or Q (they look like 1 and 0)
VIN_CHARACTERS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------
def load_eligible_cars():
    """Read data.csv and keep cars we can price sensibly.

    - MSRP of exactly 2000 is a placeholder in this dataset for old cars,
      not a real price, so value-retained % would be meaningless.
    - Cars before 2000 would be 25+ years old at sale time.
    """
    with open(SOURCE_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if int(r["MSRP"]) > 2000 and int(r["Year"]) >= 2000]


def make_vin(used_vins):
    """Return a random, unique 17-character fake VIN."""
    while True:
        vin = "".join(random.choice(VIN_CHARACTERS) for _ in range(17))
        if vin not in used_vins:
            used_vins.add(vin)
            return vin


def build_vehicles(cars):
    """Sample cars and give each one a vehicle_id and a VIN.

    The original Kaggle columns are kept exactly as they are (messy headers,
    blanks and all): cleaning is the job of the dbt staging models.
    """
    sample = random.sample(cars, NUM_VEHICLES)
    used_vins = set()
    vehicles = []
    for vehicle_id, car in enumerate(sample, start=1):
        vehicles.append({"vehicle_id": vehicle_id, "vin": make_vin(used_vins), **car})
    return vehicles


# ---------------------------------------------------------------------------
# Auction sales
# ---------------------------------------------------------------------------
def price_car(msrp, car_year, damage_type, title_type):
    """Sale price = MSRP x age factor x damage share x title discount x noise."""
    age = SALE_YEAR - car_year
    age_factor = max(0.15, 0.88 ** age)          # ~12% value lost per year, floor 15%
    value_share = DAMAGE_TYPES[damage_type][1]
    title_factor = SALVAGE_DISCOUNT if title_type == "Salvage" else 1.0
    noise = max(0.5, random.gauss(1.0, 0.15))    # +/- ~15%, never below half
    price = msrp * age_factor * value_share * title_factor * noise
    return max(100, round(price))                # auctions have a minimum price


def build_sales(vehicles):
    """Create listings. Damage and title belong to the car; unsold cars are relisted."""
    damage_names = list(DAMAGE_TYPES)
    damage_weights = [DAMAGE_TYPES[d][0] for d in damage_names]
    used_lot_numbers = set()
    sales = []

    for v in vehicles:
        damage_type = random.choices(damage_names, weights=damage_weights)[0]
        _, _, salvage_pct, sell_pct = DAMAGE_TYPES[damage_type]
        title_type = "Salvage" if random.random() < salvage_pct else "Clean"
        yard_state = random.choice(YARD_STATES)
        # first listing somewhere in Jan-Oct, so relistings stay inside the year
        sale_date = date(SALE_YEAR, 1, 1) + timedelta(days=random.randint(0, 303))

        for _ in range(MAX_LISTINGS):
            lot_number = random.randint(10_000_000, 99_999_999)
            while lot_number in used_lot_numbers:
                lot_number = random.randint(10_000_000, 99_999_999)
            used_lot_numbers.add(lot_number)

            is_sold = random.random() < sell_pct
            sales.append({
                "sale_id": len(sales) + 1,
                "vehicle_id": v["vehicle_id"],
                "lot_number": lot_number,
                "damage_type": damage_type,
                "title_type": title_type,
                "yard_state": yard_state,
                "sale_date": sale_date.isoformat(),
                # unsold lots still get a few bids that didn't reach the reserve
                "bid_count": random.randint(1, 30) if is_sold else random.randint(0, 3),
                "sale_price": price_car(int(v["MSRP"]), int(v["Year"]), damage_type, title_type)
                              if is_sold else "",          # unsold = no price
                "is_sold": is_sold,
            })
            if is_sold:
                break
            sale_date += timedelta(days=DAYS_BETWEEN_LISTINGS)

    return sales


# ---------------------------------------------------------------------------
# Bad batch (only for demoing that dbt tests catch bad data)
# ---------------------------------------------------------------------------
def build_bad_batch(sales):
    """A small file of listings: 2 good rows and one row for each kind of problem."""
    next_id = len(sales) + 1
    template = sales[0]                          # a real, valid listing to copy from

    def row(**changes):
        return {**template, "lot_number": random.randint(10_000_000, 99_999_999), **changes}

    return [
        row(sale_id=next_id),                                              # good
        row(sale_id=next_id + 1, is_sold=False, sale_price="", bid_count=0),  # good, unsold
        row(sale_id=next_id + 2, sale_price=-500),                         # negative price
        row(sale_id=template["sale_id"]),                                  # duplicate sale_id
        row(sale_id=next_id + 3, vehicle_id=99999),                        # unknown vehicle
        row(sale_id=next_id + 4, damage_type="Fire"),                      # unknown damage type
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows):>5} rows -> {path.relative_to(REPO_ROOT)}")


def main():
    random.seed(SEED)
    vehicles = build_vehicles(load_eligible_cars())
    sales = build_sales(vehicles)
    bad_rows = build_bad_batch(sales)

    write_csv(GENERATED_DIR / "vehicles.csv", vehicles)
    write_csv(GENERATED_DIR / "auction_sales.csv", sales)
    write_csv(BAD_BATCH_DIR / "auction_sales_bad.csv", bad_rows)


if __name__ == "__main__":
    main()
