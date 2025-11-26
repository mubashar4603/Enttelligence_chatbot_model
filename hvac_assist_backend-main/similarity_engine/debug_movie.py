import csv
import sys

filename = "AI_Data_Dump_with_Growth.csv"
search_title = "2/22: 2025 Best Picture Showcase Day One Marathon"

print(f"Searching for '{search_title}' in {filename}...")

try:
    # Try reading with utf-16 as in the original script
    with open(filename, 'r', encoding='utf-16') as f:
        # It seems the file is tab separated based on the original script
        reader = csv.DictReader(f, delimiter='\t')
        
        found = False
        rows = []
        for row in reader:
            if row['Title'].strip() == search_title:
                found = True
                rows.append(row)
        
        if not found:
            print("Title NOT FOUND in CSV.")
        else:
            print(f"Title FOUND. {len(rows)} rows found.")
            print("Sample data:")
            for i, row in enumerate(rows):
                print(f"Row {i}: DBR={row.get('DBR')}, Sales={row.get('Sales Estimate')}, CumRev={row.get('cumulative_revenue')}")
                
            # Check filtering logic
            # Logic from script:
            # active = group[group['daily_revenue'] > 10] (daily_revenue is Sales Estimate)
            # if len(active) < 3: continue
            # total_rev = group['cumulative_revenue'].max()
            # if total_rev < 100: continue
            
            active_days = 0
            max_rev = 0.0
            
            for row in rows:
                try:
                    daily = float(row.get('Sales Estimate', 0))
                except:
                    daily = 0
                
                try:
                    cum = float(row.get('cumulative_revenue', 0))
                except:
                    cum = 0
                
                if daily > 10:
                    active_days += 1
                
                if cum > max_rev:
                    max_rev = cum
            
            print(f"\nAnalysis:")
            print(f"Active Days (>10 daily rev): {active_days} (Threshold: 3)")
            print(f"Max Cumulative Revenue: {max_rev} (Threshold: 100)")
            
            if active_days < 3:
                print("FAIL: Not enough active days.")
            if max_rev < 100:
                print("FAIL: Total revenue too low.")
                
except Exception as e:
    print(f"Error reading file: {e}")
