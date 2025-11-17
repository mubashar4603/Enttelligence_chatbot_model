"""
Performance-optimized service for calculating movie performance metrics.
Designed to handle millions of records efficiently using:
- Database-level aggregations
- Bulk operations
- Efficient batch processing
- Smart caching
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
import math
from statistics import median
from typing import Dict, List, Any, Optional, Tuple
from django.db.models import (
    Sum, Count, Avg, Max, Min, Q, F, DecimalField, ExpressionWrapper,
    Case, When, IntegerField
)
from django.db.models.functions import Cast, Coalesce
from django.db import transaction, connection
from movies.models import Movie, MovieDailyPerformance, MoviePerformanceComparison

logger = logging.getLogger(__name__)


class MoviePerformanceService:
    """
    High-performance service for calculating and querying movie performance metrics.
    Uses bulk operations and database aggregations for scalability.
    """
    
    @staticmethod
    def calculate_dir(date_sh: date, release_date: date) -> int:
        """
        Calculate DIR (Days In Release) according to business logic:
        
        If (date_sh < release_date):
            DIR = date_sh - release_date  # negative values (before release)
        
        If (date_sh >= release_date):
            DIR = date_sh - release_date + 1  # starting from DIR = 1 on release day
        
        Examples:
        - One day BEFORE release: release_date = July 20, date_sh = July 19 → DIR = -1
        - Opening day (release day): release_date = July 20, date_sh = July 20 → DIR = 1
        - One day AFTER release: release_date = July 20, date_sh = July 21 → DIR = 2
        
        Args:
            date_sh: Show date
            release_date: Movie release date
            
        Returns:
            DIR value (integer)
        """
        diff = (date_sh - release_date).days
        if diff < 0:
            return diff
        else:
            return diff + 1
    
    @staticmethod
    def calculate_dbr(running_date: date, release_date: date) -> Optional[int]:
        """
        Calculate DBR (Days Before Release) according to SQL logic.
        
        DBR = Running Date - Release Date
        Constraint: DBR <= 2 (Default)
        
        Args:
            running_date: Running date
            release_date: Movie release date
            
        Returns:
            DBR value (integer, negative values indicate days before release)
            Returns None if DBR > 2 (outside constraint)
        """
        if not running_date:
            return None
        diff = (running_date - release_date).days
        if diff < 0:
            dbr_value = diff
        else:
            dbr_value = diff + 1
        
        # Apply constraint: DBR <= 2
        if dbr_value > 2:
            return None
        
        return dbr_value
    
    @staticmethod
    def calculate_sales_estimate(price: Decimal, reserved: int) -> Decimal:
        """
        Calculate sales estimate: price * reserved
        Handles price as string or decimal.
        
        Args:
            price: Ticket price (Decimal or string with $)
            reserved: Number of reserved seats
            
        Returns:
            Sales estimate as Decimal
        """
        if isinstance(price, str):
            # Remove $ sign and convert to float, then to Decimal
            price_str = price.replace('$', '').strip()
            try:
                price_decimal = Decimal(str(float(price_str)))
            except (ValueError, TypeError):
                return Decimal('0')
        else:
            price_decimal = Decimal(str(price)) if price else Decimal('0')
        
        return price_decimal * Decimal(str(reserved))
    
    def get_period_dir_range(self, period_label: str) -> Tuple[int, int]:
        """
        Get DIR range for common period labels.
        
        Args:
            period_label: e.g., "first_weekend", "first_week", "first_5_days"
            
        Returns:
            Tuple of (start_dir, end_dir)
        """
        period_map = {
            'first_weekend': (-1, 2),  # First Weekend: DIR -1, 1, 2 only
            'first_week': (-1, 7),
            'first_5_days': (-1, 5),
            'first_10_days': (-1, 10),
            'first_14_days': (-1, 14),
            'first_30_days': (-1, 30),
            'opening_weekend': (-1, 2),  # Opening Weekend: DIR -1, 1, 2 only
        }
        return period_map.get(period_label.lower(), (-1, 2))  # Default to first weekend range
    
    @transaction.atomic
    def calculate_daily_performance_bulk(
        self,
        title: Optional[str] = None,
        batch_size: int = 10000
    ) -> int:
        """
        Bulk calculate and store daily performance metrics for all movies or a specific title.
        Uses efficient database aggregations to handle millions of records.
        
        Args:
            title: Optional movie title to limit calculation
            batch_size: Number of records to process per batch
            
        Returns:
            Number of records created/updated
        """
        logger.info(f"🔄 Starting bulk calculation of daily performance metrics...")
        
        # Build query
        query = Movie.objects.all()
        if title:
            query = query.filter(title__iexact=title)
        
        # Get distinct movie titles and release dates
        # Note: This counts distinct (title, release_date) combinations
        # So a movie with multiple release dates or title variations will be counted separately
        movies = query.values('title', 'release_date').distinct().order_by('title', 'release_date')
        total_movies = movies.count()
        
        # Log title variations for transparency
        if not title:  # Only log when processing all movies
            title_counts = {}
            for movie in movies:
                title_normalized = movie['title'].upper().strip()
                if title_normalized not in title_counts:
                    title_counts[title_normalized] = []
                title_counts[title_normalized].append({
                    'title': movie['title'],
                    'release_date': movie['release_date']
                })
            
            # Check for duplicates/variations
            variations = {k: v for k, v in title_counts.items() if len(v) > 1}
            if variations:
                logger.info(f"   ℹ️  Found {len(variations)} movie(s) with multiple title/release combinations:")
                for normalized, variants in variations.items():
                    for variant in variants:
                        logger.info(f"      - {variant['title']} ({variant['release_date']})")
        
        logger.info(f"📊 Processing {total_movies} distinct (title, release_date) combinations...")
        
        created_count = 0
        total_records_after_processing = {}
        
        for idx, movie_info in enumerate(movies, 1):
            if idx % 100 == 0:
                logger.info(f"   Processing movie {idx}/{total_movies}: {movie_info['title']}")
            
            title_str = movie_info['title']
            release_date_val = movie_info['release_date']
            movie_created_count = 0
            records_filtered_out = 0
            records_processed = 0
            
            # Get all records for this movie
            movie_records = Movie.objects.filter(
                title__iexact=title_str,
                release_date=release_date_val
            )
            total_movie_records = movie_records.count()
            
            # Debug: Show date ranges for first movie
            if idx == 1 and total_movie_records > 0:
                from django.db.models import Min, Max
                date_range = movie_records.aggregate(
                    min_date_sh=Min('date_sh'),
                    max_date_sh=Max('date_sh'),
                    min_running_date=Min('running_date'),
                    max_running_date=Max('running_date')
                )
                logger.info(f"   📅 Date ranges for '{title_str}':")
                logger.info(f"      release_date: {release_date_val}")
                logger.info(f"      date_sh range: {date_range['min_date_sh']} to {date_range['max_date_sh']}")
                logger.info(f"      running_date range: {date_range['min_running_date']} to {date_range['max_running_date']}")
                days_before = (release_date_val - date_range['max_date_sh']).days if date_range['max_date_sh'] < release_date_val else 0
                days_after = (date_range['min_date_sh'] - release_date_val).days if date_range['min_date_sh'] > release_date_val else 0
                logger.info(f"      Days before release (max date_sh): {days_before}")
                logger.info(f"      Days after release (min date_sh): {days_after}")
                
                # Check if release_date seems wrong based on date_sh values
                if days_after > 30:
                    # Release date is more than 30 days before the earliest show date - likely wrong
                    logger.error(f"   ❌ POTENTIAL DATA ISSUE: release_date ({release_date_val}) is {days_after} days before earliest show date ({date_range['min_date_sh']})")
                    logger.error(f"      This suggests the release_date in the database may be incorrect!")
                    logger.error(f"      Expected release_date should be closer to the show dates (likely around {date_range['min_date_sh']} or a few days before)")
                    logger.error(f"      To fix: UPDATE movies SET release_date = '2025-12-05' WHERE title = '{title_str}' AND release_date = '{release_date_val}'")
                elif days_before < 0:
                    # Show dates are before release date - might be presales
                    if days_before < -50:
                        logger.warning(f"   ⚠️  All show dates are {abs(days_before)} days before release_date - these are presales records")
                elif days_after >= 0 and days_after <= 2:
                    # Dates look reasonable for first weekend
                    logger.info(f"   ✅ Date ranges look correct for first weekend (DIR -1, 1, 2)")
            
            # Aggregate by date_sh AND running_date for accurate DBR calculation
            # DBR is calculated from running_date, so we need to group by both
            # to capture all advance booking scenarios
            from django.db import connection
            
            # Use raw SQL aggregation - group by date_sh and running_date
            # This ensures we capture all DBR variations
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            date_sh,
                            running_date::date as running_date_val,
                            SUM(reserved) as total_reserved,
                            SUM(total_seats) as total_seats,
                            SUM(price * reserved) as total_revenue,
                            AVG(price) as avg_price,
                            COUNT(id) as count_shows,
                            SUM(checkered) as total_checkered
                        FROM movies
                        WHERE UPPER(title) = UPPER(%s)
                        AND release_date = %s
                        GROUP BY date_sh, running_date::date
                        ORDER BY date_sh, running_date::date
                    """, [title_str, release_date_val])
                    
                    # Convert raw SQL results to dictionary format
                    columns = [col[0] for col in cursor.description]
                    aggregate_list = []
                    for row in cursor.fetchall():
                        row_dict = dict(zip(columns, row))
                        # Ensure proper types
                        row_dict['date_sh'] = row_dict['date_sh']
                        row_dict['running_date_val'] = row_dict['running_date_val']
                        row_dict['total_reserved'] = int(row_dict['total_reserved'] or 0)
                        row_dict['total_seats'] = int(row_dict['total_seats'] or 0)
                        row_dict['total_revenue'] = Decimal(str(row_dict['total_revenue'] or 0))
                        row_dict['avg_price'] = Decimal(str(row_dict['avg_price'] or 0))
                        row_dict['count_shows'] = int(row_dict['count_shows'] or 0)
                        row_dict['total_checkered'] = int(row_dict['total_checkered'] or 0)
                        aggregate_list.append(row_dict)
            except Exception as e:
                # If database-level aggregation fails due to data type issues,
                # fall back to Python-level processing (slower but safe)
                logger.warning(f"Database aggregation failed: {e}. Falling back to Python-level processing.")
                
                # Get all records and process in Python
                all_records = list(movie_records.values('date_sh', 'reserved', 'price', 'total_seats', 'checkered', 'running_date'))
                
                # Group by date_sh and running_date manually
                from collections import defaultdict
                daily_dict = defaultdict(lambda: {
                    'total_reserved': 0,
                    'total_seats': 0,
                    'total_revenue': Decimal('0'),
                    'prices': [],
                    'count_shows': 0,
                    'total_checkered': 0
                })
                
                for record in all_records:
                    date_key = record['date_sh']
                    running_date_key = record.get('running_date')
                    
                    # Use reserved as-is, no filtering
                    reserved_val = int(record['reserved']) if record['reserved'] is not None else 0
                    
                    # Use price as-is, no filtering
                    price_val = Decimal(str(record['price'])) if record['price'] else Decimal('0')
                    
                    daily_dict[date_key]['total_reserved'] += reserved_val
                    daily_dict[date_key]['total_seats'] += record.get('total_seats', 0) or 0
                    daily_dict[date_key]['total_revenue'] += price_val * Decimal(str(reserved_val))
                    daily_dict[date_key]['prices'].append(price_val)
                    daily_dict[date_key]['count_shows'] += 1
                    daily_dict[date_key]['total_checkered'] += record.get('checkered', 0) or 0
                
                # Convert to list format matching the original structure
                aggregate_list = []
                for date_key in sorted(daily_dict.keys()):
                    daily_data = daily_dict[date_key]
                    avg_price = sum(daily_data['prices']) / len(daily_data['prices']) if daily_data['prices'] else Decimal('0')
                    aggregate_list.append({
                        'date_sh': date_key,
                        'running_date_val': None,  # Will be set if available from records
                        'total_reserved': daily_data['total_reserved'],
                        'total_seats': daily_data['total_seats'],
                        'total_revenue': daily_data['total_revenue'],
                        'avg_price': avg_price,
                        'count_shows': daily_data['count_shows'],
                        'total_checkered': daily_data['total_checkered']
                    })
            
            # Debug: Show sample dates for first few aggregated records
            if idx == 1 and len(aggregate_list) > 0:
                logger.info(f"   🔍 Debug: Release date = {release_date_val}")
                logger.info(f"   🔍 Sample date_sh values and DIR calculations (first 10):")
                for i, sample_data in enumerate(aggregate_list[:10]):
                    sample_date_sh = sample_data['date_sh']
                    sample_running = sample_data.get('running_date_val')
                    sample_dir = self.calculate_dir(sample_date_sh, release_date_val)
                    sample_dbr = None
                    if sample_running:
                        sample_dbr = self.calculate_dbr(sample_running, release_date_val)
                    logger.info(f"      [{i+1}] date_sh={sample_date_sh}, running_date={sample_running}, DIR={sample_dir}, DBR={sample_dbr}, days_from_release={(sample_date_sh - release_date_val).days}")
            
            for day_data in aggregate_list:
                date_sh_val = day_data['date_sh']
                running_date_val = day_data.get('running_date_val')
                dir_value = self.calculate_dir(date_sh_val, release_date_val)
                
                # Apply DIR constraint: First weekend uses DIR values -1, 1, 2
                # DIR = date_sh - release_date (if date_sh < release_date) or date_sh - release_date + 1 (if date_sh >= release_date)
                # Only store records within first weekend range (DIR -1, 1, 2)
                # OR records with valid DBR <= 2 (presales)
                dir_valid = dir_value in [-1, 1, 2]
                
                # Calculate DBR from running_date
                # DBR = Running Date - Release Date (negative values for presales)
                # Store DBR for all presales records (date_sh < release_date)
                dbr_value = None
                dbr_valid = False
                if running_date_val:
                    dbr_value = self.calculate_dbr(running_date_val, release_date_val)
                    # DBR is valid if it's negative (presales) and date_sh is before release
                    # This ensures we capture all presales data
                    if dbr_value is not None and dbr_value < 0 and date_sh_val < release_date_val:
                        dbr_valid = True
                    else:
                        dbr_value = None  # Don't store DBR if not presales
                
                # Only store records that meet at least one constraint:
                # - DIR is -1, 1, 2 (first weekend), OR
                # - DBR is valid (presales, date_sh < release_date)
                if not dir_valid and not dbr_valid:
                    # Skip records that don't meet either constraint
                    records_filtered_out += 1
                    continue
                
                records_processed += 1
                
                total_reserved = day_data['total_reserved'] or 0
                total_seats = day_data['total_seats'] or 0
                total_revenue = day_data['total_revenue'] or Decimal('0')
                avg_price = day_data['avg_price'] or Decimal('0')
                total_checkered = day_data.get('total_checkered', 0) or 0
                
                # Calculate occupancy rate: impressions/(total_seats - checkered)
                # where impressions = reserved (they are the same)
                occupancy_rate = None
                available = total_seats - total_checkered
                if available > 0:
                    occupancy_rate = (float(total_reserved) / float(available)) * 100
                
                # Calculate DoD metrics by comparing with previous day
                dod_revenue_change = None
                dod_reserved_change = None
                
                if dir_value >= -1:  # Only calculate DoD for release date onwards
                    prev_day = date_sh_val - timedelta(days=1)
                    prev_day_perf = MovieDailyPerformance.objects.filter(
                        title__iexact=title_str,
                        release_date=release_date_val,
                        date_sh=prev_day
                    ).first()
                    
                    if prev_day_perf and prev_day_perf.total_revenue > 0:
                        # DoD Revenue change
                        revenue_diff = float(total_revenue) - float(prev_day_perf.total_revenue)
                        dod_revenue_change = (revenue_diff / float(prev_day_perf.total_revenue)) * 100
                        
                        # DoD Reserved change
                        if prev_day_perf.total_reserved_seats > 0:
                            reserved_diff = total_reserved - prev_day_perf.total_reserved_seats
                            dod_reserved_change = (reserved_diff / prev_day_perf.total_reserved_seats) * 100
                
                # Get or create performance record
                # Note: We may have multiple records for same date_sh but different running_date (different DBR)
                # For aggregation purposes, we'll use date_sh as primary key but track DBR separately
                # If same date_sh has multiple DBR values, we'll combine them
                
                # Check if we already have a record for this date_sh
                existing_perf = MovieDailyPerformance.objects.filter(
                    title__iexact=title_str,
                    release_date=release_date_val,
                    date_sh=date_sh_val
                ).first()
                
                if existing_perf:
                    # Update existing record, adding to totals if needed
                    # If same date_sh has multiple running_date dates, combine them
                    existing_perf.total_reserved_seats += total_reserved
                    existing_perf.total_impressions += total_reserved
                    existing_perf.total_revenue += total_revenue
                    existing_perf.total_seats += total_seats
                    # Update DBR if this one is more negative (further before release)
                    if dbr_value and (existing_perf.dbr_value is None or dbr_value < existing_perf.dbr_value):
                        existing_perf.dbr_value = dbr_value
                    # Recalculate average price
                    total_price_sum = (existing_perf.avg_price * existing_perf.total_reserved_seats) + (avg_price * total_reserved)
                    existing_perf.avg_price = total_price_sum / existing_perf.total_reserved_seats if existing_perf.total_reserved_seats > 0 else avg_price
                    existing_perf.save()
                    performance_obj = existing_perf
                    created = False
                else:
                    # Create new record
                    performance_obj = MovieDailyPerformance.objects.create(
                        title=title_str,
                        release_date=release_date_val,
                        date_sh=date_sh_val,
                        dir_value=dir_value,
                        dbr_value=dbr_value,
                        total_reserved_seats=total_reserved,
                        total_impressions=total_reserved,
                        total_revenue=total_revenue,
                        total_seats=total_seats,
                        dod_revenue_change=dod_revenue_change,
                        dod_reserved_change=dod_reserved_change,
                        avg_price=avg_price,
                        occupancy_rate=occupancy_rate,
                    )
                    created = True
                
                if created:
                    created_count += 1
                    movie_created_count += 1
            
            # Calculate cumulative metrics in a separate efficient query
            self._update_cumulative_metrics(title_str, release_date_val)
            
            # Calculate total records for this specific movie
            movie_total_records = MovieDailyPerformance.objects.filter(
                title__iexact=title_str,
                release_date=release_date_val
            ).count()
            total_records_after_processing[(title_str, release_date_val)] = movie_total_records
            
            logger.info(f"✅ Created {movie_created_count} new records, {movie_total_records} total records for '{title_str}' ({release_date_val})")
            if records_filtered_out > 0:
                logger.info(f"   📋 Summary: {total_movie_records} movie records found, {records_processed} passed DIR/DBR filters, {records_filtered_out} filtered out")
                if movie_total_records == 0 and records_filtered_out > 0:
                    logger.warning(f"   ⚠️  All records filtered out! This movie's dates don't meet DIR [-1,1,2] or valid DBR constraints.")
        
        # Calculate total records
        if title:
            # For specific movie query, return the count for the last movie processed
            if total_records_after_processing:
                # Get the last entry (should be the only one for a single title query)
                final_total = list(total_records_after_processing.values())[-1] if total_records_after_processing else 0
            else:
                final_total = 0
        else:
            # For all movies, return total count
            final_total = MovieDailyPerformance.objects.count()
        
        # Show warning if no records created for a specific movie query
        if title and final_total == 0 and created_count == 0:
            logger.warning(f"⚠️  No performance records created for '{title}'. Possible reasons:")
            logger.warning(f"   - Movie records don't have date_sh values with DIR in [-1, 1, 2] (first weekend)")
            logger.warning(f"   - Movie records don't have valid DBR (presales: running_date < release_date, date_sh < release_date)")
            logger.warning(f"   - All records may already exist (updates don't count as 'created')")
        
        return created_count
    
    @transaction.atomic
    def _update_cumulative_metrics(self, title: str, release_date: date):
        """
        Update cumulative revenue and reserved seats correctly.
        
        IMPORTANT: Cumulative presales should only include DBR records where date_sh < release_date.
        This ensures presales cumulative is calculated correctly and doesn't include post-release data.
        
        Process:
        1. Calculate presales cumulative (DBR records, date_sh < release_date, ordered by DBR)
        2. First Weekend Revenue records (DIR -1, 1, 2) don't need cumulative (they're daily revenue)
        3. Ensure cumulative is monotonic (always increases or stays same)
        """
        # Step 1: Get all presales records (DBR records where date_sh < release_date)
        # These should have cumulative_revenue calculated from daily revenue
        presales_performances = (
            MovieDailyPerformance.objects
            .filter(
                title__iexact=title,
                release_date=release_date,
                dbr_value__isnull=False,
                date_sh__lt=release_date  # Only presales (before release)
            )
            .order_by('dbr_value')  # Order by DBR (most negative to least negative)
        )
        
        # Step 2: Calculate presales cumulative from daily revenue
        # This ensures cumulative is presales-only and monotonic
        cumulative_revenue = Decimal('0')
        cumulative_reserved = 0
        max_cumulative_so_far = Decimal('0')
        
        presales_updates = []
        for perf in presales_performances:
            # Add daily revenue to cumulative
            cumulative_revenue += perf.total_revenue
            cumulative_reserved += perf.total_reserved_seats
            
            # Ensure monotonicity (should never decrease as DBR becomes less negative)
            if cumulative_revenue < max_cumulative_so_far:
                # Data issue: use previous maximum
                cumulative_revenue = max_cumulative_so_far
            else:
                max_cumulative_so_far = cumulative_revenue
            
            perf.cumulative_revenue = cumulative_revenue
            perf.cumulative_reserved = cumulative_reserved
            presales_updates.append(perf)
        
        # Step 3: For First Weekend records (DIR -1, 1, 2), cumulative_revenue should be 0
        # These are post-release daily revenue, not cumulative presales
        # We set cumulative to 0 to indicate these are not presales cumulative values
        first_weekend_performances = (
            MovieDailyPerformance.objects
            .filter(
                title__iexact=title,
                release_date=release_date,
                dir_value__in=[-1, 1, 2]
            )
        )
        
        # First Weekend records are daily revenue, not cumulative presales
        # Set cumulative to 0 to avoid confusion with presales cumulative
        first_weekend_updates = []
        for perf in first_weekend_performances:
            # DIR records are daily revenue, not cumulative presales
            # Set cumulative to 0 to indicate it's not a presales cumulative value
            perf.cumulative_revenue = Decimal('0')
            perf.cumulative_reserved = 0
            first_weekend_updates.append(perf)
        
        # Bulk update all records
        all_updates = presales_updates + first_weekend_updates
        if all_updates:
            MovieDailyPerformance.objects.bulk_update(
                all_updates,
                ['cumulative_revenue', 'cumulative_reserved'],
                batch_size=1000
            )
    
    def get_movie_performance_by_period(
        self,
        title: str,
        period_label: str = 'first_weekend',
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Get movie performance for a specific period (e.g., first weekend).
        Uses cached MovieDailyPerformance table for fast queries.
        
        Args:
            title: Movie title
            period_label: Period identifier (first_weekend, first_week, etc.)
            use_cache: Whether to use pre-calculated cache
            
        Returns:
            Dict with performance metrics
        """
        # Get DIR range for period
        start_dir, end_dir = self.get_period_dir_range(period_label)
        
        # For first_weekend, use raw SQL to match exact SQL logic
        # SQL uses: (date_sh - release_date) BETWEEN -1 AND 1, which translates to DIR -1, 1, 2
        # DIR formula: if date_sh < release_date: DIR = date_sh - release_date, else: DIR = date_sh - release_date + 1
        if period_label == 'first_weekend':
            from django.db import connection
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        MIN(release_date) AS release_date,
                        SUM(reserved) as total_reserved,
                        SUM(price * reserved) as total_revenue,
                        AVG(price) as avg_price,
                        SUM(total_seats) as total_seats,
                        SUM(checkered) as total_checkered
                    FROM movies
                    WHERE UPPER(title) = UPPER(%s)
                    AND (date_sh - release_date) BETWEEN -1 AND 1
                """, [title])
                
                row = cursor.fetchone()
                if not row or not row[0]:
                    return {'error': f'No first weekend data found for "{title}"'}
                
                release_date = row[0]
                total_reserved = int(row[1] or 0)
                total_revenue = Decimal(str(row[2] or 0))
                avg_price = Decimal(str(row[3] or 0))
                total_seats = int(row[4] or 0)
                total_checkered = int(row[5] or 0)
                
                available = total_seats - total_checkered
                occupancy_rate = (float(total_reserved) / float(available)) * 100 if available > 0 else 0.0
                
                return {
                    'title': title,
                    'release_date': release_date,
                    'period': period_label,
                    'dir_range': (-1, 2),  # SQL uses date_diff -1 to 1, which is DIR -1, 1, 2
                    'total_revenue': total_revenue,
                    'total_reserved_seats': total_reserved,
                    'total_impressions': total_reserved,
                    'avg_price': avg_price,
                    'avg_occupancy_rate': occupancy_rate,
                }
        
        if use_cache:
            # Fast query using pre-calculated table for other periods
            performances = (
                MovieDailyPerformance.objects
                .filter(
                    title__iexact=title,
                    dir_value__gte=start_dir,
                    dir_value__lte=end_dir
                )
                .aggregate(
                    total_revenue=Sum('total_revenue'),
                    total_reserved=Sum('total_reserved_seats'),
                    total_impressions=Sum('total_impressions'),
                    avg_price=Avg('avg_price'),
                    avg_occupancy=Avg('occupancy_rate')
                )
            )
            
            # Get release date
            release_date = (
                MovieDailyPerformance.objects
                .filter(title__iexact=title)
                .values_list('release_date', flat=True)
                .first()
            )
            
            return {
                'title': title,
                'release_date': release_date,
                'period': period_label,
                'dir_range': (start_dir, end_dir),
                'total_revenue': performances['total_revenue'] or Decimal('0'),
                'total_reserved_seats': performances['total_reserved'] or 0,
                'total_impressions': performances['total_impressions'] or 0,
                'avg_price': performances['avg_price'] or Decimal('0'),
                'avg_occupancy_rate': performances['avg_occupancy'] or 0.0,
            }
        else:
            # Fallback to direct calculation from Movie table
            return self._calculate_performance_from_raw_data(title, start_dir, end_dir)
    
    def _calculate_performance_from_raw_data(
        self,
        title: str,
        start_dir: int,
        end_dir: int
    ) -> Dict[str, Any]:
        """
        Calculate performance directly from Movie table (fallback method).
        Less efficient but doesn't require pre-calculation.
        """
        # Get release date
        release_date = (
            Movie.objects
            .filter(title__iexact=title)
            .values_list('release_date', flat=True)
            .first()
        )
        
        if not release_date:
            return {'error': 'Movie not found'}
        
        # Calculate date range
        if start_dir < 0:
            start_date = release_date + timedelta(days=start_dir)
        else:
            start_date = release_date + timedelta(days=start_dir - 1)
        
        end_date = release_date + timedelta(days=end_dir - 1)
        
        # Aggregate using raw SQL with safe casting
        from django.db import connection
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        SUM(reserved) as total_reserved,
                        SUM(total_seats) as total_seats,
                        SUM(price * reserved) as total_revenue,
                        AVG(price) as avg_price,
                        SUM(checkered) as total_checkered
                    FROM movies
                    WHERE UPPER(title) = UPPER(%s)
                    AND release_date = %s
                    AND date_sh >= %s
                    AND date_sh <= %s
                """, [title, release_date, start_date, end_date])
                
                row = cursor.fetchone()
                if row:
                    results = {
                        'total_reserved': int(row[0] or 0),
                        'total_seats': int(row[1] or 0),
                        'total_revenue': Decimal(str(row[2] or 0)),
                        'avg_price': Decimal(str(row[3] or 0)),
                        'total_checkered': int(row[4] or 0)
                    }
                else:
                    results = {
                        'total_reserved': 0,
                        'total_seats': 0,
                        'total_revenue': Decimal('0'),
                        'avg_price': Decimal('0'),
                        'total_checkered': 0
                    }
        except Exception as e:
            logger.warning(f"Database aggregation failed in fallback method: {e}. Using Python-level processing.")
            # Fall back to Python processing
            records = list(Movie.objects.filter(
                title__iexact=title,
                release_date=release_date,
                date_sh__gte=start_date,
                date_sh__lte=end_date
            ).values('reserved', 'price', 'total_seats', 'checkered'))
            
            total_revenue = Decimal('0')
            total_reserved = 0
            total_seats = 0
            total_checkered = 0
            prices = []
            
            for record in records:
                reserved_val = int(record['reserved']) if record['reserved'] is not None else 0
                price_val = Decimal(str(record['price'])) if record['price'] else Decimal('0')
                
                total_revenue += price_val * Decimal(str(reserved_val))
                total_reserved += reserved_val
                total_seats += record.get('total_seats', 0) or 0
                total_checkered += record.get('checkered', 0) or 0
                if price_val:
                    prices.append(price_val)
            
            avg_price = sum(prices) / len(prices) if prices else Decimal('0')
            
            results = {
                'total_revenue': total_revenue,
                'total_reserved': total_reserved,
                'total_seats': total_seats,
                'avg_price': avg_price,
                'total_checkered': total_checkered
            }
        
        total_revenue = results['total_revenue'] or Decimal('0')
        total_reserved = results['total_reserved'] or 0
        total_seats = results['total_seats'] or 0
        avg_price = results['avg_price'] or Decimal('0')
        total_checkered = results.get('total_checkered', 0) or 0
        
        occupancy_rate = None
        available = total_seats - total_checkered
        if available > 0:
            occupancy_rate = (float(total_reserved) / float(available)) * 100
        
        return {
            'title': title,
            'release_date': release_date,
            'dir_range': (start_dir, end_dir),
            'total_revenue': total_revenue,
            'total_reserved_seats': total_reserved,
            'total_impressions': total_reserved,
            'avg_price': avg_price,
            'avg_occupancy_rate': occupancy_rate or 0.0,
        }
    
    def _get_canonical_release_date(self, title: str) -> Optional[date]:
        """
        Determine the primary release date for a title.
        Prefers the release with the highest first weekend revenue (DIR -1, 1, 2).
        Falls back to the earliest release date if first weekend data is missing.
        """
        # 1) Prefer release dates from Movie table (full showtime data)
        release_dates = list(
            Movie.objects
            .filter(title__iexact=title)
            .values_list('release_date', flat=True)
            .distinct()
        )
        
        # 2) If Movie table has no entry for this title (CSV-only title),
        #    fall back to MovieDailyPerformance, which is populated from
        #    AI_Data_Dump_All_Titles.
        if not release_dates:
            release_dates = list(
                MovieDailyPerformance.objects
                .filter(title__iexact=title)
                .values_list('release_date', flat=True)
                .distinct()
            )
        
        release_dates = sorted([rd for rd in release_dates if rd])
        if not release_dates:
            return None
        
        fw_totals = (
            MovieDailyPerformance.objects
            .filter(
                title__iexact=title,
                release_date__in=release_dates,
                dir_value__in=[-1, 1, 2]
            )
            .values('release_date')
            .annotate(total=Sum('total_revenue'))
        )
        
        totals_map = {row['release_date']: row['total'] or Decimal('0') for row in fw_totals}
        if totals_map:
            max_total = max(totals_map.values())
            if max_total > 0:
                candidates = [rd for rd in release_dates if totals_map.get(rd, Decimal('0')) == max_total]
                if candidates:
                    return min(candidates)
        
        return release_dates[0]
    
    def get_day_by_day_trend(
        self,
        title: str,
        start_dir: Optional[int] = None,
        end_dir: Optional[int] = None,
        use_cache: bool = True,
        release_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Get day-by-day performance trend for a movie.
        
        Args:
            title: Movie title
            start_dir: Starting DIR (default: -1 for first weekend start)
            end_dir: Ending DIR (default: 2 for first weekend end)
            use_cache: Whether to use cached data
            
        Returns:
            List of daily performance dictionaries
        """
        if start_dir is None:
            start_dir = -1
        if end_dir is None:
            end_dir = 2
        
        if release_date is None:
            release_date = self._get_canonical_release_date(title)
        if not release_date:
            return []
        
        if use_cache:
            # Apply DIR constraint: First weekend uses DIR values -1, 1, 2
            # DIR = date_sh - release_date (if date_sh < release_date) or date_sh - release_date + 1 (if date_sh >= release_date)
            performances = (
                MovieDailyPerformance.objects
                .filter(
                    title__iexact=title,
                    release_date=release_date,
                    dir_value__in=[-1, 1, 2]  # Constraint: DIR -1, 1, 2 (first weekend)
                )
                .filter(
                    dir_value__gte=start_dir if start_dir is not None else -1,
                    dir_value__lte=end_dir if end_dir is not None else 2
                )
                .order_by('dir_value')
                .values(
                    'dir_value',
                    'date_sh',
                    'total_revenue',
                    'total_reserved_seats',
                    'dod_revenue_change',
                    'dod_reserved_change',
                    'avg_price',
                    'occupancy_rate'
                )
            )
            
            return list(performances)
        else:
            # Calculate from raw data
            return self._calculate_day_by_day_from_raw(title, start_dir, end_dir, release_date)
    
    def get_day_by_day_dbr_trend(
        self,
        title: str,
        start_dbr: Optional[int] = None,
        end_dbr: Optional[int] = None,
        use_cache: bool = True,
        release_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Get day-by-day presales trend for a movie based on DBR (Days Before Release).
        Trends flow from maximum negative DBR to minimum negative DBR (e.g., -60 → -1),
        representing cumulative presales as release date approaches.
        
        Args:
            title: Movie title
            start_dbr: Starting DBR (if None, uses maximum available negative DBR in data)
            end_dbr: Ending DBR (if None, uses minimum available negative DBR in data, typically -1)
            use_cache: Whether to use cached data
            
        Returns:
            List of daily presales dictionaries, ordered from maximum negative DBR to minimum negative DBR
        """
        if release_date is None:
            release_date = self._get_canonical_release_date(title)
        if not release_date:
            return []
        
        if use_cache:
            
            # First, find the actual DBR range available for this movie
            # IMPORTANT: Only presales data (DBR < 0 and date_sh < release_date)
            dbr_range = (
                MovieDailyPerformance.objects
                .filter(
                    title__iexact=title, 
                    release_date=release_date,
                    dbr_value__isnull=False,
                    dbr_value__lt=0,  # Only presales (DBR must be negative)
                    date_sh__lt=release_date  # Only records before release date
                )
                .aggregate(
                    min_dbr=Min('dbr_value'),
                    max_dbr=Max('dbr_value')
                )
            )
            
            # If no DBR data found, return empty list
            if dbr_range['min_dbr'] is None or dbr_range['max_dbr'] is None:
                return []
            
            # Use available range if not specified, otherwise use provided range
            actual_start_dbr = start_dbr if start_dbr is not None else dbr_range['max_dbr']  # Most negative (e.g., -60)
            actual_end_dbr = end_dbr if end_dbr is not None else dbr_range['min_dbr']  # Least negative (e.g., -1)
            
            # Ensure start_dbr is more negative than end_dbr (start < end for negative numbers)
            if actual_start_dbr > actual_end_dbr:
                actual_start_dbr, actual_end_dbr = actual_end_dbr, actual_start_dbr
            
            # Only presales (DBR must be negative)
            if actual_end_dbr >= 0:
                actual_end_dbr = -1
            
            performances = (
                MovieDailyPerformance.objects
                .filter(
                    title__iexact=title,
                    release_date=release_date,
                    dbr_value__isnull=False,
                    dbr_value__gte=actual_start_dbr,  # More negative (e.g., -60)
                    dbr_value__lte=actual_end_dbr,  # Less negative (e.g., -1), but must be negative
                    date_sh__lt=release_date  # Only presales (before release date)
                )
                .order_by('dbr_value')  # Ascending: -60, -59, ..., -1
                .values(
                    'dbr_value',
                    'date_sh',
                    'total_revenue',
                    'total_reserved_seats',
                    'cumulative_revenue',
                    'cumulative_reserved',
                    'dod_revenue_change',
                    'dod_reserved_change',
                    'avg_price',
                    'occupancy_rate'
                )
            )
            
            return list(performances)
        else:
            # Use get_cumulative_advance_booking as fallback for raw data
            # For raw data, use provided range or default to reasonable range
            if start_dbr is None:
                start_dbr = -60  # Default to wider range
            if end_dbr is None:
                end_dbr = -1
            
            try:
                result = self.get_cumulative_advance_booking(title, start_dbr, end_dbr, release_date)
                if 'error' in result:
                    return []
                return result.get('daily_data', [])
            except Exception as e:
                logger.warning(f"Error fetching DBR trend from raw data: {e}")
                return []
    
    def _calculate_day_by_day_from_raw(
        self,
        title: str,
        start_dir: int,
        end_dir: int,
        release_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """Calculate day-by-day from raw Movie table."""
        if release_date is None:
            release_date = self._get_canonical_release_date(title)
        if not release_date:
            return []
        
        results = []
        
        # Reverse calculate date_sh from DIR value:
        # If DIR < 0: date_sh = release_date + DIR (since DIR = date_sh - release_date)
        # If DIR >= 0: date_sh = release_date + (DIR - 1) (since DIR = (date_sh - release_date) + 1)
        # Examples: DIR=-1 → date_sh = release_date - 1, DIR=1 → date_sh = release_date, DIR=2 → date_sh = release_date + 1
        for dir_val in range(start_dir, end_dir + 1):
            if dir_val < 0:
                date_sh_val = release_date + timedelta(days=dir_val)
            else:
                date_sh_val = release_date + timedelta(days=dir_val - 1)
            
            # Use raw SQL for consistency and to handle edge cases
            from django.db import connection
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            SUM(reserved) as total_reserved,
                            SUM(total_seats) as total_seats,
                            SUM(price * reserved) as total_revenue,
                            AVG(price) as avg_price,
                            SUM(checkered) as total_checkered
                        FROM movies
                        WHERE UPPER(title) = UPPER(%s)
                        AND release_date = %s
                        AND date_sh = %s
                    """, [title, release_date, date_sh_val])
                    
                    row = cursor.fetchone()
                    if row:
                        daily_data = {
                            'total_reserved': int(row[0] or 0),
                            'total_seats': int(row[1] or 0),
                            'total_revenue': Decimal(str(row[2] or 0)),
                            'avg_price': Decimal(str(row[3] or 0)),
                            'total_checkered': int(row[4] or 0)
                        }
                    else:
                        daily_data = {
                            'total_reserved': 0,
                            'total_seats': 0,
                            'total_revenue': Decimal('0'),
                            'avg_price': Decimal('0'),
                            'total_checkered': 0
                        }
            except Exception as e:
                logger.warning(f"Day-by-day calculation failed: {e}")
                daily_data = {
                    'total_reserved': 0,
                    'total_seats': 0,
                    'total_revenue': Decimal('0'),
                    'avg_price': Decimal('0'),
                    'total_checkered': 0
                }
            
            total_revenue = daily_data['total_revenue'] or Decimal('0')
            total_reserved = daily_data['total_reserved'] or 0
            total_seats = daily_data['total_seats'] or 0
            avg_price = daily_data['avg_price'] or Decimal('0')
            total_checkered = daily_data['total_checkered'] or 0
            
            occupancy_rate = None
            available = total_seats - total_checkered
            if available > 0:
                occupancy_rate = (float(total_reserved) / float(available)) * 100
            
            results.append({
                'dir_value': dir_val,
                'date_sh': date_sh_val,
                'total_revenue': total_revenue,
                'total_reserved_seats': total_reserved,
                'dod_revenue_change': None,  # Would need previous day data
                'dod_reserved_change': None,
                'avg_price': avg_price,
                'occupancy_rate': occupancy_rate
            })
        
        return results
    
    def compare_movies_performance(
        self,
        title1: str,
        title2: str,
        period_label: str = 'first_weekend',
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Compare performance between two movies for a given period.
        
        Args:
            title1: First movie title
            title2: Second movie title
            period_label: Period to compare
            use_cache: Use cached comparison data if available
            
        Returns:
            Comparison dictionary
        """
        start_dir, end_dir = self.get_period_dir_range(period_label)
        
        if use_cache:
            # Check if comparison exists
            comparison = MoviePerformanceComparison.objects.filter(
                title1__iexact=title1,
                title2__iexact=title2,
                period_label=period_label
            ).first()
            
            if comparison:
                return {
                    'title1': title1,
                    'title2': title2,
                    'period': period_label,
                    'dir_range': (comparison.dir_range_start, comparison.dir_range_end),
                    'title1_total_revenue': comparison.title1_total_revenue,
                    'title2_total_revenue': comparison.title2_total_revenue,
                    'title1_total_reserved': comparison.title1_total_reserved,
                    'title2_total_reserved': comparison.title2_total_reserved,
                    'revenue_difference': comparison.revenue_difference,
                    'revenue_difference_percent': comparison.revenue_difference_percent,
                }
        
        # Calculate comparison
        perf1 = self.get_movie_performance_by_period(title1, period_label, use_cache)
        perf2 = self.get_movie_performance_by_period(title2, period_label, use_cache)
        
        if 'error' in perf1 or 'error' in perf2:
            return {'error': 'One or both movies not found'}
        
        revenue1 = perf1['total_revenue']
        revenue2 = perf2['total_revenue']
        
        revenue_diff = revenue1 - revenue2
        revenue_diff_pct = None
        if revenue2 > 0:
            revenue_diff_pct = (float(revenue_diff) / float(revenue2)) * 100
        
        # Cache the comparison
        if use_cache and 'release_date' in perf1 and 'release_date' in perf2:
            MoviePerformanceComparison.objects.update_or_create(
                title1=title1,
                title2=title2,
                period_label=period_label,
                defaults={
                    'release_date1': perf1['release_date'],
                    'release_date2': perf2['release_date'],
                    'dir_range_start': start_dir,
                    'dir_range_end': end_dir,
                    'title1_total_revenue': revenue1,
                    'title2_total_revenue': revenue2,
                    'title1_total_reserved': perf1['total_reserved_seats'],
                    'title2_total_reserved': perf2['total_reserved_seats'],
                    'revenue_difference': revenue_diff,
                    'revenue_difference_percent': revenue_diff_pct,
                }
            )
        
        return {
            'title1': title1,
            'title2': title2,
            'period': period_label,
            'dir_range': (start_dir, end_dir),
            'title1_total_revenue': revenue1,
            'title2_total_revenue': revenue2,
            'title1_total_reserved': perf1['total_reserved_seats'],
            'title2_total_reserved': perf2['total_reserved_seats'],
            'revenue_difference': revenue_diff,
            'revenue_difference_percent': revenue_diff_pct,
        }
    
    def get_current_first_weekend_movies(self) -> List[Dict[str, Any]]:
        """
        Get all movies currently in their first weekend (DIR -1 to DIR 2).
        Uses efficient query on cached table.
        
        Returns:
            List of movies with first weekend data including additional metrics
        """
        from django.db.models import Sum, Avg, Max
        
        performances = (
            MovieDailyPerformance.objects
            .filter(dir_value__in=[-1, 1, 2])  # First Weekend: DIR -1, 1, 2
            .values('title', 'release_date')
            .distinct()
            .annotate(
                first_weekend_revenue=Sum('total_revenue'),
                first_weekend_reserved=Sum('total_reserved_seats'),
                first_weekend_impressions=Sum('total_impressions'),
                avg_price=Avg('avg_price'),
                avg_occupancy=Avg('occupancy_rate')
            )
            .order_by('-first_weekend_revenue')
        )
        
        # Enhance with genre and studio info from Movie model
        enhanced_list = []
        for perf in performances:
            try:
                # Get first movie record for metadata
                movie_sample = Movie.objects.filter(
                    title=perf['title'],
                    release_date=perf['release_date']
                ).first()
                
                enhanced_perf = dict(perf)
                if movie_sample:
                    enhanced_perf['genre'] = movie_sample.genre
                    enhanced_perf['studio_name'] = movie_sample.studio_name
                    enhanced_perf['rating'] = movie_sample.rating
                else:
                    enhanced_perf['genre'] = None
                    enhanced_perf['studio_name'] = None
                    enhanced_perf['rating'] = None
                
                enhanced_list.append(enhanced_perf)
            except Exception:
                enhanced_list.append(perf)
        
        return enhanced_list
    
    def get_advance_bookings(
        self,
        title: str,
        dbr_threshold: int = 0
    ) -> Dict[str, Any]:
        """
        Get advance booking data for a movie up to DBR threshold.
        Uses raw Movie table for accurate DBR calculation since DBR varies by running_date.
        
        Args:
            title: Movie title
            dbr_threshold: Maximum DBR to include. 
                - If 0: Returns all advance bookings (DBR < 0) - matches SQL: DBR < 0
                - If negative (e.g., -7): Returns DBR <= threshold (e.g., DBR <= -7)
            
        Returns:
            Advance booking metrics
        """
        from django.db import connection
        
        # Query directly from Movie table to get accurate DBR-based aggregations
        # DBR is calculated from running_date, which varies per record
        # SQL uses: DBR < 0 for "total advance reservations"
        # If threshold is 0, use < 0 (strictly less than, all advance bookings)
        # If threshold is negative, use <= threshold (less than or equal)
        comparison_op = "<" if dbr_threshold == 0 else "<="
        
        with connection.cursor() as cursor:
            # For "total advance reservations", match expected SQL exactly:
            # No filters on price/reserved being valid, just SUM(reserved) where DBR < 0
            if dbr_threshold == 0:
                # Match expected SQL: SELECT SUM(reserved) WHERE DBR < 0 (no filters)
                cursor.execute("""
                    SELECT 
                        COALESCE(SUM(reserved), 0) as total_reserved,
                        COALESCE(SUM(price * reserved), 0) as total_revenue
                    FROM movies
                    WHERE UPPER(title) = UPPER(%s)
                    AND (
                        CASE 
                            WHEN (running_date::date - release_date) < 0 
                            THEN (running_date::date - release_date)
                            WHEN (running_date::date - release_date) >= 0 
                            THEN (running_date::date - release_date) + 1
                        END
                    ) < 0
                """, [title])
            else:
                # For specific DBR threshold, no filters
                cursor.execute(f"""
                    SELECT 
                        SUM(reserved) as total_reserved,
                        SUM(price * reserved) as total_revenue
                    FROM movies
                    WHERE UPPER(title) = UPPER(%s)
                    AND (
                        CASE 
                            WHEN (running_date::date - release_date) < 0 
                            THEN (running_date::date - release_date)
                            WHEN (running_date::date - release_date) >= 0 
                            THEN (running_date::date - release_date) + 1
                        END
                    ) {comparison_op} %s
                """, [title, dbr_threshold])
            
            row = cursor.fetchone()
            total_reserved = int(row[0] or 0)
            total_revenue = Decimal(str(row[1] or 0))
        
        return {
            'title': title,
            'dbr_threshold': dbr_threshold,
            'total_advance_reservations': total_reserved,
            'total_advance_revenue': total_revenue,
        }
    
    def compare_all_movies_first_weekend(self) -> List[Dict[str, Any]]:
        """
        Compare first weekend revenue for all movies.
        First Weekend Revenue = sum of total_revenue for DIR -1, 1, 2 only.
        
        SQL logic: (date_sh - release_date) BETWEEN -1 AND 1
        Which translates to DIR values: -1, 1, 2 (DIR = diff + 1 when diff >= 0)
        """
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    title,
                    MIN(release_date) AS release_date,
                    ROUND(SUM(price * reserved), 2) AS first_weekend_revenue
                FROM movies
                WHERE (date_sh - release_date) BETWEEN -1 AND 1
                GROUP BY title
                ORDER BY first_weekend_revenue DESC
            """)
            
            columns = [col[0] for col in cursor.description]
            movies_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return movies_data
    
    def get_movies_by_dbr_range(self, dbr_min: int = -7, dbr_max: int = 0) -> List[Dict[str, Any]]:
        """Get movies with DBR in specified range."""
        from django.db import connection
        
        # Use raw SQL to get distinct movies with DBR in range (not just one per movie)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT 
                    title, 
                    release_date,
                    dbr_value
                FROM movie_daily_performance
                WHERE dbr_value IS NOT NULL
                AND dbr_value >= %s
                AND dbr_value <= %s
                ORDER BY title, dbr_value
            """, [dbr_min, dbr_max])
            
            columns = [col[0] for col in cursor.description]
            movies_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return movies_data
    
    def compare_dir_ranges(self, movie_title: str, dir_range1: Tuple[int, int], 
                         dir_range2: Tuple[int, int]) -> Dict[str, Any]:
        """Compare performance between two DIR ranges for a movie using raw SQL for accuracy."""
        from django.db import connection
        
        with connection.cursor() as cursor:
            # Use raw SQL to calculate DIR properly and get accurate revenue
            # DIR Formula:
            #   If (date_sh < release_date): DIR = date_sh - release_date (negative)
            #   If (date_sh >= release_date): DIR = date_sh - release_date + 1 (starting from 1 on release day)
            cursor.execute("""
                WITH dir_calc AS (
                    SELECT title, release_date, date_sh, reserved, price
                    FROM movies
                    WHERE UPPER(title) = UPPER(%s)
                ),
                dir_with_calc AS (
                    SELECT *,
                    CASE
                        WHEN (date_sh - release_date) < 0
                        THEN (date_sh - release_date)
                        WHEN (date_sh - release_date) >= 0
                        THEN (date_sh - release_date) + 1
                    END AS DIR
                    FROM dir_calc
                )
                SELECT
                    CASE
                        WHEN DIR BETWEEN %s AND %s THEN 'range1'
                        WHEN DIR BETWEEN %s AND %s THEN 'range2'
                    END AS dir_range,
                    SUM(price * reserved) AS revenue,
                    SUM(reserved) AS reserved_seats
                FROM dir_with_calc
                WHERE DIR BETWEEN %s AND %s
                    OR DIR BETWEEN %s AND %s
                GROUP BY
                    CASE
                        WHEN DIR BETWEEN %s AND %s THEN 'range1'
                        WHEN DIR BETWEEN %s AND %s THEN 'range2'
                    END
            """, [
                movie_title,
                dir_range1[0], dir_range1[1],  # Range 1 DIR boundaries
                dir_range2[0], dir_range2[1],  # Range 2 DIR boundaries
                dir_range1[0], dir_range1[1],  # WHERE range 1
                dir_range2[0], dir_range2[1],  # WHERE range 2
                dir_range1[0], dir_range1[1],  # GROUP BY range 1
                dir_range2[0], dir_range2[1]   # GROUP BY range 2
            ])
            
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            
            if not rows:
                return {'error': 'Movie not found'}
            
            # Parse results
            rev1 = Decimal('0')
            rev2 = Decimal('0')
            res1 = 0
            res2 = 0
            
            for row in rows:
                row_dict = dict(zip(columns, row))
                if row_dict['dir_range'] == 'range1':
                    rev1 = Decimal(str(row_dict['revenue'] or 0))
                    res1 = int(row_dict['reserved_seats'] or 0)
                elif row_dict['dir_range'] == 'range2':
                    rev2 = Decimal(str(row_dict['revenue'] or 0))
                    res2 = int(row_dict['reserved_seats'] or 0)
            
            diff = rev1 - rev2
            diff_pct = (float(diff) / float(rev2)) * 100 if rev2 > 0 else 0
            
            return {
                'range1_revenue': rev1,
                'range1_reserved': res1,
                'range2_revenue': rev2,
                'range2_reserved': res2,
                'revenue_difference': diff,
                'revenue_difference_percent': diff_pct
            }
    
    def get_highest_advance_booking(self, dbr_threshold: int = -7) -> Dict[str, Any]:
        """
        Get movie with highest advance bookings up to DBR threshold.
        Uses SQL logic: DBR < threshold (strictly less than, as per user's SQL).
        """
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    title, 
                    MIN(release_date) AS release_date,
                    SUM(reserved) AS total_advance_bookings,
                    SUM(price * reserved) AS total_advance_revenue
                FROM movies
                WHERE (
                    CASE 
                        WHEN (running_date::date - release_date) < 0 
                        THEN (running_date::date - release_date)
                        WHEN (running_date::date - release_date) >= 0 
                        THEN (running_date::date - release_date) + 1
                    END
                ) < %s
                GROUP BY title
                ORDER BY total_advance_bookings DESC
                LIMIT 1
            """, [dbr_threshold])
            
            row = cursor.fetchone()
            if not row:
                return {'error': 'No advance booking data found'}
            
            columns = [col[0] for col in cursor.description]
            result = dict(zip(columns, row))
        
        return {
            'title': result['title'],
            'release_date': result['release_date'],
            'total_advance_bookings': int(result['total_advance_bookings'] or 0),
            'total_advance_revenue': Decimal(str(result.get('total_advance_revenue') or 0))
        }
    
    def get_cumulative_advance_booking(
        self,
        movie_title: str,
        dbr_start: int,
        dbr_end: int,
        release_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Get cumulative advance booking sales for a movie in DBR range.
        Uses raw SQL matching the user's ground-truth SQL with windowed cumulative sums.
        """
        from django.db import connection
        from datetime import datetime
        
        # Query directly from Movie table grouped by DBR
        release_filter_sql = ""
        params: List[Any] = [movie_title]
        if release_date is not None:
            release_filter_sql = " AND release_date = %s"
            params.append(release_date)
        params.extend([dbr_start, dbr_end])
        
        with connection.cursor() as cursor:
            cursor.execute(f"""
                WITH movie_data AS (
                    SELECT 
                        title,
                        release_date,
                        running_date,
                        reserved,
                        price,
                        total_seats,
                        date_sh
                    FROM movies
                    WHERE UPPER(title) = UPPER(%s){release_filter_sql}
                ), dbr_calculation AS (
                    SELECT 
                        title,
                        release_date,
                        running_date,
                        reserved,
                        price,
                        total_seats,
                        date_sh,
                        CASE 
                            WHEN (running_date::date - release_date) < 0 THEN (running_date::date - release_date)
                            WHEN (running_date::date - release_date) >= 0 THEN (running_date::date - release_date) + 1
                        END AS DBR,
                        (COALESCE(reserved, 0) * COALESCE(price, 0)) AS revenue
                    FROM movie_data
                ), filtered_dbr AS (
                    SELECT 
                        title,
                        DBR,
                        SUM(COALESCE(reserved, 0)) AS daily_reserved,
                        SUM(COALESCE(revenue, 0)) AS daily_revenue,
                        SUM(COALESCE(total_seats, 0)) AS daily_total_seats
                    FROM dbr_calculation
                    WHERE DBR BETWEEN %s AND %s
                      AND DBR < 0  -- Only presales (DBR must be negative)
                      AND date_sh < release_date  -- Only records before release date
                    GROUP BY title, DBR
                ), cumulative_sales AS (
                    SELECT 
                        title,
                        DBR,
                        daily_reserved,
                        daily_revenue,
                        daily_total_seats,
                        SUM(daily_reserved) OVER (ORDER BY DBR ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_reserved,
                        SUM(daily_revenue) OVER (ORDER BY DBR ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue,
                        SUM(daily_total_seats) OVER (ORDER BY DBR ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_total_seats
                    FROM filtered_dbr
                )
                SELECT 
                    title,
                    DBR,
                    daily_reserved,
                    cumulative_reserved,
                    daily_revenue,
                    cumulative_revenue
                FROM cumulative_sales
                ORDER BY DBR
            """, params)
            
            daily_data_raw = cursor.fetchall()
            
            if not daily_data_raw:
                return {'error': f'No advance booking data found for "{movie_title}" in DBR range {dbr_start} to {dbr_end}'}
            
            daily_list = []
            for row in daily_data_raw:
                _title, dbr, daily_res, cum_res, daily_rev, cum_rev = row
                daily_list.append({
                    'dbr_value': int(dbr),
                    'daily_revenue': Decimal(str(daily_rev or 0)),
                    'daily_reserved': int(daily_res or 0),
                    'cumulative_revenue': Decimal(str(cum_rev or 0)),
                    'cumulative_reserved': int(cum_res or 0)
                })
        
        return {
            'title': movie_title,
            'dbr_range': (dbr_start, dbr_end),
            'daily_data': daily_list,
            'total_revenue': daily_list[-1]['cumulative_revenue'] if daily_list else Decimal('0'),
            'total_reserved': daily_list[-1]['cumulative_reserved'] if daily_list else 0
        }
    
    def get_best_comp_titles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get best performing movies (comp titles) sorted by first weekend revenue.
        First Weekend Revenue = sum of total_revenue for DIR -1, 1, 2 only.
        """
        from django.db.models import Sum, Avg
        
        # First Weekend Revenue = DIR -1, 1, 2 only (not DIR 3)
        comp_titles = (
            MovieDailyPerformance.objects
            .filter(dir_value__in=[-1, 1, 2])  # First Weekend: DIR -1, 1, 2 only
            .values('title', 'release_date')
            .annotate(
                first_weekend_revenue=Sum('total_revenue'),
                first_weekend_reserved=Sum('total_reserved_seats'),
                first_weekend_impressions=Sum('total_impressions'),
                avg_price=Avg('avg_price'),
                avg_occupancy=Avg('occupancy_rate')
            )
            .order_by('-first_weekend_revenue')[:limit]
        )
        
        # Enhance with genre and studio info from Movie model
        enhanced_list = []
        for comp in comp_titles:
            try:
                # Get first movie record for metadata
                movie_sample = Movie.objects.filter(
                    title=comp['title'],
                    release_date=comp['release_date']
                ).first()
                
                enhanced_comp = dict(comp)
                if movie_sample:
                    enhanced_comp['genre'] = movie_sample.genre
                    enhanced_comp['studio_name'] = movie_sample.studio_name
                    enhanced_comp['rating'] = movie_sample.rating
                else:
                    enhanced_comp['genre'] = None
                    enhanced_comp['studio_name'] = None
                    enhanced_comp['rating'] = None
                
                enhanced_list.append(enhanced_comp)
            except Exception:
                enhanced_list.append(comp)
        
        return enhanced_list

    def find_best_comp_titles_by_trajectory(
        self,
        target_title: str,
        limit: Optional[int] = None,
        min_correlation: float = 0.50,  # Lowered from 0.85 to 0.50 for growth rate similarity
        dbr_end: int = 2,
        min_dbr_overlap_ratio: float = 0.60,
        min_revenue_ratio: float = 0.3,
        max_revenue_ratio: float = 3.0
    ) -> Dict[str, Any]:
        """
        Analyze trajectory-based comp titles between the target movie and all other candidates.
        
        The comparison uses DAY-BY-DAY GROWTH PERCENTAGE RATES as the primary similarity metric.
        This compares how fast presales are growing (percentage change), not absolute values.
        
        Formula: Growth Rate = (Value_today - Value_yesterday) / Value_yesterday
        
        Example:
        - Movie A: $100 → $200 → $300 (100% then 50% growth)
        - Movie B: $1000 → $2000 → $3000 (100% then 50% growth)
        → These are similar because growth rates match, even though absolute values differ.
        
        The comparison window is constrained to the overlapping DBR → DIR(≤2) window.
        Growth rate vectors are normalized before cosine similarity is applied.
        
        Args:
            target_title: The target movie title to find comps for
            limit: Maximum number of candidates to return (None = all)
            min_correlation: Minimum trend similarity (cosine similarity) threshold (default: 0.85)
            dbr_end: Maximum DIR value to include in comparison (default: 2)
            min_dbr_overlap_ratio: Minimum overlap ratio of DBR windows (default: 0.60)
            min_revenue_ratio: Minimum revenue ratio (candidate/target) to accept (default: 0.3)
            max_revenue_ratio: Maximum revenue ratio (candidate/target) to accept (default: 3.0)
        
        Returns:
            {
                'target_title': str,
                'target_first_weekend_revenue': float,
                'target_window': [...],
                'candidates': [
                    {
                        'title': str,
                        'trend_similarity': float,
                        'overlap_window': 'DBR -30 → DIR 2',
                        'overlap_ratio': float,
                        'dbr_start_gap': int,
                        'first_weekend_revenue': '$12,345,678',
                        'target_first_weekend_revenue': '$10,123,456',
                        'first_weekend_revenue_numeric': float,
                        'target_first_weekend_revenue_numeric': float,
                        'valid_comp': bool,
                        'reasons': [...],
                        'release_date': date,
                        'genre': str,
                        'studio_name': str,
                        'rating': str
                    },
                    ...
                ],
                'valid_candidates': [...filtered list...]
            }
        """
        logger.info(f"🔍 Comparing '{target_title}' to find trajectory-based comp titles")
        target_release_date = self._get_canonical_release_date(target_title)
        if not target_release_date:
            logger.warning(f"No release date found for '{target_title}'")
            return {
                'target_title': target_title,
                'target_first_weekend_revenue': 0.0,
                'target_window': [],
                'target_final_cumulative_presales': 0.0,
                'candidates': [],
                'valid_candidates': []
            }
        
        result: Dict[str, Any] = {
            'target_title': target_title,
            'target_first_weekend_revenue': 0.0,
            'target_window': [],
            'target_final_cumulative_presales': 0.0,
            'target_release_date': target_release_date,
            'candidates': [],
            'valid_candidates': []
        }
        
        # Get DBR trajectory (only DBR values, no DIR)
        # Uses full available DBR range for target movie (from max negative to -1)
        target_window = self._get_first_weekend_window_trajectory(
            target_title,
            max_dir=None,  # Ignored - only DBR is used
            release_date=target_release_date
        )
        if not target_window:
            logger.warning(f"No DBR trajectory data found for '{target_title}'")
            return result
        
        target_time_values = [point['time_value'] for point in target_window]
        target_dbrs = [value for value in target_time_values if value < 0]
        target_first_dbr = min(target_dbrs) if target_dbrs else None
        target_window_map = {point['time_value']: point for point in target_window}
        target_total_revenue = float(target_window[-1]['cumulative_revenue']) - float(target_window[0]['cumulative_revenue'])
        result['target_first_weekend_revenue'] = max(target_total_revenue, 0.0)
        result['target_window'] = target_window
        target_final_cumulative = float(target_window[-1]['cumulative_revenue']) if target_window else 0.0
        result['target_final_cumulative_presales'] = target_final_cumulative
        
        # Use MovieDailyPerformance as the primary source of candidate titles,
        # since this table contains the cleaned cumulative revenue and growth
        # metrics used for trajectory analysis.
        #
        # PERFORMANCE NOTE:
        # We intentionally *do not* filter by revenue scale here so that
        # low-grossing and high-grossing films with similar growth patterns
        # can still be considered as comps. Instead, we simply prioritise
        # titles with more presales data points and cap the total number of
        # candidates to keep the query fast.
        
        # Filter to recent movies only (last 3 years) to reduce candidate pool
        three_years_ago = date.today() - timedelta(days=3*365)
        
        candidate_qs = (
            MovieDailyPerformance.objects
            .exclude(title__iexact=target_title)
            .filter(release_date__gte=three_years_ago)  # Only recent movies
            .values('title')
            .annotate(point_count=Count('id'))
        )

        # To guarantee responsiveness within 60s timeout, cap the number of candidate titles we
        # evaluate per query. Sort by number of presales points so we prefer
        # movies with richer DBR trajectories (better growth comparison).
        MAX_CANDIDATES = 40  # Reduced from 60 to stay well within 60s timeout
        MAX_VALID_MATCHES = 10  # Early exit if we find enough good matches (reduced from 15)
        
        candidate_qs = candidate_qs.order_by('-point_count')[:MAX_CANDIDATES]
        all_titles = [row['title'] for row in candidate_qs]

        logger.info(
            f"   Evaluating {len(all_titles)} candidate movies for '{target_title}' "
            f"(capped at {MAX_CANDIDATES}, filtered to releases since {three_years_ago})"
        )
        
        processed_titles = set()
        valid_matches_found = 0
        
        for candidate_title in all_titles:
            if not candidate_title:
                continue
            
            candidate_key = candidate_title.lower()
            if candidate_key in processed_titles:
                continue
            processed_titles.add(candidate_key)
            
            candidate_release_date = self._get_canonical_release_date(candidate_title)
            if not candidate_release_date:
                continue
            
            try:
                # Get DBR trajectory (only DBR values, no DIR)
                # Uses full available DBR range for candidate movie (from max negative to -1)
                candidate_window = self._get_first_weekend_window_trajectory(
                    candidate_title,
                    max_dir=None,  # Ignored - only DBR is used
                    release_date=candidate_release_date
                )
                if not candidate_window:
                    continue
                
                candidate_time_values = [point['time_value'] for point in candidate_window]
                candidate_dbrs = [value for value in candidate_time_values if value < 0]
                if not candidate_dbrs:
                    continue
                
                target_keys = set(target_time_values)
                candidate_keys = set(candidate_time_values)
                common_keys = sorted(target_keys.intersection(candidate_keys))
                
                if len(common_keys) < 3:
                    # Need at least three shared points to compare trajectories
                    continue
                
                shortest_length = min(len(target_keys), len(candidate_keys))
                overlap_ratio = (
                    len(common_keys) / shortest_length
                    if shortest_length > 0
                    else 0.0
                )
                
                overlap_start = common_keys[0]
                overlap_end = common_keys[-1]
                
                # For Growth(%) calculation, use CUMULATIVE revenue values
                # This matches the client definition:
                #   Growth(%) = (Today's Cumulative / Yesterday's Cumulative - 1) * 100
                # Example: cumulative -44=$120, -43=$150 → Growth% = (150 - 120) / 120 * 100 = 25%
                candidate_window_map = {point['time_value']: point for point in candidate_window}
                target_cumulative_values = [
                    float(target_window_map[key]['cumulative_revenue']) for key in common_keys
                ]
                candidate_cumulative_values = [
                    float(candidate_window_map[key]['cumulative_revenue']) for key in common_keys
                ]
                
                target_start_value = target_cumulative_values[0]
                candidate_start_value = candidate_cumulative_values[0]
                target_end_value = target_cumulative_values[-1]
                candidate_end_value = candidate_cumulative_values[-1]
                
                target_overlap_revenue = target_end_value - target_start_value
                candidate_overlap_revenue = candidate_end_value - candidate_start_value
                candidate_final_cumulative = float(candidate_window[-1]['cumulative_revenue']) if candidate_window else 0.0

                # Secondary metric: similarity of the cumulative trajectories themselves
                # (shape-based, independent of absolute level), for reporting.
                try:
                    normalized_target = self._normalize_vector(target_cumulative_values)
                    normalized_candidate = self._normalize_vector(candidate_cumulative_values)
                    cumulative_trajectory_similarity = self._cosine_similarity(
                        normalized_target, normalized_candidate
                    )
                except Exception:
                    cumulative_trajectory_similarity = 0.0
                
                # Calculate Growth(%) similarity using cumulative revenue (day-over-day change of cumulative)
                # This compares how fast presales are growing day-over-day, not absolute values.
                # Method: Calculate DoD% on cumulative values and compare day-by-day with ±2% tolerance.
                # Example: Movie A cumulative: 100 → 200 (100% growth) vs Movie B: 1,000 → 2,000 (100% growth)
                # → Similar because Growth% matches (within ±2%).
                growth_alignment = self._analyze_growth_alignment(
                    target_cumulative_values,
                    candidate_cumulative_values
                )
                
                # PRIMARY METRIC: Use Growth% (DoD% on cumulative) match ratio as similarity metric
                growth_rate_similarity = growth_alignment.get('growth_rate_similarity', 0.0)
                dod_match_ratio = growth_alignment.get('dod_match_ratio', 0.0)
                avg_dod_difference = growth_alignment.get('avg_dod_difference', 0.0)
                
                # Use DoD% match ratio as the primary similarity metric
                # This is the percentage of days where DoD% difference is within ±2%
                # If 70% of days match within ±2%, similarity = 0.70
                trend_similarity = growth_rate_similarity  # This is now the DoD% match ratio
                
                rejection_reasons: List[str] = []
                
                if overlap_ratio < min_dbr_overlap_ratio:
                    rejection_reasons.append(
                        f"Only {overlap_ratio:.0%} of the presales window overlaps (need ≥{min_dbr_overlap_ratio:.0%})"
                    )
                
                if trend_similarity < min_correlation:
                    rejection_reasons.append(
                        f"Trend similarity {trend_similarity:.2f} below threshold {min_correlation:.2f}"
                    )
                
                # Revenue scale is recorded for context but no longer used as a hard filter.
                # This allows movies with very different absolute revenue (e.g. $100 vs $1,000)
                # but similar growth patterns to still be considered comp titles.
                revenue_ratio = (
                    (candidate_overlap_revenue / target_overlap_revenue)
                    if target_overlap_revenue > 0
                    else 0.0
                )
                
                candidate_record = {
                    'title': candidate_title,
                    'release_date': candidate_release_date,
                    'trend_similarity': trend_similarity,  # Now based on growth rate similarity
                    'growth_rate_similarity': growth_rate_similarity,  # Day-by-day growth percentage similarity
                    'cumulative_trajectory_similarity': cumulative_trajectory_similarity,  # For reference
                    'overlap_window': self._format_time_window(overlap_start, overlap_end),
                    'overlap_ratio': overlap_ratio,
                    'shared_points': len(common_keys),
                    'first_weekend_revenue_numeric': max(candidate_overlap_revenue, 0.0),
                    'first_weekend_revenue': self._format_currency(candidate_overlap_revenue),
                    'target_first_weekend_revenue_numeric': max(target_overlap_revenue, 0.0),
                    'target_first_weekend_revenue': self._format_currency(target_overlap_revenue),
                    'target_final_cumulative_presales': target_final_cumulative,
                    'revenue_ratio': revenue_ratio,
                    'valid_comp': len(rejection_reasons) == 0,
                    'reasons': rejection_reasons or [f"Day-by-day DoD% patterns match: {dod_match_ratio:.0%} of days within ±2% (avg difference: {avg_dod_difference:.1f}%)"],
                    'genre': None,
                    'studio_name': None,
                    'rating': None,
                    'final_cumulative_presales': candidate_final_cumulative,
                    'growth_alignment': growth_alignment
                }
                
                # Attach metadata
                movie_sample = Movie.objects.filter(
                    title=candidate_title,
                    release_date=candidate_release_date
                ).first()
                if movie_sample:
                    candidate_record['genre'] = movie_sample.genre
                    candidate_record['studio_name'] = movie_sample.studio_name
                    candidate_record['rating'] = movie_sample.rating
                
                result['candidates'].append(candidate_record)
                
                # Early exit if we've found enough valid matches (performance optimization)
                if candidate_record.get('valid_comp', False):
                    valid_matches_found += 1
                    if valid_matches_found >= MAX_VALID_MATCHES:
                        logger.info(f"   Early exit: Found {valid_matches_found} valid matches (target: {MAX_VALID_MATCHES})")
                        break
            
            except Exception as exc:
                logger.warning(f"Error analyzing comp candidate '{candidate_title}': {exc}")
                continue
        
        # Sort candidates by similarity (descending)
        result['candidates'].sort(key=lambda x: x['trend_similarity'], reverse=True)
        if limit is not None:
            result['candidates'] = result['candidates'][:limit]
        
        result['valid_candidates'] = [c for c in result['candidates'] if c['valid_comp']]
        
        logger.info(f"✅ Found {len(result['valid_candidates'])} valid comp titles for '{target_title}'")
        return result
    
    def _get_cumulative_presales_trajectory(
        self,
        title: str,
        dbr_start: Optional[int] = None,
        dbr_end: Optional[int] = None,
        release_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Get cumulative presales trajectory for a movie by DBR.
        Returns list of {dbr_value, cumulative_revenue, cumulative_reserved} ordered by DBR ascending.
        
        This represents cumulative presales as DBR approaches 0 (from max negative → -1),
        where each point shows the running total of all presales collected up to that DBR date.
        
        IMPORTANT: Only presales data (DBR < 0, date_sh < release_date) is included.
        
        PREFERS MovieDailyPerformance table (cleaned data) over raw movies table.
        
        Uses the FULL available DBR range for each movie (from maximum negative to -1).
        
        Args:
            title: Movie title
            dbr_start: Starting DBR (if None, uses maximum available negative DBR in data for this movie)
            dbr_end: Ending DBR (if None, uses minimum available negative DBR in data, typically -1)
            
        Returns:
            List of trajectory points with dbr_value, cumulative_revenue, cumulative_reserved
            Sorted by DBR ascending (most negative to least negative: e.g., -60, -59, ..., -1)
        """
        if release_date is None:
            release_date = self._get_canonical_release_date(title)
        if not release_date:
            return []
        
        # If dbr_start or dbr_end not specified, find the actual range for this movie
        # This ensures each movie uses its full available DBR range (max negative to -1)
        
        # PREFER: Get from MovieDailyPerformance (cleaned data) first
        # This uses the cleaned and pre-calculated cumulative values
        # get_day_by_day_dbr_trend will automatically find the full range if start_dbr/end_dbr are None
        try:
            dbr_trend = self.get_day_by_day_dbr_trend(
                title,
                start_dbr=dbr_start,  # None = use max available negative DBR for this movie
                end_dbr=dbr_end,  # None = use min available negative DBR (typically -1) for this movie
                use_cache=True,  # This uses MovieDailyPerformance
                release_date=release_date
            )
            
            if dbr_trend:
                # Extract trajectory from MovieDailyPerformance data
                trajectory = []
                for day_data in dbr_trend:
                    dbr = day_data.get('dbr_value')
                    if dbr is None:
                        continue
                    
                    # Filter by DBR constraint: Only presales (DBR < 0) and within optional range
                    if dbr >= 0:
                        continue
                    if dbr_start is not None and dbr < dbr_start:
                        continue
                    if dbr_end is not None and dbr > dbr_end:
                        continue
                    
                    # Use cumulative_revenue from MovieDailyPerformance (already calculated)
                    cumulative_revenue = day_data.get('cumulative_revenue')
                    cumulative_reserved = day_data.get('cumulative_reserved', 0)
                    
                    if cumulative_revenue is not None:
                        trajectory.append({
                            'dbr_value': int(dbr),
                            'cumulative_revenue': Decimal(str(cumulative_revenue)),
                            'cumulative_reserved': int(cumulative_reserved or 0)
                        })
                
                # Sort by DBR ascending (most negative to least negative: -60, -59, ..., -1)
                trajectory.sort(key=lambda x: x['dbr_value'])
                if trajectory:
                    return trajectory
        except Exception as e:
            logger.warning(f"Error getting trajectory from MovieDailyPerformance for '{title}': {e}")
        
        # Fallback: Get from raw movies table via get_cumulative_advance_booking
        try:
            result = self.get_cumulative_advance_booking(title, dbr_start, dbr_end, release_date)
            if 'daily_data' in result and result['daily_data']:
                trajectory = []
                for day_data in result['daily_data']:
                    dbr_val_raw = day_data.get('dbr_value', None)
                    if dbr_val_raw is None:
                        continue
                    dbr_val = int(dbr_val_raw)
                    # Filter by optional DBR constraints
                    if dbr_start is not None and dbr_val < dbr_start:
                        continue
                    if dbr_end is not None and dbr_val > dbr_end:
                        continue
                    trajectory.append({
                        'dbr_value': dbr_val,
                        'cumulative_revenue': Decimal(str(day_data.get('cumulative_revenue', 0))),
                        'cumulative_reserved': int(day_data.get('cumulative_reserved', 0))
                    })
                # Sort by DBR ascending (most negative to least negative: -60, -59, ..., -1)
                trajectory.sort(key=lambda x: x['dbr_value'])
                return trajectory
        except Exception as e:
            logger.warning(f"Error getting cumulative advance booking for '{title}': {e}")
        
        # Final fallback: Calculate cumulative from daily data
        try:
            dbr_trend = self.get_day_by_day_dbr_trend(
                title,
                start_dbr=dbr_start,
                end_dbr=dbr_end,
                use_cache=False,  # Force raw data
                release_date=release_date
            )
            
            if not dbr_trend:
                return []
            
            # Extract trajectory data and calculate cumulative if needed
            trajectory = []
            cumulative_revenue = Decimal('0')
            cumulative_reserved = 0
            
            # Sort by DBR first (most negative to least negative)
            sorted_dbr_trend = sorted(dbr_trend, key=lambda x: x.get('dbr_value', 0))
            
            for day_data in sorted_dbr_trend:
                dbr = day_data.get('dbr_value')
                if dbr is None:
                    continue
                
                # Filter by DBR constraint: Only presales (DBR < 0)
                if dbr >= 0:
                    continue
                
                # Get daily revenue (not cumulative)
                daily_revenue = day_data.get('total_revenue')
                daily_reserved = day_data.get('total_reserved_seats', 0)
                
                # If cumulative_revenue is already available, use it
                if day_data.get('cumulative_revenue') is not None:
                    cumulative_revenue = Decimal(str(day_data.get('cumulative_revenue')))
                    cumulative_reserved = day_data.get('cumulative_reserved', 0)
                else:
                    # Calculate cumulative by adding daily revenue
                    if daily_revenue:
                        cumulative_revenue += Decimal(str(daily_revenue))
                    cumulative_reserved += int(daily_reserved or 0)
                
                trajectory.append({
                    'dbr_value': int(dbr),
                    'cumulative_revenue': cumulative_revenue,
                    'cumulative_reserved': int(cumulative_reserved)
                })
            
            return trajectory
        except Exception as e:
            logger.warning(f"Error calculating cumulative trajectory from daily data for '{title}': {e}")
            return []
    
    def _calculate_trajectory_similarity(
        self,
        trajectory1: List[Dict[str, Any]],
        trajectory2: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate similarity score between two cumulative presales trajectories using Pearson correlation.
        
        Uses proper min-max normalization (0-1) to compare curve shapes, then calculates
        Pearson correlation coefficient. This allows comparison of booking trends regardless
        of absolute revenue scale.
        
        Returns:
            Pearson correlation coefficient between -1.0 and 1.0
            (1.0 = identical trend, 0.0 = no correlation, -1.0 = opposite trend)
        """
        if not trajectory1 or not trajectory2:
            return 0.0
        
        # Normalize trajectories to same DBR range for comparison
        # Find common DBR range
        dbr_set1 = {point['dbr_value'] for point in trajectory1}
        dbr_set2 = {point['dbr_value'] for point in trajectory2}
        common_dbrs = sorted(dbr_set1.intersection(dbr_set2))
        
        if len(common_dbrs) < 3:  # Need at least 3 points for meaningful comparison
            return 0.0
        
        # Extract cumulative revenue values for common DBR points
        traj1_dict = {point['dbr_value']: point['cumulative_revenue'] for point in trajectory1}
        traj2_dict = {point['dbr_value']: point['cumulative_revenue'] for point in trajectory2}
        
        traj1_values = [float(traj1_dict[dbr]) for dbr in common_dbrs]
        traj2_values = [float(traj2_dict[dbr]) for dbr in common_dbrs]
        
        # Apply proper min-max normalization (0-1 scale) for shape comparison
        # This allows comparison of curve shapes regardless of absolute values
        min1 = min(traj1_values) if traj1_values else 0.0
        max1 = max(traj1_values) if traj1_values else 1.0
        min2 = min(traj2_values) if traj2_values else 0.0
        max2 = max(traj2_values) if traj2_values else 1.0
        
        # Handle edge cases
        if max1 == min1:
            if max1 == 0:
                normalized1 = [0.0] * len(traj1_values)
            else:
                normalized1 = [1.0] * len(traj1_values)
        else:
            normalized1 = [(v - min1) / (max1 - min1) for v in traj1_values]
        
        if max2 == min2:
            if max2 == 0:
                normalized2 = [0.0] * len(traj2_values)
            else:
                normalized2 = [1.0] * len(traj2_values)
        else:
            normalized2 = [(v - min2) / (max2 - min2) for v in traj2_values]
        
        # Calculate Pearson correlation on normalized curves
        # This measures shape similarity (trend pattern), not absolute scale
        correlation = self._pearson_correlation(normalized1, normalized2)
        
        return correlation
    
    def _calculate_revenue_alignment_score(
        self,
        target_trajectory: List[Dict[str, Any]],
        candidate_trajectory: List[Dict[str, Any]],
        common_dbrs: List[int]
    ) -> float:
        """
        Calculate median revenue ratio across the shared DBR window.
        
        This captures whether both movies are operating at similar absolute
        presales levels throughout the presales window, not just at First Weekend.
        """
        if not target_trajectory or not candidate_trajectory or not common_dbrs:
            return 0.0

        target_dict = {point['dbr_value']: float(point['cumulative_revenue']) for point in target_trajectory}
        candidate_dict = {point['dbr_value']: float(point['cumulative_revenue']) for point in candidate_trajectory}

        ratios: List[float] = []
        for dbr in common_dbrs:
            target_value = target_dict.get(dbr)
            candidate_value = candidate_dict.get(dbr)

            if target_value is None or candidate_value is None:
                continue

            if target_value <= 0 or candidate_value <= 0:
                continue

            ratios.append(min(target_value, candidate_value) / max(target_value, candidate_value))

        if not ratios:
            return 0.0

        return float(median(ratios))
    
    def _calculate_revenue_similarity(
        self,
        target_first_weekend: float,
        candidate_first_weekend: float,
        target_final_presales: float,
        candidate_final_presales: float
    ) -> Tuple[float, str]:
        """
        Calculate revenue similarity using the best available data.
        
        Prefers First Weekend totals when available. If both movies lack
        opening-weekend revenue (e.g., still in presales), falls back to the
        final cumulative presales (DBR -1) to keep comps that share the same
        presale scale.
        
        Returns:
            similarity ratio (0-1), basis string ('first_weekend', 'presales_final', 'insufficient_data')
        """
        if target_first_weekend > 0 and candidate_first_weekend > 0:
            ratio = min(target_first_weekend, candidate_first_weekend) / max(target_first_weekend, candidate_first_weekend)
            return ratio, 'first_weekend'
        
        if target_final_presales > 0 and candidate_final_presales > 0:
            ratio = min(target_final_presales, candidate_final_presales) / max(target_final_presales, candidate_final_presales)
            return ratio, 'presales_final'
        
        return 0.0, 'insufficient_data'
    
    def _get_first_weekend_window_trajectory(
        self,
        title: str,
        max_dir: Optional[int] = None,  # Ignored - only DBR is used
        release_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Build DBR trajectory window (earliest presale through -1) with cumulative revenue.
        
        Uses ONLY DBR values (Days Before Release, negative values).
        Uses the FULL available DBR range for each movie:
        - From maximum negative DBR available (e.g., -60, -45, -30) to -1
        - Each movie uses its own actual DBR range, not a fixed range
        """
        # Presales (DBR < 0) - use full available range (None = auto-detect range for this movie)
        dbr_trajectory = self._get_cumulative_presales_trajectory(
            title,
            dbr_start=None,  # None = use max available negative DBR for this movie
            dbr_end=None,  # None = use min available negative DBR (typically -1) for this movie
            release_date=release_date
        )
        if not dbr_trajectory:
            return []
        
        trajectory: List[Dict[str, Any]] = []
        previous_cumulative = None
        
        for point in dbr_trajectory:
            cumulative_revenue = Decimal(str(point.get('cumulative_revenue', 0) or 0))
            if previous_cumulative is None:
                daily_revenue = cumulative_revenue
            else:
                daily_revenue = cumulative_revenue - previous_cumulative
            previous_cumulative = cumulative_revenue
            
            trajectory.append({
                'time_value': int(point['dbr_value']),  # DBR value (negative)
                'time_label': 'DBR',
                'cumulative_revenue': cumulative_revenue,
                'daily_revenue': daily_revenue
            })
        
        # Sort by DBR ascending (most negative to least negative: -60, -59, ..., -1)
        trajectory.sort(key=lambda x: x['time_value'])
        return trajectory
    
    def _normalize_vector(self, values: List[float]) -> List[float]:
        if not values:
            return []
        first_val = values[0]
        shifted = [v - first_val for v in values]
        norm = math.sqrt(sum(v * v for v in shifted))
        if norm == 0:
            return [0.0 for _ in shifted]
        return [v / norm for v in shifted]
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        numerator = sum(vec1[i] * vec2[i] for i in range(len(vec1)))
        denom1 = math.sqrt(sum(v * v for v in vec1))
        denom2 = math.sqrt(sum(v * v for v in vec2))
        if denom1 == 0 or denom2 == 0:
            return 0.0
        return max(-1.0, min(1.0, numerator / (denom1 * denom2)))
    
    def _format_time_window(self, start: int, end: int) -> str:
        def label(value: int) -> str:
            return f"DBR {value}" if value < 0 else f"DIR {value}"
        return f"{label(start)} → {label(end)}"
    
    def _format_currency(self, amount: float) -> str:
        if amount is None:
            return "$0"
        return "${:,.0f}".format(amount)
    
    def _pearson_correlation(self, x: List[float], y: List[float]) -> float:
        """
        Calculate Pearson correlation coefficient between two lists.
        
        Returns:
            Pearson correlation coefficient between -1.0 and 1.0
            (1.0 = perfect positive correlation, 0.0 = no correlation, -1.0 = perfect negative correlation)
        """
        if len(x) != len(y) or len(x) < 2:
            return 0.0
        
        # Calculate means
        mean_x = sum(x) / len(x)
        mean_y = sum(y) / len(y)
        
        # Calculate numerator and denominators
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(len(x)))
        denom_x = sum((x[i] - mean_x) ** 2 for i in range(len(x)))
        denom_y = sum((y[i] - mean_y) ** 2 for i in range(len(y)))
        
        if denom_x == 0 or denom_y == 0:
            return 0.0
        
        correlation = numerator / ((denom_x ** 0.5) * (denom_y ** 0.5))
        
        # Return raw correlation coefficient (not normalized)
        # Clamp to [-1, 1] range to handle floating point errors
        return max(-1.0, min(1.0, correlation))
    
    def _safe_ratio(self, a: float, b: float) -> Optional[float]:
        """Return min/max ratio for two magnitudes, ignoring zeros."""
        if a is None or b is None:
            return None
        a_abs = abs(a)
        b_abs = abs(b)
        if a_abs <= 1e-6 or b_abs <= 1e-6:
            return None
        return min(a_abs, b_abs) / max(a_abs, b_abs)

    def _calculate_growth_rates(self, values: List[float]) -> List[float]:
        """
        Calculate day-by-day growth percentage rates.
        
        Formula: Growth Rate = (Value_today - Value_yesterday) / Value_yesterday
        
        Example:
        - DBR -25: $100, DBR -24: $200 → Growth Rate = (200-100)/100 = 1.0 (100% growth)
        - DBR -24: $200, DBR -23: $300 → Growth Rate = (300-200)/200 = 0.5 (50% growth)
        
        Returns list of growth rates (one less than input values).
        """
        if not values or len(values) < 2:
            return []
        
        growth_rates = []
        for idx in range(1, len(values)):
            prev_value = values[idx - 1]
            curr_value = values[idx]
            
            # Handle different cases for growth rate calculation
            if prev_value > 1e-6:  # Avoid division by very small numbers
                # Growth rate as percentage: (new - old) / old
                growth_rate = (curr_value - prev_value) / prev_value
                # Clamp extreme values to reasonable range (-10 to 10, i.e., -1000% to 1000%)
                growth_rate = max(-10.0, min(10.0, growth_rate))
                growth_rates.append(growth_rate)
            elif prev_value <= 1e-6 and curr_value > 1e-6:
                # Special case: from near-zero to positive = very high growth
                # Use a normalized representation: log(1 + ratio) to avoid infinite values
                growth_rates.append(2.0)  # Represent as ~200% growth (reasonable upper bound)
            elif prev_value > 1e-6 and curr_value <= 1e-6:
                # Dropped to near-zero: negative growth
                growth_rates.append(-0.9)  # Represent as -90% decline
            else:
                # Both near-zero or negative, no meaningful growth
                growth_rates.append(0.0)
        
        return growth_rates
    
    def _analyze_growth_alignment(self, target_values: List[float], candidate_values: List[float]) -> Dict[str, float]:
        """
        Compare day-to-day growth percentage rates between two trajectories.
        
        This compares the RATE of growth (percentage change), not absolute values.
        Movies with similar growth rates are considered similar performers.
        
        Method: Calculate DoD% for each day transition, compare day-by-day.
        If DoD% difference is within ±2 percentage points, count as match.
        
        Example:
        - Movie A: DBR -45=$100, -44=$200, -43=$300 → DoD%: 100%, 50%
        - Movie B: DBR -45=$1000, -44=$2000, -43=$3000 → DoD%: 100%, 50%
        → These are similar because DoD% values match (within ±2% tolerance)
        """
        if not target_values or not candidate_values or len(target_values) != len(candidate_values):
            return {
                'direction_alignment': 0.0,
                'median_growth_ratio': 0.0,
                'avg_growth_ratio': 0.0,
                'growth_rate_similarity': 0.0,
                'dod_match_ratio': 0.0,
                'avg_dod_difference': 0.0
            }

        # Calculate growth rates (percentage change day-by-day) as percentages (0.0 = 0%, 1.0 = 100%)
        target_growth_rates = self._calculate_growth_rates(target_values)
        candidate_growth_rates = self._calculate_growth_rates(candidate_values)
        
        if not target_growth_rates or not candidate_growth_rates or len(target_growth_rates) != len(candidate_growth_rates):
            return {
                'direction_alignment': 0.0,
                'median_growth_ratio': 0.0,
                'avg_growth_ratio': 0.0,
                'growth_rate_similarity': 0.0,
                'dod_match_ratio': 0.0,
                'avg_dod_difference': 0.0
            }
        
        # PRIMARY METHOD: Compare DoD% day-by-day with ±2% tolerance
        # Convert growth rates to percentages (multiply by 100)
        target_dod_percentages = [rate * 100.0 for rate in target_growth_rates]  # 1.0 → 100%
        candidate_dod_percentages = [rate * 100.0 for rate in candidate_growth_rates]  # 1.0 → 100%
        
        matches_within_tolerance = 0
        total_comparisons = len(target_dod_percentages)
        dod_differences = []
        
        for idx in range(total_comparisons):
            target_dod = target_dod_percentages[idx]
            candidate_dod = candidate_dod_percentages[idx]
            
            # Calculate absolute difference in percentage points
            dod_diff = abs(target_dod - candidate_dod)
            dod_differences.append(dod_diff)
            
            # If difference is within ±2 percentage points, count as match
            if dod_diff <= 2.0:
                matches_within_tolerance += 1
        
        # Calculate match ratio (percentage of days within ±2% tolerance)
        dod_match_ratio = (matches_within_tolerance / total_comparisons) if total_comparisons > 0 else 0.0
        
        # Calculate average DoD% difference
        avg_dod_difference = (sum(dod_differences) / len(dod_differences)) if dod_differences else 0.0
        
        # Growth rate similarity = match ratio (0.0 to 1.0)
        # If 70% of days match within ±2%, similarity = 0.70
        growth_rate_similarity = dod_match_ratio
        
        # Also calculate direction alignment and ratios for backward compatibility
        matching_direction = 0
        comparisons = 0
        ratios: List[float] = []

        for idx in range(len(target_growth_rates)):
            target_rate = target_growth_rates[idx]
            candidate_rate = candidate_growth_rates[idx]
            
            # Check if both positive or both negative (same direction)
            if (target_rate >= 0 and candidate_rate >= 0) or (target_rate <= 0 and candidate_rate <= 0):
                matching_direction += 1
            
            # Calculate ratio of growth rates
            if candidate_rate != 0:
                ratio = abs(target_rate / candidate_rate) if abs(target_rate) <= abs(candidate_rate) else abs(candidate_rate / target_rate)
                ratios.append(ratio)
            
            comparisons += 1

        direction_alignment = (matching_direction / comparisons) if comparisons else 0.0
        median_ratio = float(median(ratios)) if ratios else 0.0
        avg_ratio = float(sum(ratios) / len(ratios)) if ratios else 0.0

        return {
            'direction_alignment': direction_alignment,
            'median_growth_ratio': median_ratio,
            'avg_growth_ratio': avg_ratio,
            'growth_rate_similarity': growth_rate_similarity,  # Now based on ±2% match ratio
            'dod_match_ratio': dod_match_ratio,  # Percentage of days within ±2%
            'avg_dod_difference': avg_dod_difference  # Average DoD% difference in percentage points
        }

    def _format_growth_alignment_text(self, growth_alignment: Dict[str, float]) -> str:
        if not growth_alignment:
            return "Slope alignment unavailable"
        direction_pct = growth_alignment.get('direction_alignment', 0.0) * 100
        median_ratio = growth_alignment.get('median_growth_ratio', 0.0)
        return f"{direction_pct:.0f}% daily direction match; median growth ratio {median_ratio:.2f}x"

    def _compute_dbr_overlap(self, target_traj: List[Dict[str, Any]], candidate_traj: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Compute overlap statistics for DBR-based cumulative trajectories."""
        target_map = {int(point['dbr_value']): float(point['cumulative_revenue']) for point in target_traj if point.get('dbr_value') is not None}
        candidate_map = {int(point['dbr_value']): float(point['cumulative_revenue']) for point in candidate_traj if point.get('dbr_value') is not None}

        common_dbrs = sorted(set(target_map.keys()).intersection(candidate_map.keys()))
        if len(common_dbrs) < 3:
            return None

        target_values = [target_map[dbr] for dbr in common_dbrs]
        candidate_values = [candidate_map[dbr] for dbr in common_dbrs]

        normalized_target = self._normalize_vector(target_values)
        normalized_candidate = self._normalize_vector(candidate_values)
        similarity = self._cosine_similarity(normalized_target, normalized_candidate)

        shortest_length = min(len(target_map), len(candidate_map)) or 1
        overlap_ratio = len(common_dbrs) / shortest_length

        growth_alignment = self._analyze_growth_alignment(target_values, candidate_values)

        return {
            'common_dbrs': common_dbrs,
            'overlap_ratio': overlap_ratio,
            'similarity': similarity,
            'growth_alignment': growth_alignment,
            'target_values': target_values,
            'candidate_values': candidate_values
        }

    def _get_trajectory_metrics(self, trajectory: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extract key metrics from a cumulative presales trajectory.
        
        Returns:
            Dictionary with metrics like:
            - early_growth_rate: Growth in first half of trajectory
            - late_growth_rate: Growth in second half of trajectory
            - booking_pattern: 'early', 'late', or 'consistent'
        """
        if not trajectory or len(trajectory) < 2:
            return {
                'early_growth_rate': 0.0,
                'late_growth_rate': 0.0,
                'booking_pattern': 'unknown'
            }
        
        # Split trajectory into early and late halves
        mid_point = len(trajectory) // 2
        early_trajectory = trajectory[:mid_point]
        late_trajectory = trajectory[mid_point:]
        
        # Calculate growth rates
        early_start = float(early_trajectory[0]['cumulative_revenue']) if early_trajectory else 0.0
        early_end = float(early_trajectory[-1]['cumulative_revenue']) if early_trajectory else 0.0
        early_growth = (early_end / early_start) if early_start > 0 else 0.0
        
        late_start = float(late_trajectory[0]['cumulative_revenue']) if late_trajectory else 0.0
        late_end = float(late_trajectory[-1]['cumulative_revenue']) if late_trajectory else 0.0
        late_growth = (late_end / late_start) if late_start > 0 else 0.0
        
        # Determine booking pattern
        if late_growth > early_growth * 1.5:
            booking_pattern = 'late'
        elif early_growth > late_growth * 1.5:
            booking_pattern = 'early'
        else:
            booking_pattern = 'consistent'
        
        return {
            'early_growth_rate': early_growth,
            'late_growth_rate': late_growth,
            'booking_pattern': booking_pattern
        }
    
    def format_comp_titles_analysis(
        self,
        target_title: str,
        comp_titles: Any,
        include_trajectory_details: bool = True
    ) -> str:
        """
        Format comp titles analysis with detailed trend analysis and reasoning.
        
        Args:
            target_title: The target movie title
            comp_titles: Result from find_best_comp_titles_by_trajectory
            include_trajectory_details: Whether to include detailed trajectory analysis
            
        Returns:
            Formatted analysis string with trend analysis and reasoning
        """
        candidates: List[Dict[str, Any]] = []
        valid_candidates: List[Dict[str, Any]] = []
        target_first_weekend_total = 0.0
        
        if isinstance(comp_titles, dict):
            candidates = comp_titles.get('candidates', [])
            valid_candidates = [c for c in candidates if c.get('valid_comp')]
            target_first_weekend_total = comp_titles.get('target_first_weekend_revenue', 0.0)
        else:
            candidates = comp_titles or []
            valid_candidates = candidates
        
        if not candidates:
            return f"No comparable titles found for '{target_title}' based on cumulative presales trajectory."
        
        # Get target movie trajectory and First Weekend Revenue for context
        target_trajectory = self._get_cumulative_presales_trajectory(target_title, dbr_end=2)
        target_final = target_trajectory[-1]['cumulative_revenue'] if target_trajectory else Decimal('0')
        target_metrics = self._get_trajectory_metrics(target_trajectory) if target_trajectory else {}
        target_fw_revenue = target_first_weekend_total / 1_000_000 if target_first_weekend_total else float(target_final) / 1_000_000
        
        lines = []
        lines.append(f"**Comparable Presales Trajectories for {target_title}:**\n")
        lines.append("Day-by-day GROWTH PERCENTAGE RATES are compared (not absolute values).")
        lines.append("Formula: Growth Rate = (Value_today - Value_yesterday) / Value_yesterday")
        lines.append("Movies with similar growth rates are considered similar performers, regardless of absolute revenue scale.")
        lines.append("Matches require strong overlap, high growth rate similarity, and closely aligned daily growth patterns.\n")
        lines.append(f"**Target Summary:**")
        lines.append(f"- First Weekend (DIR -1 → 2): ${target_fw_revenue:.2f}M")
        lines.append(f"- Final Cumulative Presales: ${float(target_final)/1_000_000:.2f}M")
        lines.append(f"- Booking Pattern: {target_metrics.get('booking_pattern', 'unknown').title()}")
        lines.append("")
        
        if valid_candidates:
            lines.append(f"**Best Comp Titles ({len(valid_candidates)} matches):**")
            for idx, comp in enumerate(valid_candidates, 1):
                growth_rate_sim = comp.get('growth_rate_similarity', comp.get('trend_similarity', 0.0))
                dod_match_ratio = comp.get('growth_alignment', {}).get('dod_match_ratio', 0.0)
                avg_dod_diff = comp.get('growth_alignment', {}).get('avg_dod_difference', 0.0)
                final_millions = float(comp.get('final_cumulative_presales', 0.0)) / 1_000_000
                fw_millions = comp.get('first_weekend_revenue_numeric', 0.0) / 1_000_000
                target_fw_millions = comp.get('target_first_weekend_revenue_numeric', 0.0) / 1_000_000
                revenue_ratio = comp.get('revenue_ratio', 0.0)
                lines.append(f"{idx}. **{comp['title']}**")
                lines.append(f"   - Growth Rate Similarity: {growth_rate_sim:.1%} (day-by-day growth % match)")
                if dod_match_ratio > 0:
                    lines.append(f"   - Daily Growth Match: {dod_match_ratio:.0%} of days within ±2% tolerance (avg difference: {avg_dod_diff:.1f}%)")
                lines.append(f"   - DBR Overlap: {comp['overlap_window']} ({comp.get('shared_points', 0)} matching days)")
                lines.append(f"   - First Weekend Revenue: ${fw_millions:.2f}M")
                lines.append(f"   - Final Cumulative Presales: ${final_millions:.2f}M")
                if comp.get('genre'):
                    lines.append(f"   - Genre: {comp['genre']}")
                if comp.get('studio_name'):
                    lines.append(f"   - Studio: {comp['studio_name']}")
                lines.append("")
        else:
            lines.append("**Best Comp Titles:**")
            lines.append("No movies found with matching day-by-day growth rate patterns.")
            lines.append("")
        
        return "\n".join(lines)
    
    def find_movies_performing_like(
        self,
        target_title: str,
        limit: int = 6,
        min_similarity_threshold: float = 0.3
    ) -> Dict[str, Any]:
        """
        Find movies that are performing similarly to a target movie based on cumulative presales trajectory.
        
        This method answers queries like "which movies are performing like [target movie]?"
        by analyzing cumulative presales growth patterns (DBR vs cumulative revenue).
        
        Args:
            target_title: Movie title to find similar performers for
            limit: Maximum number of similar movies to return
            min_similarity_threshold: Minimum similarity score (0.0-1.0) to include
            
        Returns:
            Dictionary with:
            - target_movie: Target movie info and trajectory summary
            - similar_movies: List of movies with similar trajectories
            - analysis: Formatted analysis text
        """
        logger.info(f"🔍 Finding movies performing like '{target_title}'")
        
        target_release_date = self._get_canonical_release_date(target_title)
        if not target_release_date:
            return {
                'target_movie': {'title': target_title},
                'similar_movies': [],
                'analysis': f"No release information found for '{target_title}'. Unable to compare trajectories.",
                'error': 'No canonical release'
            }

        # Get target movie's trajectory
        target_trajectory = self._get_cumulative_presales_trajectory(target_title, release_date=target_release_date)
        
        if not target_trajectory or len(target_trajectory) == 0:
            return {
                'target_movie': {'title': target_title},
                'similar_movies': [],
                'analysis': f"No presales trajectory data found for '{target_title}'. Cannot find similar performing movies.",
                'error': 'No trajectory data'
            }
        
        # Get target movie metrics
        target_metrics = self._get_trajectory_metrics(target_trajectory)
        target_final = target_trajectory[-1]['cumulative_revenue']
        target_millions = float(target_final) / 1_000_000
        
        # Get all other movies and compare
        all_titles = list(
            Movie.objects
            .exclude(title__iexact=target_title)
            .values_list('title', flat=True)
            .distinct()
        )
        
        similar_movies = []
        
        for candidate_title in all_titles:
            if not candidate_title:
                continue
            candidate_release_date = self._get_canonical_release_date(candidate_title)
            if not candidate_release_date:
                continue
            
            try:
                candidate_trajectory = self._get_cumulative_presales_trajectory(
                    candidate_title,
                    release_date=candidate_release_date
                )
                
                if not candidate_trajectory or len(candidate_trajectory) == 0:
                    continue
                
                overlap_stats = self._compute_dbr_overlap(target_trajectory, candidate_trajectory)
                if not overlap_stats:
                    continue
                
                similarity_score = overlap_stats['similarity']
                if similarity_score < min_similarity_threshold:
                    continue
                
                # Get candidate metrics
                candidate_metrics = self._get_trajectory_metrics(candidate_trajectory)
                candidate_final = candidate_trajectory[-1]['cumulative_revenue']
                candidate_millions = float(candidate_final) / 1_000_000
                
                # Get movie metadata
                movie_sample = Movie.objects.filter(
                    title=candidate_title,
                    release_date=candidate_release_date
                ).first()
                
                similar_movies.append({
                    'title': candidate_title,
                    'release_date': candidate_release_date,
                    'similarity_score': similarity_score,
                    'final_cumulative_presales': candidate_final,
                    'final_cumulative_millions': candidate_millions,
                    'booking_pattern': candidate_metrics.get('booking_pattern', 'unknown'),
                    'early_growth_rate': candidate_metrics.get('early_growth_rate', 0),
                    'late_growth_rate': candidate_metrics.get('late_growth_rate', 0),
                    'overlap_ratio': overlap_stats['overlap_ratio'],
                    'shared_points': len(overlap_stats['common_dbrs']),
                    'shared_window': self._format_time_window(overlap_stats['common_dbrs'][0], overlap_stats['common_dbrs'][-1]),
                    'growth_alignment': overlap_stats['growth_alignment'],
                    'genre': movie_sample.genre if movie_sample else None,
                    'studio_name': movie_sample.studio_name if movie_sample else None,
                    'rating': movie_sample.rating if movie_sample else None
                })
                
            except Exception as e:
                logger.warning(f"Error processing '{candidate_title}': {e}")
                continue
        
        # Sort by similarity (highest first)
        similar_movies.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # Get top matches
        top_similar = similar_movies[:limit]
        
        # Format analysis
        analysis = self._format_performance_like_analysis(
            target_title,
            target_trajectory,
            target_metrics,
            target_millions,
            top_similar
        )
        
        # Get target movie metadata
        target_movie_sample = Movie.objects.filter(title__iexact=target_title, release_date=target_release_date).first()
        
        return {
            'target_movie': {
                'title': target_title,
                'release_date': target_release_date,
                'final_cumulative_presales': target_final,
                'final_cumulative_millions': target_millions,
                'booking_pattern': target_metrics.get('booking_pattern', 'unknown'),
                'early_growth_rate': target_metrics.get('early_growth_rate', 0),
                'late_growth_rate': target_metrics.get('late_growth_rate', 0),
                'genre': target_movie_sample.genre if target_movie_sample else None,
                'studio_name': target_movie_sample.studio_name if target_movie_sample else None,
                'rating': target_movie_sample.rating if target_movie_sample else None
            },
            'similar_movies': top_similar,
            'analysis': analysis,
            'total_found': len(similar_movies),
            'returned': len(top_similar)
        }
    
    def _format_performance_like_analysis(
        self,
        target_title: str,
        target_trajectory: List[Dict[str, Any]],
        target_metrics: Dict[str, Any],
        target_millions: float,
        similar_movies: List[Dict[str, Any]]
    ) -> str:
        """
        Format analysis for "movies performing like [target]" query.
        """
        if not similar_movies:
            return f"No movies found with similar cumulative presales trajectory to '{target_title}'."
        
        lines = []
        lines.append(f"**Movies Performing Like {target_title}:**\n")
        
        # Describe target movie's pattern
        target_pattern = target_metrics.get('booking_pattern', 'unknown')
        pattern_description = {
            'early': "strong early presales momentum with sustained demand",
            'late': "slow early growth followed by sharp acceleration near release",
            'consistent': "moderate, steady growth throughout the presales window"
        }.get(target_pattern, "similar cumulative presales growth patterns")
        
        lines.append(f"{target_title} shows {pattern_description}, reaching approximately **${target_millions:.2f}M** in cumulative presales.\n")
        lines.append(f"Based on cumulative presales trajectories (DBR vs cumulative revenue), the following movies show similar performance:\n")
        
        # List similar movies
        for idx, movie in enumerate(similar_movies, 1):
            similarity = movie['similarity_score']
            comp_millions = movie['final_cumulative_millions']
            pattern = movie['booking_pattern']
            growth_text = self._format_growth_alignment_text(movie.get('growth_alignment', {}))
            
            lines.append(f"{idx}. **{movie['title']}**")
            lines.append(f"   - Similarity Score: {similarity:.3f}")
            if movie.get('shared_window'):
                lines.append(f"   - Shared DBR Window: {movie['shared_window']} ({movie.get('shared_points', 0)} points, {movie.get('overlap_ratio', 0):.0%} overlap)")
            lines.append(f"   - Slope Alignment: {growth_text}")
            lines.append(f"   - Final Cumulative Presales: ${comp_millions:.2f}M")
            lines.append(f"   - Booking Pattern: {pattern.title()}")
            
            # Add trajectory description
            if pattern == 'late':
                lines.append(f"   - Trajectory: Slow start in early DBR window (DBR -50 to -30), sharp acceleration in final two weeks")
            elif pattern == 'early':
                lines.append(f"   - Trajectory: Strong early momentum (DBR -50 to -30), sustained growth")
            elif pattern == 'consistent':
                lines.append(f"   - Trajectory: Steady, moderate growth throughout presales window")
            
            if movie.get('genre'):
                lines.append(f"   - Genre: {movie['genre']}")
            lines.append("")
        
        # Summary
        if len(similar_movies) > 1:
            best_match = similar_movies[0]
            lines.append(f"**Best Match:** {best_match['title']} (similarity: {best_match['similarity_score']:.3f})")
            lines.append(f"\nBoth {target_title} and {best_match['title']} exhibit similar day-by-day cumulative growth patterns,")
            lines.append(f"with {target_title} reaching ${target_millions:.2f}M and {best_match['title']} reaching ${best_match['final_cumulative_millions']:.2f}M,")
            lines.append(f"sharing {best_match.get('shared_points', 0)} DBR points where {self._format_growth_alignment_text(best_match.get('growth_alignment', {}))}.")
        
        return "\n".join(lines)
    
    def get_top_circuit_in_dma(self, dma_name: str) -> Dict[str, Any]:
        """Return the circuit with the most theaters in a given DMA (case-insensitive)."""
        from django.db.models import Count
        qs = (
            Movie.objects
            .filter(dma__isnull=False)
            .filter(dma__iexact=dma_name)
            .values('circuit_name')
            .annotate(theater_count=Count('theater_id', distinct=True))
            .order_by('-theater_count')
        )
        top = qs.first()
        if not top:
            return {'error': f'No theaters found in DMA "{dma_name}"'}
        return {
            'dma': dma_name,
            'circuit_name': top['circuit_name'] or 'Unknown',
            'theater_count': int(top['theater_count'] or 0)
        }

    def get_movies_with_runtime_over(self, minutes: int, limit: int = 50) -> List[Dict[str, Any]]:
        """List distinct movies with runtime > minutes, ordered by runtime desc."""
        qs = (
            Movie.objects
            .filter(runtime__isnull=False)
            .filter(runtime__gt=minutes)
            .values('title', 'release_date', 'runtime', 'genre', 'rating', 'studio_name')
            .distinct()
            .order_by('-runtime')[:limit]
        )
        return list(qs)

