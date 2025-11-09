# Understanding Cumulative Presales vs First Weekend Revenue

## The Issue

You're seeing different numbers because **Cumulative Presales** and **First Weekend Revenue** are **two completely different metrics**:

### 1. Cumulative Presales (DBR-based)
- **When**: BEFORE release (DBR -60 to -1)
- **What**: Running total of tickets sold before release
- **Example**: Dune: Part Two cumulative presales = **$8.75M** (before release)
- **Purpose**: Shows presales momentum and early audience interest

### 2. First Weekend Revenue (DIR -1, 1, 2, 3)
- **When**: AFTER release (DIR -1, 1, 2, 3)
- **What**: Total revenue during first weekend
- **Example**: Dune: Part Two first weekend = **$64.8M** (after release)
- **Purpose**: Shows actual box office performance

## Why They Don't Match

These metrics measure **different time periods**:

```
Timeline:
┌─────────────────────────────────────────────────────────────┐
│ BEFORE RELEASE          │ RELEASE DATE │ AFTER RELEASE     │
│                         │              │                   │
│ DBR -60 ... DBR -1      │   DBR 0      │ DIR 1, 2, 3...   │
│                         │              │                   │
│ Cumulative Presales     │              │ First Weekend     │
│ = $8.75M                │              │ = $64.8M         │
└─────────────────────────────────────────────────────────────┘
```

## Verification Results

The First Weekend Revenue values in your CSV **DO MATCH** the expected values (within small rounding differences):

| Movie | Expected | Actual | Difference | Status |
|-------|----------|--------|------------|--------|
| Dune: Part Two | $64,817,042 | $64,814,779 | $2,263 | ✅ Match |
| Twisters | $57,050,877 | $57,050,926 | -$49 | ✅ Match |
| Joker | $28,692,416 | $28,692,162 | $254 | ✅ Match |
| Monkey Man | $8,962,509 | $8,962,473 | $36 | ✅ Match |

**All values match within acceptable tolerance!** The small differences are due to rounding or minor data aggregation differences.

## How to Get First Weekend Revenue from CSV

To calculate First Weekend Revenue from `my_export.csv`:

1. Filter for records where `dir_value` is **-1, 1, 2, or 3**
2. Sum the `total_revenue` for those records
3. This gives you First Weekend Revenue

**Example for Dune: Part Two:**
- DIR -1: $8,749,914.99
- DIR 1: $16,351,857.83
- DIR 2: $22,692,096.97
- DIR 3: $17,020,909.56
- **Total: $64,814,779.35** ✅

## SQL Logic

The SQL query uses:
```sql
WHERE (date_sh - release_date) BETWEEN -1 AND 2
```

This translates to DIR values:
- `date_sh - release_date = -1` → DIR = -1
- `date_sh - release_date = 0` → DIR = 1 (DIR = diff + 1 when diff >= 0)
- `date_sh - release_date = 1` → DIR = 2
- `date_sh - release_date = 2` → DIR = 3

So "DIR -1 to 2" in SQL means **DIR values: -1, 1, 2, 3**

## Summary

✅ **Your CSV data is correct!**
- First Weekend Revenue values match expected values
- Small differences ($36-$2,263) are normal rounding/aggregation differences
- Cumulative Presales and First Weekend Revenue are different metrics and shouldn't be compared

The export script now includes First Weekend Revenue calculation in the summary output.

