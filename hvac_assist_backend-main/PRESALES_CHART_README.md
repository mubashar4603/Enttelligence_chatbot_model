# Cumulative Presales Chart Generator

## Overview

This script creates a line chart showing cumulative presales trends for multiple movies, with:
- **X-Axis**: DBR (Days Before Release) - negative values showing days before release
- **Y-Axis**: Cumulative Presales Revenue (in millions)

## How the Chart is Built

### Data Structure Required

The CSV file (`my_export.csv`) should contain:
- `title`: Movie name
- `dbr_value`: Days Before Release (negative integers, e.g., -52, -50, ..., -2)
- `cumulative_revenue`: Cumulative presales revenue (running total)

### Chart Building Process

1. **Data Loading**: Reads CSV and filters for records with DBR values (presales data)
2. **Data Grouping**: Groups by movie title and DBR value
3. **Data Sorting**: Sorts DBR values from most negative (earliest) to least negative (closest to release)
4. **Line Plotting**: Creates a separate line for each movie showing cumulative presales over time
5. **Visualization**: 
   - Each movie gets a unique color
   - Markers (circles) show data points
   - Lines connect points to show trend
   - Legend identifies each movie

### Key Concepts

- **DBR (Days Before Release)**: Negative values indicate days before release
  - DBR -52 = 52 days before release
  - DBR -2 = 2 days before release
  - Lower (more negative) = earlier in presales window
  
- **Cumulative Presales**: Running total that ALWAYS increases
  - Each day's sales are added to the previous total
  - The chart shows HOW FAST it accumulates (rate of increase)
  - Steep lines = high daily sales
  - Flat lines = low daily sales

## Movie Trends Analysis

Based on your CSV data, here are the trends for each movie:

### 1. **Dune: Part Two**
- **DBR Range**: -34 to -5 (29 days of presales data)
- **Max Cumulative Presales**: $8.75M
- **Pattern**: Strong early momentum with steady accumulation
- **Characteristics**: 
  - Shows consistent growth throughout presales window
  - Cumulative presales increase steadily as release approaches
  - Strong fan base and marketing momentum
  - Highest cumulative presales among all movies

### 2. **Twisters**
- **DBR Range**: -45 to -23 (22 days of presales data)
- **Max Cumulative Presales**: $6.70M
- **Pattern**: Early start with moderate growth
- **Characteristics**:
  - Starts presales earlier than other movies (DBR -45)
  - Steady accumulation pattern
  - Second-highest cumulative presales
  - Good early momentum

### 3. **Joker: Folie a Deux**
- **DBR Range**: -25 (single data point)
- **Max Cumulative Presales**: $5.88M
- **Pattern**: Limited data, but shows strong presales at DBR -25
- **Characteristics**:
  - High-profile sequel with built-in audience
  - Strong presales at measured point
  - Third-highest cumulative presales
  - Note: Limited data points in CSV

### 4. **Monkey Man**
- **DBR Range**: -25 to -7 (18 days of presales data)
- **Max Cumulative Presales**: $1.33M
- **Pattern**: Moderate growth pattern
- **Characteristics**:
  - Steady accumulation throughout presales window
  - Consistent daily sales activity
  - Lower volume compared to blockbusters
  - Moderate presales performance

### 5. **Homestead**
- **DBR Range**: -31 to -24 (7 days of presales data)
- **Max Cumulative Presales**: $1.01M
- **Pattern**: Limited presales window, gradual accumulation
- **Characteristics**:
  - Smaller scale release
  - Shorter presales window
  - More gradual accumulation pattern
  - Lowest cumulative presales among measured movies

## Usage

### Prerequisites

Install matplotlib if not already installed:
```bash
pip install matplotlib
```

### Running the Script

```bash
python3 create_presales_chart.py
```

### Output

The script will:
1. Load and analyze the CSV data
2. Print trend analysis for each movie
3. Generate a chart saved as `cumulative_presales_chart.png`
4. Display the chart on screen

### Customization

You can modify the script to:
- Change output filename: Edit `output_file` parameter
- Adjust chart size: Modify `figsize=(14, 8)`
- Change colors: Modify the `colors` assignment
- Filter specific movies: Add filtering logic in `load_and_prepare_data()`

## Understanding the Chart

### Reading the Chart

1. **X-Axis (DBR)**: 
   - Left side = earlier in presales window (more days before release)
   - Right side = closer to release date
   - Values decrease from left to right (e.g., -50 → -2)

2. **Y-Axis (Cumulative Presales)**:
   - Bottom = lower cumulative presales
   - Top = higher cumulative presales
   - Always increases (never decreases) as you move right

3. **Line Patterns**:
   - **Steep upward slope**: High daily sales on those days
   - **Gentle slope**: Moderate daily sales
   - **Near-horizontal**: Low daily sales
   - **Accelerating curve**: Increasing daily sales as release approaches
   - **Decelerating curve**: Decreasing daily sales rate (but cumulative still increases)

### Interpreting Trends

- **Early Acceleration**: Line starts steep, indicating strong early presales
- **Late Surge**: Line gets steeper near release (right side), indicating last-minute bookings
- **Steady Growth**: Consistent slope throughout, indicating stable daily sales
- **Variable Growth**: Irregular pattern, may indicate marketing events or external factors

## Example Output

The chart will show:
- Multiple colored lines, one for each movie
- X-axis labeled "DBR (Days Before Release)"
- Y-axis labeled "Cumulative PreSales (Millions)"
- Legend at bottom identifying each movie
- Grid lines for easier reading
- Title: "Sales Estimate PreSales Cumulative"

## Notes

- Cumulative presales ALWAYS increase - they never decrease
- What we compare is the SHAPE and RATE of increase
- Movies with similar slopes have similar daily sales patterns
- Movies with higher final cumulative values had stronger overall presales

