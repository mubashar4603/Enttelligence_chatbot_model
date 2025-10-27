# Language Query Fix

## Issue
**Query**: "List all languages available for movie screenings"

**Problem**: The query was not being recognized and returned a generic response:
> "I'm Entelligence AI Assistant, your film analytics expert. I can help with comp titles, sales predictions, performance analysis, market opportunities, and basic database queries about movies and theaters. Could you please be more specific about what you'd like to know?"

---

## Root Cause

1. **Missing Keyword Recognition**: The `understand_query_intent` method didn't recognize queries containing "language" or "lang" as `amenities_format` queries.

2. **Missing Handler Logic**: The `handle_amenities_format_query` method didn't have logic to handle language-related queries.

---

## The Fix

### 1. Added Language Keywords to Query Type Detection (Line ~370)

**Before:**
```python
elif any(word in query_lower for word in ['amenities', 'theater id', 'imax count', '4dx count', 'format movies']):
    query_type = 'amenities_format'
```

**After:**
```python
elif any(word in query_lower for word in ['amenities', 'theater id', 'imax count', '4dx count', 'format movies', 'languages', 'language', 'lang']):
    query_type = 'amenities_format'
```

### 2. Added Language Query Handler (Line ~3400)

**Added logic to `handle_amenities_format_query`** to handle language queries:

```python
# Check for language queries
if 'languag' in query_lower or 'lang' in query_lower:
    # Get all unique language formats from database
    languages = Movie.objects.exclude(
        language_format__isnull=True
    ).exclude(
        language_format=''
    ).values_list('language_format', flat=True).distinct()
    
    languages_list = sorted([lang for lang in languages if lang and lang.strip()])
    
    # Count movies for each language
    language_counts = {}
    for lang in languages_list:
        count = Movie.objects.filter(language_format__iexact=lang).values('mm_id').distinct().count()
        language_counts[lang] = count
    
    # Sort by count (descending) and then by name
    sorted_languages = sorted(language_counts.items(), key=lambda x: (-x[1], x[0]))
    
    response = f"**Available Languages for Movie Screenings:**\n\n"
    for lang, count in sorted_languages:
        response += f"• **{lang}**: {count:,} unique movie(s)\n"
    
    response += f"\n**Total languages available:** {len(languages_list)}"
    
    return {
        'type': 'amenities_format',
        'message': response,
        'data': {'languages': languages_list, 'language_counts': dict(language_counts)},
        'sources': None,
        'retrieved_count': len(languages_list),
        'accuracy': '100%',
        'query_type': 'amenities_format'
    }
```

---

## Result

✅ **Before:**
- Query not recognized
- Generic "could you be more specific" response

✅ **After:**
- Query properly categorized as `amenities_format`
- Returns list of available languages with movie counts
- Shows total number of languages available

---

## Test Query

```bash
curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{"message": "List all languages available for movie screenings"}'
```

**Expected Response:**
```
Available Languages for Movie Screenings:

• English: 6 unique movie(s)
• Spanish: 2 unique movie(s)
• French: 1 unique movie(s)

Total languages available: 3
```

---

## Files Modified

- `hvac_assist_backend-main/chat/intelligent_film_analytics_agent.py`
  - Line ~370: Added language keywords to query type detection
  - Line ~3400-3450: Added language query handling logic

---

## Additional Notes

- The query now properly retrieves unique language formats from the `language_format` field in the Movie model
- Results are sorted by popularity (movie count) and then alphabetically
- The response includes both the language list and movie counts for each language
