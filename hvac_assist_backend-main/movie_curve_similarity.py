import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from scipy.interpolate import interp1d
from scipy.spatial.distance import euclidean
from fastdtw import fastdtw
import faiss
import requests
import warnings
import matplotlib.pyplot as plt
from datetime import datetime
warnings.filterwarnings('ignore')

# Set professional matplotlib style
plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['figure.figsize'] = (14, 8)
plt.rcParams['font.size'] = 10

class MovieComparisonSystem:
    def __init__(self, csv_path, ollama_url="http://localhost:11434"):
        self.csv_path = csv_path
        self.ollama_url = ollama_url
        self.df = None
        self.movie_features = {}
        self.feature_vectors = None
        self.faiss_index = None
        self.movie_names = []

        print("🎬 Initializing Movie Comparison System...")
        self.load_and_process_data()

    def load_and_process_data(self):
        print("📊 Loading data from CSV...")
        self.df = pd.read_csv(self.csv_path)

        required_cols = ['Title', 'DBR', 'Sales Estimate', 'cumulative_revenue']
        for col in required_cols:
            if col not in self.df.columns:
                raise ValueError(f"Missing required column: {col}")

        initial_count = len(self.df)
        self.df = self.df.dropna(subset=required_cols)
        cleaned_count = len(self.df)

        if initial_count > cleaned_count:
            print(f"⚠️  Removed {initial_count - cleaned_count} rows with missing values")

        print(f"✅ Loaded {len(self.df)} rows with {self.df['Title'].nunique()} unique movies")

    def interpolate_missing_dbr(self, movie_df):
        try:
            movie_df = movie_df.sort_values('DBR').copy()
            movie_df = movie_df.drop_duplicates(subset=['DBR'], keep='first')

            min_dbr = movie_df['DBR'].min()
            max_dbr = movie_df['DBR'].max()

            if min_dbr == max_dbr:
                return movie_df

            complete_dbr = np.arange(min_dbr, max_dbr + 1)

            if len(movie_df) > 1:
                f_sales = interp1d(movie_df['DBR'].values,
                                   movie_df['Sales Estimate'].values,
                                   kind='linear', fill_value='extrapolate', bounds_error=False)
                f_cumulative = interp1d(movie_df['DBR'].values,
                                        movie_df['cumulative_revenue'].values,
                                        kind='linear', fill_value='extrapolate', bounds_error=False)

                interpolated_sales = f_sales(complete_dbr)
                interpolated_cumulative = f_cumulative(complete_dbr)
            else:
                interpolated_sales = np.full(len(complete_dbr), movie_df['Sales Estimate'].iloc[0])
                interpolated_cumulative = np.full(len(complete_dbr), movie_df['cumulative_revenue'].iloc[0])

            interpolated_df = pd.DataFrame({
                'Title': movie_df['Title'].iloc[0],
                'DBR': complete_dbr,
                'Sales Estimate': interpolated_sales,
                'cumulative_revenue': interpolated_cumulative
            })

            return interpolated_df

        except Exception as e:
            print(f"⚠️  Error interpolating: {str(e)}")
            return movie_df

    def extract_features(self, movie_df):
        features = {}
        try:
            pre_release = movie_df[movie_df['DBR'] < 0]
            post_release = movie_df[movie_df['DBR'] >= 0]

            features['pre_release_momentum'] = pre_release['Sales Estimate'].mean() if len(pre_release) > 0 else 0
            features['opening_week_perf'] = post_release['Sales Estimate'].mean() if len(post_release) > 0 else 0
            features['total_revenue'] = movie_df['cumulative_revenue'].max()
            features['revenue_velocity'] = features['total_revenue'] / len(movie_df) if len(movie_df) > 0 else 0
            features['peak_sales'] = movie_df['Sales Estimate'].max()

            if len(movie_df) > 0 and movie_df['Sales Estimate'].std() > 0:
                peak_idx = movie_df['Sales Estimate'].idxmax()
                if pd.notna(peak_idx) and peak_idx in movie_df.index:
                    peak_dbr = movie_df.loc[peak_idx, 'DBR']
                    features['days_to_peak'] = (peak_dbr + 50) / 55
                else:
                    features['days_to_peak'] = 0.5
            else:
                features['days_to_peak'] = 0.5

            pre_avg = features['pre_release_momentum']
            post_avg = features['opening_week_perf']
            features['pre_post_ratio'] = pre_avg / post_avg if post_avg > 0 else 0

            if len(movie_df) > 2:
                early_half = movie_df.iloc[:len(movie_df)//2]
                late_half = movie_df.iloc[len(movie_df)//2:]
                early_avg = early_half['Sales Estimate'].mean()
                late_avg = late_half['Sales Estimate'].mean()
                features['growth_rate'] = (late_avg - early_avg) / early_avg if early_avg > 0 else 0
            else:
                features['growth_rate'] = 0

            if len(movie_df) > 1 and movie_df['cumulative_revenue'].std() > 0:
                scaler = MinMaxScaler()
                normalized_cumulative = scaler.fit_transform(
                    movie_df['cumulative_revenue'].values.reshape(-1, 1)
                ).flatten()
                features['curve_area'] = np.trapz(normalized_cumulative)
            else:
                features['curve_area'] = 0

            features['volatility'] = movie_df['Sales Estimate'].std()

            for key in features:
                if not np.isfinite(features[key]):
                    features[key] = 0

        except Exception as e:
            print(f"⚠️  Error extracting features: {str(e)}")
            features = {
                'pre_release_momentum': 0, 'opening_week_perf': 0, 'total_revenue': 0,
                'revenue_velocity': 0, 'peak_sales': 0, 'days_to_peak': 0.5,
                'pre_post_ratio': 0, 'growth_rate': 0, 'curve_area': 0, 'volatility': 0
            }

        return features

    def build_feature_matrix(self):
        print("\n🔧 Building feature matrix...")

        all_features = []
        self.movie_names = []
        failed_movies = []

        unique_movies = self.df['Title'].unique()
        total_movies = len(unique_movies)

        for idx, movie in enumerate(unique_movies):
            if (idx + 1) % 500 == 0:
                print(f"  Processing {idx + 1}/{total_movies} movies...")

            try:
                movie_df = self.df[self.df['Title'] == movie].copy()

                if len(movie_df) < 2:
                    failed_movies.append(movie)
                    continue

                movie_df = self.interpolate_missing_dbr(movie_df)
                features = self.extract_features(movie_df)

                self.movie_features[movie] = {
                    'features': features,
                    'data': movie_df
                }

                feature_vector = [
                    features['pre_release_momentum'], features['opening_week_perf'],
                    features['total_revenue'], features['revenue_velocity'],
                    features['peak_sales'], features['days_to_peak'],
                    features['pre_post_ratio'], features['growth_rate'],
                    features['curve_area'], features['volatility']
                ]

                if not all(np.isfinite(v) for v in feature_vector):
                    failed_movies.append(movie)
                    continue

                all_features.append(feature_vector)
                self.movie_names.append(movie)

            except Exception as e:
                print(f"⚠️  Skipping movie '{movie}': {str(e)}")
                failed_movies.append(movie)
                continue

        if not all_features:
            raise ValueError("No valid movies found!")

        self.feature_vectors = np.array(all_features, dtype='float32')
        scaler = MinMaxScaler()
        self.feature_vectors = scaler.fit_transform(self.feature_vectors).astype('float32')

        print(f"✅ Feature matrix built: {self.feature_vectors.shape}")
        if failed_movies:
            print(f"⚠️  Skipped {len(failed_movies)} movies with insufficient data")

    def build_faiss_index(self):
        print("\n🚀 Building FAISS index...")
        dimension = self.feature_vectors.shape[1]
        self.faiss_index = faiss.IndexFlatL2(dimension)
        self.faiss_index.add(self.feature_vectors)
        print(f"✅ FAISS index built with {self.faiss_index.ntotal} vectors")

    def calculate_dtw_similarity(self, movie1_name, movie2_name):
        """Calculate DTW distance with proper normalization for shape matching"""
        try:
            movie1_data = self.movie_features[movie1_name]['data']
            movie2_data = self.movie_features[movie2_name]['data']

            # Get cumulative revenue curves as numpy arrays
            curve1 = np.array(movie1_data['cumulative_revenue'].values, dtype=float).flatten()
            curve2 = np.array(movie2_data['cumulative_revenue'].values, dtype=float).flatten()

            if len(curve1) == 0 or len(curve2) == 0:
                return float('inf')

            # CRITICAL: Normalize to 0-1 range for SHAPE comparison
            curve1_min = curve1.min()
            curve1_max = curve1.max()
            curve2_min = curve2.min()
            curve2_max = curve2.max()

            # Normalize curves to 0-1 range
            if curve1_max > curve1_min:
                curve1_norm = (curve1 - curve1_min) / (curve1_max - curve1_min)
            else:
                curve1_norm = np.ones_like(curve1) * 0.5

            if curve2_max > curve2_min:
                curve2_norm = (curve2 - curve2_min) / (curve2_max - curve2_min)
            else:
                curve2_norm = np.ones_like(curve2) * 0.5

            # Convert to list for fastdtw (it works better with lists)
            curve1_list = curve1_norm.tolist()
            curve2_list = curve2_norm.tolist()

            # Calculate DTW without radius first for accuracy
            distance, path = fastdtw(curve1_list, curve2_list, dist=euclidean)

            # Normalize by average length
            avg_length = (len(curve1_list) + len(curve2_list)) / 2.0
            normalized_distance = distance / avg_length if avg_length > 0 else float('inf')

            return normalized_distance

        except Exception as e:
            print(f"⚠️  DTW Error for {movie1_name} vs {movie2_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            return float('inf')

    def find_similar_movies(self, movie_name, top_k=5):
        if movie_name not in self.movie_names:
            return f"❌ Movie '{movie_name}' not found in database"

        try:
            movie_idx = self.movie_names.index(movie_name)
            query_vector = self.feature_vectors[movie_idx:movie_idx+1]

            # Get ALL movies for DTW comparison (not just FAISS top-k)
            search_k = len(self.movie_names)
            distances, indices = self.faiss_index.search(query_vector, search_k)

            print(f"\n🔍 Searching for movies similar to '{movie_name}'...")
            print(f"   Comparing with {search_k} movies using DTW curve matching...")

            candidates = []
            successful_dtw = 0
            failed_dtw = 0

            for dist, idx in zip(distances[0], indices[0]):
                candidate_name = self.movie_names[idx]

                if candidate_name == movie_name:
                    continue

                dtw_dist = self.calculate_dtw_similarity(movie_name, candidate_name)

                if not np.isfinite(dtw_dist):
                    failed_dtw += 1
                    continue

                successful_dtw += 1

                # PURE DTW-based ranking for same curve shape
                # Lower DTW = more similar curve shape
                # Use DTW as primary metric (90%) and FAISS as secondary (10%)
                combined_score = 0.1 * (1 / (1 + dist)) + 0.9 * (1 / (1 + dtw_dist))

                candidates.append({
                    'movie': candidate_name,
                    'similarity_score': combined_score,
                    'faiss_distance': float(dist),
                    'dtw_distance': float(dtw_dist)
                })

            print(f"   ✅ Successful DTW: {successful_dtw}, ❌ Failed: {failed_dtw}")

            if not candidates:
                print("   ⚠️  No valid candidates found!")
                return []

            # Sort by DTW distance (lower is better)
            candidates = sorted(candidates, key=lambda x: x['dtw_distance'])

            print(f"   📊 Top {min(top_k, len(candidates))} results by curve similarity:")
            for i, c in enumerate(candidates[:top_k], 1):
                print(f"      {i}. {c['movie']}: DTW={c['dtw_distance']:.4f}, Score={c['similarity_score']:.3f}")
            print()

            return candidates[:top_k]

        except Exception as e:
            print(f"❌ Error in find_similar_movies: {str(e)}")
            return f"❌ Error: {str(e)}"

    def generate_explanation_with_ollama(self, query_movie, similar_movies):
        # CRITICAL FIX: Check if similar_movies is empty or error
        if not similar_movies or isinstance(similar_movies, str):
            return "No similar movies found to analyze."

        try:
            query_features = self.movie_features[query_movie]['features']

            context = f"Query Movie: {query_movie}\n"
            context += f"Total Revenue: ${query_features['total_revenue']:,.0f}\n"
            context += f"Pre-release Momentum: ${query_features['pre_release_momentum']:,.0f}/day\n"
            context += f"Opening Week: ${query_features['opening_week_perf']:,.0f}/day\n\n"

            context += "Similar Movies:\n"
            for i, movie in enumerate(similar_movies, 1):
                movie_name = movie['movie']
                movie_features = self.movie_features[movie_name]['features']
                context += f"{i}. {movie_name} (Similarity: {movie['similarity_score']:.1%})\n"
                context += f"   Revenue: ${movie_features['total_revenue']:,.0f}\n"
                context += f"   Opening: ${movie_features['opening_week_perf']:,.0f}/day\n"

            prompt = f"""You are a movie analyst. Based ONLY on this data, explain why these movies are similar to {query_movie}.

{context}

Write 2-3 sentences explaining the similarity patterns. ONLY use the movies listed above."""

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": "llama3:8b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2}
                },
                timeout=30
            )

            if response.status_code == 200:
                return response.json()['response'].strip()
            else:
                return "Analysis: These movies show similar revenue patterns and performance trends."

        except Exception as e:
            return f"Analysis: These movies show similar revenue patterns. (Ollama unavailable: {str(e)})"

    def chatbot_query(self, query, show_graph=False, save_graph_path=None):
        query_lower = query.lower()

        # Pattern 1: Similar movies
        if "performing like" in query_lower or "similar to" in query_lower:
            movie_name = None

            if "performing like" in query_lower:
                parts = query_lower.split("performing like")
                if len(parts) > 1:
                    movie_name = parts[1].strip().strip('?').strip()
            elif "similar to" in query_lower:
                parts = query_lower.split("similar to")
                if len(parts) > 1:
                    movie_name = parts[1].strip().strip('?').strip()

            if movie_name:
                # Find exact match (case-insensitive)
                matched_movie = None
                for movie in self.movie_names:
                    if movie.lower() == movie_name:
                        matched_movie = movie
                        break

                # Try partial match
                if not matched_movie:
                    for movie in self.movie_names:
                        if movie_name in movie.lower():
                            matched_movie = movie
                            break

                if matched_movie:
                    similar = self.find_similar_movies(matched_movie, top_k=5)

                    if isinstance(similar, str):
                        return similar

                    # CRITICAL CHECK: Verify we got results
                    if not similar or len(similar) == 0:
                        return f"⚠️ No similar movies found for '{matched_movie}'"

                    response = f"🎬 Movies performing like '{matched_movie}':\n\n"
                    for i, movie in enumerate(similar, 1):
                        response += f"{i}. {movie['movie']}\n"
                        response += f"   Similarity: {movie['similarity_score']:.1%}\n"
                        response += f"   DTW Distance: {movie['dtw_distance']:.4f}\n"

                    explanation = self.generate_explanation_with_ollama(matched_movie, similar)
                    response += f"\n💡 Analysis:\n{explanation}"

                    if show_graph and len(similar) > 0:
                        print("\n📊 Generating graph...")
                        self.plot_comparison_graph(matched_movie, similar, save_path=save_graph_path)

                    return response
                else:
                    return f"❌ Movie '{movie_name}' not found"

        # Pattern 2: Compare movies
        elif "compare" in query_lower:
            query_clean = query_lower.replace("compare", "").strip()

            parts = []
            separators = [" with ", " and ", " vs ", " versus "]
            for sep in separators:
                if sep in query_clean:
                    parts = [p.strip().strip('?').strip() for p in query_clean.split(sep) if p.strip()]
                    break

            if len(parts) >= 2:
                movie1_name = parts[0]
                movie2_name = parts[1]

                matched1 = None
                matched2 = None

                for movie in self.movie_names:
                    if movie.lower() == movie1_name:
                        matched1 = movie
                    if movie.lower() == movie2_name:
                        matched2 = movie

                if not matched1:
                    for movie in self.movie_names:
                        if movie1_name in movie.lower():
                            matched1 = movie
                            break

                if not matched2:
                    for movie in self.movie_names:
                        if movie2_name in movie.lower():
                            matched2 = movie
                            break

                if not matched1:
                    return f"❌ Movie '{movie1_name}' not found"
                if not matched2:
                    return f"❌ Movie '{movie2_name}' not found"

                # Calculate similarity
                dtw_dist = self.calculate_dtw_similarity(matched1, matched2)

                idx1 = self.movie_names.index(matched1)
                idx2 = self.movie_names.index(matched2)
                vec1 = self.feature_vectors[idx1]
                vec2 = self.feature_vectors[idx2]
                feature_sim = 1 / (1 + np.linalg.norm(vec1 - vec2))

                features1 = self.movie_features[matched1]['features']
                features2 = self.movie_features[matched2]['features']

                response = f"📊 Comparison: {matched1} vs {matched2}\n\n"
                response += f"Feature Similarity: {feature_sim:.1%}\n"
                response += f"Curve Similarity (DTW): {dtw_dist:.4f} ({'High' if dtw_dist < 5 else 'Medium' if dtw_dist < 10 else 'Low'})\n\n"
                response += f"🎬 {matched1}:\n"
                response += f"  Total Revenue: ${features1['total_revenue']:,.0f}\n"
                response += f"  Opening Week: ${features1['opening_week_perf']:,.0f}/day\n"
                response += f"  Peak Sales: ${features1['peak_sales']:,.0f}\n\n"
                response += f"🎬 {matched2}:\n"
                response += f"  Total Revenue: ${features2['total_revenue']:,.0f}\n"
                response += f"  Opening Week: ${features2['opening_week_perf']:,.0f}/day\n"
                response += f"  Peak Sales: ${features2['peak_sales']:,.0f}\n"

                rev_diff = features1['total_revenue'] - features2['total_revenue']
                response += f"\n📈 Revenue Difference: ${abs(rev_diff):,.0f}\n"
                response += f"Winner: {matched1 if rev_diff > 0 else matched2}\n"

                if show_graph:
                    print("\n📊 Generating comparison graph...")
                    self.plot_direct_comparison(matched1, matched2, save_path=save_graph_path)

                return response

        return "❓ I can help with:\n1. 'Which movie is performing like [movie]?'\n2. 'Compare [movie1] with [movie2]'"

    def compare_curves_visually(self, movie1_name, movie2_name):
        """
        Visual comparison of two movie curves (for debugging)
        """
        if movie1_name not in self.movie_names or movie2_name not in self.movie_names:
            print("❌ One or both movies not found")
            return

        movie1_data = self.movie_features[movie1_name]['data']
        movie2_data = self.movie_features[movie2_name]['data']

        curve1 = np.array(movie1_data['cumulative_revenue'].values, dtype=float)
        curve2 = np.array(movie2_data['cumulative_revenue'].values, dtype=float)

        # Normalize
        curve1_norm = (curve1 - curve1.min()) / (curve1.max() - curve1.min()) if curve1.max() > curve1.min() else curve1
        curve2_norm = (curve2 - curve2.min()) / (curve2.max() - curve2.min()) if curve2.max() > curve2.min() else curve2

        # Calculate DTW
        dtw_dist = self.calculate_dtw_similarity(movie1_name, movie2_name)

        print(f"\n📊 Curve Comparison: {movie1_name} vs {movie2_name}")
        print(f"   {'='*50}")
        print(f"   DTW Distance: {dtw_dist:.6f}")
        print(f"   ")
        print(f"   {movie1_name}:")
        print(f"      Points: {len(curve1)}")
        print(f"      Revenue: ${curve1.min():,.0f} → ${curve1.max():,.0f}")
        print(f"      Growth: {(curve1.max()/curve1.min()):.1f}x")
        print(f"      Normalized shape: {curve1_norm[:5].tolist()} ... {curve1_norm[-3:].tolist()}")
        print(f"   ")
        print(f"   {movie2_name}:")
        print(f"      Points: {len(curve2)}")
        print(f"      Revenue: ${curve2.min():,.0f} → ${curve2.max():,.0f}")
        print(f"      Growth: {(curve2.max()/curve2.min()):.1f}x")
        print(f"      Normalized shape: {curve2_norm[:5].tolist()} ... {curve2_norm[-3:].tolist()}")
        print(f"   ")
        print(f"   Similarity Level:")
        if dtw_dist < 0.05:
            print(f"      🟢 VERY HIGH - Almost identical curves!")
        elif dtw_dist < 0.15:
            print(f"      🟡 HIGH - Very similar growth pattern")
        elif dtw_dist < 0.30:
            print(f"      🟠 MEDIUM - Somewhat similar")
        else:
            print(f"      🔴 LOW - Different curves")
        print(f"   {'='*50}\n")

    def plot_comparison_graph(self, query_movie, similar_movies, save_path=None):
        # Implementation same as before...
        pass

    def plot_direct_comparison(self, movie1_name, movie2_name, save_path=None):
        # Implementation same as before...
        pass

    def run(self):
        self.build_feature_matrix()
        self.build_faiss_index()
        print("\n✅ System ready!")
        print("=" * 60)


# ======================== MAIN ========================
if __name__ == "__main__":
    system = MovieComparisonSystem(csv_path="sample.csv")
    system.run()

    print("\n" + "="*60)
    print("🔬 DETAILED CURVE ANALYSIS")
    print("="*60)

    # Compare Avatar vs Titanic (should be VERY similar)
    print("\n🎯 TEST 1: Avatar vs Titanic (Expected: VERY HIGH similarity)")
    system.compare_curves_visually("Avatar", "Titanic")

    # Compare Avatar vs Scream VI (should be different)
    print("\n🎯 TEST 2: Avatar vs Scream VI (Expected: LOWER similarity)")
    system.compare_curves_visually("Avatar", "Scream VI")

    # Compare Avatar vs M3GAN (should be similar)
    print("\n🎯 TEST 3: Avatar vs M3GAN (Expected: HIGH similarity)")
    system.compare_curves_visually("Avatar", "M3GAN")

    print("\n" + "="*60)
    print("🤖 CHATBOT QUERY TEST")
    print("="*60)

    # Test chatbot
    print("\n📝 Query: Which movie is performing like Avatar?")
    response = system.chatbot_query("Which movie is performing like Avatar?")
    print(response)

    print("\n" + "="*60)
    print("💡 EXPECTED RESULTS:")
    print("   - Avatar vs Titanic should have DTW < 0.05 (VERY similar)")
    print("   - Top similar movie to Avatar should be Titanic")
    print("   - M3GAN should also appear in top results")
    print("="*60)