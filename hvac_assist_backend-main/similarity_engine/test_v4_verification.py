import movie_similarity_bot_V4 as bot
import sys
import os

# Redirect stdout to capture output
original_stdout = sys.stdout

def run_test(query):
    print(f"\n\nTesting Query: {query}")
    print("-" * 50)
    try:
        result = bot.ask(query)
        # print(result['message'])
    except Exception as e:
        print(f"Error: {e}")

def main():
    # Initialize the system once
    print("Initializing system...")
    if not bot.initialize_system():
        print("Initialization failed!")
        return

    # Test Case 1: The one user asked about (Short run, low revenue)
    run_test("which top 2 movies is similar to 3almashi?")

    # Test Case 2: A known blockbuster (Long run, high revenue)
    # We need to pick a movie that is likely in the DB. 
    # I'll try 'Avatar' or 'Titanic' if they exist, or just pick one from the DB dump I saw earlier.
    # I saw '1 Million Followers' in the CSV head.
    run_test("find similar movies to 1 Million Followers")

    # Test Case 3: Another random one if possible, or just rely on these.
    # Let's try to find a movie with more history if possible.
    # I'll just stick to these two for now to verify the logic holds for different profiles.

if __name__ == "__main__":
    main()
