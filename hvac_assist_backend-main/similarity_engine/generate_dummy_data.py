import csv
import random
from datetime import datetime, timedelta

def generate_realistic_growth_curve(dbr_range, peak_revenue_range=(500000, 5000000)):
    """
    Generate a realistic movie revenue growth curve
    Returns cumulative revenue for each DBR
    """
    length = len(dbr_range)
    peak_revenue = random.uniform(*peak_revenue_range)
    
    # Find release day (DBR = 1)
    release_idx = None
    for i, dbr in enumerate(dbr_range):
        if dbr == 1:
            release_idx = i
            break
    
    if release_idx is None:
        release_idx = length // 2  # Fallback
    
    cumulative_revenues = []
    
    for i, dbr in enumerate(dbr_range):
        if dbr < 0:
            # Pre-release: very slow growth (pre-sales)
            progress = (i / release_idx) if release_idx > 0 else 0
            revenue = peak_revenue * 0.05 * progress * random.uniform(0.5, 1.5)
        else:
            # Post-release: exponential decay from peak
            days_after_release = i - release_idx
            decay_rate = random.uniform(0.15, 0.35)
            
            # Peak on opening weekend, then decay
            if days_after_release <= 3:
                multiplier = 1.0 - (days_after_release * 0.1)
            else:
                multiplier = 0.7 * (1 - decay_rate) ** (days_after_release - 3)
            
            daily_revenue = peak_revenue * multiplier * random.uniform(0.7, 1.3)
            
            if cumulative_revenues:
                revenue = cumulative_revenues[-1] + daily_revenue
            else:
                revenue = daily_revenue
        
        cumulative_revenues.append(max(0, revenue))
    
    return cumulative_revenues


def create_similar_curve(base_curve, similarity_factor=0.85):
    """
    Create a similar but not identical curve
    similarity_factor: 0.0 = completely different, 1.0 = identical
    """
    similar_curve = []
    for val in base_curve:
        # Add controlled variation
        variation = random.uniform(1 - (1 - similarity_factor), 1 + (1 - similarity_factor))
        similar_curve.append(val * variation)
    return similar_curve


def generate_dummy_data(input_file, output_file):
    """
    Generate completely random but realistic movie data
    Only takes movie names and metadata from original file
    """
    
    # Read original file to get movie list and metadata
    movies_metadata = []
    
    # Try different encodings
    encodings = ['utf-16', 'utf-16-le', 'utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
    df_loaded = False
    
    for encoding in encodings:
        try:
            with open(input_file, 'r', encoding=encoding) as f:
                # File is tab-delimited
                reader = csv.DictReader(f, delimiter='\t')
                seen_titles = set()
                for row in reader:
                    title = row['Title']
                    if title not in seen_titles:
                        seen_titles.add(title)
                        movies_metadata.append({
                            'Title': title,
                            'studio_name': row.get('studio_name', ''),
                            'genre': row.get('genre', ''),
                            'rating': row.get('rating', ''),
                            'runtime': row.get('runtime', ''),
                            'onsale_date': row.get('onsale_date', ''),
                            'release_date': row.get('release_date', '')
                        })
            df_loaded = True
            print(f"Successfully loaded file with {encoding} encoding")
            break
        except (UnicodeDecodeError, KeyError, Exception) as e:
            movies_metadata = []  # Reset on error
            continue
    
    if not df_loaded:
        print(f"Error: Could not read {input_file} with any encoding")
        return
    
    print(f"Found {len(movies_metadata)} unique movies")
    
    # Define similarity groups for testing
    similarity_groups = [
        {'movies': ['3almashi', '6 Days'], 'overlap_range': (-20, 5)},
        {'movies': ['Venom: The Last Dance', 'Joker: Folie à Deux'], 'overlap_range': (-15, 8)},
        {'movies': ['The Wild Robot', 'Transformers One'], 'overlap_range': (-25, 3)},
    ]
    
    # Pre-generate master curves for similarity groups
    group_master_curves = {}
    for idx, group in enumerate(similarity_groups):
        overlap_start, overlap_end = group['overlap_range']
        overlap_dbrs = list(range(overlap_start, overlap_end + 1))
        master_curve = generate_realistic_growth_curve(overlap_dbrs, peak_revenue_range=(1000000, 8000000))
        group_master_curves[idx] = {
            'dbrs': overlap_dbrs,
            'curve': master_curve,
            'movies': group['movies']
        }
    
    all_rows = []
    
    for movie in movies_metadata:
        title = movie['Title']
        
        # Determine DBR range (random but varied)
        range_type = random.choice(['short', 'medium', 'long'])
        if range_type == 'short':
            start_dbr = random.randint(-15, -5)
            end_dbr = random.randint(3, 7)
        elif range_type == 'medium':
            start_dbr = random.randint(-30, -15)
            end_dbr = random.randint(5, 10)
        else:  # long
            start_dbr = random.randint(-50, -30)
            end_dbr = random.randint(8, 10)
        
        # Check if this movie is part of a similarity group
        movie_group_idx = None
        for idx, group_data in group_master_curves.items():
            if title in group_data['movies']:
                movie_group_idx = idx
                # Adjust DBR range to include overlap
                overlap_start = group_data['dbrs'][0]
                overlap_end = group_data['dbrs'][-1]
                
                # Ensure this movie's range includes the overlap
                if title == group_data['movies'][0]:
                    # First movie: larger range
                    start_dbr = min(start_dbr, overlap_start - random.randint(5, 15))
                    end_dbr = max(end_dbr, overlap_end + random.randint(0, 5))
                else:
                    # Other movies: range is subset or equal
                    start_dbr = overlap_start
                    end_dbr = overlap_end
                break
        
        dbr_range = list(range(start_dbr, end_dbr + 1))
        
        # Generate revenue curve
        if movie_group_idx is not None:
            # This movie is part of a similarity group
            group_data = group_master_curves[movie_group_idx]
            overlap_dbrs = group_data['dbrs']
            master_curve = group_data['curve']
            
            # Generate full curve
            cumulative_revenues = []
            for dbr in dbr_range:
                if dbr in overlap_dbrs:
                    # Use similar curve for overlap
                    idx = overlap_dbrs.index(dbr)
                    base_val = master_curve[idx]
                    # Add slight variation (85-95% similarity)
                    similar_val = base_val * random.uniform(0.90, 1.10)
                    cumulative_revenues.append(similar_val)
                else:
                    # Generate random for non-overlap
                    if cumulative_revenues:
                        daily_growth = random.uniform(10000, 200000)
                        cumulative_revenues.append(cumulative_revenues[-1] + daily_growth)
                    else:
                        cumulative_revenues.append(random.uniform(1000, 50000))
        else:
            # Regular movie: completely random realistic curve
            cumulative_revenues = generate_realistic_growth_curve(dbr_range)
        
        # Generate rows for each DBR
        for i, dbr in enumerate(dbr_range):
            cumulative_revenue = cumulative_revenues[i]
            
            # Calculate daily sales and growth
            if i > 0:
                sales_estimate = cumulative_revenue - cumulative_revenues[i-1]
                if cumulative_revenues[i-1] > 0:
                    growth_percent = (sales_estimate / cumulative_revenues[i-1]) * 100
                else:
                    growth_percent = 0
            else:
                sales_estimate = cumulative_revenue
                growth_percent = 0
            
            row = {
                'Title': title,
                'DBR': dbr,
                'Sales Estimate': round(sales_estimate, 2),
                'Growth (%)': round(growth_percent, 2),
                'studio_name': movie['studio_name'],
                'genre': movie['genre'],
                'rating': movie['rating'],
                'runtime': movie['runtime'],
                'onsale_date': movie['onsale_date'],
                'release_date': movie['release_date'],
                'Running Date': 0,
                'Reserved': 0,
                'cumulative_revenue': round(cumulative_revenue, 2)
            }
            all_rows.append(row)
    
    # Write to CSV
    fieldnames = ['Title', 'DBR', 'Sales Estimate', 'Growth (%)', 'studio_name', 'genre', 
                  'rating', 'runtime', 'onsale_date', 'release_date', 'Running Date', 
                  'Reserved', 'cumulative_revenue']
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    
    print(f"✓ Generated dummy data saved to {output_file}")
    print(f"✓ Total rows: {len(all_rows)}")
    print(f"✓ Total movies: {len(movies_metadata)}")
    print(f"\nSimilarity groups created:")
    for idx, group_data in group_master_curves.items():
        print(f"  - {' vs '.join(group_data['movies'])}")


if __name__ == "__main__":
    input_csv = "AI_Data_Dump_with_Growth.csv"
    output_csv = "Dummy_Data_with_Growth.csv"
    generate_dummy_data(input_csv, output_csv)
