#!/usr/bin/env python3
"""
Script to check Twisters presales (DBR) trend in MovieDailyPerformance table
"""
import os
import sys
import django
from decimal import Decimal

# Setup Django
os.chdir('/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main')
sys.path.insert(0, '/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')
django.setup()

from movies.models import Movie, MovieDailyPerformance
from movies.performance_service import MoviePerformanceService
from django.db.models import Min, Max, Sum, Count, Q

def check_twisters_data():
    """Check Twisters data in MovieDailyPerformance table"""
    
    print("=" * 80)
    print("CHECKING TWISTERS PRESALES (DBR) DATA IN MovieDailyPerformance TABLE")
    print("=" * 80)
    print()
    
    # Find all Twisters movies (case-insensitive)
    twisters_movies = Movie.objects.filter(title__icontains='twisters').values_list('title', flat=True).distinct()
    
    if not twisters_movies:
        print("❌ No movies found with 'Twisters' in the title")
        return
    
    print(f"📊 Found {len(twisters_movies)} Twisters movie(s):")
    for title in twisters_movies:
        print(f"   - {title}")
    print()
    
    # Use the first matching title
    movie_title = twisters_movies[0]
    print(f"🔍 Checking data for: '{movie_title}'")
    print()
    
    # Check MovieDailyPerformance table
    print("=" * 80)
    print("MovieDailyPerformance Table Data")
    print("=" * 80)
    
    # Get all DBR records for Twisters, grouped by release_date
    # Note: Twisters has multiple release dates, so we need to check each separately
    release_dates = MovieDailyPerformance.objects.filter(
        title__iexact=movie_title
    ).values_list('release_date', flat=True).distinct()
    
    print(f"📅 Release dates found: {', '.join(str(d) for d in release_dates)}")
    print()
    
    # Get DBR records grouped by release_date
    dbr_records_by_release = {}
    for release_date in release_dates:
        dbr_records_by_release[release_date] = MovieDailyPerformance.objects.filter(
            title__iexact=movie_title,
            release_date=release_date,
            dbr_value__isnull=False
        ).order_by('dbr_value')
    
    # Get all DBR records for summary (across all releases)
    dbr_records = MovieDailyPerformance.objects.filter(
        title__iexact=movie_title,
        dbr_value__isnull=False
    ).order_by('release_date', 'dbr_value')
    
    dbr_count = dbr_records.count()
    
    if dbr_count == 0:
        print("❌ NO DBR RECORDS FOUND for Twisters in MovieDailyPerformance table!")
        print()
        print("💡 This means the table needs to be populated.")
        print("   Run: python manage.py calculate_performance_metrics")
        print()
        
        # Check if there are any DIR records
        dir_records = MovieDailyPerformance.objects.filter(
            title__iexact=movie_title,
            dir_value__isnull=False
        ).count()
        
        if dir_records > 0:
            print(f"   ⚠️  Found {dir_records} DIR records but no DBR records")
            print("   This suggests DBR calculation may not be working correctly")
        else:
            print("   ⚠️  No DIR records either - table may be empty")
        
        return
    
    print(f"✅ Found {dbr_count} DBR records")
    print()
    
    # Get DBR range per release_date
    print("📈 DBR Range by Release Date:")
    for release_date in sorted(release_dates):
        release_records = dbr_records_by_release[release_date]
        if release_records.exists():
            dbr_range = release_records.aggregate(
                min_dbr=Min('dbr_value'),
                max_dbr=Max('dbr_value')
            )
            count = release_records.count()
            print(f"   {release_date}: DBR {dbr_range['min_dbr']} to {dbr_range['max_dbr']} ({count} records)")
    
    # Overall range
    dbr_range = dbr_records.aggregate(
        min_dbr=Min('dbr_value'),
        max_dbr=Max('dbr_value')
    )
    print(f"\n📈 Overall DBR Range: {dbr_range['min_dbr']} to {dbr_range['max_dbr']}")
    print()
    
    # Show sample DBR records
    print("Sample DBR Records (first 10 and last 10):")
    print("-" * 80)
    print(f"{'DBR':<6} {'Date':<12} {'Daily Revenue':<18} {'Cumulative Revenue':<20} {'Daily Reserved':<15} {'Cumulative Reserved':<20}")
    print("-" * 80)
    
    # First 10
    for record in dbr_records[:10]:
        dbr = record.dbr_value
        date_sh = record.date_sh.strftime('%Y-%m-%d') if record.date_sh else 'N/A'
        daily_rev = f"${record.total_revenue:,.2f}" if record.total_revenue else "$0.00"
        cum_rev = f"${record.cumulative_revenue:,.2f}" if record.cumulative_revenue else "$0.00"
        daily_res = f"{record.total_reserved_seats:,}" if record.total_reserved_seats else "0"
        cum_res = f"{record.cumulative_reserved:,}" if record.cumulative_reserved else "0"
        
        print(f"{dbr:<6} {date_sh:<12} {daily_rev:<18} {cum_rev:<20} {daily_res:<15} {cum_res:<20}")
    
    if dbr_count > 20:
        print("...")
        # Last 10
        for record in dbr_records[dbr_count-10:]:
            dbr = record.dbr_value
            date_sh = record.date_sh.strftime('%Y-%m-%d') if record.date_sh else 'N/A'
            daily_rev = f"${record.total_revenue:,.2f}" if record.total_revenue else "$0.00"
            cum_rev = f"${record.cumulative_revenue:,.2f}" if record.cumulative_revenue else "$0.00"
            daily_res = f"{record.total_reserved_seats:,}" if record.total_reserved_seats else "0"
            cum_res = f"{record.cumulative_reserved:,}" if record.cumulative_reserved else "0"
            
            print(f"{dbr:<6} {date_sh:<12} {daily_rev:<18} {cum_rev:<20} {daily_res:<15} {cum_res:<20}")
    
    print()
    
    # Check data validity
    print("=" * 80)
    print("Data Validation")
    print("=" * 80)
    
    # Check if cumulative values are increasing (per release_date)
    issues = []
    
    for release_date, records in dbr_records_by_release.items():
        prev_cum_rev = None
        prev_cum_res = None
        prev_dbr = None
        
        for record in records:
            if prev_cum_rev is not None:
                # Cumulative should increase as DBR approaches 0 (less negative)
                if record.dbr_value > prev_dbr:  # Less negative (closer to release)
                    if record.cumulative_revenue < prev_cum_rev:
                        issues.append(f"[{release_date}] DBR {record.dbr_value}: Cumulative revenue decreased from ${prev_cum_rev:,.2f} to ${record.cumulative_revenue:,.2f}")
                    if record.cumulative_reserved < prev_cum_res:
                        issues.append(f"[{release_date}] DBR {record.dbr_value}: Cumulative reserved decreased from {prev_cum_res:,} to {record.cumulative_reserved:,}")
            
            prev_dbr = record.dbr_value
            prev_cum_rev = record.cumulative_revenue
            prev_cum_res = record.cumulative_reserved
    
    if issues:
        print("⚠️  WARNING: Found potential data issues:")
        for issue in issues[:10]:  # Show first 10 issues
            print(f"   • {issue}")
        if len(issues) > 10:
            print(f"   ... and {len(issues) - 10} more issues")
    else:
        print("✅ Cumulative values are increasing correctly (as expected)")
    
    print()
    
    # Check raw Movie data
    print("=" * 80)
    print("Raw Movie Table Data Check")
    print("=" * 80)
    
    twisters_movie_records = Movie.objects.filter(title__iexact=movie_title)
    raw_count = twisters_movie_records.count()
    
    print(f"📊 Found {raw_count:,} raw Movie records for '{movie_title}'")
    
    if raw_count == 0:
        print("❌ No raw Movie records found!")
        return
    
    # Check release date
    release_dates = twisters_movie_records.values_list('release_date', flat=True).distinct()
    print(f"📅 Release dates found: {', '.join(str(d) for d in release_dates)}")
    
    # Check running_date range
    running_dates = twisters_movie_records.exclude(running_date__isnull=True).values_list('running_date', flat=True).distinct()
    if running_dates:
        min_running = min(running_dates)
        max_running = max(running_dates)
        print(f"📅 Running dates range: {min_running} to {max_running}")
        
        # Calculate expected DBR range
        if release_dates:
            release_date = release_dates[0]
            perf_service = MoviePerformanceService()
            
            expected_min_dbr = None
            expected_max_dbr = None
            
            for running_date in running_dates:
                dbr = perf_service.calculate_dbr(running_date, release_date)
                if dbr and dbr < 0:  # Only presales (negative DBR)
                    if expected_min_dbr is None or dbr < expected_min_dbr:
                        expected_min_dbr = dbr
                    if expected_max_dbr is None or dbr > expected_max_dbr:
                        expected_max_dbr = dbr
            
            print(f"🔢 Expected DBR range (from raw data): {expected_min_dbr} to {expected_max_dbr}")
            
            if expected_min_dbr and expected_max_dbr:
                if dbr_range['min_dbr'] != expected_min_dbr or dbr_range['max_dbr'] != expected_max_dbr:
                    print(f"⚠️  WARNING: DBR range mismatch!")
                    print(f"   Expected: {expected_min_dbr} to {expected_max_dbr}")
                    print(f"   Actual: {dbr_range['min_dbr']} to {dbr_range['max_dbr']}")
                else:
                    print("✅ DBR range matches expected values")
    
    print()
    
    # Test using performance service
    print("=" * 80)
    print("Performance Service Test")
    print("=" * 80)
    
    perf_service = MoviePerformanceService()
    
    try:
        dbr_trend = perf_service.get_day_by_day_dbr_trend(
            title=movie_title,
            start_dbr=None,
            end_dbr=None,
            use_cache=True
        )
        
        if dbr_trend:
            print(f"✅ Performance service returned {len(dbr_trend)} DBR data points")
            print()
            print("First 5 records:")
            for i, day in enumerate(dbr_trend[:5]):
                dbr_val = day.get('dbr_value', 'N/A')
                cum_rev = day.get('cumulative_revenue', 0)
                cum_res = day.get('cumulative_reserved', 0)
                print(f"   DBR {dbr_val}: Cumulative ${cum_rev:,.2f}, {cum_res:,} seats")
        else:
            print("❌ Performance service returned empty DBR trend")
            print("   Trying without cache...")
            dbr_trend_raw = perf_service.get_day_by_day_dbr_trend(
                title=movie_title,
                start_dbr=None,
                end_dbr=None,
                use_cache=False
            )
            if dbr_trend_raw:
                print(f"   ✅ Raw calculation returned {len(dbr_trend_raw)} records")
                print("   This suggests cached data needs to be recalculated")
            else:
                print("   ❌ Raw calculation also returned empty")
    
    except Exception as e:
        print(f"❌ Error testing performance service: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    
    if dbr_count == 0:
        print("❌ ACTION REQUIRED: MovieDailyPerformance table needs to be populated")
        print("   Run: python manage.py calculate_performance_metrics")
    elif issues:
        print("⚠️  Data exists but has validation issues")
        print("   Consider recalculating: python manage.py calculate_performance_metrics")
    else:
        print("✅ Data appears to be correct!")

if __name__ == "__main__":
    check_twisters_data()

