# Language Formats Query Fix - Updated

## Issue
**Query**: "List all languages available for movie screenings"

**Problem**: The query was showing only 3 languages when the database actually contains many more language formats.

---

## Root Cause

The database doesn't just have simple language names like "English" or "Spanish". It actually stores **language formats** like:
- `NULL` (default/standard)
- `Spanish Dubbed`
- `English Subtitles`
- `Spanish Subtitles`
- `English Dubbed`
- `Spanish Dub &amp; Sub`
- `undefined`
- `Hindi Subtitles`
- `English Dub &amp; Sub`

The initial implementation was:
1. Not properly handling these format strings
2. Not showing all available formats
3. Not filtering out NULL and 'undefined' values correctly

---

## The Fix

### Updated Language Query Handler

**New Implementation:**
```python
# Get all unique language formats with their counts
languages_data = Movie.objects.exclude(
    Q(language_format__isnull=True) | 
    Q(language_format='') | 
    Q(language_format='undefined')
).values('language_format').annotate(
    count=Count('id'),
    unique_movies=Count('mm_id', distinct=True)
).order_by('-unique_movies')

# Display format
response = f"**Available Language Formats for Movie Screenings:**\n\n"
for lang_info in languages_list:
    lang = lang_info['language_format']
    count = lang_info['count']
    unique_movies = lang_info['unique_movies']
    
    # Clean up HTML entities
    lang_clean = lang.replace('&amp;', '&')
    
    response += f"• **{lang_clean}**: {unique_movies:,} unique movie(s) ({count:,} total showings)\n"
```

---

## Key Changes

1. **Proper Filtering**: Now excludes `NULL`, empty strings, and 'undefined' values
2. **HTML Entity Cleaning**: Converts `&amp;` to `&` for display
3. **Better Statistics**: Shows both unique movies and total showings count
4. **Sorting**: Orders by popularity (most movies first)

---

## Expected Output

```
Available Language Formats for Movie Screenings:

• Spanish Dubbed: 6 unique movie(s) (123,456 total showings)
• English Subtitles: 5 unique movie(s) (98,765 total showings)
• Spanish Subtitles: 4 unique movie(s) (87,654 total showings)
• English Dubbed: 3 unique movie(s) (76,543 total showings)
• Spanish Dub & Sub: 2 unique movie(s) (65,432 total showings)
• Hindi Subtitles: 2 unique movie(s) (54,321 total showings)
• English Dub & Sub: 1 unique movie(s) (43,210 total showings)

Total language formats available: 7
```

---

## Result

✅ **Before:**
- Only showing 3 languages
- Missing actual language formats from database
- Not counting all available formats

✅ **After:**
- Shows ALL language formats from database
- Properly excludes NULL and undefined values
- Shows both unique movie counts and total showings
- Cleans up HTML entities for better display
- Sorted by popularity

---

## Files Modified

- `hvac_assist_backend-main/chat/intelligent_film_analytics_agent.py`
  - Lines ~3400-3450: Complete rewrite of language query handler
  - Now uses proper Django ORM aggregation
  - Filters out invalid values correctly
  - Shows proper statistics for each format
