#!/usr/bin/env python3
"""
PostgreSQL Models for Film Performance Analytics
Creates database tables and views for statistical queries
"""

import psycopg2
from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class FilmAnalyticsDatabase:
    def __init__(self, db_config):
        """Initialize database connection"""
        self.db_config = db_config
        self.engine = create_engine(
            f"postgresql://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        )
        self.metadata = MetaData()
        
    def create_tables(self):
        """Create all necessary tables"""
        logger.info("🗄️ Creating PostgreSQL tables for film analytics...")
        
        # Main film performance data table
        film_performance_data = Table(
            'film_performance_data',
            self.metadata,
            Column('id', Integer, primary_key=True),
            Column('title', String(255), nullable=False),
            Column('genre', String(100)),
            Column('rating', String(20)),
            Column('studio_name', String(255)),
            Column('theater_name', String(255)),
            Column('theater_city', String(100)),
            Column('theater_state', String(50)),
            Column('circuit_name', String(255)),
            Column('dma', String(100)),
            Column('date_sh', DateTime),
            Column('time_sh', String(20)),
            Column('auditorium', String(50)),
            Column('price_clean', Float),
            Column('reserved', Integer),
            Column('available', Integer),
            Column('total_seats', Integer),
            Column('sales_estimate', Float),
            Column('occupancy_rate', Float),
            Column('screen_format', String(100)),
            Column('movie_format', String(50)),
            Column('language_format', String(50)),
            Column('country', String(50)),
            Column('runtime', Integer),
            Column('release_date', DateTime),
            Column('running_date', DateTime),
            Column('amenities', Text),
            Column('year', Integer),
            Column('created_at', DateTime, default=datetime.now)
        )
        
        # Film summary table
        film_summary = Table(
            'film_summary',
            self.metadata,
            Column('id', Integer, primary_key=True),
            Column('title', String(255), nullable=False),
            Column('genre', String(100)),
            Column('rating', String(20)),
            Column('studio_name', String(255)),
            Column('release_date', DateTime),
            Column('total_reserved', Integer),
            Column('total_seats', Integer),
            Column('total_sales', Float),
            Column('avg_price', Float),
            Column('overall_occupancy', Float),
            Column('theater_count', Integer),
            Column('city_count', Integer),
            Column('circuit_count', Integer),
            Column('format_count', Integer),
            Column('dod_growth', Float),
            Column('weekend_ratio', Float),
            Column('peak_time', String(20)),
            Column('best_format', String(100)),
            Column('top_market', String(100)),
            Column('year', Integer),
            Column('created_at', DateTime, default=datetime.now)
        )
        
        # Theater performance table
        theater_performance = Table(
            'theater_performance',
            self.metadata,
            Column('id', Integer, primary_key=True),
            Column('theater_name', String(255), nullable=False),
            Column('theater_city', String(100)),
            Column('theater_state', String(50)),
            Column('circuit_name', String(255)),
            Column('dma', String(100)),
            Column('total_capacity', Integer),
            Column('total_reserved', Integer),
            Column('total_sales', Float),
            Column('avg_price', Float),
            Column('overall_occupancy', Float),
            Column('movie_count', Integer),
            Column('capacity_utilization', Float),
            Column('price_optimization', Float),
            Column('market_position', String(50)),
            Column('amenities', Text),
            Column('year', Integer),
            Column('created_at', DateTime, default=datetime.now)
        )
        
        # Market analysis table
        market_analysis = Table(
            'market_analysis',
            self.metadata,
            Column('id', Integer, primary_key=True),
            Column('city', String(100), nullable=False),
            Column('state', String(50)),
            Column('dma', String(100)),
            Column('date', DateTime),
            Column('total_market_capacity', Integer),
            Column('total_market_reserved', Integer),
            Column('total_market_sales', Float),
            Column('market_occupancy', Float),
            Column('theater_count', Integer),
            Column('circuit_diversity', Integer),
            Column('format_diversity', Integer),
            Column('price_range_min', Float),
            Column('price_range_max', Float),
            Column('capacity_utilization', Float),
            Column('year', Integer),
            Column('created_at', DateTime, default=datetime.now)
        )
        
        # Comparative analysis table
        comparative_analysis = Table(
            'comparative_analysis',
            self.metadata,
            Column('id', Integer, primary_key=True),
            Column('title', String(255), nullable=False),
            Column('genre', String(100)),
            Column('rating', String(20)),
            Column('studio_name', String(255)),
            Column('release_date', DateTime),
            Column('total_reserved', Integer),
            Column('total_seats', Integer),
            Column('total_sales', Float),
            Column('avg_price', Float),
            Column('overall_occupancy', Float),
            Column('dod_growth', Float),
            Column('market_penetration', Float),
            Column('geographic_spread', Integer),
            Column('circuit_diversity', Integer),
            Column('format_diversity', Integer),
            Column('peak_time', String(20)),
            Column('best_format', String(100)),
            Column('top_market', String(100)),
            Column('weekend_ratio', Float),
            Column('performance_profile', JSONB),
            Column('year', Integer),
            Column('created_at', DateTime, default=datetime.now)
        )
        
        # Create all tables
        self.metadata.create_all(self.engine)
        logger.info("✅ All tables created successfully")
        
    def create_views(self):
        """Create useful views for analytics"""
        logger.info("📊 Creating analytical views...")
        
        views = {
            'top_performing_films': """
                CREATE OR REPLACE VIEW top_performing_films AS
                SELECT 
                    title,
                    genre,
                    rating,
                    studio_name,
                    total_sales,
                    overall_occupancy,
                    theater_count,
                    city_count,
                    RANK() OVER (ORDER BY total_sales DESC) as sales_rank,
                    RANK() OVER (ORDER BY overall_occupancy DESC) as occupancy_rank
                FROM film_summary
                ORDER BY total_sales DESC;
            """,
            
            'theater_opportunities': """
                CREATE OR REPLACE VIEW theater_opportunities AS
                SELECT 
                    theater_name,
                    theater_city,
                    theater_state,
                    circuit_name,
                    overall_occupancy,
                    capacity_utilization,
                    price_optimization,
                    market_position,
                    CASE 
                        WHEN overall_occupancy < 25 THEN 'High Opportunity'
                        WHEN overall_occupancy < 50 THEN 'Medium Opportunity'
                        ELSE 'Low Opportunity'
                    END as opportunity_level
                FROM theater_performance
                ORDER BY capacity_utilization ASC;
            """,
            
            'market_penetration_analysis': """
                CREATE OR REPLACE VIEW market_penetration_analysis AS
                SELECT 
                    city,
                    state,
                    dma,
                    market_occupancy,
                    theater_count,
                    circuit_diversity,
                    format_diversity,
                    capacity_utilization,
                    CASE 
                        WHEN market_occupancy < 20 THEN 'Underperforming'
                        WHEN market_occupancy < 40 THEN 'Moderate'
                        ELSE 'High Performing'
                    END as market_status
                FROM market_analysis
                ORDER BY market_occupancy DESC;
            """,
            
            'comparative_film_analysis': """
                CREATE OR REPLACE VIEW comparative_film_analysis AS
                SELECT 
                    title,
                    genre,
                    rating,
                    studio_name,
                    total_sales,
                    overall_occupancy,
                    dod_growth,
                    market_penetration,
                    geographic_spread,
                    circuit_diversity,
                    format_diversity,
                    peak_time,
                    best_format,
                    top_market,
                    weekend_ratio,
                    RANK() OVER (PARTITION BY genre ORDER BY total_sales DESC) as genre_rank,
                    RANK() OVER (PARTITION BY rating ORDER BY overall_occupancy DESC) as rating_rank
                FROM comparative_analysis
                ORDER BY total_sales DESC;
            """,
            
            'format_performance_analysis': """
                CREATE OR REPLACE VIEW format_performance_analysis AS
                SELECT 
                    screen_format,
                    COUNT(*) as showtime_count,
                    SUM(reserved) as total_reserved,
                    SUM(total_seats) as total_capacity,
                    AVG(occupancy_rate) as avg_occupancy,
                    AVG(price_clean) as avg_price,
                    SUM(sales_estimate) as total_sales,
                    COUNT(DISTINCT theater_name) as theater_count,
                    COUNT(DISTINCT title) as movie_count
                FROM film_performance_data
                GROUP BY screen_format
                ORDER BY total_sales DESC;
            """,
            
            'circuit_performance_analysis': """
                CREATE OR REPLACE VIEW circuit_performance_analysis AS
                SELECT 
                    circuit_name,
                    COUNT(DISTINCT theater_name) as theater_count,
                    COUNT(DISTINCT theater_city) as city_count,
                    SUM(total_seats) as total_capacity,
                    SUM(reserved) as total_reserved,
                    AVG(occupancy_rate) as avg_occupancy,
                    AVG(price_clean) as avg_price,
                    SUM(sales_estimate) as total_sales,
                    COUNT(DISTINCT title) as movie_count
                FROM film_performance_data
                GROUP BY circuit_name
                ORDER BY total_sales DESC;
            """,
            
            'time_slot_analysis': """
                CREATE OR REPLACE VIEW time_slot_analysis AS
                SELECT 
                    time_sh,
                    COUNT(*) as showtime_count,
                    SUM(reserved) as total_reserved,
                    SUM(total_seats) as total_capacity,
                    AVG(occupancy_rate) as avg_occupancy,
                    AVG(price_clean) as avg_price,
                    SUM(sales_estimate) as total_sales,
                    CASE 
                        WHEN EXTRACT(HOUR FROM time_sh::time) BETWEEN 6 AND 11 THEN 'Morning'
                        WHEN EXTRACT(HOUR FROM time_sh::time) BETWEEN 12 AND 17 THEN 'Afternoon'
                        WHEN EXTRACT(HOUR FROM time_sh::time) BETWEEN 18 AND 23 THEN 'Evening'
                        ELSE 'Late Night'
                    END as time_period
                FROM film_performance_data
                GROUP BY time_sh
                ORDER BY avg_occupancy DESC;
            """,
            
            'daily_performance_trends': """
                CREATE OR REPLACE VIEW daily_performance_trends AS
                SELECT 
                    date_sh,
                    COUNT(*) as showtime_count,
                    SUM(reserved) as total_reserved,
                    SUM(total_seats) as total_capacity,
                    AVG(occupancy_rate) as avg_occupancy,
                    AVG(price_clean) as avg_price,
                    SUM(sales_estimate) as total_sales,
                    COUNT(DISTINCT theater_name) as theater_count,
                    COUNT(DISTINCT title) as movie_count,
                    EXTRACT(DOW FROM date_sh) as day_of_week,
                    CASE 
                        WHEN EXTRACT(DOW FROM date_sh) IN (0, 6) THEN 'Weekend'
                        ELSE 'Weekday'
                    END as day_type
                FROM film_performance_data
                GROUP BY date_sh
                ORDER BY date_sh;
            """
        }
        
        with self.engine.connect() as conn:
            for view_name, view_sql in views.items():
                try:
                    conn.execute(text(view_sql))
                    logger.info(f"✅ Created view: {view_name}")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to create view {view_name}: {e}")
        
        logger.info("✅ All views created successfully")
    
    def create_indexes(self):
        """Create database indexes for better performance"""
        logger.info("🔍 Creating database indexes...")
        
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_film_performance_title ON film_performance_data(title);",
            "CREATE INDEX IF NOT EXISTS idx_film_performance_date ON film_performance_data(date_sh);",
            "CREATE INDEX IF NOT EXISTS idx_film_performance_theater ON film_performance_data(theater_name);",
            "CREATE INDEX IF NOT EXISTS idx_film_performance_city ON film_performance_data(theater_city);",
            "CREATE INDEX IF NOT EXISTS idx_film_performance_circuit ON film_performance_data(circuit_name);",
            "CREATE INDEX IF NOT EXISTS idx_film_performance_format ON film_performance_data(screen_format);",
            "CREATE INDEX IF NOT EXISTS idx_film_performance_genre ON film_performance_data(genre);",
            "CREATE INDEX IF NOT EXISTS idx_film_performance_rating ON film_performance_data(rating);",
            "CREATE INDEX IF NOT EXISTS idx_film_performance_year ON film_performance_data(year);",
            "CREATE INDEX IF NOT EXISTS idx_film_performance_occupancy ON film_performance_data(occupancy_rate);",
            "CREATE INDEX IF NOT EXISTS idx_film_performance_sales ON film_performance_data(sales_estimate);",
            
            "CREATE INDEX IF NOT EXISTS idx_film_summary_title ON film_summary(title);",
            "CREATE INDEX IF NOT EXISTS idx_film_summary_genre ON film_summary(genre);",
            "CREATE INDEX IF NOT EXISTS idx_film_summary_rating ON film_summary(rating);",
            "CREATE INDEX IF NOT EXISTS idx_film_summary_studio ON film_summary(studio_name);",
            "CREATE INDEX IF NOT EXISTS idx_film_summary_year ON film_summary(year);",
            
            "CREATE INDEX IF NOT EXISTS idx_theater_performance_name ON theater_performance(theater_name);",
            "CREATE INDEX IF NOT EXISTS idx_theater_performance_city ON theater_performance(theater_city);",
            "CREATE INDEX IF NOT EXISTS idx_theater_performance_circuit ON theater_performance(circuit_name);",
            "CREATE INDEX IF NOT EXISTS idx_theater_performance_occupancy ON theater_performance(overall_occupancy);",
            
            "CREATE INDEX IF NOT EXISTS idx_market_analysis_city ON market_analysis(city);",
            "CREATE INDEX IF NOT EXISTS idx_market_analysis_state ON market_analysis(state);",
            "CREATE INDEX IF NOT EXISTS idx_market_analysis_date ON market_analysis(date);",
            "CREATE INDEX IF NOT EXISTS idx_market_analysis_dma ON market_analysis(dma);",
            
            "CREATE INDEX IF NOT EXISTS idx_comparative_title ON comparative_analysis(title);",
            "CREATE INDEX IF NOT EXISTS idx_comparative_genre ON comparative_analysis(genre);",
            "CREATE INDEX IF NOT EXISTS idx_comparative_rating ON comparative_analysis(rating);",
            "CREATE INDEX IF NOT EXISTS idx_comparative_studio ON comparative_analysis(studio_name);"
        ]
        
        with self.engine.connect() as conn:
            for index_sql in indexes:
                try:
                    conn.execute(text(index_sql))
                except Exception as e:
                    logger.warning(f"⚠️  Failed to create index: {e}")
        
        logger.info("✅ All indexes created successfully")
    
    def setup_database(self):
        """Complete database setup"""
        logger.info("🚀 Setting up PostgreSQL database for film analytics...")
        
        try:
            self.create_tables()
            self.create_views()
            self.create_indexes()
            
            logger.info("✅ Database setup completed successfully!")
            logger.info("📊 Available tables:")
            logger.info("   • film_performance_data - Raw showtime data")
            logger.info("   • film_summary - Aggregated film performance")
            logger.info("   • theater_performance - Theater-level metrics")
            logger.info("   • market_analysis - Market-level analysis")
            logger.info("   • comparative_analysis - Film comparison data")
            
            logger.info("📈 Available views:")
            logger.info("   • top_performing_films")
            logger.info("   • theater_opportunities")
            logger.info("   • market_penetration_analysis")
            logger.info("   • comparative_film_analysis")
            logger.info("   • format_performance_analysis")
            logger.info("   • circuit_performance_analysis")
            logger.info("   • time_slot_analysis")
            logger.info("   • daily_performance_trends")
            
        except Exception as e:
            logger.error(f"❌ Database setup failed: {e}")
            raise

def main():
    """Main function to setup database"""
    db_config = {
        'host': 'localhost',
        'database': 'enttelligence_db',
        'user': 'postgres',
        'password': 'postgres',
        'port': '5432'
    }
    
    db_setup = FilmAnalyticsDatabase(db_config)
    db_setup.setup_database()

if __name__ == "__main__":
    main()
