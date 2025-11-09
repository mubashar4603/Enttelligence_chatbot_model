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
        
        for idx, movie_info in enumerate(movies, 1):
            if idx % 100 == 0:
                logger.info(f"   Processing movie {idx}/{total_movies}: {movie_info['title']}")
            
            title_str = movie_info['title']
            release_date_val = movie_info['release_date']
            
            # Get all records for this movie
            movie_records = Movie.objects.filter(
                title__iexact=title_str,
                release_date=release_date_val
            )
            
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
                    continue
                
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
            
            # Calculate cumulative metrics in a separate efficient query
            self._update_cumulative_metrics(title_str, release_date_val)
        
        # Calculate total records for this movie
        total_records = 0
        if title_str:
            total_records = MovieDailyPerformance.objects.filter(
                title__iexact=title_str,
                release_date=release_date_val
            ).count()
        else:
            total_records = MovieDailyPerformance.objects.count()
        
        logger.info(f"✅ Created {created_count} new records, {total_records} total records for this movie")
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
    
    def get_day_by_day_trend(
        self,
        title: str,
        start_dir: Optional[int] = None,
        end_dir: Optional[int] = None,
        use_cache: bool = True
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
        
        if use_cache:
            # Apply DIR constraint: First weekend uses DIR values -1, 1, 2
            # DIR = date_sh - release_date (if date_sh < release_date) or date_sh - release_date + 1 (if date_sh >= release_date)
            performances = (
                MovieDailyPerformance.objects
                .filter(
                    title__iexact=title,
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
            return self._calculate_day_by_day_from_raw(title, start_dir, end_dir)
    
    def get_day_by_day_dbr_trend(
        self,
        title: str,
        start_dbr: Optional[int] = None,
        end_dbr: Optional[int] = None,
        use_cache: bool = True
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
        if use_cache:
            # Get movie release date for filtering presales data
            movie = Movie.objects.filter(title__iexact=title).first()
            if not movie:
                return []
            release_date = movie.release_date
            
            # First, find the actual DBR range available for this movie
            # IMPORTANT: Only presales data (DBR < 0 and date_sh < release_date)
            dbr_range = (
                MovieDailyPerformance.objects
                .filter(
                    title__iexact=title, 
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
                result = self.get_cumulative_advance_booking(title, start_dbr, end_dbr)
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
        end_dir: int
    ) -> List[Dict[str, Any]]:
        """Calculate day-by-day from raw Movie table."""
        release_date = (
            Movie.objects
            .filter(title__iexact=title)
            .values_list('release_date', flat=True)
            .first()
        )
        
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
    
    def get_cumulative_advance_booking(self, movie_title: str, dbr_start: int, 
                                      dbr_end: int) -> Dict[str, Any]:
        """
        Get cumulative advance booking sales for a movie in DBR range.
        Uses raw SQL matching the user's ground-truth SQL with windowed cumulative sums.
        """
        from django.db import connection
        from datetime import datetime
        
        # Query directly from Movie table grouped by DBR
        with connection.cursor() as cursor:
            cursor.execute("""
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
                    WHERE UPPER(title) = UPPER(%s)
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
            """, [movie_title, dbr_start, dbr_end])
            
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
        min_correlation: float = 0.80,
        dbr_end: int = -1
    ) -> List[Dict[str, Any]]:
        """
        Find best comparable titles based on cumulative presales trajectory similarity.
        
        This method analyzes cumulative presales growth patterns (DBR vs cumulative revenue)
        using Pearson correlation on normalized curves to identify movies with similar booking
        behavior and audience engagement dynamics.
        
        Returns ALL movies that meet the correlation threshold (≥ min_correlation), not just a fixed number.
        All movies showing the same trend are considered comp titles.
        
        Args:
            target_title: Movie title to find comparables for
            limit: Optional maximum number of comp titles to return (None = return all matches)
            min_correlation: Minimum Pearson correlation threshold (default: 0.80)
            dbr_end: Maximum DBR value to include (default: -1, only presales DBR < 0)
            
        Returns:
            List of comp titles with correlation scores and trajectory analysis, sorted by correlation (highest first)
        """
        logger.info(f"🔍 Finding comp titles for '{target_title}' based on cumulative presales trajectory")
        logger.info(f"   Using correlation threshold: {min_correlation}, DBR end: {dbr_end}")
        if limit:
            logger.info(f"   Limiting results to top {limit} matches")
        else:
            logger.info(f"   Returning ALL movies with correlation >= {min_correlation}")
        
        # Get target movie's cumulative presales trajectory
        # Only presales data (DBR < 0, date_sh < release_date)
        target_trajectory = self._get_cumulative_presales_trajectory(target_title, dbr_end=dbr_end)
        
        if not target_trajectory or len(target_trajectory) == 0:
            logger.warning(f"No presales trajectory data found for '{target_title}'")
            return []
        
        # Get all other movies in database
        all_movies = (
            Movie.objects
            .exclude(title__iexact=target_title)
            .values('title', 'release_date')
            .distinct()
        )
        
        logger.info(f"   Comparing against {all_movies.count()} candidate movies")
        
        comp_analyses = []
        
        for candidate in all_movies:
            candidate_title = candidate['title']
            
            try:
                # Get candidate's cumulative presales trajectory
                # Filter by DBR constraint: DBR <= 2
                candidate_trajectory = self._get_cumulative_presales_trajectory(
                    candidate_title, 
                    dbr_end=dbr_end
                )
                
                if not candidate_trajectory or len(candidate_trajectory) == 0:
                    continue
                
                # Calculate trajectory similarity (Pearson correlation)
                correlation = self._calculate_trajectory_similarity(
                    target_trajectory,
                    candidate_trajectory
                )
                
                # Filter by minimum correlation threshold
                # All movies meeting this threshold are comp titles
                if correlation < min_correlation:
                    continue
                
                # Get First Weekend Revenue for both target and candidate
                # This is critical for comp title selection - revenue scale matters!
                target_first_weekend = self.get_movie_performance_by_period(
                    target_title, 
                    'first_weekend', 
                    use_cache=True
                )
                candidate_first_weekend = self.get_movie_performance_by_period(
                    candidate_title, 
                    'first_weekend', 
                    use_cache=True
                )
                
                target_fw_revenue = float(target_first_weekend.get('total_revenue', 0) or 0) if 'error' not in target_first_weekend else 0.0
                candidate_fw_revenue = float(candidate_first_weekend.get('total_revenue', 0) or 0) if 'error' not in candidate_first_weekend else 0.0
                
                # Calculate revenue scale similarity score (0-1, where 1 = identical revenue)
                # Use logarithmic scale to handle wide revenue ranges better
                revenue_similarity = 0.0
                if target_fw_revenue > 0 and candidate_fw_revenue > 0:
                    # Calculate ratio (smaller / larger)
                    ratio = min(target_fw_revenue, candidate_fw_revenue) / max(target_fw_revenue, candidate_fw_revenue)
                    # Convert to similarity score (ratio of 0.5 = 50% difference = 0.5 similarity)
                    # ratio of 0.8 = 20% difference = 0.8 similarity
                    # ratio of 1.0 = identical = 1.0 similarity
                    revenue_similarity = ratio
                
                # Calculate composite score: 60% revenue scale + 40% trajectory correlation
                # Revenue scale is more important for comp titles (similar performance)
                # Trajectory correlation is secondary (similar booking pattern)
                composite_score = (revenue_similarity * 0.6) + (correlation * 0.4)
                
                # Get final cumulative presales
                final_cumulative = candidate_trajectory[-1]['cumulative_revenue'] if candidate_trajectory else Decimal('0')
                
                # Get additional metrics for the candidate
                candidate_metrics = self._get_trajectory_metrics(candidate_trajectory)
                
                # Get movie metadata
                movie_sample = Movie.objects.filter(
                    title=candidate_title,
                    release_date=candidate['release_date']
                ).first()
                
                comp_analysis = {
                    'title': candidate_title,
                    'release_date': candidate['release_date'],
                    'correlation': correlation,
                    'correlation_percent': correlation * 100,  # For display as percentage
                    'revenue_similarity': revenue_similarity,
                    'revenue_similarity_percent': revenue_similarity * 100,
                    'composite_score': composite_score,  # Combined score for ranking
                    'first_weekend_revenue': Decimal(str(candidate_fw_revenue)),
                    'target_first_weekend_revenue': Decimal(str(target_fw_revenue)),
                    'final_cumulative_presales': final_cumulative,
                    'genre': movie_sample.genre if movie_sample else None,
                    'studio_name': movie_sample.studio_name if movie_sample else None,
                    'rating': movie_sample.rating if movie_sample else None,
                    'trajectory': candidate_trajectory,  # Include full trajectory for analysis
                    **candidate_metrics
                }
                
                comp_analyses.append(comp_analysis)
                
            except Exception as e:
                logger.warning(f"Error processing candidate '{candidate_title}': {e}")
                continue
        
        # Sort by composite score (highest first) - considers both revenue scale and trajectory
        comp_analyses.sort(key=lambda x: x['composite_score'], reverse=True)
        
        # Return all matches that meet the threshold, or limit if specified
        if limit is not None:
            comp_titles = comp_analyses[:limit]
        else:
            comp_titles = comp_analyses  # Return all matches
        
        logger.info(f"✅ Found {len(comp_titles)} comp titles for '{target_title}' (correlation >= {min_correlation})")
        logger.info(f"   Target First Weekend Revenue: ${float(comp_analyses[0]['target_first_weekend_revenue'])/1_000_000:.2f}M" if comp_analyses else "")
        for idx, comp in enumerate(comp_titles, 1):
            fw_rev = float(comp['first_weekend_revenue']) / 1_000_000
            rev_sim = comp['revenue_similarity']
            corr = comp['correlation']
            comp_score = comp['composite_score']
            logger.info(f"   {idx}. {comp['title']} (First Weekend: ${fw_rev:.2f}M, Revenue Similarity: {rev_sim:.3f}, Correlation: {corr:.3f}, Composite: {comp_score:.3f})")
        
        return comp_titles
    
    def _get_cumulative_presales_trajectory(
        self, 
        title: str, 
        dbr_start: Optional[int] = None,
        dbr_end: int = -1
    ) -> List[Dict[str, Any]]:
        """
        Get cumulative presales trajectory for a movie by DBR.
        Returns list of {dbr_value, cumulative_revenue, cumulative_reserved} ordered by DBR ascending.
        
        This represents cumulative presales as DBR approaches 0 (from -60 → -1),
        where each point shows the running total of all presales collected up to that DBR date.
        
        IMPORTANT: Only presales data (DBR < 0, date_sh < release_date) is included.
        
        Args:
            title: Movie title
            dbr_start: Starting DBR (if None, uses maximum available negative DBR in data)
            dbr_end: Ending DBR (default: -1, only presales DBR < 0)
            
        Returns:
            List of trajectory points with dbr_value, cumulative_revenue, cumulative_reserved
        """
        # First, try to get from get_cumulative_advance_booking (most accurate)
        # Use default start if not provided
        if dbr_start is None:
            dbr_start = -60  # Default to wide range
        
        try:
            result = self.get_cumulative_advance_booking(title, dbr_start, dbr_end)
            if 'daily_data' in result and result['daily_data']:
                trajectory = []
                for day_data in result['daily_data']:
                    dbr_val = int(day_data.get('dbr_value', 0))
                    # Filter by DBR constraint: DBR <= 2
                    if dbr_val > dbr_end:
                        continue
                    trajectory.append({
                        'dbr_value': dbr_val,
                        'cumulative_revenue': Decimal(str(day_data.get('cumulative_revenue', 0))),
                        'cumulative_reserved': int(day_data.get('cumulative_reserved', 0))
                    })
                # Sort by DBR ascending (most negative to least negative: -60, -59, ..., 2)
                trajectory.sort(key=lambda x: x['dbr_value'])
                return trajectory
        except Exception as e:
            logger.warning(f"Error getting cumulative advance booking for '{title}': {e}")
        
        # Fallback: Get DBR-based trend data and calculate cumulative
        dbr_trend = self.get_day_by_day_dbr_trend(
            title, 
            start_dbr=dbr_start,
            end_dbr=dbr_end,
            use_cache=True
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
        comp_titles: List[Dict[str, Any]],
        include_trajectory_details: bool = True
    ) -> str:
        """
        Format comp titles analysis with detailed trend analysis and reasoning.
        
        Args:
            target_title: The target movie title
            comp_titles: List of comp title dictionaries from find_best_comp_titles_by_trajectory
            include_trajectory_details: Whether to include detailed trajectory analysis
            
        Returns:
            Formatted analysis string with trend analysis and reasoning
        """
        if not comp_titles:
            return f"No comparable titles found for '{target_title}' based on cumulative presales trajectory."
        
        # Get target movie trajectory and First Weekend Revenue for context
        target_trajectory = self._get_cumulative_presales_trajectory(target_title)
        target_final = target_trajectory[-1]['cumulative_revenue'] if target_trajectory else Decimal('0')
        target_metrics = self._get_trajectory_metrics(target_trajectory) if target_trajectory else {}
        target_first_weekend = self.get_movie_performance_by_period(target_title, 'first_weekend', use_cache=True)
        target_fw_revenue = float(target_first_weekend.get('total_revenue', 0) or 0) / 1_000_000 if 'error' not in target_first_weekend else 0.0
        
        lines = []
        lines.append(f"**Best Comparable Titles for {target_title}:**\n")
        lines.append(f"**Target Movie Performance:**")
        lines.append(f"- First Weekend Revenue (DIR -1, 1, 2): ${target_fw_revenue:.2f}M")
        lines.append(f"- Final Cumulative Presales: ${float(target_final)/1_000_000:.2f}M")
        lines.append(f"- Booking Pattern: {target_metrics.get('booking_pattern', 'unknown').title()}")
        lines.append("")
        lines.append("**Selection Methodology:**")
        lines.append("Comp titles are selected based on a composite score that combines:")
        lines.append("1. **Revenue Scale Similarity (60% weight)**: How close First Weekend Revenue values are")
        lines.append("2. **Trajectory Correlation (40% weight)**: How similar the presales growth curve shapes are")
        lines.append("")
        
        # Analyze each comp title with detailed reasoning
        for idx, comp in enumerate(comp_titles[:5], 1):  # Top 5 comp titles
            comp_title = comp['title']
            comp_fw_revenue = comp.get('first_weekend_revenue', 0)
            comp_cumulative = float(comp.get('final_cumulative_presales', 0)) / 1_000_000
            correlation = comp.get('correlation', 0)
            revenue_sim = comp.get('revenue_similarity', 0)
            composite_score = comp.get('composite_score', 0)
            comp_pattern = comp.get('booking_pattern', 'unknown')
            
            lines.append(f"**{idx}. {comp_title}**")
            lines.append(f"   **First Weekend Revenue:** ${comp_fw_revenue:.2f}M")
            lines.append(f"   **Final Cumulative Presales:** ${comp_cumulative:.2f}M")
            lines.append("")
            
            # Revenue scale analysis
            revenue_diff = abs(target_fw_revenue - comp_fw_revenue)
            revenue_diff_pct = (revenue_diff / target_fw_revenue * 100) if target_fw_revenue > 0 else 0
            
            lines.append(f"   **Revenue Scale Similarity: {revenue_sim:.1%}**")
            if revenue_sim >= 0.8:
                lines.append(f"   ✓ Excellent match: Revenue difference is only ${revenue_diff:.2f}M ({revenue_diff_pct:.1f}%)")
            elif revenue_sim >= 0.6:
                lines.append(f"   ✓ Good match: Revenue difference is ${revenue_diff:.2f}M ({revenue_diff_pct:.1f}%)")
            elif revenue_sim >= 0.4:
                lines.append(f"   ⚠ Moderate match: Revenue difference is ${revenue_diff:.2f}M ({revenue_diff_pct:.1f}%)")
            else:
                lines.append(f"   ⚠ Lower match: Revenue difference is ${revenue_diff:.2f}M ({revenue_diff_pct:.1f}%)")
            
            # Trajectory pattern analysis
            lines.append(f"   **Trajectory Correlation: {correlation:.1%}**")
            target_pattern = target_metrics.get('booking_pattern', 'unknown')
            
            if target_pattern == comp_pattern:
                if comp_pattern == 'late':
                    lines.append(f"   ✓ Both show **late surge pattern**: Slow start, then sharp acceleration in final weeks (DBR -10 to -1)")
                elif comp_pattern == 'early':
                    lines.append(f"   ✓ Both show **early acceleration pattern**: Strong momentum from early DBR window (DBR -50 to -30)")
                elif comp_pattern == 'consistent':
                    lines.append(f"   ✓ Both show **steady growth pattern**: Consistent daily booking activity throughout presales window")
            else:
                lines.append(f"   ⚠ Different patterns: Target shows {target_pattern}, {comp_title} shows {comp_pattern}")
            
            # Trend details
            if include_trajectory_details and comp.get('trajectory'):
                trajectory = comp.get('trajectory', [])
                if len(trajectory) >= 2:
                    early_rev = float(trajectory[0]['cumulative_revenue']) / 1_000_000 if trajectory else 0
                    mid_rev = float(trajectory[len(trajectory)//2]['cumulative_revenue']) / 1_000_000 if len(trajectory) > 2 else 0
                    final_rev = float(trajectory[-1]['cumulative_revenue']) / 1_000_000 if trajectory else 0
                    
                    lines.append(f"   **Trend Analysis:**")
                    lines.append(f"   - Early Presales (DBR -50 to -30): ${early_rev:.2f}M")
                    if mid_rev > 0:
                        lines.append(f"   - Mid Presales (DBR -30 to -15): ${mid_rev:.2f}M")
                    lines.append(f"   - Final Presales (DBR -15 to -1): ${final_rev:.2f}M")
                    
                    if comp_pattern == 'late':
                        lines.append(f"   - Pattern: Gradual early growth, then {((final_rev - mid_rev) / mid_rev * 100):.0f}% surge in final weeks")
                    elif comp_pattern == 'early':
                        lines.append(f"   - Pattern: Strong early momentum with {((mid_rev - early_rev) / early_rev * 100):.0f}% growth in first half")
            
            # Why it's a good comp
            lines.append(f"   **Composite Score: {composite_score:.3f}** (Higher = Better Match)")
            lines.append(f"   - Revenue similarity contributes: {revenue_sim * 0.6:.3f} ({revenue_sim:.1%} × 60%)")
            lines.append(f"   - Trajectory correlation contributes: {correlation * 0.4:.3f} ({correlation:.1%} × 40%)")
            lines.append("")
            
            # Reasoning summary
            if idx == 1:
                lines.append(f"   **Why {comp_title} is the Best Match:**")
                if revenue_sim >= 0.7:
                    lines.append(f"   • Revenue scale is very similar (within {revenue_diff_pct:.1f}%), indicating comparable box office performance potential")
                if correlation >= 0.8:
                    lines.append(f"   • Presales trajectory shape is highly correlated ({correlation:.1%}), suggesting similar audience booking behavior")
                if target_pattern == comp_pattern:
                    lines.append(f"   • Both movies show the same booking pattern ({comp_pattern}), indicating comparable audience engagement dynamics")
                lines.append("")
        
        # Secondary comparables
        if len(comp_titles) > 1:
            lines.append("\n**Secondary Comparables:**")
            lines.append("\nAdditional titles with somewhat similar cumulative trends include:")
            
            for comp in comp_titles[1:4]:  # Next 3
                comp_millions = float(comp.get('final_cumulative_presales', 0)) / 1_000_000
                similarity = comp.get('trajectory_similarity', 0)
                pattern = comp.get('booking_pattern', 'unknown')
                lines.append(f"- **{comp['title']}**: ${comp_millions:.2f}M cumulative presales, {pattern} booking pattern (similarity: {similarity:.3f})")
        
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
        
        # Get target movie's trajectory
        target_trajectory = self._get_cumulative_presales_trajectory(target_title)
        
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
        all_movies = (
            Movie.objects
            .exclude(title__iexact=target_title)
            .values('title', 'release_date')
            .distinct()
        )
        
        similar_movies = []
        
        for candidate in all_movies:
            candidate_title = candidate['title']
            
            try:
                candidate_trajectory = self._get_cumulative_presales_trajectory(candidate_title)
                
                if not candidate_trajectory or len(candidate_trajectory) == 0:
                    continue
                
                # Calculate similarity
                similarity_score = self._calculate_trajectory_similarity(
                    target_trajectory,
                    candidate_trajectory
                )
                
                # Filter by minimum threshold
                if similarity_score < min_similarity_threshold:
                    continue
                
                # Get candidate metrics
                candidate_metrics = self._get_trajectory_metrics(candidate_trajectory)
                candidate_final = candidate_trajectory[-1]['cumulative_revenue']
                candidate_millions = float(candidate_final) / 1_000_000
                
                # Get movie metadata
                movie_sample = Movie.objects.filter(
                    title=candidate_title,
                    release_date=candidate['release_date']
                ).first()
                
                similar_movies.append({
                    'title': candidate_title,
                    'release_date': candidate['release_date'],
                    'similarity_score': similarity_score,
                    'final_cumulative_presales': candidate_final,
                    'final_cumulative_millions': candidate_millions,
                    'booking_pattern': candidate_metrics.get('booking_pattern', 'unknown'),
                    'early_growth_rate': candidate_metrics.get('early_growth_rate', 0),
                    'late_growth_rate': candidate_metrics.get('late_growth_rate', 0),
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
        target_movie_sample = Movie.objects.filter(title__iexact=target_title).first()
        
        return {
            'target_movie': {
                'title': target_title,
                'release_date': target_movie_sample.release_date if target_movie_sample else None,
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
            
            lines.append(f"{idx}. **{movie['title']}**")
            lines.append(f"   - Similarity Score: {similarity:.3f}")
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
            lines.append(f"reflecting comparable scale and shape in their presales trajectories.")
        
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

