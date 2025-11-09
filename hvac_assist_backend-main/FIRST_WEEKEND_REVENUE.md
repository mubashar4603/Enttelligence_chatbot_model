# First Weekend Revenue Calculation

## Definition

**First Weekend Revenue (DIR -1 to 2)** = Sum of total_revenue for DIR values: **-1, 1, 2, 3**

## SQL Logic

The SQL query uses:
```sql
WHERE (date_sh - release_date) BETWEEN -1 AND 2
```

This translates to DIR values based on the DIR calculation formula:

### DIR Calculation Formula
```python
if (date_sh < release_date):
    DIR = date_sh - release_date  # negative values (before release)
    
if (date_sh >= release_date):
    DIR = date_sh - release_date + 1  # starting from DIR = 1 on release day
```

### Mapping
| Scenario                  | Release Date | Date_Sh | Calculation | DIR Value | Day Description |
| ------------------------- | ------------ | ------- | ----------- | --------- | --------------- |
| One day BEFORE release    | July 20      | July 19 | -1          | **-1**    | Day before release |
| Opening day (release day) | July 20      | July 20 | 0 + 1       | **1**     | Release day |
| One day AFTER release     | July 20      | July 21 | 1 + 1       | **2**     | Day 1 after release |

## Result

**First Weekend Revenue** includes:
- **DIR -1**: Revenue from day before release
- **DIR 1**: Revenue from release day
- **DIR 2**: Revenue from day 1 after release
- **DIR 3**: Revenue from day 2 after release

**Total = Sum of total_revenue for DIR -1, 1, 2, 3**

## Implementation

### In Code
```python
# Filter for First Weekend Revenue
MovieDailyPerformance.objects.filter(
    dir_value__in=[-1, 1, 2, 3]
).aggregate(
    first_weekend_revenue=Sum('total_revenue')
)
```

### In SQL
```sql
SELECT SUM(total_revenue) as first_weekend_revenue
FROM movie_daily_performance
WHERE dir_value IN (-1, 1, 2, 3)
```

## Verification

From your CSV data (`my_export.csv`), First Weekend Revenue for each movie:

| Movie | DIR -1 | DIR 1 | DIR 2 | DIR 3 | **Total** |
|-------|--------|-------|-------|-------|-----------|
| Dune: Part Two | $8,749,915 | $16,351,858 | $22,692,097 | $17,020,910 | **$64,814,780** |
| Twisters | $6,695,866 | $15,220,204 | $19,518,315 | $15,616,541 | **$57,050,926** |
| Joker: Folie a Deux | $5,876,739 | $10,205,053 | $8,219,815 | $4,390,554 | **$28,692,162** |
| Monkey Man | $1,329,784 | $2,576,320 | $3,019,447 | $2,036,922 | **$8,962,473** |

## Important Notes

1. **DIR -1 to 2** in SQL terms means **DIR values: -1, 1, 2, 3**
2. This is a **4-day period**: day before release + first 3 days after release
3. The calculation matches the SQL constraint: `(date_sh - release_date) BETWEEN -1 AND 2`
4. All code has been updated to use `dir_value__in=[-1, 1, 2, 3]` for First Weekend queries

