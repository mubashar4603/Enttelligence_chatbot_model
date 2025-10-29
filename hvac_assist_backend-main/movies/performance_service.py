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
        Calculate DIR (Days In Release) according to SQL logic:
        - If date_sh < release_date: DIR = date_sh - release_date (negative)
        - If date_sh >= release_date: DIR = (date_sh - release_date) + 1
        
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
    def calculate_dbr(last_updates: datetime, release_date: date) -> int:
        """
        Calculate DBR (Days Before Release) according to SQL logic.
        
        Args:
            last_updates: Last update timestamp
            release_date: Movie release date
            
        Returns:
            DBR value (integer, negative values indicate days before release)
        """
        if not last_updates:
            return None
        update_date = last_updates.date()
        diff = (update_date - release_date).days
        if diff < 0:
            return diff
        else:
            return diff + 1
    
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
            'first_weekend': (-1, 3),
            'first_week': (-1, 7),
            'first_5_days': (-1, 5),
            'first_10_days': (-1, 10),
            'first_14_days': (-1, 14),
            'first_30_days': (-1, 30),
            'opening_weekend': (-1, 3),
        }
        return period_map.get(period_label.lower(), (-1, 3))
    
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
            
            # Aggregate by date_sh AND last_updates date for accurate DBR calculation
            # DBR is calculated from last_updates, so we need to group by both
            # to capture all advance booking scenarios
            from django.db import connection
            
            # Use raw SQL aggregation - group by date_sh and last_updates date
            # This ensures we capture all DBR variations
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT 
                            date_sh,
                            last_updates::date as last_update_date,
                            SUM(
                                CASE 
                                    WHEN reserved IS NULL OR reserved < 0 THEN 0
                                    ELSE reserved
                                END
                            ) as total_reserved,
                            SUM(
                                COALESCE(actual_total_seats, 0)
                            ) as total_seats,
                            SUM(
                                CASE 
                                    WHEN reserved IS NULL OR reserved < 0 THEN 0
                                    WHEN price IS NULL OR price <= 0 THEN 0
                                    ELSE (price * reserved)
                                END
                            ) as total_revenue,
                            AVG(
                                CASE 
                                    WHEN price IS NULL OR price <= 0 THEN NULL
                                    ELSE price
                                END
                            ) as avg_price,
                            COUNT(id) as count_shows
                        FROM movies
                        WHERE UPPER(title) = UPPER(%s)
                        AND release_date = %s
                        AND price IS NOT NULL 
                        AND price > 0
                        GROUP BY date_sh, last_updates::date
                        ORDER BY date_sh, last_updates::date
                    """, [title_str, release_date_val])
                    
                    # Convert raw SQL results to dictionary format
                    columns = [col[0] for col in cursor.description]
                    aggregate_list = []
                    for row in cursor.fetchall():
                        row_dict = dict(zip(columns, row))
                        # Ensure proper types
                        row_dict['date_sh'] = row_dict['date_sh']
                        row_dict['last_update_date'] = row_dict['last_update_date']
                        row_dict['total_reserved'] = int(row_dict['total_reserved'] or 0)
                        row_dict['total_seats'] = int(row_dict['total_seats'] or 0)
                        row_dict['total_revenue'] = Decimal(str(row_dict['total_revenue'] or 0))
                        row_dict['avg_price'] = Decimal(str(row_dict['avg_price'] or 0))
                        row_dict['count_shows'] = int(row_dict['count_shows'] or 0)
                        aggregate_list.append(row_dict)
            except Exception as e:
                # If database-level aggregation fails due to data type issues,
                # fall back to Python-level processing (slower but safe)
                logger.warning(f"Database aggregation failed: {e}. Falling back to Python-level processing.")
                
                # Get all records and process in Python
                all_records = list(movie_records.filter(
                    price__isnull=False,
                    price__gt=0
                ).values('date_sh', 'reserved', 'price', 'actual_total_seats'))
                
                # Group by date_sh manually
                from collections import defaultdict
                daily_dict = defaultdict(lambda: {
                    'total_reserved': 0,
                    'total_seats': 0,
                    'total_revenue': Decimal('0'),
                    'prices': [],
                    'count_shows': 0
                })
                
                for record in all_records:
                    date_key = record['date_sh']
                    
                    # Safely convert reserved
                    try:
                        reserved_val = int(record['reserved']) if record['reserved'] is not None else 0
                        if reserved_val < 0:
                            reserved_val = 0
                    except (ValueError, TypeError):
                        reserved_val = 0
                    
                    # Safely get price
                    price_val = Decimal(str(record['price'])) if record['price'] else Decimal('0')
                    
                    daily_dict[date_key]['total_reserved'] += reserved_val
                    daily_dict[date_key]['total_seats'] += record.get('actual_total_seats', 0) or 0
                    daily_dict[date_key]['total_revenue'] += price_val * Decimal(str(reserved_val))
                    daily_dict[date_key]['prices'].append(price_val)
                    daily_dict[date_key]['count_shows'] += 1
                
                # Convert to list format matching the original structure
                aggregate_list = []
                for date_key in sorted(daily_dict.keys()):
                    daily_data = daily_dict[date_key]
                    avg_price = sum(daily_data['prices']) / len(daily_data['prices']) if daily_data['prices'] else Decimal('0')
                    aggregate_list.append({
                        'date_sh': date_key,
                        'total_reserved': daily_data['total_reserved'],
                        'total_seats': daily_data['total_seats'],
                        'total_revenue': daily_data['total_revenue'],
                        'avg_price': avg_price,
                        'count_shows': daily_data['count_shows']
                    })
            
            for day_data in aggregate_list:
                date_sh_val = day_data['date_sh']
                last_update_date = day_data.get('last_update_date')
                dir_value = self.calculate_dir(date_sh_val, release_date_val)
                
                total_reserved = day_data['total_reserved'] or 0
                total_seats = day_data['total_seats'] or 0
                total_revenue = day_data['total_revenue'] or Decimal('0')
                avg_price = day_data['avg_price'] or Decimal('0')
                
                # Calculate occupancy rate
                occupancy_rate = None
                if total_seats > 0:
                    occupancy_rate = (float(total_reserved) / float(total_seats)) * 100
                
                # Calculate DBR from last_updates date (not just when DIR < 0)
                # DBR represents when the data was last updated relative to release
                dbr_value = None
                if last_update_date:
                    from datetime import datetime
                    # Convert date to datetime for calculate_dbr
                    last_updates_dt = datetime.combine(last_update_date, datetime.min.time())
                    dbr_value = self.calculate_dbr(last_updates_dt, release_date_val)
                
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
                # Note: We may have multiple records for same date_sh but different last_updates (different DBR)
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
                    # If same date_sh has multiple last_updates dates, combine them
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
        Update cumulative revenue and reserved seats for all DIR values.
        Uses efficient ordered query to calculate running totals.
        """
        performances = (
            MovieDailyPerformance.objects
            .filter(title__iexact=title, release_date=release_date)
            .order_by('dir_value')
        )
        
        cumulative_revenue = Decimal('0')
        cumulative_reserved = 0
        
        # Use bulk_update for efficiency
        updates = []
        for perf in performances:
            cumulative_revenue += perf.total_revenue
            cumulative_reserved += perf.total_reserved_seats
            
            perf.cumulative_revenue = cumulative_revenue
            perf.cumulative_reserved = cumulative_reserved
            updates.append(perf)
        
        if updates:
            MovieDailyPerformance.objects.bulk_update(
                updates,
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
        
        # For first_weekend, use raw SQL to match exact SQL logic: DATEDIFF <= 2
        # SQL uses: DATEDIFF(date_sh, release_date) <= 2, which is date_sh - release_date between -1 and 2
        if period_label == 'first_weekend':
            from django.db import connection
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        MIN(release_date) AS release_date,
                        SUM(
                            CASE 
                                WHEN reserved IS NULL OR reserved < 0 THEN 0
                                ELSE reserved
                            END
                        ) as total_reserved,
                        SUM(
                            CASE 
                                WHEN reserved IS NULL OR reserved < 0 THEN 0
                                WHEN price IS NULL OR price <= 0 THEN 0
                                ELSE (price * reserved)
                            END
                        ) as total_revenue,
                        AVG(
                            CASE 
                                WHEN price IS NULL OR price <= 0 THEN NULL
                                ELSE price
                            END
                        ) as avg_price,
                        SUM(
                            COALESCE(actual_total_seats, 0)
                        ) as total_seats
                    FROM movies
                    WHERE UPPER(title) = UPPER(%s)
                    AND (date_sh - release_date) BETWEEN -1 AND 2
                    AND price IS NOT NULL 
                    AND price > 0
                    AND reserved IS NOT NULL
                    AND reserved >= 0
                """, [title])
                
                row = cursor.fetchone()
                if not row or not row[0]:
                    return {'error': f'No first weekend data found for "{title}"'}
                
                release_date = row[0]
                total_reserved = int(row[1] or 0)
                total_revenue = Decimal(str(row[2] or 0))
                avg_price = Decimal(str(row[3] or 0))
                total_seats = int(row[4] or 0)
                
                occupancy_rate = (float(total_reserved) / float(total_seats)) * 100 if total_seats > 0 else 0.0
                
                return {
                    'title': title,
                    'release_date': release_date,
                    'period': period_label,
                    'dir_range': (-1, 2),  # SQL uses date_diff -1 to 2, which is DIR -1, 1, 2, 3
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
                        SUM(
                            CASE 
                                WHEN reserved IS NULL OR reserved < 0 THEN 0
                                ELSE reserved
                            END
                        ) as total_reserved,
                        SUM(
                            COALESCE(actual_total_seats, 0)
                        ) as total_seats,
                        SUM(
                            CASE 
                                WHEN reserved IS NULL OR reserved < 0 THEN 0
                                WHEN price IS NULL OR price <= 0 THEN 0
                                ELSE (price * reserved)
                            END
                        ) as total_revenue,
                        AVG(
                            CASE 
                                WHEN price IS NULL OR price <= 0 THEN NULL
                                ELSE price
                            END
                        ) as avg_price
                    FROM movies
                    WHERE UPPER(title) = UPPER(%s)
                    AND release_date = %s
                    AND date_sh >= %s
                    AND date_sh <= %s
                    AND price IS NOT NULL 
                    AND price > 0
                """, [title, release_date, start_date, end_date])
                
                row = cursor.fetchone()
                if row:
                    results = {
                        'total_reserved': int(row[0] or 0),
                        'total_seats': int(row[1] or 0),
                        'total_revenue': Decimal(str(row[2] or 0)),
                        'avg_price': Decimal(str(row[3] or 0))
                    }
                else:
                    results = {
                        'total_reserved': 0,
                        'total_seats': 0,
                        'total_revenue': Decimal('0'),
                        'avg_price': Decimal('0')
                    }
        except Exception as e:
            logger.warning(f"Database aggregation failed in fallback method: {e}. Using Python-level processing.")
            # Fall back to Python processing
            records = list(Movie.objects.filter(
                title__iexact=title,
                release_date=release_date,
                date_sh__gte=start_date,
                date_sh__lte=end_date,
                price__isnull=False,
                price__gt=0
            ).values('reserved', 'price', 'actual_total_seats'))
            
            total_revenue = Decimal('0')
            total_reserved = 0
            total_seats = 0
            prices = []
            
            for record in records:
                try:
                    reserved_val = int(record['reserved']) if record['reserved'] is not None else 0
                    if reserved_val < 0:
                        reserved_val = 0
                except (ValueError, TypeError):
                    reserved_val = 0
                
                price_val = Decimal(str(record['price'])) if record['price'] else Decimal('0')
                
                total_revenue += price_val * Decimal(str(reserved_val))
                total_reserved += reserved_val
                total_seats += record.get('actual_total_seats', 0) or 0
                prices.append(price_val)
            
            avg_price = sum(prices) / len(prices) if prices else Decimal('0')
            
            results = {
                'total_revenue': total_revenue,
                'total_reserved': total_reserved,
                'total_seats': total_seats,
                'avg_price': avg_price
            }
        
        total_revenue = results['total_revenue'] or Decimal('0')
        total_reserved = results['total_reserved'] or 0
        total_seats = results['total_seats'] or 0
        avg_price = results['avg_price'] or Decimal('0')
        
        occupancy_rate = None
        if total_seats > 0:
            occupancy_rate = (float(total_reserved) / float(total_seats)) * 100
        
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
            end_dir: Ending DIR (default: 3 for first weekend end)
            use_cache: Whether to use cached data
            
        Returns:
            List of daily performance dictionaries
        """
        if start_dir is None:
            start_dir = -1
        if end_dir is None:
            end_dir = 3
        
        if use_cache:
            performances = (
                MovieDailyPerformance.objects
                .filter(
                    title__iexact=title,
                    dir_value__gte=start_dir,
                    dir_value__lte=end_dir
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
                            SUM(
                                CASE 
                                    WHEN reserved IS NULL OR reserved < 0 THEN 0
                                    ELSE reserved
                                END
                            ) as total_reserved,
                            SUM(
                                COALESCE(actual_total_seats, 0)
                            ) as total_seats,
                            SUM(
                                CASE 
                                    WHEN reserved IS NULL OR reserved < 0 THEN 0
                                    WHEN price IS NULL OR price <= 0 THEN 0
                                    ELSE (price * reserved)
                                END
                            ) as total_revenue,
                            AVG(
                                CASE 
                                    WHEN price IS NULL OR price <= 0 THEN NULL
                                    ELSE price
                                END
                            ) as avg_price
                        FROM movies
                        WHERE UPPER(title) = UPPER(%s)
                        AND release_date = %s
                        AND date_sh = %s
                        AND price IS NOT NULL 
                        AND price > 0
                    """, [title, release_date, date_sh_val])
                    
                    row = cursor.fetchone()
                    if row:
                        daily_data = {
                            'total_reserved': int(row[0] or 0),
                            'total_seats': int(row[1] or 0),
                            'total_revenue': Decimal(str(row[2] or 0)),
                            'avg_price': Decimal(str(row[3] or 0))
                        }
                    else:
                        daily_data = {
                            'total_reserved': 0,
                            'total_seats': 0,
                            'total_revenue': Decimal('0'),
                            'avg_price': Decimal('0')
                        }
            except Exception as e:
                logger.warning(f"Day-by-day calculation failed: {e}")
                daily_data = {
                    'total_reserved': 0,
                    'total_seats': 0,
                    'total_revenue': Decimal('0'),
                    'avg_price': Decimal('0')
                }
            
            total_revenue = daily_data['total_revenue'] or Decimal('0')
            total_reserved = daily_data['total_reserved'] or 0
            total_seats = daily_data['total_seats'] or 0
            avg_price = daily_data['avg_price'] or Decimal('0')
            
            occupancy_rate = None
            if total_seats > 0:
                occupancy_rate = (float(total_reserved) / float(total_seats)) * 100
            
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
        Get all movies currently in their first weekend (DIR -1 to DIR 3).
        Uses efficient query on cached table.
        
        Returns:
            List of movies with first weekend data including additional metrics
        """
        from django.db.models import Sum, Avg, Max
        
        performances = (
            MovieDailyPerformance.objects
            .filter(dir_value__gte=-1, dir_value__lte=3)
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
        Uses raw Movie table for accurate DBR calculation since DBR varies by last_updates.
        
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
        # DBR is calculated from last_updates, which varies per record
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
                        COALESCE(SUM(
                            CASE 
                                WHEN price IS NULL OR price <= 0 OR price::text ~ '^[^0-9]' THEN 0
                                WHEN reserved IS NULL OR reserved < 0 THEN 0
                                ELSE (CAST(REPLACE(price::text, '$', '') AS DECIMAL(10,2)) * reserved)
                            END
                        ), 0) as total_revenue
                    FROM movies
                    WHERE UPPER(title) = UPPER(%s)
                    AND (
                        CASE 
                            WHEN (last_updates::date - release_date) < 0 
                            THEN (last_updates::date - release_date)
                            WHEN (last_updates::date - release_date) >= 0 
                            THEN (last_updates::date - release_date) + 1
                        END
                    ) < 0
                """, [title])
            else:
                # For specific DBR threshold, use filters for data quality
                cursor.execute(f"""
                    SELECT 
                        SUM(
                            CASE 
                                WHEN reserved IS NULL OR reserved < 0 THEN 0
                                ELSE reserved
                            END
                        ) as total_reserved,
                        SUM(
                            CASE 
                                WHEN reserved IS NULL OR reserved < 0 THEN 0
                                WHEN price IS NULL OR price <= 0 THEN 0
                                ELSE (price * reserved)
                            END
                        ) as total_revenue
                    FROM movies
                    WHERE UPPER(title) = UPPER(%s)
                    AND price IS NOT NULL 
                    AND price > 0
                    AND reserved IS NOT NULL
                    AND reserved >= 0
                    AND (
                        CASE 
                            WHEN (last_updates::date - release_date) < 0 
                            THEN (last_updates::date - release_date)
                            WHEN (last_updates::date - release_date) >= 0 
                            THEN (last_updates::date - release_date) + 1
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
        Uses SQL logic: DATEDIFF(date_sh, release_date) <= 2
        Which translates to: date_sh - release_date between -1 and 2 (DIR -1, 1, 2, 3)
        """
        from django.db import connection
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    title,
                    MIN(release_date) AS release_date,
                    ROUND(SUM(
                        CASE 
                            WHEN reserved IS NULL OR reserved < 0 THEN 0
                            WHEN price IS NULL OR price <= 0 THEN 0
                            ELSE (price * reserved)
                        END
                    ), 2) AS first_weekend_revenue
                FROM movies
                WHERE (date_sh - release_date) BETWEEN -1 AND 2
                AND price IS NOT NULL 
                AND price > 0
                AND reserved IS NOT NULL
                AND reserved >= 0
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
        """Compare performance between two DIR ranges for a movie."""
        from django.db.models import Sum
        
        release_date = (
            MovieDailyPerformance.objects
            .filter(title__iexact=movie_title)
            .values_list('release_date', flat=True)
            .distinct()
            .first()
        )
        
        if not release_date:
            return {'error': 'Movie not found'}
        
        range1_data = (
            MovieDailyPerformance.objects
            .filter(
                title__iexact=movie_title,
                release_date=release_date,
                dir_value__gte=dir_range1[0],
                dir_value__lte=dir_range1[1]
            )
            .aggregate(
                revenue=Sum('total_revenue'),
                reserved=Sum('total_reserved_seats')
            )
        )
        
        range2_data = (
            MovieDailyPerformance.objects
            .filter(
                title__iexact=movie_title,
                release_date=release_date,
                dir_value__gte=dir_range2[0],
                dir_value__lte=dir_range2[1]
            )
            .aggregate(
                revenue=Sum('total_revenue'),
                reserved=Sum('total_reserved_seats')
            )
        )
        
        rev1 = range1_data['revenue'] or Decimal('0')
        rev2 = range2_data['revenue'] or Decimal('0')
        res1 = range1_data['reserved'] or 0
        res2 = range2_data['reserved'] or 0
        
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
                    SUM(
                        CASE 
                            WHEN reserved IS NULL OR reserved < 0 THEN 0
                            ELSE reserved
                        END
                    ) AS total_advance_bookings,
                    SUM(
                        CASE 
                            WHEN reserved IS NULL OR reserved < 0 THEN 0
                            WHEN price IS NULL OR price <= 0 THEN 0
                            ELSE (price * reserved)
                        END
                    ) AS total_advance_revenue
                FROM movies
                WHERE price IS NOT NULL 
                AND price > 0
                AND reserved IS NOT NULL
                AND reserved >= 0
                AND (
                    CASE 
                        WHEN (last_updates::date - release_date) < 0 
                        THEN (last_updates::date - release_date)
                        WHEN (last_updates::date - release_date) >= 0 
                        THEN (last_updates::date - release_date) + 1
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
        Uses raw SQL for accurate DBR calculation from last_updates.
        """
        from django.db import connection
        from datetime import datetime
        
        # Query directly from Movie table grouped by DBR
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    CASE 
                        WHEN (last_updates::date - release_date) < 0 
                        THEN (last_updates::date - release_date)
                        WHEN (last_updates::date - release_date) >= 0 
                        THEN (last_updates::date - release_date) + 1
                    END AS DBR,
                    SUM(
                        CASE 
                            WHEN reserved IS NULL OR reserved < 0 THEN 0
                            ELSE reserved
                        END
                    ) as daily_reserved,
                    SUM(
                        CASE 
                            WHEN reserved IS NULL OR reserved < 0 THEN 0
                            WHEN price IS NULL OR price <= 0 THEN 0
                            ELSE (price * reserved)
                        END
                    ) as daily_revenue
                FROM movies
                WHERE UPPER(title) = UPPER(%s)
                AND price IS NOT NULL 
                AND price > 0
                AND reserved IS NOT NULL
                AND reserved >= 0
                AND (date_sh - release_date) <= 2
                AND (
                    CASE 
                        WHEN (last_updates::date - release_date) < 0 
                        THEN (last_updates::date - release_date)
                        WHEN (last_updates::date - release_date) >= 0 
                        THEN (last_updates::date - release_date) + 1
                    END
                ) BETWEEN %s AND %s
                GROUP BY DBR
                ORDER BY DBR
            """, [movie_title, dbr_start, dbr_end])
            
            daily_data_raw = cursor.fetchall()
            
            if not daily_data_raw:
                return {'error': f'No advance booking data found for "{movie_title}" in DBR range {dbr_start} to {dbr_end}'}
            
            cumulative_revenue = Decimal('0')
            cumulative_reserved = 0
            daily_list = []
            
            for row in daily_data_raw:
                dbr, daily_res, daily_rev = row
                daily_reserved_val = int(daily_res or 0)
                daily_revenue_val = Decimal(str(daily_rev or 0))
                
                cumulative_revenue += daily_revenue_val
                cumulative_reserved += daily_reserved_val
                
                daily_list.append({
                    'dbr_value': int(dbr),
                    'daily_revenue': daily_revenue_val,
                    'daily_reserved': daily_reserved_val,
                    'cumulative_revenue': cumulative_revenue,
                    'cumulative_reserved': cumulative_reserved
                })
        
        return {
            'title': movie_title,
            'dbr_range': (dbr_start, dbr_end),
            'daily_data': daily_list,
            'total_revenue': cumulative_revenue,
            'total_reserved': cumulative_reserved
        }
    
    def get_best_comp_titles(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get best performing movies (comp titles) sorted by first weekend revenue."""
        from django.db.models import Sum, Avg
        
        comp_titles = (
            MovieDailyPerformance.objects
            .filter(dir_value__gte=-1, dir_value__lte=3)
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

