from django.db import models

class Movie(models.Model):
    # Unique identifiers
    id = models.BigAutoField(primary_key=True)
    theater_id = models.CharField(max_length=100)
    mm_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Theater information
    circuit_name = models.CharField(max_length=255)
    theater_name = models.CharField(max_length=255)
    theater_address = models.CharField(max_length=255)
    theater_city = models.CharField(max_length=100)
    theater_state = models.CharField(max_length=50)
    theater_zip = models.CharField(max_length=20)
    country = models.CharField(max_length=50)
    dma = models.CharField(max_length=100, blank=True, null=True)  # DMA region
    
    # Movie details
    title = models.CharField(max_length=255)
    studio_name = models.CharField(max_length=255)
    release_date = models.DateField()
    runtime = models.IntegerField(null=True, blank=True)
    genre = models.CharField(max_length=100)
    rating = models.CharField(max_length=20)
    
    # Showtime information
    date_sh = models.DateField()  # Show date
    time_sh = models.TimeField()  # Show time
    auditorium = models.CharField(max_length=50)
    screen_format = models.CharField(max_length=50)
    movie_format = models.CharField(max_length=50)
    language_format = models.CharField(max_length=50)
    
    # Pricing
    price = models.DecimalField(max_digits=8, decimal_places=2)
    child = models.DecimalField(max_digits=8, decimal_places=2)
    senior = models.DecimalField(max_digits=8, decimal_places=2)
    
    # Seating status
    total_seats = models.IntegerField()
    available = models.IntegerField()
    reserved = models.IntegerField()
    checkered = models.IntegerField()  # Blocked for social distancing
    actual_total_seats = models.IntegerField()
    actual_available = models.IntegerField()
    actual_reserved = models.IntegerField()
    actual_checkered = models.IntegerField()
    before_reserved = models.IntegerField()
    on_reserved = models.IntegerField()
    after_reserved = models.IntegerField()
    seating_type = models.CharField(max_length=50)
    
    # Theater amenities
    amenities = models.TextField(blank=True)
    
    # Status flags
    ticket_availability = models.BooleanField(default=True)
    is_ticketing = models.BooleanField(default=True)
    source_flag = models.CharField(max_length=50, blank=True)
    
    # Timestamps and dates
    last_updates = models.DateTimeField()
    running_date = models.DateField()
    dsr_date_sh = models.DateTimeField(null=True, blank=True)
    dsr_last_updates = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'movies'
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['theater_id']),
            models.Index(fields=['date_sh']),
            models.Index(fields=['genre']),
            models.Index(fields=['theater_city', 'theater_state']),
        ]
        
    def __str__(self):
        return f"{self.title} at {self.theater_name} ({self.date_sh} {self.time_sh})"
        
    def get_occupancy_rate(self):
        """Calculate the current occupancy rate"""
        if self.total_seats > 0:
            return (self.reserved / self.total_seats) * 100
        return 0
        
    def get_actual_occupancy_rate(self):
        """Calculate the actual occupancy rate based on actual seats"""
        if self.actual_total_seats > 0:
            return (self.actual_reserved / self.actual_total_seats) * 100
        return 0




# Additional Django models for film analytics
from django.db import models
from django.db.models import JSONField
from movies.models import Movie
import uuid

class FilmPerformanceSummary(models.Model):
    """Aggregated film performance data for analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Film details
    title = models.CharField(max_length=255, db_index=True)
    genre = models.CharField(max_length=100, db_index=True)
    rating = models.CharField(max_length=20, db_index=True)
    studio_name = models.CharField(max_length=255, db_index=True)
    release_date = models.DateField(db_index=True)
    
    # Performance metrics
    total_reserved = models.IntegerField()
    total_seats = models.IntegerField()
    total_sales = models.DecimalField(max_digits=12, decimal_places=2)
    avg_price = models.DecimalField(max_digits=8, decimal_places=2)
    overall_occupancy = models.FloatField()
    
    # Market metrics
    theater_count = models.IntegerField()
    city_count = models.IntegerField()
    circuit_count = models.IntegerField()
    format_count = models.IntegerField()
    
    # Performance patterns
    dod_growth = models.FloatField(null=True, blank=True)  # Day-over-day growth
    weekend_ratio = models.FloatField(null=True, blank=True)
    peak_time = models.CharField(max_length=20, blank=True)
    best_format = models.CharField(max_length=100, blank=True)
    top_market = models.CharField(max_length=100, blank=True)
    
    # Year for filtering
    year = models.IntegerField(db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'film_performance_summary'
        indexes = [
            models.Index(fields=['title', 'year']),
            models.Index(fields=['genre', 'year']),
            models.Index(fields=['rating', 'year']),
            models.Index(fields=['studio_name', 'year']),
            models.Index(fields=['overall_occupancy']),
            models.Index(fields=['total_sales']),
        ]
        unique_together = ['title', 'year']
    
    def __str__(self):
        return f"{self.title} ({self.year}) - ${self.total_sales:,.2f}"

class TheaterPerformance(models.Model):
    """Theater-level performance analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Theater details
    theater_name = models.CharField(max_length=255, db_index=True)
    theater_city = models.CharField(max_length=100, db_index=True)
    theater_state = models.CharField(max_length=50, db_index=True)
    circuit_name = models.CharField(max_length=255, db_index=True)
    dma = models.CharField(max_length=100, blank=True, null=True)
    
    # Performance metrics
    total_capacity = models.IntegerField()
    total_reserved = models.IntegerField()
    total_sales = models.DecimalField(max_digits=12, decimal_places=2)
    avg_price = models.DecimalField(max_digits=8, decimal_places=2)
    overall_occupancy = models.FloatField()
    
    # Opportunity metrics
    movie_count = models.IntegerField()
    capacity_utilization = models.FloatField()
    price_optimization = models.FloatField()
    market_position = models.CharField(max_length=50)  # High, Medium, Low
    
    # Amenities
    amenities = models.TextField(blank=True)
    
    # Year for filtering
    year = models.IntegerField(db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'theater_performance'
        indexes = [
            models.Index(fields=['theater_name', 'year']),
            models.Index(fields=['theater_city', 'year']),
            models.Index(fields=['circuit_name', 'year']),
            models.Index(fields=['overall_occupancy']),
            models.Index(fields=['capacity_utilization']),
        ]
        unique_together = ['theater_name', 'theater_city', 'year']
    
    def __str__(self):
        return f"{self.theater_name} ({self.theater_city}) - {self.overall_occupancy:.1f}%"

class MarketAnalysis(models.Model):
    """Market-level performance analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Market details
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=50, db_index=True)
    dma = models.CharField(max_length=100, blank=True, null=True)
    date = models.DateField(db_index=True)
    
    # Market metrics
    total_market_capacity = models.IntegerField()
    total_market_reserved = models.IntegerField()
    total_market_sales = models.DecimalField(max_digits=12, decimal_places=2)
    market_occupancy = models.FloatField()
    
    # Market diversity
    theater_count = models.IntegerField()
    circuit_diversity = models.IntegerField()
    format_diversity = models.IntegerField()
    price_range_min = models.DecimalField(max_digits=8, decimal_places=2)
    price_range_max = models.DecimalField(max_digits=8, decimal_places=2)
    capacity_utilization = models.FloatField()
    
    # Year for filtering
    year = models.IntegerField(db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'market_analysis'
        indexes = [
            models.Index(fields=['city', 'year']),
            models.Index(fields=['state', 'year']),
            models.Index(fields=['date']),
            models.Index(fields=['market_occupancy']),
            models.Index(fields=['capacity_utilization']),
        ]
        unique_together = ['city', 'date']
    
    def __str__(self):
        return f"{self.city}, {self.state} ({self.date}) - {self.market_occupancy:.1f}%"

class ComparativeAnalysis(models.Model):
    """Comparative analysis for film performance matching"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Film details
    title = models.CharField(max_length=255, db_index=True)
    genre = models.CharField(max_length=100, db_index=True)
    rating = models.CharField(max_length=20, db_index=True)
    studio_name = models.CharField(max_length=255, db_index=True)
    release_date = models.DateField(db_index=True)
    
    # Performance metrics
    total_reserved = models.IntegerField()
    total_seats = models.IntegerField()
    total_sales = models.DecimalField(max_digits=12, decimal_places=2)
    avg_price = models.DecimalField(max_digits=8, decimal_places=2)
    overall_occupancy = models.FloatField()
    
    # Comparative metrics
    dod_growth = models.FloatField(null=True, blank=True)
    market_penetration = models.FloatField()
    geographic_spread = models.IntegerField()
    circuit_diversity = models.IntegerField()
    format_diversity = models.IntegerField()
    
    # Performance patterns
    peak_time = models.CharField(max_length=20, blank=True)
    best_format = models.CharField(max_length=100, blank=True)
    top_market = models.CharField(max_length=100, blank=True)
    weekend_ratio = models.FloatField(null=True, blank=True)
    
    # Performance profile (JSON field for complex data)
    performance_profile = JSONField(default=dict, blank=True)
    
    # Year for filtering
    year = models.IntegerField(db_index=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'comparative_analysis'
        indexes = [
            models.Index(fields=['title', 'year']),
            models.Index(fields=['genre', 'year']),
            models.Index(fields=['rating', 'year']),
            models.Index(fields=['studio_name', 'year']),
            models.Index(fields=['overall_occupancy']),
            models.Index(fields=['total_sales']),
            models.Index(fields=['market_penetration']),
        ]
        unique_together = ['title', 'year']
    
    def __str__(self):
        return f"{self.title} ({self.year}) - Comparative Analysis"

class EmbeddingChunk(models.Model):
    """Store embedding chunk metadata"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Chunk details
    chunk_type = models.CharField(max_length=50, db_index=True)  # film_performance, comparative_analysis, etc.
    chunk_text = models.TextField()
    vector_id = models.CharField(max_length=255, unique=True, db_index=True)
    
    # Metadata (JSON field for flexible data)
    metadata = JSONField(default=dict)
    
    # Related models (optional foreign keys)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, null=True, blank=True)
    film_summary = models.ForeignKey(FilmPerformanceSummary, on_delete=models.CASCADE, null=True, blank=True)
    theater_performance = models.ForeignKey(TheaterPerformance, on_delete=models.CASCADE, null=True, blank=True)
    market_analysis = models.ForeignKey(MarketAnalysis, on_delete=models.CASCADE, null=True, blank=True)
    comparative_analysis = models.ForeignKey(ComparativeAnalysis, on_delete=models.CASCADE, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'embedding_chunks'
        indexes = [
            models.Index(fields=['chunk_type']),
            models.Index(fields=['vector_id']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.chunk_type} - {self.vector_id}"

class QueryLog(models.Model):
    """Log queries for analytics and improvement"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Query details
    query_text = models.TextField()
    query_type = models.CharField(max_length=50, db_index=True)  # comparative, opportunity, market, etc.
    
    # Response details
    response_text = models.TextField()
    response_time = models.FloatField()  # in seconds
    vector_count = models.IntegerField()  # number of vectors retrieved
    
    # User details
    user = models.ForeignKey('accounts.CustomUser', on_delete=models.SET_NULL, null=True, blank=True)
    conversation = models.ForeignKey('chat.Conversation', on_delete=models.SET_NULL, null=True, blank=True)
    
    # Performance metrics
    relevance_score = models.FloatField(null=True, blank=True)
    user_rating = models.IntegerField(null=True, blank=True)  # 1-5 rating
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'query_logs'
        indexes = [
            models.Index(fields=['query_type']),
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
            models.Index(fields=['response_time']),
        ]
    
    def __str__(self):
        return f"Query: {self.query_text[:50]}... - {self.query_type}"


class MovieDailyPerformance(models.Model):
    """
    Pre-calculated daily performance metrics for movies based on DIR (Days In Release).
    This model stores aggregated daily data for fast querying of performance analytics.
    
    DIR Calculation (as per SQL logic):
    - If DATEDIFF(date_sh, release_date) < 0: DIR = DATEDIFF(date_sh, release_date)
    - If DATEDIFF(date_sh, release_date) >= 0: DIR = DATEDIFF(date_sh, release_date) + 1
    
    This enables fast queries for:
    - First weekend performance (DIR -1 to DIR 3)
    - Day-over-Day growth analysis
    - Weekly comparisons
    - Advance booking analysis (DBR - Days Before Release)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Movie details
    title = models.CharField(max_length=255, db_index=True)
    release_date = models.DateField(db_index=True)
    
    # Time metrics
    date_sh = models.DateField(db_index=True)  # Show date
    dir_value = models.IntegerField(db_index=True)  # Days In Release (calculated)
    dbr_value = models.IntegerField(null=True, blank=True, db_index=True)  # Days Before Release (if applicable)
    
    # Daily aggregated metrics
    total_reserved_seats = models.IntegerField(default=0)
    total_impressions = models.IntegerField(default=0)  # Same as reserved_seats
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)  # Sales estimate = price * reserved
    total_seats = models.IntegerField(default=0)
    
    # Day-over-Day metrics (calculated)
    dod_revenue_change = models.FloatField(null=True, blank=True)  # Percentage change vs previous day
    dod_reserved_change = models.FloatField(null=True, blank=True)  # Percentage change in reservations
    
    # Revenue breakdown (if needed)
    cumulative_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    cumulative_reserved = models.IntegerField(default=0)
    
    # Additional metrics
    avg_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    occupancy_rate = models.FloatField(null=True, blank=True)
    
    # Timestamps
    calculated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'movie_daily_performance'
        indexes = [
            models.Index(fields=['title', 'release_date']),
            models.Index(fields=['title', 'dir_value']),
            models.Index(fields=['title', 'dbr_value']),
            models.Index(fields=['dir_value']),
            models.Index(fields=['date_sh']),
            models.Index(fields=['total_revenue']),
        ]
        unique_together = [['title', 'release_date', 'date_sh']]  # One record per movie per day
    
    def __str__(self):
        return f"{self.title} (DIR {self.dir_value}) - ${self.total_revenue:,.2f}"


class MoviePerformanceComparison(models.Model):
    """
    Pre-calculated comparison data for multiple movies over time periods.
    Used for queries like "Compare first weekend of Movie A vs Movie B"
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Comparison details
    title1 = models.CharField(max_length=255, db_index=True)
    title2 = models.CharField(max_length=255, db_index=True)
    release_date1 = models.DateField()
    release_date2 = models.DateField()
    
    # Time period
    dir_range_start = models.IntegerField()
    dir_range_end = models.IntegerField()
    period_label = models.CharField(max_length=100)  # e.g., "first_weekend", "first_week", "first_5_days"
    
    # Comparison metrics
    title1_total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    title2_total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    title1_total_reserved = models.IntegerField(default=0)
    title2_total_reserved = models.IntegerField(default=0)
    
    revenue_difference = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    revenue_difference_percent = models.FloatField(null=True, blank=True)
    
    # Timestamps
    calculated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'movie_performance_comparison'
        indexes = [
            models.Index(fields=['title1', 'title2']),
            models.Index(fields=['period_label']),
        ]
    
    def __str__(self):
        return f"{self.title1} vs {self.title2} ({self.period_label})"
