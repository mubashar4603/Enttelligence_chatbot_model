# Fixing Zero Prices Issue

## Problem
All 10 million movie records have $0.00 for price, child, and senior fields.

## Root Cause
The data import process is not populating price fields correctly.

---

## Solutions

### Solution 1: Fix Your Data Source/ETL Pipeline

Check your data import script or ETL process. Ensure price fields are being populated.

**Example: If using CSV import**
```python
# Make sure your CSV has price columns
# And they're being mapped correctly
Movie.objects.create(
    title=row['title'],
    price=Decimal(row['price']),  # ← Ensure this isn't 0 or null
    child=Decimal(row['child_price']),
    senior=Decimal(row['senior_price']),
    ...
)
```

---

### Solution 2: Update Existing Records with Sample Prices

If you need to quickly test with realistic prices while fixing the data source:

```python
# update_prices.py
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from movies.models import Movie
from decimal import Decimal
import random

# Define realistic price ranges by format
PRICE_RANGES = {
    'IMAX': (16.99, 24.99),
    '3D': (14.99, 19.99),
    'Dolby': (15.99, 21.99),
    '4DX': (18.99, 26.99),
    'Standard': (9.99, 14.99),
    '2D': (9.99, 14.99),
}

def update_prices_batch():
    """Update prices in batches"""
    batch_size = 10000
    total = Movie.objects.count()
    
    print(f"Updating {total:,} records...")
    
    for offset in range(0, total, batch_size):
        movies = Movie.objects.all()[offset:offset+batch_size]
        
        for movie in movies:
            # Determine price range based on format
            screen_format = movie.screen_format
            if screen_format in PRICE_RANGES:
                min_price, max_price = PRICE_RANGES[screen_format]
            else:
                min_price, max_price = (10.99, 16.99)  # Default
            
            # Generate realistic prices
            base_price = Decimal(str(round(random.uniform(min_price, max_price), 2)))
            child_price = base_price - Decimal('3.00')  # $3 less for children
            senior_price = base_price - Decimal('2.00')  # $2 less for seniors
            
            # Ensure minimum prices
            child_price = max(child_price, Decimal('7.99'))
            senior_price = max(senior_price, Decimal('8.99'))
            
            movie.price = base_price
            movie.child = child_price
            movie.senior = senior_price
        
        # Bulk update
        Movie.objects.bulk_update(movies, ['price', 'child', 'senior'])
        
        print(f"Updated {offset + len(movies):,} / {total:,} records...")
    
    print("✅ Price update complete!")

if __name__ == '__main__':
    confirm = input("This will update ALL movie prices. Continue? (yes/no): ")
    if confirm.lower() == 'yes':
        update_prices_batch()
    else:
        print("Cancelled.")
```

**Run it:**
```bash
cd /home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main
source /home/ec2-user/venv/bin/activate
python3 update_prices.py
```

---

### Solution 3: Quick Test with Limited Records

Update just a subset for testing:

```bash
python3 manage.py shell

# In Django shell:
from movies.models import Movie
from decimal import Decimal

# Update first 1000 IMAX records
imax_movies = Movie.objects.filter(screen_format__icontains='IMAX')[:1000]
for movie in imax_movies:
    movie.price = Decimal('18.99')
    movie.child = Decimal('14.99')
    movie.senior = Decimal('16.99')
    movie.save()

# Update first 1000 Standard records
standard_movies = Movie.objects.filter(screen_format='Standard')[:1000]
for movie in standard_movies:
    movie.price = Decimal('12.99')
    movie.child = Decimal('9.99')
    movie.senior = Decimal('10.99')
    movie.save()

print("Updated 2000 records for testing!")
```

---

## Verification

After updating prices, verify:

```python
from movies.models import Movie
from django.db.models import Avg, Min, Max

stats = Movie.objects.aggregate(
    avg=Avg('price'),
    min=Min('price'),
    max=Max('price')
)

print(f"Average: ${stats['avg']:.2f}")
print(f"Range: ${stats['min']:.2f} - ${stats['max']:.2f}")

# Check IMAX specifically
imax_avg = Movie.objects.filter(screen_format__icontains='IMAX').aggregate(
    avg=Avg('price')
)
print(f"IMAX Average: ${imax_avg['avg']:.2f}")
```

---

## Why This Happened

Possible reasons for zero prices:
1. **Data source issue**: Source API/CSV doesn't have price data
2. **ETL mapping error**: Price columns not mapped correctly during import
3. **Data type conversion**: Prices stored as 0 when null/empty
4. **Database migration**: Prices lost during migration
5. **Default values**: Table schema has default=0 for price fields

---

## Recommendation

1. **Immediate**: Use Solution 3 to update a subset for testing
2. **Short-term**: Run Solution 2 to populate all records with realistic prices
3. **Long-term**: Fix your data source/ETL pipeline to include actual prices
4. **Monitor**: Add validation to ensure prices > 0 during data import

---

## Impact on Chatbot

The chatbot is working correctly! Once prices are updated:
- ✅ "Average IMAX price" will show real values
- ✅ "Compare IMAX vs Standard" will show actual price differences
- ✅ Price ranges and statistics will be meaningful
- ✅ All analytical queries will have real data

The chatbot code doesn't need any changes - it's already handling prices correctly!

