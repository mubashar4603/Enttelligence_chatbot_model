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
