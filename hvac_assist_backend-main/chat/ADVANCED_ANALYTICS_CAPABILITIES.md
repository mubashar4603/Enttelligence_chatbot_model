# Advanced Analytics Capabilities

## Enhanced Intelligent Agent Features

The Entelligence AI Assistant now supports sophisticated film analytics queries similar to the examples provided. Here are the new capabilities:

### 1. **IMAX Performance Analysis**
- **Query Examples**: "Is WEAPONS over performing on IMAX screens?", "How is IMAX performance compared to regular screens?"
- **Capabilities**: 
  - Compares IMAX vs regular screen occupancy rates
  - Calculates IMAX overperformance percentages
  - Analyzes IMAX screen utilization and capacity
- **Response Format**: "WEAPONS is overperforming by 50% on IMAX screens with 32% of sales on IMAX screens."

### 2. **Geographic Performance Analysis**
- **Query Examples**: "How is WEAPONS performing in less populated areas?", "Geographic performance analysis"
- **Capabilities**:
  - Analyzes performance by city and region
  - Identifies high-performing vs low-performing markets
  - Calculates average occupancy across different geographic areas
- **Response Format**: "WEAPONS is underperforming by 18% in less populated areas compared to comp titles."

### 3. **Programming Analysis**
- **Query Examples**: "How is WEAPONS programmed compared to other films?", "Capacity comparison"
- **Capabilities**:
  - Compares showtime programming across films
  - Analyzes total capacity and showtime distribution
  - Identifies programming advantages/disadvantages
- **Response Format**: "FREAKIER FRIDAY has 19% more capacity than WEAPONS and is programmed on 13% more showtimes."

### 4. **Presales Analysis**
- **Query Examples**: "Presales analysis for WEAPONS", "Advance ticket sales trends"
- **Capabilities**:
  - Tracks presales trends over time
  - Analyzes day-over-day occupancy changes
  - Identifies increasing/decreasing presales patterns
- **Response Format**: "WEAPONS presales show an increasing trend with current occupancy at 65.2%. The trend represents a 12.3% increase over the tracked period."

### 5. **Daypart Analysis**
- **Query Examples**: "What showtimes perform best?", "Daypart performance analysis"
- **Capabilities**:
  - Analyzes performance by time periods (morning, afternoon, evening, late night)
  - Identifies best-performing dayparts
  - Provides occupancy and capacity data by time slot
- **Response Format**: "FANTASTIC FOUR performs best during evening with 78.5% occupancy across 45 showtimes with 12,500 total seats."

### 6. **Theater Tracking Analysis**
- **Query Examples**: "Where are my opportunities?", "Theater tracking report"
- **Capabilities**:
  - Identifies top-performing theaters and circuits
  - Generates theater recommendations for outreach
  - Analyzes circuit-level performance
- **Response Format**: "You should call Marcus Theaters. Key theaters (Theater A, B, and C) in Milwaukee have higher occupancy rates with less programmed seats during key evening dayparts."

### 7. **Daily Earnings Analysis**
- **Query Examples**: "What will every title earn by end of day?", "Today's earnings projection"
- **Capabilities**:
  - Calculates projected end-of-day revenue for films
  - Compares earnings across multiple films
  - Uses reserved seats and pricing data for projections
- **Response Format**: "WEAPONS is projected to earn $2,847,392.50 by end of day across 1,247 showtimes."

### 8. **Performance Comparison**
- **Query Examples**: "What films are performing like JURASSIC WORLD REBIRTH?", "Similar performance analysis"
- **Capabilities**:
  - Finds films with similar performance patterns
  - Compares occupancy rates and performance metrics
  - Identifies comparable films by genre and rating
- **Response Format**: "Movies performing similarly to JURASSIC WORLD REBIRTH (with 72.3% occupancy) include: DUNE: PART TWO, TWISTERS, and MONKEY MAN. These movies have similar occupancy rates and performance patterns."

### 9. **Second Weekend Drop Analysis**
- **Query Examples**: "How much will SUPERMAN drop in its second weekend?", "Second weekend projections"
- **Capabilities**:
  - Predicts performance drops for returning films
  - Uses historical data and comp title analysis
  - Provides percentage drop predictions
- **Response Format**: "SUPERMAN is estimated to drop 50% when comparing it to similarly performing features."

### 10. **Thursday Overperformance Analysis**
- **Query Examples**: "Is WEAPONS over performing on Thursday?", "Thursday performance comparison"
- **Capabilities**:
  - Compares Thursday performance to comp titles
  - Calculates overperformance percentages
  - Analyzes presales data for Thursday showings
- **Response Format**: "Yes, compared to the comp films, WEAPONS is over performing by about 20% on Thursday."

## Query Processing Enhancements

### Advanced Query Detection
The agent now recognizes sophisticated query patterns including:
- IMAX-specific terminology
- Geographic performance indicators
- Programming and capacity keywords
- Presales and advance sales terminology
- Daypart and time-based analysis
- Theater tracking and opportunity keywords
- Earnings and revenue projections
- Performance comparison language

### Data-Driven Responses
All responses are generated using:
- **Database Analytics**: FilmPerformanceSummary, TheaterPerformance, MarketAnalysis, ComparativeAnalysis tables
- **Real-time Calculations**: Occupancy rates, revenue projections, performance comparisons
- **Sophisticated Analysis**: Similarity scoring, trend analysis, geographic clustering
- **Actionable Insights**: Specific recommendations with data backing

### Response Format
Responses follow the professional format demonstrated in the examples:
- **Specific Metrics**: Exact percentages, dollar amounts, and counts
- **Data Sources**: Clear indication of which database tables were used
- **Actionable Recommendations**: Specific theaters, circuits, or strategies to pursue
- **Contextual Analysis**: Comparisons to comp titles and industry benchmarks

## Technical Implementation

### New Handler Methods
- `handle_imax_analysis_query()`: IMAX performance analysis
- `handle_geographic_analysis_query()`: Geographic performance analysis
- `handle_programming_analysis_query()`: Programming and capacity analysis
- `handle_presales_analysis_query()`: Presales trend analysis
- `handle_daypart_analysis_query()`: Time-based performance analysis
- `handle_tracking_analysis_query()`: Theater tracking and recommendations
- `handle_daily_earnings_query()`: Daily earnings projections
- `handle_performance_comparison_query()`: Performance comparison analysis

### Enhanced Query Intent Detection
- Added detection for advanced analytics keywords
- Improved movie title extraction
- Enhanced query type classification
- Better handling of complex, multi-part queries

### Data Processing Enhancements
- Sophisticated similarity scoring algorithms
- Geographic clustering and analysis
- Time-based trend analysis
- Revenue calculation with pricing data
- Performance comparison algorithms

## Usage Examples

The agent can now handle queries like:
- "What are the best comp titles for WEAPONS?"
- "Is WEAPONS over performing on IMAX screens?"
- "How is WEAPONS performing in less populated areas?"
- "Where are my opportunities?"
- "What showtimes do I want to keep?"
- "What is every title going to earn by end of day?"
- "What films are performing like JURASSIC WORLD REBIRTH?"

All responses are data-driven, specific, and actionable, providing the same level of sophistication as the examples provided.
