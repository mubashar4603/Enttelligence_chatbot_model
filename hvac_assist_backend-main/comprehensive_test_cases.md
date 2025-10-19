# 🎬 Comprehensive Test Cases for Intelligent Film Analytics System

## System Overview
- **Database**: 7.4M+ movie records in PostgreSQL
- **Vector Database**: 1.85M vectors in Pinecone
- **LLM**: Llama3 8B via Ollama
- **API Endpoint**: `POST http://3.234.43.140:8000/api/messages/`
- **Agent**: Intelligent Film Analytics Agent with hybrid RAG + database approach

---

## 🧪 Test Case Categories

### 1. **Basic Database Queries** (Simple Facts)

#### Test Case 1.1: Total Reserved Seats
**Query**: `"What is the total reserved seats for Twisters?"`
**Expected Response**: 
- Should return exact number from database
- Format: "Twisters has X total reserved seats across all theaters"
- Should be 100% accurate to database records

#### Test Case 1.2: Theater Count
**Query**: `"How many theaters are showing Dune: Part Two?"`
**Expected Response**:
- Exact count of unique theaters showing the movie
- Format: "Dune: Part Two is showing in X theaters"

#### Test Case 1.3: Average Price
**Query**: `"What is the average ticket price for Twisters?"`
**Expected Response**:
- Calculated average price across all showtimes
- Format: "The average ticket price for Twisters is $X.XX"

#### Test Case 1.4: Top Showtimes
**Query**: `"Show me the top 5 showtimes for Dune: Part Two by reserved seats"`
**Expected Response**:
- List of top 5 showtimes with theater names, times, and reserved seat counts
- Should be sorted by reserved seats (descending)

#### Test Case 1.5: Revenue Calculation
**Query**: `"What is the total revenue for Twisters?"`
**Expected Response**:
- Total revenue = sum of (reserved seats × price) for all showtimes
- Format: "Twisters has generated $X,XXX,XXX in total revenue"

---

### 2. **Comparative Analysis Queries** (Complex Analytics)

#### Test Case 2.1: Best Comp Titles
**Query**: `"What are the best comp titles for Twisters?"`
**Expected Response**:
- Should use vector search to find similar movies
- Return movies with similar performance patterns
- Include similarity scores and reasoning

#### Test Case 2.2: Performance Comparison
**Query**: `"Compare Twisters vs Dune: Part Two performance"`
**Expected Response**:
- Side-by-side comparison of key metrics
- Occupancy rates, revenue, theater count
- Performance analysis and insights

#### Test Case 2.3: Genre Comparison
**Query**: `"How is Dune: Part Two performing compared to similar sci-fi movies?"`
**Expected Response**:
- Compare against other sci-fi movies in database
- Performance metrics relative to genre average
- Market positioning analysis

#### Test Case 2.4: Studio Performance
**Query**: `"How are Warner Bros movies performing compared to other studios?"`
**Expected Response**:
- Aggregate performance metrics for Warner Bros movies
- Comparison with other studios
- Market share analysis

---

### 3. **Performance Analysis Queries** (Advanced Analytics)

#### Test Case 3.1: Day-of-Week Analysis
**Query**: `"How is Twisters performing on Thursday compared to comp titles?"`
**Expected Response**:
- Thursday-specific performance metrics
- Comparison with similar movies on Thursdays
- Day-of-week performance patterns

#### Test Case 3.2: Format Performance
**Query**: `"Is Dune: Part Two overperforming or underperforming on IMAX screens?"`
**Expected Response**:
- IMAX-specific performance analysis
- Comparison with standard format performance
- Premium format effectiveness

#### Test Case 3.3: Geographic Performance
**Query**: `"How is Twisters performing in less populated areas?"`
**Expected Response**:
- Performance analysis by city size/population
- Rural vs urban market performance
- Geographic opportunity analysis

#### Test Case 3.4: Time-based Trends
**Query**: `"Is Dune: Part Two overperforming on Thursday?"`
**Expected Response**:
- Thursday performance vs other days
- Trend analysis over time
- Day-specific insights

---

### 4. **Sales & Revenue Queries** (Financial Analytics)

#### Test Case 4.1: Weekend Projections
**Query**: `"What are the estimated sales for Twisters this weekend?"`
**Expected Response**:
- Weekend sales projection based on current data
- Historical weekend performance patterns
- Confidence intervals for projections

#### Test Case 4.2: Revenue Breakdown
**Query**: `"Show me the sales breakdown for Dune: Part Two by format"`
**Expected Response**:
- Revenue breakdown by screen format (IMAX, Standard, etc.)
- Format performance analysis
- Revenue optimization insights

#### Test Case 4.3: Box Office Projections
**Query**: `"What is the projected box office for Twisters?"`
**Expected Response**:
- Total box office projection
- Based on current performance trends
- Market potential analysis

---

### 5. **Market & Opportunity Queries** (Strategic Analysis)

#### Test Case 5.1: Market Opportunities
**Query**: `"Where are the market opportunities for Twisters?"`
**Expected Response**:
- Underperforming markets identified
- Geographic opportunities
- Optimization recommendations

#### Test Case 5.2: Optimal Showtimes
**Query**: `"What are the best showtimes for Dune: Part Two?"`
**Expected Response**:
- Time slots with highest occupancy
- Revenue optimization recommendations
- Scheduling insights

#### Test Case 5.3: Underperforming Markets
**Query**: `"Which cities are underperforming for Twisters?"`
**Expected Response**:
- List of underperforming cities
- Performance metrics vs expectations
- Improvement recommendations

#### Test Case 5.4: Expansion Opportunities
**Query**: `"Where are my opportunities for Dune: Part Two?"`
**Expected Response**:
- Market expansion opportunities
- Untapped geographic areas
- Growth potential analysis

---

### 6. **Weekend & Drop Analysis** (Trend Analysis)

#### Test Case 6.1: Weekend Drop Prediction
**Query**: `"How much will Dune: Part Two drop in its second weekend?"`
**Expected Response**:
- Second weekend drop percentage prediction
- Based on historical patterns
- Confidence level for prediction

#### Test Case 6.2: Drop Analysis
**Query**: `"What is the weekend drop prediction for Twisters?"`
**Expected Response**:
- Weekend-to-weekend performance analysis
- Drop rate calculations
- Trend analysis

---

### 7. **Format & Screen Analysis** (Technical Analysis)

#### Test Case 7.1: Format Performance
**Query**: `"How is Dune: Part Two performing on IMAX screens?"`
**Expected Response**:
- IMAX-specific performance metrics
- Comparison with other formats
- Premium format effectiveness

#### Test Case 7.2: Screen Optimization
**Query**: `"What is the best screen format for Twisters?"`
**Expected Response**:
- Format performance comparison
- Revenue per format analysis
- Optimization recommendations

---

### 8. **Geographic Performance** (Location Analysis)

#### Test Case 8.1: State Comparison
**Query**: `"How is Twisters performing in California vs New York?"`
**Expected Response**:
- State-by-state performance comparison
- Market characteristics analysis
- Regional insights

#### Test Case 8.2: Top Markets
**Query**: `"Which states are the top markets for Dune: Part Two?"`
**Expected Response**:
- Ranked list of top-performing states
- Market performance metrics
- Geographic insights

---

### 9. **Capacity & Occupancy** (Operational Analysis)

#### Test Case 9.1: Occupancy Rates
**Query**: `"What is the overall occupancy rate for Twisters?"`
**Expected Response**:
- Overall occupancy percentage
- Capacity utilization analysis
- Performance benchmarks

#### Test Case 9.2: Capacity Analysis
**Query**: `"Which theaters have the highest capacity utilization for Dune: Part Two?"`
**Expected Response**:
- Top theaters by capacity utilization
- Theater performance rankings
- Optimization opportunities

---

### 10. **Complex Multi-Parameter Queries** (Advanced Analytics)

#### Test Case 10.1: Multi-Factor Analysis
**Query**: `"What are the best comp titles for Twisters and how are they performing?"`
**Expected Response**:
- Comp title identification
- Performance comparison
- Multi-factor analysis

#### Test Case 10.2: Comprehensive Analysis
**Query**: `"Show me estimated sales for Dune: Part Two and compare with comp titles"`
**Expected Response**:
- Sales projections
- Comp title comparisons
- Comprehensive performance analysis

#### Test Case 10.3: Geographic + Format Analysis
**Query**: `"How is Twisters overperforming in less populated areas compared to comp titles?"`
**Expected Response**:
- Geographic performance analysis
- Comp title comparisons
- Rural market insights

#### Test Case 10.4: Market + Opportunity Analysis
**Query**: `"What are the market opportunities for Dune: Part Two and where should I focus?"`
**Expected Response**:
- Market opportunity identification
- Strategic focus recommendations
- Actionable insights

---

## 🚀 **Testing Commands**

### Start the Server
```bash
cd /home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main
source /home/ec2-user/venv/bin/activate
python manage.py runserver 0.0.0.0:8000
```

### Test API Endpoint
```bash
curl -X POST http://3.234.43.140:8000/api/messages/ \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What is the total reserved seats for Twisters?",
    "conversation": 1
  }'
```

### Python Test Script
```python
import requests
import json

def test_query(query):
    url = "http://3.234.43.140:8000/api/messages/"
    data = {
        "content": query,
        "conversation": 1
    }
    response = requests.post(url, json=data)
    return response.json()

# Test all queries
queries = [
    "What is the total reserved seats for Twisters?",
    "How many theaters are showing Dune: Part Two?",
    "What are the best comp titles for Twisters?",
    "Compare Twisters vs Dune: Part Two performance",
    "Where are the market opportunities for Twisters?",
    # ... add all 20+ queries
]

for query in queries:
    result = test_query(query)
    print(f"Query: {query}")
    print(f"Response: {result}")
    print("-" * 50)
```

---

## ✅ **Success Criteria**

### Accuracy Requirements
- **100% accuracy** on factual database queries
- **Mathematical precision** in all calculations
- **Consistent formatting** across responses
- **Proper error handling** for invalid queries

### Performance Requirements
- **Response time**: < 5 seconds for simple queries
- **Response time**: < 10 seconds for complex analytical queries
- **Vector search**: Relevant results with high confidence scores
- **Database queries**: Optimized performance

### Quality Requirements
- **Natural language responses** (not raw data dumps)
- **Contextual insights** and analysis
- **Actionable recommendations** where appropriate
- **Professional formatting** with clear structure

---

## 🔍 **Expected System Behavior**

### Query Type Detection
The intelligent agent should automatically detect:
- **Database queries**: Direct facts from tables
- **Comparative queries**: Vector search + database analysis
- **Analytical queries**: Complex calculations and insights
- **Opportunity queries**: Market analysis and recommendations

### Response Generation
- **Hybrid approach**: Combine RAG (vector search) with direct database queries
- **Llama LLM**: Generate natural language responses
- **Data validation**: Ensure all numbers match database records
- **Context awareness**: Provide relevant insights and analysis

### Error Handling
- **Invalid queries**: Graceful error messages
- **Missing data**: Clear explanations
- **System errors**: Fallback responses
- **Timeout handling**: Appropriate error messages

---

## 📊 **Test Results Tracking**

Track the following metrics for each test case:
- ✅ **Accuracy**: Does the response match database records?
- ✅ **Completeness**: Are all requested data points included?
- ✅ **Clarity**: Is the response easy to understand?
- ✅ **Speed**: Response time within requirements?
- ✅ **Format**: Professional presentation?

---

## 🎯 **Priority Test Cases**

### High Priority (Must Pass)
1. Total reserved seats queries
2. Theater count queries
3. Revenue calculations
4. Comp title identification
5. Performance comparisons

### Medium Priority (Should Pass)
1. Geographic analysis
2. Format performance
3. Market opportunities
4. Weekend predictions
5. Occupancy analysis

### Low Priority (Nice to Have)
1. Complex multi-parameter queries
2. Advanced trend analysis
3. Strategic recommendations
4. Detailed market insights
5. Optimization suggestions

---

This comprehensive test suite will validate that the intelligent film analytics system can handle all types of queries with 100% accuracy and provide valuable insights for film industry decision-making.
