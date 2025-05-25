import asyncio
import aiohttp
import time
import statistics
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import List, Dict, Any
import random
from collections import defaultdict, Counter
import traceback

@dataclass
class TestResult:
    method: str
    operation: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    success_rate: float
    throughput: float  # requests per second
    total_time: float
    error_breakdown: Dict[str, int]  # New: error type counts
    timeout_count: int  # New: timeout specific tracking
    connection_errors: int  # New: connection issues

@dataclass
class ErrorReport:
    """Detailed error tracking for debugging"""
    error_type: str
    error_message: str
    timestamp: float
    method: str
    operation: str
    response_time: float
    request_details: Dict[str, Any]

class PerformanceTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[TestResult] = []
        self.error_log: List[ErrorReport] = []  # New: comprehensive error tracking
        self.debug_mode = True  # New: enable detailed debugging
    
    def log_error(self, error_type: str, error_msg: str, method: str, operation: str, 
                  response_time: float, request_details: Dict[str, Any] = None):
        """Log detailed error information for debugging"""
        if self.debug_mode:
            error_report = ErrorReport(
                error_type=error_type,
                error_message=error_msg,
                timestamp=time.time(),
                method=method,
                operation=operation,
                response_time=response_time,
                request_details=request_details or {}
            )
            self.error_log.append(error_report)
            
            # Real-time error logging for immediate feedback
            print(f"⚠️  ERROR [{method}|{operation}]: {error_type} - {error_msg[:100]}...")
    
    async def reset_server(self, session: aiohttp.ClientSession):
        """Reset server state before each test"""
        try:
            timeout = aiohttp.ClientTimeout(total=10)  # 10s timeout
            async with session.post(f"{self.base_url}/reset", timeout=timeout) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    self.log_error("HTTP_ERROR", f"Reset failed with status {response.status}", 
                                 "reset", "server_reset", 0, {"status": response.status})
                    return None
        except asyncio.TimeoutError:
            self.log_error("TIMEOUT", "Reset operation timed out", "reset", "server_reset", 10.0)
            return None
        except Exception as e:
            self.log_error("CONNECTION_ERROR", str(e), "reset", "server_reset", 0, 
                          {"exception_type": type(e).__name__, "traceback": traceback.format_exc()})
            return None
    
    async def buy_ticket(self, session: aiohttp.ClientSession, method: str) -> Dict[str, Any]:
        """Buy a single ticket using specified method"""
        start_time = time.time()
        request_details = {"method": method, "endpoint": f"/buy-ticket/{method}"}
        
        try:
            timeout = aiohttp.ClientTimeout(total=5)  # 5s timeout per request
            async with session.post(f"{self.base_url}/buy-ticket/{method}", timeout=timeout) as response:
                end_time = time.time()
                response_time = end_time - start_time
                
                if response.status != 200:
                    self.log_error("HTTP_ERROR", f"HTTP {response.status}", method, "ticket_buying", 
                                 response_time, {**request_details, "status": response.status})
                    return {
                        "success": False,
                        "response_time": response_time,
                        "error_type": "HTTP_ERROR",
                        "error": f"HTTP {response.status}"
                    }
                
                try:
                    result = await response.json()
                    success = result.get("status") == "success"
                    
                    if not success and self.debug_mode:
                        # Log business logic failures for analysis
                        self.log_error("BUSINESS_LOGIC", result.get("msg", "Unknown business error"), 
                                     method, "ticket_buying", response_time, 
                                     {**request_details, "server_response": result})
                    
                    return {
                        "success": success,
                        "response_time": response_time,
                        "response": result,
                        "error_type": "BUSINESS_LOGIC" if not success else None
                    }
                except json.JSONDecodeError as e:
                    self.log_error("JSON_DECODE", str(e), method, "ticket_buying", response_time, 
                                 {**request_details, "response_text": await response.text()})
                    return {
                        "success": False,
                        "response_time": response_time,
                        "error_type": "JSON_DECODE",
                        "error": str(e)
                    }
                    
        except asyncio.TimeoutError:
            end_time = time.time()
            response_time = end_time - start_time
            self.log_error("TIMEOUT", "Request timed out", method, "ticket_buying", response_time, request_details)
            return {
                "success": False,
                "response_time": response_time,
                "error_type": "TIMEOUT",
                "error": "Request timed out"
            }
        except aiohttp.ClientConnectorError as e:
            end_time = time.time()
            response_time = end_time - start_time
            self.log_error("CONNECTION_ERROR", str(e), method, "ticket_buying", response_time, 
                          {**request_details, "exception_type": type(e).__name__})
            return {
                "success": False,
                "response_time": response_time,
                "error_type": "CONNECTION_ERROR",
                "error": str(e)
            }
        except Exception as e:
            end_time = time.time()
            response_time = end_time - start_time
            self.log_error("UNEXPECTED_ERROR", str(e), method, "ticket_buying", response_time, 
                          {**request_details, "exception_type": type(e).__name__, 
                           "traceback": traceback.format_exc()})
            return {
                "success": False,
                "response_time": response_time,
                "error_type": "UNEXPECTED_ERROR",
                "error": str(e)
            }
    
    async def book_seat(self, session: aiohttp.ClientSession, method: str, row: int, col: int) -> Dict[str, Any]:
        """Book a specific seat using specified method"""
        start_time = time.time()
        request_details = {"method": method, "row": row, "col": col, "endpoint": f"/book-seat/{method}/{row}/{col}"}
        
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with session.post(f"{self.base_url}/book-seat/{method}/{row}/{col}", timeout=timeout) as response:
                end_time = time.time()
                response_time = end_time - start_time
                
                if response.status != 200:
                    self.log_error("HTTP_ERROR", f"HTTP {response.status}", method, "seat_booking", 
                                 response_time, {**request_details, "status": response.status})
                    return {
                        "success": False,
                        "response_time": response_time,
                        "error_type": "HTTP_ERROR",
                        "error": f"HTTP {response.status}"
                    }
                
                try:
                    result = await response.json()
                    success = result.get("status") == "success"
                    
                    if not success and self.debug_mode:
                        self.log_error("BUSINESS_LOGIC", result.get("msg", "Unknown business error"), 
                                     method, "seat_booking", response_time, 
                                     {**request_details, "server_response": result})
                    
                    return {
                        "success": success,
                        "response_time": response_time,
                        "response": result,
                        "error_type": "BUSINESS_LOGIC" if not success else None
                    }
                except json.JSONDecodeError as e:
                    self.log_error("JSON_DECODE", str(e), method, "seat_booking", response_time, 
                                 {**request_details, "response_text": await response.text()})
                    return {
                        "success": False,
                        "response_time": response_time,
                        "error_type": "JSON_DECODE",
                        "error": str(e)
                    }
                    
        except asyncio.TimeoutError:
            end_time = time.time()
            response_time = end_time - start_time
            self.log_error("TIMEOUT", "Request timed out", method, "seat_booking", response_time, request_details)
            return {
                "success": False,
                "response_time": response_time,
                "error_type": "TIMEOUT",
                "error": "Request timed out"
            }
        except aiohttp.ClientConnectorError as e:
            end_time = time.time()
            response_time = end_time - start_time
            self.log_error("CONNECTION_ERROR", str(e), method, "seat_booking", response_time, 
                          {**request_details, "exception_type": type(e).__name__})
            return {
                "success": False,
                "response_time": response_time,
                "error_type": "CONNECTION_ERROR",
                "error": str(e)
            }
        except Exception as e:
            end_time = time.time()
            response_time = end_time - start_time
            self.log_error("UNEXPECTED_ERROR", str(e), method, "seat_booking", response_time, 
                          {**request_details, "exception_type": type(e).__name__, 
                           "traceback": traceback.format_exc()})
            return {
                "success": False,
                "response_time": response_time,
                "error_type": "UNEXPECTED_ERROR", 
                "error": str(e)
            }

    async def test_ticket_buying(self, method: str, num_clients: int, requests_per_client: int):
        """Test ticket buying performance with multiple clients"""
        print(f"\n🎫 Testing ticket buying - Method: {method}, Clients: {num_clients}, Requests/client: {requests_per_client}")
        
        # Clear previous errors for this test
        initial_error_count = len(self.error_log)
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=200)) as session:
            # Reset server
            reset_result = await self.reset_server(session)
            if not reset_result:
                print(f"❌ Failed to reset server for {method} test!")
                return
            
            start_time = time.time()
            tasks = []
            
            # Create tasks for all clients
            for client_id in range(num_clients):
                for request_id in range(requests_per_client):
                    task = self.buy_ticket(session, method)
                    tasks.append(task)
            
            # Execute all requests concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()
            
            # Filter out exceptions and count error types
            valid_results = []
            error_breakdown = defaultdict(int)
            timeout_count = 0
            connection_errors = 0
            
            for result in results:
                if isinstance(result, Exception):
                    self.log_error("ASYNCIO_EXCEPTION", str(result), method, "ticket_buying", 0, 
                                 {"exception_type": type(result).__name__})
                    error_breakdown["ASYNCIO_EXCEPTION"] += 1
                else:
                    valid_results.append(result)
                    if not result["success"]:
                        error_type = result.get("error_type", "UNKNOWN")
                        error_breakdown[error_type] += 1
                        if error_type == "TIMEOUT":
                            timeout_count += 1
                        elif error_type == "CONNECTION_ERROR":
                            connection_errors += 1
            
            # Calculate statistics
            successful = sum(1 for r in valid_results if r["success"])
            failed = len(valid_results) - successful
            response_times = [r["response_time"] for r in valid_results]
            total_time = end_time - start_time
            
            test_result = TestResult(
                method=method,
                operation="ticket_buying",
                total_requests=len(valid_results),
                successful_requests=successful,
                failed_requests=failed,
                avg_response_time=statistics.mean(response_times) if response_times else 0,
                min_response_time=min(response_times) if response_times else 0,
                max_response_time=max(response_times) if response_times else 0,
                success_rate=(successful / len(valid_results)) * 100 if valid_results else 0,
                throughput=len(valid_results) / total_time if total_time > 0 else 0,
                total_time=total_time,
                error_breakdown=dict(error_breakdown),
                timeout_count=timeout_count,
                connection_errors=connection_errors
            )
            
            self.results.append(test_result)
            self.print_test_result(test_result)
            
            # Print error summary for this test
            new_errors = len(self.error_log) - initial_error_count
            if new_errors > 0:
                print(f"🐛 {new_errors} new errors logged during this test")

    async def test_mixed_workload(self, method: str, num_clients: int):
        """Test mixed workload: tickets + seats"""
        print(f"\n🔀 Testing mixed workload - Method: {method}, Clients: {num_clients}")
        
        async with aiohttp.ClientSession() as session:
            await self.reset_server(session)
            
            start_time = time.time()
            tasks = []
            
            for client_id in range(num_clients):
                # Each client does both ticket buying and seat booking
                tasks.append(self.buy_ticket(session, method))
                row = random.randint(0, 9)
                col = random.randint(0, 19)
                tasks.append(self.book_seat(session, method, row, col))
            
            results = await asyncio.gather(*tasks)
            end_time = time.time()
            
            successful = sum(1 for r in results if r["success"])
            failed = len(results) - successful
            response_times = [r["response_time"] for r in results]
            total_time = end_time - start_time
            
            test_result = TestResult(
                method=method,
                operation="mixed_workload",
                total_requests=len(results),
                successful_requests=successful,
                failed_requests=failed,
                avg_response_time=statistics.mean(response_times),
                min_response_time=min(response_times),
                max_response_time=max(response_times),
                success_rate=(successful / len(results)) * 100,
                throughput=len(results) / total_time,
                total_time=total_time,
                error_breakdown=defaultdict(int),
                timeout_count=0,
                connection_errors=0
            )
            
            self.results.append(test_result)
            self.print_test_result(test_result)

    async def test_seat_booking(self, method: str, num_clients: int, requests_per_client: int):
        """Test seat booking performance with multiple clients - strategically fill seats"""
        print(f"\n💺 Testing seat booking - Method: {method}, Clients: {num_clients}, Requests/client: {requests_per_client}")
        print(f"   🎯 Strategy: Filling seats systematically to create contention")
        
        initial_error_count = len(self.error_log)
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=200)) as session:
            # Reset server
            reset_result = await self.reset_server(session)
            if not reset_result:
                print(f"❌ Failed to reset server for {method} test!")
                return
            
            start_time = time.time()
            tasks = []
            
            # Calculate total requests to determine filling strategy
            total_requests = num_clients * requests_per_client
            total_seats = 10 * 20  # 200 seats
            
            if total_requests <= total_seats:
                # Fill seats systematically - front to back, left to right
                print(f"   📋 Systematic filling: {total_requests} requests for {total_seats} seats")
                seat_assignments = []
                for row in range(10):
                    for col in range(20):
                        seat_assignments.append((row, col))
                        if len(seat_assignments) >= total_requests:
                            break
                    if len(seat_assignments) >= total_requests:
                        break
                
                # Distribute seats to clients
                task_index = 0
                for client_id in range(num_clients):
                    for request_id in range(requests_per_client):
                        if task_index < len(seat_assignments):
                            row, col = seat_assignments[task_index]
                            task = self.book_seat(session, method, row, col)
                            tasks.append(task)
                            task_index += 1
            else:
                # More requests than seats - create intentional contention
                print(f"   ⚔️  High contention: {total_requests} requests for {total_seats} seats")
                print(f"   🎲 Using weighted random selection favoring front rows")
                
                # Weight front rows more heavily to create hotspots
                row_weights = [0.3, 0.25, 0.2, 0.15, 0.05, 0.03, 0.015, 0.005, 0.003, 0.002]  # Front rows more popular
                
                for client_id in range(num_clients):
                    for request_id in range(requests_per_client):
                        # Weighted selection for realistic behavior
                        row = random.choices(range(10), weights=row_weights)[0]
                        
                        # For columns, prefer center seats (aisle and middle)
                        if random.random() < 0.6:  # 60% prefer good seats
                            col = random.choice([8, 9, 10, 11])  # Center-ish seats
                        else:
                            col = random.randint(0, 19)  # Any seat
                        
                        task = self.book_seat(session, method, row, col)
                        tasks.append(task)
            
            print(f"   🚀 Launching {len(tasks)} concurrent seat booking requests...")
            
            # Execute all requests concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()
            
            # Process results and count errors
            valid_results = []
            error_breakdown = defaultdict(int)
            timeout_count = 0
            connection_errors = 0
            
            for result in results:
                if isinstance(result, Exception):
                    self.log_error("ASYNCIO_EXCEPTION", str(result), method, "seat_booking", 0,
                                 {"exception_type": type(result).__name__})
                    error_breakdown["ASYNCIO_EXCEPTION"] += 1
                else:
                    valid_results.append(result)
                    if not result["success"]:
                        error_type = result.get("error_type", "UNKNOWN")
                        error_breakdown[error_type] += 1
                        if error_type == "TIMEOUT":
                            timeout_count += 1
                        elif error_type == "CONNECTION_ERROR":
                            connection_errors += 1
            
            # Calculate statistics
            successful = sum(1 for r in valid_results if r["success"])
            failed = len(valid_results) - successful
            response_times = [r["response_time"] for r in valid_results]
            total_time = end_time - start_time
            
            # Calculate seat utilization
            expected_max_seats = min(total_requests, total_seats)
            seat_utilization = (successful / expected_max_seats) * 100 if expected_max_seats > 0 else 0
            
            print(f"   📊 Seat utilization: {successful}/{expected_max_seats} ({seat_utilization:.1f}%)")
            
            test_result = TestResult(
                method=method,
                operation="seat_booking",
                total_requests=len(valid_results),
                successful_requests=successful,
                failed_requests=failed,
                avg_response_time=statistics.mean(response_times) if response_times else 0,
                min_response_time=min(response_times) if response_times else 0,
                max_response_time=max(response_times) if response_times else 0,
                success_rate=(successful / len(valid_results)) * 100 if valid_results else 0,
                throughput=len(valid_results) / total_time if total_time > 0 else 0,
                total_time=total_time,
                error_breakdown=dict(error_breakdown),
                timeout_count=timeout_count,
                connection_errors=connection_errors
            )
            
            self.results.append(test_result)
            self.print_test_result(test_result)
            
            new_errors = len(self.error_log) - initial_error_count
            if new_errors > 0:
                print(f"🐛 {new_errors} new errors logged during this test")
                
            # Additional seat booking analysis
            if successful > 0:
                business_logic_errors = error_breakdown.get("BUSINESS_LOGIC", 0)
                contention_rate = (business_logic_errors / len(valid_results)) * 100
                print(f"   ⚔️  Contention rate: {business_logic_errors} conflicts ({contention_rate:.1f}%)")

    async def test_seat_filling_capacity(self, method: str):
        """Special test to verify we can actually fill all seats"""
        print(f"\n🎯 CAPACITY TEST - Filling all seats with {method}")
        
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=50)) as session:
            await self.reset_server(session)
            
            start_time = time.time()
            tasks = []
            
            # Try to book every single seat
            for row in range(10):
                for col in range(20):
                    task = self.book_seat(session, method, row, col)
                    tasks.append(task)
            
            print(f"   📋 Attempting to book all 200 seats sequentially...")
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()
            
            valid_results = [r for r in results if not isinstance(r, Exception)]
            successful = sum(1 for r in valid_results if r["success"])
            
            print(f"   ✅ Successfully booked: {successful}/200 seats ({successful/200*100:.1f}%)")
            print(f"   ⏱️  Total time: {end_time - start_time:.2f}s")
            
            if successful < 200:
                failed_results = [r for r in valid_results if not r["success"]]
                print(f"   ❌ {len(failed_results)} booking failures detected")

    def print_test_result(self, result: TestResult):
        """Print formatted test result with error details"""
        print(f"📊 Results for {result.method} - {result.operation}:")
        print(f"   Total requests: {result.total_requests}")
        print(f"   Successful: {result.successful_requests} ({result.success_rate:.1f}%)")
        print(f"   Failed: {result.failed_requests}")
        print(f"   Avg response time: {result.avg_response_time*1000:.2f}ms")
        print(f"   Min/Max response time: {result.min_response_time*1000:.2f}ms / {result.max_response_time*1000:.2f}ms")
        print(f"   Throughput: {result.throughput:.2f} requests/second")
        print(f"   Total time: {result.total_time:.2f}s")
        
        # Error breakdown
        if result.error_breakdown:
            print(f"   🚨 Error breakdown:")
            for error_type, count in result.error_breakdown.items():
                print(f"      {error_type}: {count}")
        
        if result.timeout_count > 0:
            print(f"   ⏰ Timeouts: {result.timeout_count}")
        if result.connection_errors > 0:
            print(f"   🔌 Connection errors: {result.connection_errors}")

    def generate_error_analysis(self):
        """Generate comprehensive error analysis report"""
        if not self.error_log:
            print("\n✅ No errors detected during testing!")
            return
            
        print("\n" + "="*80)
        print("🔍 COMPREHENSIVE ERROR ANALYSIS")
        print("="*80)
        
        # Error frequency by type
        error_types = Counter([error.error_type for error in self.error_log])
        print(f"\n📊 Error Types (Total: {len(self.error_log)} errors):")
        for error_type, count in error_types.most_common():
            percentage = (count / len(self.error_log)) * 100
            print(f"   {error_type}: {count} ({percentage:.1f}%)")
        
        # Error frequency by method
        method_errors = Counter([error.method for error in self.error_log])
        print(f"\n🔧 Errors by Synchronization Method:")
        for method, count in method_errors.most_common():
            print(f"   {method}: {count} errors")
        
        # Error frequency by operation
        operation_errors = Counter([error.operation for error in self.error_log])
        print(f"\n⚙️ Errors by Operation:")
        for operation, count in operation_errors.most_common():
            print(f"   {operation}: {count} errors")
        
        # Sample of recent errors for debugging
        print(f"\n🔍 Recent Error Samples (last 10):")
        recent_errors = self.error_log[-10:]
        for i, error in enumerate(recent_errors, 1):
            print(f"   {i}. [{error.method}|{error.operation}] {error.error_type}: {error.error_message[:80]}...")
            if error.request_details:
                print(f"      Details: {error.request_details}")
        
        # Performance impact analysis
        print(f"\n📈 Error Performance Impact:")
        error_response_times = [error.response_time for error in self.error_log if error.response_time > 0]
        if error_response_times:
            avg_error_time = statistics.mean(error_response_times)
            max_error_time = max(error_response_times)
            print(f"   Average error response time: {avg_error_time*1000:.2f}ms")
            print(f"   Maximum error response time: {max_error_time*1000:.2f}ms")

    def generate_report(self):
        """Generate comprehensive performance report"""
        print("\n" + "="*80)
        print("📈 COMPREHENSIVE PERFORMANCE REPORT")
        print("="*80)
        
        # Group results by operation type
        operations = {}
        for result in self.results:
            if result.operation not in operations:
                operations[result.operation] = []
            operations[result.operation].append(result)
        
        for operation, results in operations.items():
            print(f"\n🔍 {operation.upper()} COMPARISON:")
            print("-" * 60)
            
            # Sort by throughput (descending)
            results.sort(key=lambda x: x.throughput, reverse=True)
            
            for i, result in enumerate(results, 1):
                print(f"{i}. {result.method.upper()}")
                print(f"   Success Rate: {result.success_rate:.1f}%")
                print(f"   Throughput: {result.throughput:.2f} req/s")
                print(f"   Avg Response: {result.avg_response_time*1000:.2f}ms")
                print()
        
        # Overall winner analysis
        print("\n🏆 PERFORMANCE WINNERS:")
        print("-" * 40)
        
        best_throughput = max(self.results, key=lambda x: x.throughput)
        best_success_rate = max(self.results, key=lambda x: x.success_rate)
        best_response_time = min(self.results, key=lambda x: x.avg_response_time)
        
        print(f"🚀 Best Throughput: {best_throughput.method} ({best_throughput.operation}) - {best_throughput.throughput:.2f} req/s")
        print(f"✅ Best Success Rate: {best_success_rate.method} ({best_success_rate.operation}) - {best_success_rate.success_rate:.1f}%")
        print(f"⚡ Best Response Time: {best_response_time.method} ({best_response_time.operation}) - {best_response_time.avg_response_time*1000:.2f}ms")
    
    def save_results_to_file(self, filename: str = "performance_results.json"):
        """Save results to JSON file with error details"""
        data = {
            "test_results": [],
            "error_log": [],
            "summary": {
                "total_tests": len(self.results),
                "total_errors": len(self.error_log),
                "error_rate": len(self.error_log) / sum(r.total_requests for r in self.results) * 100 if self.results else 0
            }
        }
        
        # Test results
        for result in self.results:
            data["test_results"].append({
                "method": result.method,
                "operation": result.operation,
                "total_requests": result.total_requests,
                "successful_requests": result.successful_requests,
                "failed_requests": result.failed_requests,
                "avg_response_time_ms": result.avg_response_time * 1000,
                "min_response_time_ms": result.min_response_time * 1000,
                "max_response_time_ms": result.max_response_time * 1000,
                "success_rate_percent": result.success_rate,
                "throughput_rps": result.throughput,
                "total_time_seconds": result.total_time,
                "error_breakdown": result.error_breakdown,
                "timeout_count": result.timeout_count,
                "connection_errors": result.connection_errors
            })
        
        # Error log
        for error in self.error_log:
            data["error_log"].append({
                "error_type": error.error_type,
                "error_message": error.error_message,
                "timestamp": error.timestamp,
                "method": error.method,
                "operation": error.operation,
                "response_time_ms": error.response_time * 1000,
                "request_details": error.request_details
            })
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Detailed results with error analysis saved to {filename}")

async def run_ticket_buying_tests():
    """Run only ticket buying performance tests"""
    tester = PerformanceTester()
    
    print("🎫 Starting Ticket Buying Performance Tests")
    print("=" * 50)
    
    methods = ["mutex", "semaphore", "spinlock"]
    test_scenarios = [
        {"clients": 10, "requests_per_client": 5},   # 50 requests
        {"clients": 20, "requests_per_client": 10},  # 200 requests
        {"clients": 50, "requests_per_client": 2},   # 100 requests
        {"clients": 100, "requests_per_client": 3},  # 300 requests
        {"clients": 200, "requests_per_client": 1},  # 200 requests - stress test
        
    ]
    
    # Test ticket buying only
    for scenario in test_scenarios:
        for method in methods:
            await tester.test_ticket_buying(
                method, 
                scenario["clients"], 
                scenario["requests_per_client"]
            )
            await asyncio.sleep(1)  # Brief pause between tests
    
    # Generate final report
    tester.generate_report()
    tester.generate_error_analysis()
    tester.save_results_to_file("ticket_buying_results.json")

async def run_seat_booking_tests():
    """Run only seat booking performance tests"""
    tester = PerformanceTester()
    
    print("💺 Starting Seat Booking Performance Tests")
    print("=" * 50)
    
    methods = ["mutex", "semaphore", "spinlock"]
    test_scenarios = [
        {"clients": 10, "requests_per_client": 5},   # 50 requests - systematic filling
        {"clients": 20, "requests_per_client": 10},  # 200 requests - exactly fill all seats
        {"clients": 50, "requests_per_client": 2},   # 100 requests - half capacity
        {"clients": 100, "requests_per_client": 3},  # 300 requests - overbook, high contention
        {"clients": 200, "requests_per_client": 1},  # 200 requests - stress test
    ]
    
    # Test seat booking with strategic filling
    for scenario in test_scenarios:
        for method in methods:
            await tester.test_seat_booking(
                method, 
                scenario["clients"], 
                scenario["requests_per_client"]
            )
            await asyncio.sleep(1)
    
    # Capacity tests - can we actually fill all seats?
    print("\n" + "="*60)
    print("🎯 SEAT CAPACITY VERIFICATION TESTS")
    print("="*60)
    
    for method in methods:
        await tester.test_seat_filling_capacity(method)
        await asyncio.sleep(2)
    
    # Generate final report
    tester.generate_report()
    tester.generate_error_analysis()
    tester.save_results_to_file("seat_booking_results.json")

async def run_comprehensive_tests():
    """Run all performance tests"""
    tester = PerformanceTester()
    
    print("🚀 Starting Comprehensive Performance Tests")
    print("=" * 50)
    
    methods = ["mutex", "semaphore", "spinlock"]
    test_scenarios = [
        {"clients": 10, "requests_per_client": 5},   # 50 requests - should fill systematically
        {"clients": 20, "requests_per_client": 10},  # 200 requests - exactly fill all seats
        {"clients": 50, "requests_per_client": 2},   # 100 requests - half capacity
        {"clients": 100, "requests_per_client": 3},  # 300 requests - overbook, high contention
    ]
    
    # Test ticket buying
    print("\n" + "="*60)
    print("🎫 TICKET BUYING TESTS")
    print("="*60)
    for scenario in test_scenarios:
        for method in methods:
            await tester.test_ticket_buying(
                method, 
                scenario["clients"], 
                scenario["requests_per_client"]
            )
            await asyncio.sleep(1)  # Brief pause between tests
    
    # Test seat booking with strategic filling
    print("\n" + "="*60)
    print("💺 SEAT BOOKING TESTS")
    print("="*60)
    for scenario in test_scenarios:
        for method in methods:
            await tester.test_seat_booking(
                method, 
                scenario["clients"], 
                scenario["requests_per_client"]
            )
            await asyncio.sleep(1)
    
    # Capacity tests - can we actually fill all seats?
    print("\n" + "="*60)
    print("🎯 SEAT CAPACITY VERIFICATION TESTS")
    print("="*60)
    
    for method in methods:
        await tester.test_seat_filling_capacity(method)
        await asyncio.sleep(2)
    
    # Test mixed workload
    print("\n" + "="*60)
    print("🔀 MIXED WORKLOAD TESTS")
    print("="*60)
    for clients in [20, 50, 100]:
        for method in methods:
            await tester.test_mixed_workload(method, clients)
            await asyncio.sleep(1)
    
    # Generate final report
    tester.generate_report()
    tester.generate_error_analysis()
    tester.save_results_to_file()

async def run_super_stress_test():
    """Run EXTREME load stress test - 1000 clients with 10 requests each"""
    print("\n💀 SUPER STRESS TEST - EXTREME Load Simulation")
    print("🚨 WARNING: This will hammer your server with 10,000+ requests per method!")
    print("=" * 70)
    
    # Ask for confirmation because this is BRUTAL
    confirm = input("⚠️  Are you sure you want to proceed? This may crash your server! (y/N): ").strip().lower()
    if confirm != 'y':
        print("🛡️  Super stress test cancelled. Probably a wise choice!")
        return
    
    tester = PerformanceTester()
    methods = ["mutex", "semaphore", "spinlock"]
    
    print("🔥 Preparing for MAXIMUM CARNAGE...")
    print("📊 Test configuration:")
    print("   👥 Clients: 1000")
    print("   📋 Requests per client: 10") 
    print("   🎯 Total requests per method: 10,000")
    print("   ⚡ Expected chaos level: MAXIMUM")
    
    # Super extreme load test
    for method in methods:
        print(f"\n💣 SUPER STRESS testing {method} with 1000 clients x 10 requests = 10,000 operations...")
        print(f"🚨 Brace for impact! Testing {method.upper()} synchronization limits...")
        
        # Ticket buying super stress
        print(f"\n🎫 TICKET BUYING CARNAGE - {method}")
        await tester.test_ticket_buying(method, 1000, 10)
        await asyncio.sleep(5)  # Longer pause to let server recover
        
        # Seat booking super stress  
        print(f"\n💺 SEAT BOOKING MASSACRE - {method}")
        await tester.test_seat_booking(method, 1000, 10)
        await asyncio.sleep(5)  # Server recovery time
        
        print(f"✅ {method.upper()} survived the onslaught! (or did it?)")
    
    print("\n🏁 SUPER STRESS TEST COMPLETE!")
    print("🎉 If your server is still alive, congratulations!")
    print("💀 If it crashed... well, that's why we test!")
    
    tester.generate_report()
    tester.generate_error_analysis()
    tester.save_results_to_file("super_stress_test_results.json")

async def run_stress_test():
    """Run high-load stress test"""
    print("\n💥 STRESS TEST - High Load Simulation")
    print("=" * 50)
    
    tester = PerformanceTester()
    methods = ["mutex", "semaphore", "spinlock"]
    
    # Extreme load test
    for method in methods:
        print(f"\n🔥 Stress testing {method} with 200 concurrent clients...")
        await tester.test_ticket_buying(method, 200, 1)
        await asyncio.sleep(2)
        
        await tester.test_seat_booking(method, 200, 1)
        await asyncio.sleep(2)
    
    tester.generate_report()
    tester.save_results_to_file("stress_test_results.json")

if __name__ == "__main__":
    print("🎯 FastAPI Synchronization Performance Tester")
    print("Choose test type:")
    print("1. Ticket Buying Tests Only 🎫")
    print("2. Seat Booking Tests Only 💺")
    print("3. Comprehensive Tests (both) 🚀")
    print("4. Stress Test (high load) 💥")
    print("5. Super Stress Test (EXTREME - 10K requests!) 💀")
    print("6. All Tests (comprehensive + stress + super stress)")
    
    choice = input("Enter choice (1-6): ").strip()
    
    if choice == "1":
        asyncio.run(run_ticket_buying_tests())
    elif choice == "2":
        asyncio.run(run_seat_booking_tests())
    elif choice == "3":
        asyncio.run(run_comprehensive_tests())
    elif choice == "4":
        asyncio.run(run_stress_test())
    elif choice == "5":
        asyncio.run(run_super_stress_test())
    elif choice == "6":
        asyncio.run(run_comprehensive_tests())
        asyncio.run(run_stress_test())
        asyncio.run(run_super_stress_test())
    else:
        print("Invalid choice. Running comprehensive tests...")
        asyncio.run(run_comprehensive_tests())
