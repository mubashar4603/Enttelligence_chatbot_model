#!/usr/bin/env python3
"""
COMPREHENSIVE CSV COLUMN MAPPING ANALYSIS
Ensures ALL CSV columns are mapped to Movie model fields
"""

def analyze_csv_mapping():
    """Analyze CSV columns vs Movie model fields"""
    
    # CSV columns from the actual file
    csv_columns = [
        'id', 'circuit_name', 'theater_id', 'theater_name', 'theater_address',
        'theater_city', 'theater_state', 'theater_zip', 'title', 'date_sh',
        'time_sh', 'auditorium', 'price', 'child', 'senior', 'total_seats',
        'available', 'reserved', 'checkered', 'amenities', 'ticket_availability',
        'last_updates', 'running_date', 'screen_format', 'movie_format', 'dma',
        'studio_name', 'release_date', 'before_reserved', 'on_reserved',
        'after_reserved', 'seating_type', 'source_flag', 'mm_id',
        'actual_total_seats', 'actual_available', 'actual_reserved',
        'actual_checkered', 'dsr_date_sh', 'dsr_last_updates',
        'language_format', 'country', 'runtime', 'genre', 'rating', 'is_ticketing'
    ]
    
    # Movie model fields
    movie_fields = [
        'id', 'theater_id', 'mm_id', 'circuit_name', 'theater_name',
        'theater_address', 'theater_city', 'theater_state', 'theater_zip',
        'country', 'dma', 'title', 'studio_name', 'release_date', 'runtime',
        'genre', 'rating', 'date_sh', 'time_sh', 'auditorium', 'screen_format',
        'movie_format', 'language_format', 'price', 'child', 'senior',
        'total_seats', 'available', 'reserved', 'checkered', 'actual_total_seats',
        'actual_available', 'actual_reserved', 'actual_checkered',
        'before_reserved', 'on_reserved', 'after_reserved', 'seating_type',
        'amenities', 'ticket_availability', 'is_ticketing', 'source_flag',
        'last_updates', 'running_date', 'dsr_date_sh', 'dsr_last_updates'
    ]
    
    print("🔍 CSV COLUMN MAPPING ANALYSIS")
    print("=" * 60)
    
    print(f"📊 CSV Columns: {len(csv_columns)}")
    print(f"📊 Movie Fields: {len(movie_fields)}")
    
    print("\n✅ DIRECT MAPPINGS:")
    print("-" * 40)
    direct_mappings = []
    for csv_col in csv_columns:
        if csv_col in movie_fields:
            direct_mappings.append(csv_col)
            print(f"✓ {csv_col} → {csv_col}")
    
    print(f"\n📈 Direct mappings: {len(direct_mappings)}/{len(csv_columns)}")
    
    print("\n⚠️ MISSING MAPPINGS:")
    print("-" * 40)
    missing_mappings = []
    for csv_col in csv_columns:
        if csv_col not in movie_fields:
            missing_mappings.append(csv_col)
            print(f"❌ {csv_col} - NOT MAPPED!")
    
    print(f"\n📉 Missing mappings: {len(missing_mappings)}")
    
    print("\n🔍 FIELD ANALYSIS:")
    print("-" * 40)
    print("• All CSV columns should be mapped to Movie model")
    print("• No columns should be skipped")
    print("• Data types must be handled correctly")
    
    return {
        'csv_columns': csv_columns,
        'movie_fields': movie_fields,
        'direct_mappings': direct_mappings,
        'missing_mappings': missing_mappings
    }

if __name__ == "__main__":
    mapping_analysis = analyze_csv_mapping()
    
    print("\n🎯 RECOMMENDATION:")
    print("=" * 60)
    if len(mapping_analysis['missing_mappings']) == 0:
        print("✅ ALL CSV COLUMNS ARE PROPERLY MAPPED!")
        print("✅ No columns will be skipped during import")
    else:
        print("❌ SOME COLUMNS ARE NOT MAPPED!")
        print("❌ These columns will be skipped during import")
        print("❌ Update the import script to include all columns")
