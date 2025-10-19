#!/usr/bin/env python3
"""
Quick Test Script for Film Analytics System
Run individual queries to test the system
"""

import requests
import json

def get_auth_token():
    """Get authentication token using admin credentials"""
    login_url = "http://localhost:8000/api/auth/login/"
    login_data = {
        "username": "admin",
        "password": "admin"
    }
    
    try:
        response = requests.post(login_url, json=login_data)
        if response.status_code == 200:
            result = response.json()
            return result.get('access')
        else:
            print(f"Login failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def test_query(query, token):
    """Test a single query"""
    url = "http://localhost:8000/api/chat/chat/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "message": query
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            print(f"✅ SUCCESS")
            print(f"Query: {query}")
            print(f"Response: {json.dumps(result, indent=2)}")
            print("-" * 50)
            return True
        else:
            print(f"❌ FAILED - HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    """Test key queries"""
    print("🎬 Quick Film Analytics System Test")
    print("=" * 40)
    
    # Get authentication token
    print("🔐 Getting authentication token...")
    token = get_auth_token()
    if not token:
        print("❌ Failed to get authentication token")
        return
    
    print("✅ Authentication successful!")
    print()
    
    # Test queries in order of priority
    test_queries = [
        # High Priority Tests
        "What is the total reserved seats for Twisters?",
        "How many theaters are showing Dune: Part Two?", 
        "What is the average ticket price for Twisters?",
        "What are the best comp titles for Twisters?",
        "Compare Twisters vs Dune: Part Two performance",
        
        # Medium Priority Tests
        "Where are the market opportunities for Twisters?",
        "How is Dune: Part Two performing on IMAX screens?",
        "What is the overall occupancy rate for Twisters?",
        "Which states are the top markets for Dune: Part Two?",
        "What are the estimated sales for Twisters this weekend?",
    ]
    
    successful = 0
    total = len(test_queries)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n🧪 Test {i}/{total}")
        if test_query(query, token):
            successful += 1
    
    print(f"\n📊 Results: {successful}/{total} tests passed ({(successful/total)*100:.1f}%)")
    
    if successful == total:
        print("🎉 All tests passed! System is working perfectly.")
    elif successful >= total * 0.8:
        print("👍 Most tests passed! System is working well.")
    else:
        print("⚠️ Several tests failed. Check the system configuration.")

if __name__ == "__main__":
    main()
