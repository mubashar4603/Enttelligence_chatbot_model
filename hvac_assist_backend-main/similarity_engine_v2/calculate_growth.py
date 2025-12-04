import pandas as pd
import numpy as np

def calculate_growth(input_file, output_file):
    """
    Calculate growth percentage based on cumulative sales estimate.
    Growth (%) = ((Today's Cumulative Value - Yesterday's Cumulative Value) / Yesterday's Cumulative Value) * 100
    
    Args:
        input_file (str): Path to input CSV file
        output_file (str): Path to output CSV file
    """
    # Read the CSV file with UTF-16 encoding (based on the file format)
    try:
        df = pd.read_csv(input_file, encoding='utf-16le', sep='\t')
    except:
        # Try UTF-8 if UTF-16 fails
        df = pd.read_csv(input_file, encoding='utf-8')
    
    # Clean column names (remove extra spaces)
    df.columns = df.columns.str.strip()
    
    # Convert 'Cuml. Sales Estimate' to numeric, removing commas and quotes
    df['Cuml. Sales Estimate'] = df['Cuml. Sales Estimate'].astype(str).str.replace(',', '').str.replace('"', '')
    df['Cuml. Sales Estimate'] = pd.to_numeric(df['Cuml. Sales Estimate'], errors='coerce')
    
    # Sort by Title and DBR to ensure proper order
    df = df.sort_values(['Title', 'DBR']).reset_index(drop=True)
    
    # Initialize Growth column
    df['Growth (%)'] = np.nan
    
    # Calculate growth for each movie
    for title in df['Title'].unique():
        # Get indices for this movie
        movie_indices = df[df['Title'] == title].index.tolist()
        
        # Calculate growth for each row (except the first one for each movie)
        for i in range(len(movie_indices)):
            current_idx = movie_indices[i]
            
            if i == 0:
                # First row for this movie - no previous value to compare
                df.loc[current_idx, 'Growth (%)'] = 0
            else:
                previous_idx = movie_indices[i - 1]
                
                # Get cumulative values
                current_cumulative = df.loc[current_idx, 'Cuml. Sales Estimate']
                previous_cumulative = df.loc[previous_idx, 'Cuml. Sales Estimate']
                
                # Calculate growth percentage
                # Treat very small values (< 0.01) as effectively zero to avoid astronomical percentages
                if pd.notna(previous_cumulative) and previous_cumulative >= 0.01:
                    growth = ((current_cumulative - previous_cumulative) / previous_cumulative) * 100
                    df.loc[current_idx, 'Growth (%)'] = round(growth, 2)
                else:
                    df.loc[current_idx, 'Growth (%)'] = 0
    
    # Save to new file
    df.to_csv(output_file, index=False, encoding='utf-8')
    print(f"✓ Growth calculation completed!")
    print(f"✓ New file saved: {output_file}")
    print(f"✓ Total rows processed: {len(df)}")
    print(f"✓ Total movies: {df['Title'].nunique()}")
    
    # Show sample data
    print("\n--- Sample data with Growth (%) ---")
    sample = df[df['Growth (%)'].notna()].head(10)[['Title', 'DBR', 'Cuml. Sales Estimate', 'Growth (%)']]
    print(sample.to_string(index=False))

if __name__ == "__main__":
    # Input and output file paths
    input_file = "AI_Data_Dump_1203.csv"
    output_file = "AI_Data_Dump_1203_with_Growth.csv"
    
    # Calculate growth
    calculate_growth(input_file, output_file)
