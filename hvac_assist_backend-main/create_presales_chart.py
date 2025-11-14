"""
Script to create a cumulative presales chart by querying the MovieDailyPerformance table.

X-Axis: DBR (Days Before Release) - uses full available DBR range for each movie
Y-Axis: Cumulative Revenue

Usage:
    python3 create_presales_chart.py Twisters "Dune: Part Two"
    python3 create_presales_chart.py --movies-list "Twisters" "Dune: Part Two"
    python3 create_presales_chart.py -m "Twisters" "Homestead"
    python3 create_presales_chart.py  # (will prompt before plotting all movies)
"""

import os
import sys
import argparse
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

# Configure Django settings so we can query the MovieDailyPerformance table
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

from movies.models import MovieDailyPerformance

# DBR values are already calculated in MovieDailyPerformance table
# No need for calculation functions


def load_and_prepare_data(movie_titles=None):
    """
    Query the MovieDailyPerformance table and prepare data for charting.
    Uses pre-calculated DBR values and cumulative revenue.
    
    Args:
        movie_titles: Optional list of movie titles to filter. If None, loads all movies.
                     Titles are matched case-insensitively and partially.
    
    Returns:
        Dictionary: {
            'presales': {movie_label: [(dbr_value, cumulative_revenue), ...]},
            'first_weekend': {movie_label: total_revenue},
            'up_to_first_weekend': {movie_label: total_revenue}
        }
    """
    if movie_titles:
        print(f"Loading data from MovieDailyPerformance table for: {', '.join(movie_titles)}...")
    else:
        print("Loading data from MovieDailyPerformance table for all movies...")
    
    try:
        # Query MovieDailyPerformance - get all DBR data (both negative and positive)
        # DBR can be negative (before release) or positive (after release)
        queryset = (
            MovieDailyPerformance.objects
            .filter(
                dbr_value__isnull=False  # Include both negative and positive DBR values
            )
        )
        
        # Filter by movie titles if provided
        if movie_titles:
            from django.db.models import Q
            # Build case-insensitive partial match query
            title_filters = Q()
            for title in movie_titles:
                title_filters |= Q(title__icontains=title.strip())
            queryset = queryset.filter(title_filters)
        
        queryset = queryset.values('title', 'release_date', 'dbr_value', 'cumulative_revenue', 'total_revenue')
        queryset = queryset.order_by('title', 'release_date', 'dbr_value')  # Sort by DBR ascending (most negative to most positive)
        
    except OperationalError as exc:
        raise SystemExit(f"Error querying MovieDailyPerformance table: {exc}") from exc
    
    # Group by movie and DBR to get cumulative revenue
    presales_data = defaultdict(dict)  # {movie_label: {dbr_value: cumulative_revenue}}
    movie_title_lookup = {}
    
    for row in queryset:
        title = row['title'].strip() if row['title'] else 'Unknown Title'
        release_date = row['release_date']
        dbr_value = row['dbr_value']
        cumulative_revenue = float(row['cumulative_revenue'] or 0.0)
        
        if not release_date or dbr_value is None:
            continue
        
        movie_label = f"{title} ({release_date.isoformat()})"
        movie_title_lookup[movie_label] = title
        
        # Store cumulative revenue for this DBR value
        # If multiple records exist for same DBR, use the maximum (most recent)
        if dbr_value not in presales_data[movie_label] or cumulative_revenue > presales_data[movie_label][dbr_value]:
            presales_data[movie_label][dbr_value] = cumulative_revenue
    
    # Convert to sorted list format: [(dbr_value, cumulative_revenue), ...]
    processed_presales = {}
    max_presales = defaultdict(float)
    
    for movie_label, dbr_dict in presales_data.items():
        # Sort by DBR ascending (most negative to most positive: -60, -59, ..., -1, 0, 1, 2, ...)
        sorted_dbrs = sorted(dbr_dict.keys())
        monotonic_data = [(dbr, dbr_dict[dbr]) for dbr in sorted_dbrs]
        
        if monotonic_data:
            processed_presales[movie_label] = monotonic_data
            max_presales[movie_label] = monotonic_data[-1][1]  # Final cumulative value
    
    # For first weekend, we can optionally query DIR values if needed
    # But since we're focusing on DBR only, we'll set first_weekend to empty
    first_weekend_revenue = defaultdict(float)
    first_weekend_breakdown = defaultdict(lambda: {-1: 0.0, 1: 0.0, 2: 0.0})
    
    # Calculate "Up to First Weekend" totals (using final presales cumulative)
    up_to_first_weekend = {}
    all_movie_labels = set(processed_presales.keys())
    
    for movie_label in all_movie_labels:
        # Use final cumulative presales as "up to first weekend" (DBR only)
        up_to_first_weekend[movie_label] = max_presales.get(movie_label, 0.0)
    
    print(f"Found {len(processed_presales)} movie release(s) with DBR presales data\n")
    
    # Print summary
    print("="*80)
    print("CUMULATIVE PRESALES SUMMARY (DBR ONLY)")
    print("="*80)
    print("(Using MovieDailyPerformance table - DBR values only)\n")
    
    for movie_label in sorted(up_to_first_weekend.keys()):
        max_pres = max_presales.get(movie_label, 0.0)
        total = up_to_first_weekend[movie_label]
        
        print(f"🎬 {movie_label}:")
        if movie_label in processed_presales and processed_presales[movie_label]:
            dbr_range = f"{processed_presales[movie_label][0][0]} to {processed_presales[movie_label][-1][0]}"
            print(f"   DBR Range: {dbr_range}")
            print(f"   Final Cumulative Presales: ${max_pres/1_000_000:.2f}M")
        else:
            print(f"   Final Cumulative Presales: ${max_pres/1_000_000:.2f}M")
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
    Create a line chart showing cumulative presales by DBR.
    X-axis: DBR values (presales) from max negative to -1 (each movie uses its full available range)
    Y-axis: Cumulative revenue
    
    Args:
        data_dict: Dictionary with 'presales', 'up_to_first_weekend', 'max_presales'
        output_file: Output filename for the chart
    """
    print("\nCreating chart...")
    
    movie_data = data_dict['presales']
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
        
        all_x_values.extend(dbr_values)
        
        # Plot line with markers
        ax.plot(
            dbr_values,
            cumulative_revenue_millions,
            marker='o',
            linewidth=2,
            markersize=6,
            label=movie,
            color=colors[idx]
        )
        
        # Add annotation for final cumulative presales at last DBR point
        if dbr_values and cumulative_revenue_millions:
            last_dbr = dbr_values[-1]
            ax.annotate(
                f'Final: ${final_presales:.1f}M',
                xy=(last_dbr, final_presales),
                xytext=(10, 10),
                textcoords='offset points',
                fontsize=8,
                bbox=dict(boxstyle='round,pad=0.3', facecolor=colors[idx], alpha=0.3),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0')
            )
    
    # Customize chart
    ax.set_title('Cumulative Revenue by DBR (Days Before/After Release)', fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('Days Before/After Release (DBR)', fontsize=12)
    ax.set_ylabel('Cumulative Revenue (Millions)', fontsize=12)
    
    # Set X-axis ticks - include both negative and positive DBR values
    if all_x_values:
        x_min = min(all_x_values)
        x_max = max(all_x_values)
        
        # Create tick marks: include all DBR values (negative and positive)
        all_dbr_ticks = sorted(set(all_x_values))
        
        # Show every Nth tick to avoid overcrowding (more ticks for wider ranges)
        tick_interval = max(1, len(all_dbr_ticks) // 30)  # Show up to 30 ticks
        if tick_interval > 1:
            dbr_ticks = [all_dbr_ticks[i] for i in range(0, len(all_dbr_ticks), tick_interval)]
            # Always include min, max, and 0 if present
            if x_min not in dbr_ticks:
                dbr_ticks.insert(0, x_min)
            if x_max not in dbr_ticks:
                dbr_ticks.append(x_max)
            if 0 in all_dbr_ticks and 0 not in dbr_ticks:
                dbr_ticks.append(0)
            dbr_ticks = sorted(dbr_ticks)
        else:
            dbr_ticks = all_dbr_ticks
        
        ax.set_xticks(dbr_ticks)
        
        # Add labels with DBR prefix
        tick_labels = []
        for tick in dbr_ticks:
            if tick < 0:
                tick_labels.append(f'DBR {tick}')
            elif tick == 0:
                tick_labels.append('Release\n(DBR 0)')
            else:
                tick_labels.append(f'DBR +{tick}')
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')
        
        # Add vertical line at x=0 to mark release date
        ax.axvline(x=0, color='gray', linestyle='--', linewidth=1, alpha=0.5, label='Release Date')
        
        # Set x-axis limits with some padding
        ax.set_xlim(x_min - 2, x_max + 2)
    
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
        
        # Get final cumulative presales
        max_pres = max_presales.get(movie, 0.0) / 1_000_000
        total_up_to_weekend = max_pres
        
        print(f"\n🎬 {movie}")
        print(f"   DBR Range: {dbr_min} to {dbr_max} ({abs(dbr_max - dbr_min)} days)")
        print(f"   Initial Cumulative Presales: ${initial_cumulative:.2f}M")
        print(f"   Final Cumulative Presales: ${final_cumulative:.2f}M")
        print(f"   Presales Growth: ${total_growth:.2f}M ({growth_rate:.1f}% increase)")
        print(f"   Pattern: {pattern}")
        if early_growth > 0 or mid_growth > 0 or late_growth > 0:
            print(f"   - Early Period Growth: ${early_growth:.2f}M")
            print(f"   - Mid Period Growth: ${mid_growth:.2f}M")
            print(f"   - Late Period Growth: ${late_growth:.2f}M")

def main():
    """Main function to run the script."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Create cumulative presales chart from MovieDailyPerformance table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Plot specific movies (positional arguments)
  python3 create_presales_chart.py Twisters "Dune: Part Two"
  
  # Plot using --movies-list flag (better for titles with spaces)
  python3 create_presales_chart.py --movies-list "Twisters" "Dune: Part Two" "Joker: Folie a Deux"
  
  # Plot using short flag
  python3 create_presales_chart.py -m "Twisters" "Homestead"
  
  # Custom output filename
  python3 create_presales_chart.py Twisters Dune -o my_chart.png
  
  # Plot all movies (if no arguments provided - will prompt for confirmation)
  python3 create_presales_chart.py
        """
    )
    parser.add_argument(
        'movies',
        nargs='*',
        help='Movie titles to plot (case-insensitive partial match). If not provided, plots all movies.',
        metavar='TITLE'
    )
    parser.add_argument(
        '-m', '--movies-list',
        dest='movies_list',
        nargs='+',
        help='Alternative way to specify movies (use this if movie titles contain spaces)',
        metavar='TITLE'
    )
    parser.add_argument(
        '--output',
        '-o',
        default='cumulative_presales_chart.png',
        help='Output filename for the chart (default: cumulative_presales_chart.png)',
        metavar='FILE'
    )
    
    args = parser.parse_args()
    
    # Get movie titles from arguments (prefer --movies-list, fallback to positional)
    movie_titles = args.movies_list if args.movies_list else (args.movies if args.movies else None)
    
    if movie_titles:
        print(f"📊 Plotting charts for {len(movie_titles)} movie(s): {', '.join(movie_titles)}\n")
    else:
        print("📊 Plotting charts for all movies in database\n")
        response = input("⚠️  This may take a while and create a cluttered chart. Continue? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled. Specify movies to plot:")
            print("  python3 create_presales_chart.py Twisters 'Dune: Part Two'")
            print("  python3 create_presales_chart.py --movies-list 'Twisters' 'Dune: Part Two'")
            return
    
    # Load and prepare data directly from the database
    data_dict = load_and_prepare_data(movie_titles)
    
    if not data_dict['presales']:
        if movie_titles:
            print(f"❌ No data found for the specified movies: {', '.join(movie_titles)}")
            print("💡 Tip: Try using partial movie titles (case-insensitive)")
        else:
            print("❌ No data found with DBR values!")
        return
    
    # Show which movies were actually found
    found_movies = list(data_dict['presales'].keys())
    if movie_titles and len(found_movies) < len(movie_titles):
        print(f"\n⚠️  Warning: Only found {len(found_movies)} movie(s) matching your criteria:")
        for movie in found_movies:
            print(f"   - {movie}")
        print()
    
    # Analyze trends
    analyze_trends(data_dict)
    
    # Create chart
    try:
        create_cumulative_presales_chart(data_dict, output_file=args.output)
        print(f"\n✅ Chart saved successfully to: {args.output}")
    except ImportError:
        print("\n❌ Error: matplotlib is not installed.")
        print("Install it with: pip install matplotlib")
    except Exception as e:
        print(f"\n❌ Error creating chart: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
