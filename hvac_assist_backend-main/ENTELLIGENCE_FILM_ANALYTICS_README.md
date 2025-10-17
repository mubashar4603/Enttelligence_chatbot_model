# Entelligence Film Analytics Chatbot System

A sophisticated Django-based film performance analytics system that can answer complex comparative queries like "What films are performing like JURASSIC WORLD REBIRTH?" using advanced embedding techniques and Pinecone vector database.

## 🎯 Key Features

- **Comparative Analysis**: Find films with similar performance patterns
- **Theater Opportunities**: Identify underperforming theaters and growth opportunities
- **Market Analysis**: Analyze geographic performance and market penetration
- **Performance Tracking**: Monitor film performance metrics and trends
- **Complex Query Handling**: Answer sophisticated analytical questions

## 🏗️ System Architecture

### Core Components

1. **Django Models** (`movies/models.py`, `chat/analytics_models.py`)
   - `Movie`: Core film performance data
   - `FilmPerformanceSummary`: Aggregated performance metrics
   - `TheaterPerformance`: Theater-level analytics
   - `MarketAnalysis`: Market penetration data
   - `ComparativeAnalysis`: Comparative performance profiles
   - `EmbeddingChunk`: Vector metadata storage

2. **Embedding Pipeline** (`chat/entelligence_film_analytics_pipeline.py`)
   - Processes `Entelligence_7.4M_dataset.csv`
   - Creates multi-layered embeddings for different query types
   - Uploads to Pinecone with 768 dimensions
   - Stores metadata in Django database

3. **Query Handler** (`chat/film_analytics_query_handler.py`)
   - Processes complex comparative queries
   - Routes queries to appropriate handlers
   - Returns comprehensive analytical responses

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Activate virtual environment
source env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Pinecone

Update your Pinecone credentials in the pipeline:
```python
'PINECONE_API_KEY': "your_api_key_here",
'INDEX_NAME': "customer-database-vectors",
'DIMENSION': 768,
```

### 3. Run Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Run the Embedding Pipeline

```bash
# Run the complete pipeline
python manage.py run_entelligence_pipeline

# Or with custom chunk size
python manage.py run_entelligence_pipeline --chunk-size 50000
```

### 5. Test Queries

```python
from chat.film_analytics_query_handler import FilmAnalyticsQueryHandler

handler = FilmAnalyticsQueryHandler()
result = handler.process_query("What films are performing like JURASSIC WORLD REBIRTH?")
print(result['response'])
```

## 📊 Data Processing

### Dataset: `Entelligence_7.4M_dataset.csv`

The system processes your 7.4M record dataset with the following columns:
- `title`, `genre`, `rating`, `studio_name`
- `theater_name`, `theater_city`, `theater_state`, `circuit_name`
- `date_sh`, `time_sh`, `auditorium`, `screen_format`
- `price`, `reserved`, `total_seats`, `occupancy_rate`
- `amenities`, `dma`, `runtime`, `country`

### Embedding Types Created

1. **Film Performance Chunks**
   - Individual film performance analysis
   - Sales estimates, occupancy rates, growth metrics
   - Technical details and market context

2. **Comparative Analysis Chunks**
   - Grouped by movie title
   - Performance patterns and market penetration
   - Release strategy and format mix analysis

3. **Theater Opportunity Chunks**
   - Grouped by theater
   - Capacity utilization and optimization potential
   - Market position and recommendations

4. **Market Penetration Chunks**
   - Grouped by city and date
   - Market performance and diversity analysis
   - Opportunity identification

## 🔍 Query Types Supported

### 1. Comparative Analysis
```
"What films are performing like JURASSIC WORLD REBIRTH?"
"Which movies have similar performance to WEAPONS?"
"Find films comparable to DUNE: Part Two"
```

### 2. Theater Opportunities
```
"Where are my opportunities?"
"Show me underperforming theaters"
"What theaters should I focus on?"
```

### 3. Market Analysis
```
"How is WEAPONS performing in less populated areas?"
"Show me market penetration data"
"Which cities have growth potential?"
```

### 4. Performance Queries
```
"How is JURASSIC WORLD REBIRTH performing?"
"Show me occupancy rates for TWISTERS"
"What are the sales estimates for JOKER?"
```

## 🛠️ Configuration

### Pinecone Settings
```python
PINECONE_API_KEY = "pcsk_3DmuwS_5NT3SrpWJW9cweaEduTnvociJPwvVQFBYaJsbdc88joQoKk3JvSmRVJ6jSeiUfZ"
PINECONE_ENVIRONMENT = "us-east-1-aws"
INDEX_NAME = "customer-database-vectors"
DIMENSION = 768
```

### Embedding Model
```python
EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"  # 768 dimensions
BATCH_SIZE = 256
CHUNK_SIZE = 25000
```

## 📈 Performance Metrics

### Sales Estimation
```python
sales_estimate = avg_price * reserved_seats
```

### Occupancy Rate
```python
occupancy_rate = (reserved_seats / total_seats) * 100
```

### Market Penetration
```python
market_penetration = (cities_reached / total_cities) * 100
```

## 🔧 Advanced Usage

### Custom Query Processing

```python
from chat.film_analytics_query_handler import FilmAnalyticsQueryHandler

handler = FilmAnalyticsQueryHandler()

# Process different query types
result = handler.process_query("What films are performing like JURASSIC WORLD REBIRTH?")
print(f"Query Type: {result['query_type']}")
print(f"Response: {result['response']}")
print(f"Similar Films: {result.get('similar_films', [])}")
```

### Direct Pinecone Search

```python
from chat.entelligence_film_analytics_pipeline import EntelligenceFilmAnalyticsPipeline

pipeline = EntelligenceFilmAnalyticsPipeline()
pipeline.initialize_components()

# Search for specific patterns
matches = pipeline.index.query(
    vector=query_embedding,
    top_k=10,
    include_metadata=True
)
```

## 📝 Example Responses

### Comparative Analysis Response
```
Based on performance analysis, here are films performing similarly to JURASSIC WORLD REBIRTH:

1. **DUNE: Part Two** (Sci-Fi, PG-13)
   - Studio: Warner Bros.
   - Occupancy Rate: 78.5%
   - Total Sales: $2,213,691.00
   - Market Penetration: 85.2%
   - Day-over-Day Growth: 12.3%
   - Peak Time: 19:30
   - Best Format: IMAX
   - Top Market: Los Angeles

2. **TWISTERS** (Action, PG-13)
   - Studio: Universal
   - Occupancy Rate: 82.1%
   - Total Sales: $2,738,201.00
   - Market Penetration: 78.9%
   - Day-over-Day Growth: 8.7%
   - Peak Time: 20:00
   - Best Format: Dolby Cinema
   - Top Market: New York

Why these films are similar:
- Similar genre and rating profiles
- Comparable occupancy rates and sales performance
- Similar market penetration patterns
- Comparable day-over-day growth trends
- Similar peak performance times and format preferences
```

### Theater Opportunity Response
```
Here are the top theater opportunities I've identified:

1. **Marcus Theaters** - Milwaukee, WI
   - Circuit: Marcus Corporation
   - Current Occupancy: 45.2%
   - Capacity Utilization: 38.7%
   - Price Optimization Potential: 67.3%
   - Market Position: Medium

2. **AMC Theaters** - Chicago, IL
   - Circuit: AMC Entertainment
   - Current Occupancy: 52.1%
   - Capacity Utilization: 41.2%
   - Price Optimization Potential: 58.9%
   - Market Position: High

Recommendations:
- Focus on theaters with low capacity utilization
- Implement dynamic pricing strategies
- Consider format expansion opportunities
- Target underperforming time slots
```

## 🚨 Troubleshooting

### Common Issues

1. **Pinecone Connection Error**
   ```bash
   # Check API key and environment
   python -c "from pinecone import Pinecone; pc = Pinecone(api_key='your_key'); print(pc.list_indexes())"
   ```

2. **Memory Issues**
   ```bash
   # Reduce chunk size
   python manage.py run_entelligence_pipeline --chunk-size 10000
   ```

3. **Django Database Errors**
   ```bash
   # Run migrations
   python manage.py makemigrations
   python manage.py migrate
   ```

### Checkpoint Recovery

The pipeline automatically saves checkpoints every 10 chunks. To resume:
```bash
# Check checkpoint status
cat checkpoints/entelligence_film_analytics_checkpoint.json

# Pipeline will automatically resume from last checkpoint
python manage.py run_entelligence_pipeline
```

## 📊 Monitoring

### Query Logging
All queries are automatically logged in the `QueryLog` model:
- Query text and type
- Response time and quality
- Vector count retrieved
- User and conversation context

### Performance Metrics
- Total vectors created
- Processing time per chunk
- Memory usage
- Pinecone index statistics

## 🔮 Future Enhancements

1. **Real-time Updates**: Live data streaming
2. **Advanced Analytics**: Machine learning predictions
3. **Visualization**: Interactive dashboards
4. **API Integration**: RESTful endpoints
5. **Multi-language Support**: International markets

## 📞 Support

For issues or questions:
1. Check the troubleshooting section
2. Review the logs in `checkpoints/`
3. Verify Pinecone index status
4. Check Django database connectivity

---

**Built with ❤️ for Entelligence Film Analytics**
