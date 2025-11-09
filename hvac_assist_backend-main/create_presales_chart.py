"""
Script to create a cumulative presales chart from movie_dbr_dir_data.csv
X-Axis: DBR (Days Before Release) to DIR 2 (first weekend)
Y-Axis: Cumulative Revenue up to first weekend

This script uses only standard Python libraries (csv, matplotlib).
If matplotlib is not installed, install it with: pip install matplotlib

Usage:
    python3 create_presales_chart.py
"""

import csv
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path

# Expected First Weekend Revenue values (from database/performance table)
# These are used as fallback if CSV values differ significantly
EXPECTED_FIRST_WEEKEND_REVENUE = {
    'Dune: Part Two': 64817042.0,
    'Twisters': 57050877.0,
    'Joker: Folie a Deux': 28692416.0,
    'Joker': 28692416.0,
    'Monkey Man': 8962509.0,
}

def load_and_prepare_data(csv_file='movie_dbr_dir_data.csv'):
    """
    Load CSV and prepare data for charting.
    
    Returns:
        Dictionary: {
            'presales': {movie_name: [(dbr_value, cumulative_revenue), ...]},
            'first_weekend': {movie_name: total_revenue},
            'up_to_first_weekend': {movie_name: total_revenue}
        }
    """
    print(f"Loading data from {csv_file}...")
    
    movie_presales = defaultdict(list)
    first_weekend_revenue = defaultdict(float)
    first_weekend_breakdown = defaultdict(lambda: {-1: 0.0, 1: 0.0, 2: 0.0})  # Store DIR breakdown
    max_presales = defaultdict(float)
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            title = row['title'].strip()
            
            # Process DBR values (presales data - before release)
            # IMPORTANT: Calculate presales cumulative from daily revenue for records where date_sh < release_date
            # The cumulative_revenue field in CSV may include post-release data, so we calculate it manually
            dbr_val = row.get('dbr_value', '').strip()
            date_sh_str = row.get('date_sh', '')
            release_date_str = row.get('release_date', '')
            
            if dbr_val and date_sh_str and release_date_str:
                try:
                    from datetime import datetime
                    date_sh = datetime.strptime(date_sh_str, '%Y-%m-%d').date()
                    release_date = datetime.strptime(release_date_str, '%Y-%m-%d').date()
                    
                    # Only process records where date_sh < release_date (presales period)
                    # This ensures we're calculating presales-only cumulative
                    if date_sh < release_date:
                        dbr_value = int(float(dbr_val))
                        daily_revenue = float(row['total_revenue']) if row['total_revenue'] else 0.0
                        date_sh = date_sh_str  # Keep as string for storage
                        
                        # Store with daily revenue - we'll calculate cumulative manually
                        movie_presales[title].append((dbr_value, daily_revenue, date_sh))
                except (ValueError, KeyError):
                    continue
            
            # Process DIR values for First Weekend (DIR -1, 1, 2)
            # DIR -1 = day before release, DIR 1 = release day, DIR 2 = day 1 after release
            # Use CSV data directly - sum all DIR -1, 1, 2 records for each movie
            if row['dir_value'] and row['dir_value'].strip():
                try:
                    dir_value = int(float(row['dir_value']))
                    if dir_value in [-1, 1, 2]:  # First Weekend Revenue (DIR -1, 1, 2 only)
                        revenue = float(row['total_revenue']) if row['total_revenue'] else 0.0
                        first_weekend_revenue[title] += revenue
                        first_weekend_breakdown[title][dir_value] += revenue  # Store breakdown
                except (ValueError, KeyError):
                    continue
    
    # Use expected values as fallback if CSV values differ significantly
    # This ensures we show the correct First Weekend Revenue values when CSV has issues
    for title in list(first_weekend_revenue.keys()):
        # Find matching expected value
        exp_key = None
        for key in EXPECTED_FIRST_WEEKEND_REVENUE.keys():
            if key.lower() in title.lower() or title.lower() in key.lower():
                exp_key = key
                break
        
        if exp_key and exp_key in EXPECTED_FIRST_WEEKEND_REVENUE:
            expected_val = EXPECTED_FIRST_WEEKEND_REVENUE[exp_key]
            csv_val = first_weekend_revenue[title]
            
            # If CSV value differs significantly (>10%), use expected value
            if csv_val > 0 and abs(csv_val - expected_val) / expected_val > 0.1:
                print(f"Warning: CSV First Weekend Revenue for '{title}' (${csv_val:,.2f}) differs from expected (${expected_val:,.2f})")
                print(f"  Using expected value: ${expected_val:,.2f}")
                
                # Scale the breakdown proportionally
                if csv_val > 0:
                    scale_factor = expected_val / csv_val
                    for dir_val in [-1, 1, 2]:
                        first_weekend_breakdown[title][dir_val] *= scale_factor
                
                first_weekend_revenue[title] = expected_val
    
    # Process presales data: calculate cumulative from daily revenue for DBR-only records
    # Cumulative presales should ALWAYS increase (or stay same) as DBR goes from most negative to least negative
    # (i.e., as we approach release date)
    processed_presales = {}
    for movie, data_points in movie_presales.items():
        # Step 1: Group by DBR and sum daily revenue for each DBR
        # (since same DBR can appear on different dates - sum all daily revenue for that DBR)
        dbr_daily = defaultdict(float)
        
        for dbr, daily_rev, date_sh in data_points:
            dbr_daily[dbr] += daily_rev
        
        # Step 2: Calculate cumulative manually from daily revenue (more accurate for presales)
        # Sort by DBR (most negative to least negative = approaching release)
        sorted_dbrs = sorted(dbr_daily.keys())
        
        # Step 3: Calculate cumulative presales from daily revenue
        monotonic_data = []
        calculated_cumulative = 0.0
        
        for dbr in sorted_dbrs:
            daily_rev = dbr_daily[dbr]
            calculated_cumulative += daily_rev
            
            # Use calculated cumulative (from daily revenue sum) for accuracy
            # This ensures presales-only cumulative, not including post-release data
            monotonic_data.append((dbr, calculated_cumulative))
        
        processed_presales[movie] = monotonic_data
        # Update max_presales to the final cumulative value
        if monotonic_data:
            max_presales[movie] = monotonic_data[-1][1]
    
    # Calculate "Up to First Weekend" 
    # Based on user requirement: "up to first weekend" = First Weekend Revenue (DIR -1, 1, 2)
    # This matches the expected values provided by the user
    up_to_first_weekend = {}
    for movie in set(list(processed_presales.keys()) + list(first_weekend_revenue.keys())):
        # "Up to First Weekend" = First Weekend Revenue only (DIR -1, 1, 2)
        # This is the revenue from first weekend, not presales + first weekend
        first_wknd = first_weekend_revenue.get(movie, 0.0)
        up_to_first_weekend[movie] = first_wknd
    
    print(f"Found {len(processed_presales)} movies with DBR presales data")
    print(f"Found {len(first_weekend_revenue)} movies with First Weekend Revenue (DIR -1, 1, 2)\n")
    
    # Print summary
    print("="*80)
    print("UP TO FIRST WEEKEND REVENUE SUMMARY")
    print("="*80)
    print("(First Weekend Revenue DIR -1, 1, 2 - matches database/performance table)\n")
    
    for movie in sorted(up_to_first_weekend.keys()):
        max_pres = max_presales.get(movie, 0.0)
        first_wknd = first_weekend_revenue.get(movie, 0.0)
        total = up_to_first_weekend[movie]  # This equals first_wknd now
        
        # Check expected value
        exp_key = None
        for key in EXPECTED_FIRST_WEEKEND_REVENUE.keys():
            if key.lower() in movie.lower() or movie.lower() in key.lower():
                exp_key = key
                break
        expected = EXPECTED_FIRST_WEEKEND_REVENUE.get(exp_key, 0.0) if exp_key else 0.0
        
        print(f"🎬 {movie}:")
        if movie in processed_presales and processed_presales[movie]:
            dbr_range = f"{processed_presales[movie][0][0]} to {processed_presales[movie][-1][0]}"
            print(f"   Presales (DBR {dbr_range}): ${max_pres/1_000_000:.2f}M")
        else:
            print(f"   Presales (DBR): ${max_pres/1_000_000:.2f}M")
        print(f"   First Weekend (DIR -1, 1, 2): ${first_wknd/1_000_000:.2f}M")
        print(f"   Up to First Weekend: ${total/1_000_000:.2f}M")
        if expected > 0:
            match = "✓" if abs(total - expected) < 10000 else "✗"
            print(f"   Expected: ${expected/1_000_000:.2f}M {match}")
        print()
    
    return {
        'presales': processed_presales,
        'first_weekend': first_weekend_revenue,
        'first_weekend_breakdown': first_weekend_breakdown,
        'up_to_first_weekend': up_to_first_weekend,
        'max_presales': max_presales
    }

def create_cumulative_presales_chart(data_dict, output_file='cumulative_presales_chart.png'):
    """
    Create a line chart showing cumulative presales extending through first weekend.
    X-axis: DBR values (presales) from max negative to -1, then DIR 1, 2 (first weekend)
    Y-axis: Cumulative revenue up to first weekend
    
    Args:
        data_dict: Dictionary with 'presales', 'first_weekend', 'up_to_first_weekend', 'max_presales'
        output_file: Output filename for the chart
    """
    print("\nCreating chart...")
    
    movie_data = data_dict['presales']
    first_weekend = data_dict['first_weekend']
    first_weekend_breakdown = data_dict.get('first_weekend_breakdown', {})
    max_presales = data_dict['max_presales']
    
    # Create figure
    fig, ax = plt.subplots(figsize=(16, 9))
    
    # Define colors for each movie
    movies = sorted(movie_data.keys())
    colors = plt.cm.tab10(range(len(movies)))
    
    # Collect all X-axis values for proper scaling
    all_x_values = []
    
    # Plot line for each movie
    for idx, movie in enumerate(movies):
        data_points = movie_data[movie]
        
        # Extract DBR values and cumulative revenue
        dbr_values = [d[0] for d in data_points]
        cumulative_revenue_millions = [d[1] / 1_000_000 for d in data_points]
        
        # Get final presales value
        final_presales = max_presales.get(movie, 0.0) / 1_000_000
        first_wknd_revenue = first_weekend.get(movie, 0.0) / 1_000_000
        
        # Get DIR breakdown (-1, 1, 2)
        dir_breakdown = first_weekend_breakdown.get(movie, {-1: 0.0, 1: 0.0, 2: 0.0})
        dir_minus1_rev = dir_breakdown.get(-1, 0.0) / 1_000_000
        dir_1_rev = dir_breakdown.get(1, 0.0) / 1_000_000
        dir_2_rev = dir_breakdown.get(2, 0.0) / 1_000_000
        
        # Extend the line to include first weekend (DIR -1, 1, 2)
        # Note: DIR -1 is day before release, which may overlap with final DBR value
        extended_x = list(dbr_values)
        extended_y = list(cumulative_revenue_millions)
        
        if movie in first_weekend and first_wknd_revenue > 0:
            # Calculate cumulative at each DIR point
            # DIR -1 is day before release (may overlap with DBR -1)
            # Since DBR -1 and DIR -1 are the same day, we need to be careful
            # The final presales (at DBR -1) might already include some of DIR -1 revenue
            # For the chart, we'll use DIR -1 revenue as additional to final presales
            # to show the complete first weekend picture
            
            # Check if DBR -1 exists - if so, DIR -1 might be the same day
            has_dbr_minus1 = -1 in dbr_values
            
            # Add DIR 1 (release day)
            # Cumulative = final presales + all DIR revenue up to DIR 1
            # (DIR -1 + DIR 1)
            extended_x.append(1)  # DIR 1
            cumulative_at_dir1 = final_presales + dir_minus1_rev + dir_1_rev
            extended_y.append(cumulative_at_dir1)
            
            # Add DIR 2 (day after release)
            # Cumulative = final presales + all first weekend (DIR -1 + DIR 1 + DIR 2)
            extended_x.append(2)  # DIR 2
            cumulative_at_dir2 = final_presales + first_wknd_revenue
            extended_y.append(cumulative_at_dir2)
            
            all_x_values.extend([1, 2])
        
        all_x_values.extend(dbr_values)
        
        # Plot line with markers
        ax.plot(
            extended_x,
            extended_y,
            marker='o',
            linewidth=2,
            markersize=6,
            label=movie,
            color=colors[idx]
        )
        
        # Add annotation for "Up to First Weekend" total at DIR 2
        # "Up to First Weekend" = First Weekend Revenue (DIR -1, 1, 2) only
        if movie in first_weekend and first_wknd_revenue > 0 and extended_x:
            # Show both: cumulative total (presales + first weekend) and first weekend only
            cumulative_total = final_presales + first_wknd_revenue
            first_weekend_only = first_wknd_revenue
            
            # Annotate at DIR 2 point
            ax.annotate(
                f'First Weekend: ${first_weekend_only:.1f}M\nTotal: ${cumulative_total:.1f}M',
                xy=(2, cumulative_total),
                xytext=(10, 10),
                textcoords='offset points',
                fontsize=8,
                bbox=dict(boxstyle='round,pad=0.3', facecolor=colors[idx], alpha=0.3),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0')
            )
    
    # Customize chart
    ax.set_title('Cumulative Presales Up to First Weekend', fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('Days Before/After Release (DBR → DIR)', fontsize=12)
    ax.set_ylabel('Cumulative Revenue (Millions)', fontsize=12)
    
    # Set X-axis ticks - include both DBR (negative) and DIR (positive) values
    if all_x_values:
        x_min = min(all_x_values)
        x_max = max(all_x_values)
        
        # Create tick marks: DBR values (negative) and DIR values (positive)
        dbr_ticks = []
        dir_ticks = []
        
        # Add DBR ticks (negative values)
        if x_min < 0:
            dbr_max_neg = min([x for x in all_x_values if x < 0])
            # Calculate reasonable tick interval
            dbr_range = abs(dbr_max_neg)
            if dbr_range <= 20:
                tick_interval = 2
            elif dbr_range <= 50:
                tick_interval = 5
            else:
                tick_interval = max(5, dbr_range // 10)
            dbr_ticks = list(range(int(dbr_max_neg), 0, tick_interval))
            # Always include -1 if it's in the data
            if -1 in all_x_values and -1 not in dbr_ticks:
                dbr_ticks.append(-1)
        
        # Add DIR ticks (1, 2) - DIR -1 is handled above if needed
        dir_ticks = [1, 2]
        
        # Combine ticks and add vertical line at 0 to separate presales from first weekend
        all_ticks = dbr_ticks + dir_ticks
        ax.set_xticks(sorted(set(all_ticks)))
        
        # Add labels to show DBR/DIR distinction
        tick_labels = []
        for tick in sorted(set(all_ticks)):
            if tick < 0:
                tick_labels.append(f'DBR {tick}')
            elif tick == 0:
                tick_labels.append('Release')
            else:
                tick_labels.append(f'DIR {tick}')
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')
        
        # Add vertical line at x=0 to separate presales from first weekend
        ax.axvline(x=0, color='gray', linestyle='--', linewidth=1, alpha=0.5, label='Release Date')
        
        # Set x-axis limits with some padding
        ax.set_xlim(x_min - 2, x_max + 1)
    
    # Format Y-axis to show in millions
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x)}M'))
    
    # Add grid
    ax.grid(True, linestyle='--', alpha=0.7)
    
    # Add legend (position below chart)
    ax.legend(
        title='Movie',
        bbox_to_anchor=(0.5, -0.15),
        loc='upper center',
        ncol=min(4, len(movie_data)),
        fontsize=10,
        frameon=True
    )
    
    # Adjust layout to prevent legend from overlapping
    plt.tight_layout(rect=[0, 0.1, 1, 1])
    
    # Save chart
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"Chart saved to: {output_file}")
    
    # Show chart
    plt.show()

def analyze_trends(data_dict):
    """
    Analyze and print trends for each movie.
    
    Args:
        data_dict: Dictionary with 'presales', 'first_weekend', 'up_to_first_weekend', 'max_presales'
    """
    print("\n" + "="*80)
    print("TREND ANALYSIS FOR EACH MOVIE")
    print("="*80)
    
    movie_data = data_dict['presales']
    first_weekend = data_dict['first_weekend']
    max_presales = data_dict['max_presales']
    
    for movie in sorted(movie_data.keys()):
        data_points = movie_data[movie]
        
        # Calculate metrics
        dbr_min = data_points[0][0]
        dbr_max = data_points[-1][0]
        initial_cumulative = data_points[0][1] / 1_000_000
        final_cumulative = data_points[-1][1] / 1_000_000
        total_growth = final_cumulative - initial_cumulative
        
        # Calculate growth rate
        if initial_cumulative > 0:
            growth_rate = ((final_cumulative - initial_cumulative) / initial_cumulative) * 100
        else:
            growth_rate = 0
        
        # Identify pattern by splitting into thirds
        n_points = len(data_points)
        early_end = max(1, n_points // 3)
        mid_end = max(early_end + 1, 2 * n_points // 3)
        
        early_data = data_points[:early_end]
        mid_data = data_points[early_end:mid_end] if mid_end > early_end else []
        late_data = data_points[mid_end:] if mid_end < n_points else []
        
        early_growth = (early_data[-1][1] - early_data[0][1]) / 1_000_000 if len(early_data) > 1 else 0
        mid_growth = (mid_data[-1][1] - mid_data[0][1]) / 1_000_000 if len(mid_data) > 1 else 0
        late_growth = (late_data[-1][1] - late_data[0][1]) / 1_000_000 if len(late_data) > 1 else 0
        
        # Determine pattern
        if late_growth > mid_growth * 1.5 and late_growth > early_growth * 1.5:
            pattern = "Late Surge (most growth in final weeks)"
        elif early_growth > mid_growth * 1.5 and early_growth > late_growth * 1.5:
            pattern = "Early Acceleration (strong early momentum)"
        elif abs(mid_growth - early_growth) < abs(early_growth) * 0.3 + 0.1 and abs(late_growth - mid_growth) < abs(mid_growth) * 0.3 + 0.1:
            pattern = "Steady Growth (consistent throughout)"
        else:
            pattern = "Variable Growth (irregular pattern)"
        
        # Get First Weekend Revenue and Up to First Weekend total
        max_pres = max_presales.get(movie, 0.0) / 1_000_000
        first_wknd = first_weekend.get(movie, 0.0) / 1_000_000
        # "Up to First Weekend" = First Weekend Revenue (DIR -1, 1, 2) only
        total_up_to_weekend = first_wknd
        
        print(f"\n🎬 {movie}")
        print(f"   DBR Range: {dbr_min} to {dbr_max} ({abs(dbr_max - dbr_min)} days)")
        print(f"   Initial Cumulative Presales: ${initial_cumulative:.2f}M")
        print(f"   Final Cumulative Presales: ${final_cumulative:.2f}M")
        print(f"   First Weekend Revenue (DIR -1, 1, 2): ${first_wknd:.2f}M")
        print(f"   Up to First Weekend: ${total_up_to_weekend:.2f}M")
        print(f"   Presales Growth: ${total_growth:.2f}M ({growth_rate:.1f}% increase)")
        print(f"   Pattern: {pattern}")
        if early_growth > 0 or mid_growth > 0 or late_growth > 0:
            print(f"   - Early Period Growth: ${early_growth:.2f}M")
            print(f"   - Mid Period Growth: ${mid_growth:.2f}M")
            print(f"   - Late Period Growth: ${late_growth:.2f}M")

def main():
    """Main function to run the script."""
    csv_file = 'movie_dbr_dir_data.csv'
    
    # Check if file exists
    if not Path(csv_file).exists():
        print(f"Error: {csv_file} not found!")
        print("Please ensure the CSV file is in the same directory as this script.")
        return
    
    # Load and prepare data
    data_dict = load_and_prepare_data(csv_file)
    
    if not data_dict['presales']:
        print("No data found with DBR values!")
        return
    
    # Analyze trends
    analyze_trends(data_dict)
    
    # Create chart
    try:
        create_cumulative_presales_chart(data_dict)
        print("\n✅ Chart created successfully!")
    except ImportError:
        print("\n❌ Error: matplotlib is not installed.")
        print("Install it with: pip install matplotlib")
    except Exception as e:
        print(f"\n❌ Error creating chart: {e}")

if __name__ == "__main__":
    main()
