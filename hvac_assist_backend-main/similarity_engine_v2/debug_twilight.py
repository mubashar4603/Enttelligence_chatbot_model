from similarity_engine_v2.dbr_specific_search import DBRSpecificSimilarity
from similarity_engine_v2.core.data_loader import DataLoader
from similarity_engine_v2.core.preprocessor import MoviePreprocessor
from similarity_engine_v2.core.vector_builder import VectorBuilder
import similarity_engine_v2.config as config

# Force percentage matching
config.ENABLE_PERCENTAGE_MATCHING = True

print("Loading data...")
loader = DataLoader()
df = loader.load()

print("Processing movies...")
preprocessor = MoviePreprocessor(df)
movies_db = preprocessor.process_all_movies()

print("Building vectors...")
builder = VectorBuilder(movies_db)
embeddings, metadata = builder.build_embeddings()

finder = DBRSpecificSimilarity(movies_db, metadata)

movie1 = "Dead Man's Wire"
movie2 = "The Twilight Saga: Breaking Dawn - Part 1 (2011) Fathom Rerelease"

print(f"\nAnalyzing match between:\n1. {movie1}\n2. {movie2}")

# Check if movies exist
if movie1 not in movies_db:
    print(f"❌ '{movie1}' not found in DB")
    exit()
if movie2 not in movies_db:
    print(f"❌ '{movie2}' not found in DB")
    exit()

# Get raw data
data1 = movies_db[movie1]
data2 = movies_db[movie2]

print(f"\n{movie1} DBRs: {len(data1['dbr_list'])}")
print(f"{movie2} DBRs: {len(data2['dbr_list'])}")

# Run find_dbr_specific_matches specifically for this pair
print("\nRunning similarity search...")
results = finder.find_dbr_specific_matches(
    movie1,
    max_growth_diff=1.0,
    min_consecutive_dbrs=2,
    match_mode='percentage'
)

# Check if movie2 is in results
found = False
match_details = None

all_matches = results['high_similarity'] + results['low_similarity']
for m in all_matches:
    if m['similar_movie'] == movie2:
        found = True
        match_details = m
        break

if found:
    print(f"\n✅ FOUND in results!")
    print(f"Match Percentage: {match_details['match_percentage']}%")
    print(f"Total Matching DBRs: {match_details['total_matching_dbrs']}")
    print(f"Matching Ranges: {len(match_details['matching_ranges'])}")
    for r in match_details['matching_ranges']:
        print(f"  - Range: {r['dbr_start']} to {r['dbr_end']} (Count: {r['dbr_count']})")
else:
    print(f"\n❌ NOT FOUND in results")
    
    # Debug WHY it's not found
    print("\nDebugging mismatch...")
    
    # Manually check overlap
    dbrs1 = data1['dbr_list']
    growth1 = data1['growth_raw']
    dbr_growth1 = {d: g for d, g in zip(dbrs1[:-1], growth1)}
    
    dbrs2 = data2['dbr_list']
    growth2 = data2['growth_raw']
    dbr_growth2 = {d: g for d, g in zip(dbrs2[:-1], growth2)}
    
    common_dbrs = sorted(set(dbr_growth1.keys()) & set(dbr_growth2.keys()))
    print(f"Common DBRs: {len(common_dbrs)}")
    
    print("\nChecking specific DBRs:")
    for dbr in common_dbrs:
        g1 = dbr_growth1[dbr]
        g2 = dbr_growth2[dbr]
        diff = abs(g1 - g2)
        match = diff <= 1.0
        marker = "✅" if match else "❌"
        print(f"DBR {dbr}: {movie1}={g1:.2f}%, {movie2}={g2:.2f}%, Diff={diff:.2f}% {marker}")

