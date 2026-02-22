#!/usr/bin/env python3
"""
Test cases to verify MAC scoring algorithm mathematical correctness
"""
import time

def calculate_mac_score(success_count, fail_count, last_success_ts):
    """Copy of the actual function for testing"""
    current_time = int(time.time())
    
    # 1. Success Rate (0-45 points with Failure Rate Acceleration)
    total = success_count + fail_count
    if total > 0:
        failure_rate = fail_count / total
        
        # Soft start: First 5 attempts get minimum 15 points
        if total <= 5:
            success_rate = max(15, (success_count / total) * 40)
        else:
            base_success_rate = (success_count / total) * 40
            
            # Failure Rate Acceleration (only after 10+ attempts)
            if total >= 10:
                # PENALTY: High failure rate (>15%)
                if failure_rate > 0.15:
                    penalty = (failure_rate - 0.15) * 40
                    success_rate = max(0, base_success_rate - penalty)
                # BONUS: Low failure rate (<5%)
                elif failure_rate < 0.05:
                    bonus = min(5, (0.05 - failure_rate) * 100)  # Cap bonus at 5 points
                    success_rate = min(45, base_success_rate + bonus)  # Cap total at 45 points
                # NEUTRAL: Normal failure rate (5-15%)
                else:
                    success_rate = base_success_rate
            else:
                success_rate = base_success_rate
    else:
        success_rate = 25  # Neutral for untested
    
    # 2. Recency (0-40 points, increased from 30)
    if last_success_ts > 0:
        age_hours = (current_time - last_success_ts) / 3600
        if age_hours < 1:
            recency = 40
        elif age_hours < 24:
            recency = 30
        elif age_hours < 168:  # 1 week
            recency = 15
        else:
            recency = 5
    else:
        recency = 0  # Never successful
    
    # 3. Reliability Bonus (0-20 points, unchanged)
    if success_count >= 10:
        reliability = 20
    elif success_count >= 5:
        reliability = 10
    else:
        reliability = 0
    
    return success_rate + recency + reliability


# Test cases
print("=== MAC SCORING ALGORITHM TEST CASES ===\n")

current_time = int(time.time())

# Edge Case 1: Brand new MAC (no history)
print("1. Brand New MAC (0 success, 0 fail):")
score = calculate_mac_score(0, 0, 0)
print(f"   Score: {score}")
print(f"   Expected: 25 (neutral)")
print(f"   ✓ PASS" if score == 25 else f"   ✗ FAIL")
print()

# Edge Case 2: All failures (worst case)
print("2. All Failures (0 success, 10 fail):")
score = calculate_mac_score(0, 10, 0)
print(f"   Score: {score}")
print(f"   Expected: 0 (minimum)")
print(f"   Components: success_rate=0, recency=0, reliability=0")
print()

# Edge Case 3: All successes (best case, recent)
print("3. All Successes Recent (10 success, 0 fail, <1h ago):")
score = calculate_mac_score(10, 0, current_time - 1800)  # 30 min ago
print(f"   Score: {score}")
print(f"   Expected: ~105 (45 + 40 + 20)")
print(f"   Components: success_rate=45, recency=40, reliability=20")
print()

# Edge Case 4: Soft start - first attempt success
print("4. Soft Start - First Success (1 success, 0 fail, recent):")
score = calculate_mac_score(1, 0, current_time - 1800)
print(f"   Score: {score}")
print(f"   Expected: ~80 (40 + 40 + 0)")
print(f"   Note: Soft start gives 40 points for 100% success in first 5 attempts")
print()

# Edge Case 5: Soft start - first attempt failure
print("5. Soft Start - First Failure (0 success, 1 fail, never):")
score = calculate_mac_score(0, 1, 0)
print(f"   Score: {score}")
print(f"   Expected: 15 (soft start minimum)")
print(f"   Components: success_rate=15, recency=0, reliability=0")
print()

# Edge Case 6: High failure rate (>15%)
print("6. High Failure Rate (8 success, 3 fail = 27.3% failure):")
score = calculate_mac_score(8, 3, current_time - 1800)
print(f"   Score: {score}")
failure_rate = 3 / 11
base = (8 / 11) * 40
penalty = (failure_rate - 0.15) * 40
success_rate = max(0, base - penalty)
print(f"   Failure rate: {failure_rate:.1%}")
print(f"   Base success rate: {base:.2f}")
print(f"   Penalty: {penalty:.2f}")
print(f"   Final success_rate: {success_rate:.2f}")
print(f"   Components: success_rate={success_rate:.2f}, recency=40, reliability=0")
print()

# Edge Case 7: Low failure rate (<5%) - bonus
print("7. Low Failure Rate (19 success, 1 fail = 5% failure):")
score = calculate_mac_score(19, 1, current_time - 1800)
print(f"   Score: {score}")
failure_rate = 1 / 20
base = (19 / 20) * 40
bonus = min(5, (0.05 - failure_rate) * 100)
success_rate = min(45, base + bonus)
print(f"   Failure rate: {failure_rate:.1%}")
print(f"   Base success rate: {base:.2f}")
print(f"   Bonus: {bonus:.2f}")
print(f"   Final success_rate: {success_rate:.2f}")
print(f"   Components: success_rate={success_rate:.2f}, recency=40, reliability=20")
print()

# Edge Case 8: Old success (>1 week)
print("8. Old Success (10 success, 0 fail, 2 weeks ago):")
score = calculate_mac_score(10, 0, current_time - (14 * 24 * 3600))
print(f"   Score: {score}")
print(f"   Expected: ~70 (45 + 5 + 20)")
print(f"   Components: success_rate=45, recency=5, reliability=20")
print()

# Edge Case 9: Transition from soft start (5 attempts)
print("9. Soft Start Boundary (5 success, 0 fail, recent):")
score = calculate_mac_score(5, 0, current_time - 1800)
print(f"   Score: {score}")
print(f"   Expected: ~90 (40 + 40 + 10)")
print(f"   Note: At 5 attempts, still in soft start")
print()

# Edge Case 10: Just after soft start (6 attempts)
print("10. After Soft Start (6 success, 0 fail, recent):")
score = calculate_mac_score(6, 0, current_time - 1800)
print(f"   Score: {score}")
print(f"   Expected: ~90 (40 + 40 + 10)")
print(f"   Note: At 6 attempts, out of soft start but not yet in acceleration zone")
print()

# Edge Case 11: Failure acceleration boundary (10 attempts)
print("11. Acceleration Boundary (8 success, 2 fail = 20% failure, recent):")
score = calculate_mac_score(8, 2, current_time - 1800)
print(f"   Score: {score}")
failure_rate = 2 / 10
base = (8 / 10) * 40
penalty = (failure_rate - 0.15) * 40
success_rate = max(0, base - penalty)
print(f"   Failure rate: {failure_rate:.1%}")
print(f"   Penalty kicks in: {penalty:.2f}")
print(f"   Components: success_rate={success_rate:.2f}, recency=40, reliability=0")
print()

# Edge Case 12: Extreme failure rate
print("12. Extreme Failure Rate (1 success, 99 fail = 99% failure):")
score = calculate_mac_score(1, 99, 0)
print(f"   Score: {score}")
failure_rate = 99 / 100
base = (1 / 100) * 40
penalty = (failure_rate - 0.15) * 40
success_rate = max(0, base - penalty)
print(f"   Failure rate: {failure_rate:.1%}")
print(f"   Base: {base:.2f}, Penalty: {penalty:.2f}")
print(f"   Final success_rate: {success_rate:.2f}")
print(f"   Components: success_rate={success_rate:.2f}, recency=0, reliability=0")
print()
