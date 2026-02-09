# MacAttack.pyw Compatible Mode - Quick Reference

## 🔴 Compatible Mode ON (Fast, Like MacAttack.pyw)

### Behavior
```
Portal returns no token → MAC is INVALID → Stop, next MAC
```

### Characteristics
- ✅ **Faster** - No retries, moves to next MAC immediately
- ❌ **Higher false negatives** - Valid MACs might be missed
- ✅ **Identical to MacAttack.pyw** - Same behavior as original

### When to Use
- You have **reliable, fast proxies**
- You want **speed over accuracy**
- You're okay with **missing some valid MACs**
- You want **MacAttack.pyw behavior**

### Example
```
Scenario: Proxy times out before portal responds
Result: MAC marked invalid ❌ (might be false negative)
```

---

## 🟢 Compatible Mode OFF (Accurate, Intelligent - DEFAULT)

### Behavior
```
Portal returns no token → Analyze WHY
├─ Proxy issue (timeout, connection error) → Retry with different proxy
├─ Portal block (403, captcha) → Retry with different proxy  
└─ Portal says invalid → MAC is INVALID → Stop, next MAC
```

### Characteristics
- ✅ **Higher accuracy** - Finds more valid MACs
- ✅ **Fewer false negatives** - Retries on proxy issues
- ❌ **Slower** - More retries with different proxies
- ✅ **Intelligent** - Analyzes response to decide retry vs invalid

### When to Use
- You want **maximum accuracy**
- Your proxies might be **unreliable**
- You don't want to **miss valid MACs**
- You're okay with **slower scanning**

### Example
```
Scenario: Proxy times out before portal responds
Result: Retry with faster proxy → MAC found valid ✅
```

---

## 📊 Comparison

| Aspect | Compatible ON | Compatible OFF |
|--------|---------------|----------------|
| **Speed** | ⚡ Fast | 🐢 Slower |
| **Accuracy** | ⚠️ Lower | ✅ Higher |
| **False Negatives** | ⚠️ More | ✅ Fewer |
| **Proxy Retries** | ❌ No | ✅ Yes |
| **Behavior** | MacAttack.pyw | Intelligent |
| **Best For** | Speed | Accuracy |

---

## 🎯 Recommendation

### Default: Compatible Mode OFF
- Better accuracy
- Finds more valid MACs
- Handles unreliable proxies better

### Use Compatible Mode ON when:
- You trust your proxies 100%
- Speed is more important than accuracy
- You want exact MacAttack.pyw behavior

---

## 💡 Pro Tip

Combine with presets for best results:

### For Maximum Hits
```
Preset: Max Accuracy
Compatible Mode: OFF
Result: Slowest but finds the most valid MACs
```

### For Fast Scanning
```
Preset: Fast Scan
Compatible Mode: ON
Result: Fastest but might miss some valid MACs
```

### For Balanced
```
Preset: Balanced
Compatible Mode: OFF
Result: Good balance of speed and accuracy
```
