"""
Script to create a cumulative presales chart by querying the Movie table directly.

X-Axis: DBR (Days Before Release) extending through DIR 2 (first weekend)
Y-Axis: Cumulative Revenue up to first weekend

Usage:
    python3 create_presales_chart.py
"""

import os
import sys
from collections import defaultdict
from decimal import Decimal
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt

# Configure Django settings so we can query the Movie table directly
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hvac_assist_backend.settings')

try:
    import django
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Error: Django is not installed. Please install project dependencies before running this script."
    ) from exc

django.setup()

from django.db import OperationalError
from django.db.models import F, Sum, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce

from movies.models import Movie

# Expected First Weekend Revenue values (from database/performance table)
# These are used as fallback if CSV values differ significantly
EXPECTED_FIRST_WEEKEND_REVENUE = {
    'Dune: Part Two': 64817042.0,
    'Twisters': 57050877.0,
    'Joker: Folie a Deux': 28692416.0,
    'Joker': 28692416.0,
    'Monkey Man': 8962509.0,
}

def calculate_dir(date_sh, release_date):
    """Calculate DIR (Days In Release) using business logic."""
    if not date_sh or not release_date:
        return None
    diff = (date_sh - release_date).days
    return diff if diff < 0 else diff + 1


def calculate_dbr(running_date, release_date):
    """Calculate DBR (Days Before Release) using business logic."""
    if not running_date or not release_date:
        return None
    diff = (running_date - release_date).days
    dbr_value = diff if diff < 0 else diff + 1
    if dbr_value is None or dbr_value > 2:
        return None
    return dbr_value


def load_and_prepare_data():
    """
    Query the Movie table directly and prepare data for charting.
    
    Returns:
        Dictionary: {
            'presales': {movie_label: [(dbr_value, cumulative_revenue), ...]},
            'first_weekend': {movie_label: total_revenue},
            'up_to_first_weekend': {movie_label: total_revenue}
        }
    """
    print("Loading data from Movie table...")
    
    revenue_expression = ExpressionWrapper(
        F('price') * F('reserved'),
        output_field=DecimalField(max_digits=18, decimal_places=2)
    )
    
    try:
        queryset = (
            Movie.objects
            .values('title', 'release_date', 'date_sh', 'running_date')
            .annotate(
                total_revenue=Coalesce(
                    Sum(revenue_expression, output_field=DecimalField(max_digits=18, decimal_places=2)),
                    Decimal('0')
                ),
                total_reserved=Coalesce(Sum('reserved'), 0)
            )
            .order_by('title', 'release_date', 'date_sh', 'running_date')
        )
    except OperationalError as exc:
        raise SystemExit(f"Error querying Movie table: {exc}") from exc
    
    presales_daily = defaultdict(lambda: defaultdict(float))
    first_weekend_revenue = defaultdict(float)
    first_weekend_breakdown = defaultdict(lambda: {-1: 0.0, 1: 0.0, 2: 0.0})
    max_presales = defaultdict(float)
    movie_title_lookup = {}
    
    for row in queryset:
        title = row['title'].strip() if row['title'] else 'Unknown Title'
        release_date = row['release_date']
        date_sh = row['date_sh']
        running_date = row['running_date']
        revenue = float(row['total_revenue'] or 0.0)
        
        if not release_date:
            continue
        
        movie_label = f"{title} ({release_date.isoformat()})"
        movie_title_lookup[movie_label] = title
        
        # Calculate DBR based on running_date
        dbr_value = calculate_dbr(running_date, release_date)
        if dbr_value is not None and dbr_value < 0:
            presales_daily[movie_label][dbr_value] += revenue
        
        # Calculate DIR based on show date (date_sh)
        dir_value = calculate_dir(date_sh, release_date)
        if dir_value in [-1, 1, 2]:
            first_weekend_revenue[movie_label] += revenue
            first_weekend_breakdown[movie_label][dir_value] += revenue
    
    # Convert presales daily totals into cumulative series
    processed_presales = {}
    for movie_label, dbr_totals in presales_daily.items():
        sorted_dbrs = sorted(dbr_totals.keys())
        cumulative = 0.0
        monotonic_data = []
        for dbr_key in sorted_dbrs:
            cumulative += dbr_totals[dbr_key]
            monotonic_data.append((dbr_key, cumulative))
        if monotonic_data:
            processed_presales[movie_label] = monotonic_data
            max_presales[movie_label] = monotonic_data[-1][1]
    
    # Use expected values as fallback if database totals differ significantly
    for movie_label in list(first_weekend_revenue.keys()):
        base_title = movie_title_lookup.get(movie_label, movie_label)
        exp_key = None
        for key in EXPECTED_FIRST_WEEKEND_REVENUE.keys():
            if key.lower() in base_title.lower() or base_title.lower() in key.lower():
                exp_key = key
                break
        
        if not exp_key:
            continue
        
        expected_val = EXPECTED_FIRST_WEEKEND_REVENUE[exp_key]
        db_val = first_weekend_revenue[movie_label]
        
        if db_val > 0 and abs(db_val - expected_val) / expected_val > 0.1:
            print(f"Warning: DB First Weekend Revenue for '{movie_label}' "
                  f"(${db_val:,.2f}) differs from expected (${expected_val:,.2f})")
            print(f"  Using expected value: ${expected_val:,.2f}")
            
            if db_val > 0:
                scale_factor = expected_val / db_val
                breakdown = first_weekend_breakdown[movie_label]
                for dir_val in [-1, 1, 2]:
                    breakdown[dir_val] *= scale_factor
                first_weekend_breakdown[movie_label] = breakdown
            
            first_weekend_revenue[movie_label] = expected_val
    
    # Calculate "Up to First Weekend" totals
    up_to_first_weekend = {}
    all_movie_labels = set(processed_presales.keys()) | set(first_weekend_revenue.keys())
    
    for movie_label in all_movie_labels:
        up_to_first_weekend[movie_label] = first_weekend_revenue.get(movie_label, 0.0)
    
    print(f"Found {len(processed_presales)} movie release(s) with DBR presales data")
    print(f"Found {len(first_weekend_revenue)} movie release(s) with First Weekend Revenue (DIR -1, 1, 2)\n")
    
    # Print summary
    print("="*80)
    print("UP TO FIRST WEEKEND REVENUE SUMMARY")
    print("="*80)
    print("(First Weekend Revenue DIR -1, 1, 2 - matches database/performance table)\n")
    
    for movie_label in sorted(up_to_first_weekend.keys()):
        max_pres = max_presales.get(movie_label, 0.0)
        first_wknd = first_weekend_revenue.get(movie_label, 0.0)
        total = up_to_first_weekend[movie_label]
        
        base_title = movie_title_lookup.get(movie_label, movie_label)
        exp_key = None
        for key in EXPECTED_FIRST_WEEKEND_REVENUE.keys():
            if key.lower() in base_title.lower() or base_title.lower() in key.lower():
                exp_key = key
                break
        expected = EXPECTED_FIRST_WEEKEND_REVENUE.get(exp_key, 0.0) if exp_key else 0.0
        
        print(f"🎬 {movie_label}:")
        if movie_label in processed_presales and processed_presales[movie_label]:
            dbr_range = f"{processed_presales[movie_label][0][0]} to {processed_presales[movie_label][-1][0]}"
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
        
        # Extract DBR values and cumulative revenue (only for existing DBR points)
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
        
        # Create tick marks: include every day for DBR values and actual DIR values present
        dbr_ticks = sorted({x for x in all_x_values if x < 0})
        dir_ticks = sorted({x for x in all_x_values if x >= 0})
        
        all_ticks = dbr_ticks + dir_ticks
        ax.set_xticks(all_ticks)
        
        # Add labels to show DBR/DIR distinction
        tick_labels = []
        for tick in all_ticks:
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
        if not data_points:
            continue
        
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
    # Load and prepare data directly from the database
    data_dict = load_and_prepare_data()
    
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
