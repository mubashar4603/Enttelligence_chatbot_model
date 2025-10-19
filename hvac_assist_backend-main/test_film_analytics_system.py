#!/usr/bin/env python3
"""
Comprehensive Test Suite for Intelligent Film Analytics System
Tests 20+ different types of queries with expected responses
"""

import requests
import json
import time
from datetime import datetime
from typing import Dict, List, Any

class FilmAnalyticsTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.api_endpoint = f"{base_url}/api/chat/messages/"
        self.test_results = []
        
    def test_query(self, query: str, expected_type: str = "general") -> Dict[str, Any]:
        """Test a single query and return results"""
        start_time = time.time()
        
        try:
            data = {
                "content": query,
                "conversation": 1
            }
            
            response = requests.post(self.api_endpoint, json=data, timeout=30)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "query": query,
                    "expected_type": expected_type,
                    "status": "success",
                    "response_time": response_time,
                    "response": result,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "query": query,
                    "expected_type": expected_type,
                    "status": "error",
                    "response_time": response_time,
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "timestamp": datetime.now().isoformat()
                }
                
        except requests.exceptions.Timeout:
            return {
                "query": query,
                "expected_type": expected_type,
                "status": "timeout",
                "response_time": time.time() - start_time,
                "error": "Request timeout (>30 seconds)",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "query": query,
                "expected_type": expected_type,
                "status": "error",
                "response_time": time.time() - start_time,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def run_comprehensive_tests(self):
        """Run all test cases"""
        print("🎬 Starting Comprehensive Film Analytics System Tests")
        print("=" * 60)
        
        # Define test cases
        test_cases = [
            # 1. Basic Database Queries
            ("What is the total reserved seats for Twisters?", "basic_database"),
            ("How many theaters are showing Dune: Part Two?", "basic_database"),
            ("What is the average ticket price for Twisters?", "basic_database"),
            ("Show me the top 5 showtimes for Dune: Part Two by reserved seats", "basic_database"),
            ("What is the total revenue for Twisters?", "basic_database"),
            
            # 2. Comparative Analysis Queries
            ("What are the best comp titles for Twisters?", "comparative"),
            ("Compare Twisters vs Dune: Part Two performance", "comparative"),
            ("How is Dune: Part Two performing compared to similar sci-fi movies?", "comparative"),
            ("How are Warner Bros movies performing compared to other studios?", "comparative"),
            
            # 3. Performance Analysis Queries
            ("How is Twisters performing on Thursday compared to comp titles?", "performance"),
            ("Is Dune: Part Two overperforming or underperforming on IMAX screens?", "performance"),
            ("How is Twisters performing in less populated areas?", "performance"),
            ("Is Dune: Part Two overperforming on Thursday?", "performance"),
            
            # 4. Sales & Revenue Queries
            ("What are the estimated sales for Twisters this weekend?", "sales"),
            ("Show me the sales breakdown for Dune: Part Two by format", "sales"),
            ("What is the projected box office for Twisters?", "sales"),
            
            # 5. Market & Opportunity Queries
            ("Where are the market opportunities for Twisters?", "opportunity"),
            ("What are the best showtimes for Dune: Part Two?", "opportunity"),
            ("Which cities are underperforming for Twisters?", "opportunity"),
            ("Where are my opportunities for Dune: Part Two?", "opportunity"),
            
            # 6. Weekend & Drop Analysis
            ("How much will Dune: Part Two drop in its second weekend?", "trend"),
            ("What is the weekend drop prediction for Twisters?", "trend"),
            
            # 7. Format & Screen Analysis
            ("How is Dune: Part Two performing on IMAX screens?", "format"),
            ("What is the best screen format for Twisters?", "format"),
            
            # 8. Geographic Performance
            ("How is Twisters performing in California vs New York?", "geographic"),
            ("Which states are the top markets for Dune: Part Two?", "geographic"),
            
            # 9. Capacity & Occupancy
            ("What is the overall occupancy rate for Twisters?", "capacity"),
            ("Which theaters have the highest capacity utilization for Dune: Part Two?", "capacity"),
            
            # 10. Complex Multi-Parameter Queries
            ("What are the best comp titles for Twisters and how are they performing?", "complex"),
            ("Show me estimated sales for Dune: Part Two and compare with comp titles", "complex"),
            ("How is Twisters overperforming in less populated areas compared to comp titles?", "complex"),
            ("What are the market opportunities for Dune: Part Two and where should I focus?", "complex"),
        ]
        
        # Run tests
        total_tests = len(test_cases)
        successful_tests = 0
        failed_tests = 0
        timeout_tests = 0
        
        for i, (query, query_type) in enumerate(test_cases, 1):
            print(f"\n🧪 Test {i}/{total_tests}: {query_type.upper()}")
            print(f"Query: {query}")
            
            result = self.test_query(query, query_type)
            self.test_results.append(result)
            
            if result["status"] == "success":
                print(f"✅ SUCCESS - Response time: {result['response_time']:.2f}s")
                successful_tests += 1
            elif result["status"] == "timeout":
                print(f"⏰ TIMEOUT - Response time: {result['response_time']:.2f}s")
                timeout_tests += 1
            else:
                print(f"❌ FAILED - {result.get('error', 'Unknown error')}")
                failed_tests += 1
            
            # Add delay between requests to avoid overwhelming the server
            time.sleep(1)
        
        # Print summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total_tests}")
        print(f"✅ Successful: {successful_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⏰ Timeout: {timeout_tests}")
        print(f"Success Rate: {(successful_tests/total_tests)*100:.1f}%")
        
        # Save detailed results
        self.save_results()
        
        return {
            "total": total_tests,
            "successful": successful_tests,
            "failed": failed_tests,
            "timeout": timeout_tests,
            "success_rate": (successful_tests/total_tests)*100
        }
    
    def save_results(self):
        """Save test results to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_results_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump({
                "test_summary": {
                    "timestamp": datetime.now().isoformat(),
                    "total_tests": len(self.test_results),
                    "successful": len([r for r in self.test_results if r["status"] == "success"]),
                    "failed": len([r for r in self.test_results if r["status"] == "error"]),
                    "timeout": len([r for r in self.test_results if r["status"] == "timeout"])
                },
                "detailed_results": self.test_results
            }, f, indent=2)
        
        print(f"\n💾 Detailed results saved to: {filename}")
    
    def test_specific_query(self, query: str):
        """Test a specific query"""
        print(f"🧪 Testing Query: {query}")
        result = self.test_query(query)
        
        if result["status"] == "success":
            print(f"✅ SUCCESS - Response time: {result['response_time']:.2f}s")
            print(f"Response: {json.dumps(result['response'], indent=2)}")
        else:
            print(f"❌ FAILED - {result.get('error', 'Unknown error')}")
        
        return result

def main():
    """Main function to run tests"""
    print("🎬 Film Analytics System Test Suite")
    print("=" * 40)
    
    # Initialize tester
    tester = FilmAnalyticsTester()
    
    # Check if server is running
    try:
        response = requests.get(f"{tester.base_url}/api/", timeout=5)
        if response.status_code == 200:
            print("✅ Server is running and accessible")
        else:
            print("⚠️ Server responded with non-200 status")
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("Please make sure the Django server is running:")
        print("python manage.py runserver 0.0.0.0:8000")
        return
    
    # Run comprehensive tests
    results = tester.run_comprehensive_tests()
    
    # Print final recommendations
    print("\n🎯 RECOMMENDATIONS")
    print("=" * 40)
    
    if results["success_rate"] >= 90:
        print("🎉 EXCELLENT: System is performing very well!")
    elif results["success_rate"] >= 75:
        print("👍 GOOD: System is working well with minor issues")
    elif results["success_rate"] >= 50:
        print("⚠️ FAIR: System needs improvements")
    else:
        print("❌ POOR: System requires significant fixes")
    
    if results["timeout"] > 0:
        print(f"⏰ {results['timeout']} queries timed out - consider optimizing response times")
    
    if results["failed"] > 0:
        print(f"🔧 {results['failed']} queries failed - check error logs for details")

if __name__ == "__main__":
    main()
