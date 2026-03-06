# MACstrom vs MacReplayXC: Comprehensive Comparison

**Analysis Date:** 2026-03-06  
**MacReplayXC Version:** v4.2.0  
**MACstrom Version:** v0.7.9

---

## Executive Summary

Both projects solve the same core problem: discovering working MAC addresses on IPTV portals and serving streams to consumers. However, they take fundamentally different architectural approaches.

| Aspect | MacReplayXC | MACstrom |
|--------|-------------|----------|
| **Language** | Python (Flask) | Rust (Axum + Leptos) |
| **Architecture** | Monolithic Flask app | Modular Rust workspace |
| **MAC Discovery** | Manual import + validation | Thompson Sampling scanner |
| **Streaming** | Direct proxy/FFmpeg modes | Shared upstream + burst buffer |
| **Frontend** | Jinja2 templates + jQuery | Leptos WASM (zero JavaScript) |
| **Concurrency** | Threading + async | Tokio async runtime |
| **Memory Safety** | Runtime errors possible | Compile-time guarantees |
| **Deployment** | Docker (Python + FFmpeg) | Docker (static Rust binary) |

---

## 1. Core Architecture

### 1.1 Language & Runtime

**MacReplayXC (Python):**
- Flask web framework with Jinja2 templating
- Threading for background tasks (token refresh, watchdog)
- Mixed sync/async code (requests + aiohttp)
- Runtime type checking, potential for exceptions
- Interpreted language with GIL limitations

**MACstrom (Rust):**
- Axum web framework with Leptos fullstack UI
- Tokio async runtime (multi-threaded work-stealing)
- Pure async throughout (reqwest + hickory-dns)
- Compile-time type safety, zero-cost abstractions
- Native compiled binary with jemalloc allocator
- Zero JavaScript - entire frontend compiles to WASM

**Winner:** MACstrom for performance, memory safety, and type guarantees. MacReplayXC for rapid prototyping and Python ecosystem.

---

### 1.2 MAC Discovery Strategy

**MacReplayXC:**
- **Manual import** - users provide MAC lists
- **Validation** - tests MACs against portals
- **No automatic discovery** - relies on external sources
- **Simple approach** - straightforward but requires external MAC sources

**MACstrom:**
- **Thompson Sampling** - intelligent exploration/exploitation
- **Hierarchical block tree** - 6-level spatial partitioning (256³ space)
- **Neighborhood expansion** - spatial + linear BFS around hits
- **Persistent learning** - saves tree state with temporal decay
- **Global prior** - cross-portal learning with kappa scaling
- **Manual injection** - tested MACs feed back into learning tree
- **Prefix-aware families** - auto-clones portals for different MAC prefixes

**Winner:** MACstrom by far. Thompson Sampling is a sophisticated ML approach that discovers MACs autonomously. MacReplayXC requires manual MAC sourcing.

---

### 1.3 MAC Pool Management

**MacReplayXC:**
- **Simple scoring** - success/fail counters with soft-start
- **Basic state tracking** - available/busy/cooldown
- **Channel-level learning** - tracks which MACs work for which channels
- **Watchdog polling** - detects external usage via getProfile()
- **Thread-safe** - uses locks for concurrent access
- **Persistent scores** - saved to JSON files

**MACstrom:**
- **5-state FSM** - Available/Scan/Stream/Validate/Cooldown
- **Composite scoring** - success rate + recency + reliability + consecutive penalty
- **Watchdog penalty** - soft deprioritization (-20 score) for busy MACs
- **Channel bonus** - +10 for proven channels, -5 for failures, 0 for unknown
- **Atomic allocation** - lock-free DashMap for concurrent access
- **Persistent scores** - JSON with per-portal isolation
- **Activity-aware states** - Idle/Busy/Available labels based on watchdog

**Winner:** MACstrom has more sophisticated scoring and state management. MacReplayXC's approach is simpler but effective for its use case.

---

## 2. Streaming Architecture

### 2.1 Stream Handling

**MacReplayXC:**
- **4 streaming modes:**
  1. FFmpeg transcode (MPEG-TS → HLS)
  2. FFmpeg copy (passthrough)
  3. Proxy mode (direct relay)
  4. Direct redirect (302 to CDN)
- **Per-client connections** - each viewer gets own upstream
- **FFmpeg subprocess** - spawns external process per stream
- **HLS output** - generates .m3u8 + .ts segments
- **No shared streams** - N viewers = N upstream connections

**MACstrom:**
- **Shared upstream** - N consumers share 1 upstream connection
- **Burst buffer** - instant playback for late joiners (TS-aligned)
- **Cold-start drip-feed** - null TS packets at 200ms intervals until data arrives
- **FFmpeg in-process** - statically linked C library via FFI
- **MPEG-TS passthrough** - no transcoding overhead
- **Dynamic error frames** - H.264-encoded error messages during failures
- **Broadcast channels** - tokio broadcast for fan-out
- **PTS-based bitrate estimation** - FFmpeg probe for quality scoring

**Winner:** MACstrom's shared streaming is far more efficient. 100 viewers = 1 upstream vs 100 upstreams in MacReplayXC. The burst buffer and error frames are elegant solutions.

---

### 2.2 Failover Strategy

**MacReplayXC:**
- **Cross-portal failover** - tries alternative portals for same channel
- **MAC rotation** - switches MACs on failure
- **Grace periods** - prevents rapid reconnects
- **Channel-level learning** - remembers which MACs work
- **Exponential backoff** - delays retries after failures
- **Manual fallback order** - user-configured priority

**MACstrom:**
- **QoE-driven sorting** - composite score (quality × reliability × stalling)
- **Cross-portal grouping** - auto-merges channels by name
- **Off-air detection** - skips dead streams (<200 kbps)
- **MAC rotation** - with channel bonus/penalty learning
- **Dynamic error frames** - keeps players connected during retries
- **Bad stream detection** - HTML responses, low bitrate
- **Upstream Retry-After** - respects CDN backoff headers

**Winner:** MACstrom's QoE scoring and dynamic error frames are more sophisticated. MacReplayXC's approach is simpler but lacks quality-based prioritization.

---

## 3. Proxy Management

### 3.1 Proxy Architecture

**MacReplayXC:**
- **No built-in proxy pool** - relies on external proxy configuration
- **Per-portal proxies** - configured manually in settings
- **HTTP/SOCKS5 support** - via requests/aiohttp
- **No automatic testing** - user must verify proxies work
- **No rotation** - static proxy assignment
- **Simple approach** - suitable for stable proxy sources

**MACstrom:**
- **Automatic proxy pool** - fetches from 9 providers (25 URLs)
- **ASN-based classification** - Residential/CDN/Hosting/Infrastructure
- **GeoIP country detection** - with geographic convergence
- **Composite EWMA scoring** - success² × latency weighting
- **Two selection modes:**
  - Fair (Efraimidis-Spirakis weighted shuffle)
  - Quality (Nginx SWRR proportional distribution)
- **Portal-specific blocking** - 5-min timeout on 403 errors
- **Rehabilitation** - dead proxies get second chances
- **Demand-driven refill** - auto-fetches based on death rate
- **Named portal proxies** - per-portal with scope control (CDN/stream/browse/scan)
- **Leaf tunneling** - Shadowsocks, Trojan, SOCKS5 support
- **Split-proxy mode** - CDN redirect via proxy, stream data direct

**Winner:** MACstrom by a landslide. Fully automated proxy management with sophisticated scoring, geographic convergence, and ASN classification. MacReplayXC requires manual proxy setup.

---

### 3.2 Proxy Testing

**MacReplayXC:**
- No built-in proxy testing
- User must manually verify proxies
- No health monitoring
- No automatic removal of dead proxies

**MACstrom:**
- **4 captive-portal endpoints** - Cloudflare, Mozilla, Canonical, Brave
- **Endpoint benchmarking** - 15 runs, trim outliers, median + 2×MAD
- **4s timeout** - 4s connect + 4s total
- **Batch testing** - 10-50 concurrent workers
- **Type detection** - auto-probes HTTP/SOCKS5/SOCKS4
- **Per-source yield tracking** - EMA pass rate per provider
- **Type-balanced sampling** - proportional HTTP/SOCKS5/SOCKS4 distribution

**Winner:** MACstrom. MacReplayXC has no proxy testing infrastructure.

---

## 4. API Compatibility

### 4.1 XC API (Xtream Codes)

**MacReplayXC:**
- **Full XC API** - player_api.php + get.php
- **GET + POST support** - both methods implemented
- **Category filtering** - genre-based channel filtering
- **Portal filtering** - per-portal M3U generation
- **Authentication** - username/password per user
- **VOD support** - movies and series
- **EPG integration** - short EPG in API responses
- **M3U generation** - internal + external playlists
- **Dual-host support** - HOST + HOST_EXTERNAL for Hairpin NAT

**MACstrom:**
- **Full XC API** - player_api.php + get.php
- **GET + POST support** - both methods implemented
- **Category filtering** - genre-based channel filtering
- **Short EPG overlay** - EPG data in API responses
- **User management** - create/delete users with stream limits
- **Per-IP rate limiting** - consumer connection throttling
- **M3U generation** - standard XC format
- **No dual-host** - single endpoint configuration

**Winner:** Tie. Both have full XC API compatibility. MacReplayXC has dual-host for Hairpin NAT, MACstrom has per-IP rate limiting.

---

### 4.2 Additional Protocols

**MacReplayXC:**
- **Legacy Stalker API** - portal.php endpoints
- **M3U playlists** - public/private access control
- **Direct streaming** - /stream/ endpoints
- **No HDHomeRun** - not implemented
- **No STRM** - not implemented

**MACstrom:**
- **HDHomeRun emulation** - /discover.json, /lineup.json, /device.xml
- **STRM endpoint** - .strm file generation with KODIPROP headers
- **STRM ZIP download** - bulk export for Kodi/Jellyfin
- **M3U playlists** - standard format
- **No legacy Stalker** - XC API only

**Winner:** Depends on use case. MacReplayXC supports legacy Stalker portals. MACstrom has HDHomeRun for Plex/Jellyfin auto-detection.

---

## 5. EPG (Electronic Program Guide)

**MacReplayXC:**
- **Portal EPG** - fetches from Stalker portals
- **External XMLTV** - supports external sources
- **Manual matching** - user configures tvg-id mappings
- **Basic implementation** - functional but limited

**MACstrom:**
- **Portal EPG** - fetches from Stalker/Ministra portals
- **External XMLTV** - auto-download/decompress from URLs
- **3-tier auto-matching:**
  1. Exact tvg-id match
  2. Fuzzy Sørensen-Dice similarity
  3. Manual override
- **Dummy EPG generation** - for unmapped channels
- **Source presets** - popular EPG providers pre-configured
- **XMLTV writer** - generates compliant XMLTV output

**Winner:** MACstrom. The 3-tier auto-matching with fuzzy similarity is far more sophisticated than MacReplayXC's manual approach.

---

## 6. User Interface

### 6.1 Frontend Technology

**MacReplayXC:**
- **Jinja2 templates** - server-side rendering
- **jQuery + vanilla JS** - client-side interactivity
- **Bootstrap** - CSS framework
- **Traditional web app** - full page reloads
- **SSE for live updates** - dashboard, logs
- **Simple and functional** - easy to understand

**MACstrom:**
- **Leptos 0.8** - fullstack Rust framework
- **WASM hydration** - SSR + client-side reactivity
- **Zero JavaScript** - entire frontend is Rust → WASM
- **Tailwind CSS v4 + DaisyUI v5** - utility-first styling
- **SPA routing** - client-side navigation
- **SSE for live updates** - dashboard, logs, system stats
- **Modern reactive UI** - fine-grained reactivity

**Winner:** MACstrom for modern architecture and type safety. MacReplayXC for simplicity and ease of customization.

---

### 6.2 Dashboard Features

**MacReplayXC:**
- **Portal overview** - status, MAC counts, channel counts
- **Active streams** - real-time viewer list
- **System stats** - basic metrics
- **Quick actions** - refresh, test, download M3U
- **Settings access** - configuration management
- **Log viewer** - basic log display

**MACstrom:**
- **Scanner dashboard** - live scan progress, hit notifications
- **Bridge dashboard** - active streams, MAC pool health
- **System resource monitoring** - CPU, memory, FDs, uptime (3-level color coding)
- **Live log viewer** - level filtering, freeze/resume, runtime level changes
- **Portal crawler** - discover portals from urlscan.io
- **Proxy pool status** - working/dead/testing counts
- **MAC pool status table** - sortable columns, activity states, score breakdown tooltips
- **Real-time SSE updates** - 500ms polling from ring buffer

**Winner:** MACstrom. More comprehensive monitoring and real-time updates. MacReplayXC is simpler but less feature-rich.

---

## 7. Configuration & Settings

**MacReplayXC:**
- **Environment variables** - HOST, HOST_EXTERNAL, DEBUG_MODE
- **Web UI settings** - comprehensive settings page
- **JSON persistence** - settings.json, portals.json
- **Docker-friendly** - docker-compose.yml configuration
- **Simple structure** - easy to understand and modify

**MACstrom:**
- **Environment variables** - LEPTOS_SITE_ADDR, RUST_LOG, MACSTROM_DATA_DIR
- **Web UI settings** - collapsible sections for all modules
- **JSON persistence** - settings.json, portals.json, scan_memory/
- **Device profiles** - Router vs Desktop presets
- **Runtime log level changes** - no restart required
- **Docker-friendly** - docker-compose.yml with volume mounts
- **Complex structure** - more options but steeper learning curve

**Winner:** Tie. MacReplayXC is simpler, MACstrom is more configurable.

---

## 8. Performance & Scalability

### 8.1 Concurrency Model

**MacReplayXC:**
- **Threading** - background tasks use threading
- **GIL limitations** - Python Global Interpreter Lock
- **Mixed sync/async** - requests (sync) + aiohttp (async)
- **Process-based FFmpeg** - subprocess overhead
- **Lock-based synchronization** - potential contention

**MACstrom:**
- **Tokio async runtime** - multi-threaded work-stealing
- **No GIL** - true parallelism across cores
- **Pure async** - reqwest + hickory-dns + rustls
- **In-process FFmpeg** - FFI bindings, no subprocess
- **Lock-free data structures** - DashMap, ArcSwap
- **jemalloc allocator** - thread-local arenas

**Winner:** MACstrom. Rust's async runtime and lock-free structures provide superior concurrency. Python's GIL is a fundamental limitation.

---

### 8.2 Memory & Resource Usage

**MacReplayXC:**
- **Interpreted Python** - higher memory overhead
- **Per-stream FFmpeg** - N processes for N streams
- **JSON parsing** - runtime overhead
- **Garbage collection** - non-deterministic pauses
- **Typical footprint** - 200-500 MB base + per-stream overhead

**MACstrom:**
- **Native binary** - minimal memory footprint
- **Shared streams** - 1 upstream for N consumers
- **In-process FFmpeg** - no subprocess overhead
- **Zero-copy where possible** - Bytes type for efficient buffer sharing
- **jemalloc** - efficient allocation for high-concurrency workloads
- **Typical footprint** - 50-150 MB base + shared stream overhead

**Winner:** MACstrom. Native compilation and shared streaming result in significantly lower resource usage.

---

### 8.3 Startup Time

**MacReplayXC:**
- **Python interpreter** - ~1-2 seconds
- **Module imports** - Flask, requests, etc.
- **JSON loading** - settings, portals, MACs
- **Total** - ~2-5 seconds

**MACstrom:**
- **Native binary** - instant execution
- **JSON loading** - settings, portals, scan memory
- **WASM compilation** - browser-side, one-time
- **Total** - ~1-2 seconds

**Winner:** MACstrom. Native binaries start faster than interpreted Python.

---

## 9. Deployment & Operations

### 9.1 Docker Support

**MacReplayXC:**
- **Python base image** - Debian/Alpine
- **FFmpeg installation** - apt/apk packages
- **Multi-stage build** - not used
- **Image size** - ~500-800 MB
- **docker-compose.yml** - simple configuration
- **Volume mounts** - data persistence

**MACstrom:**
- **Alpine base** - minimal Linux distribution
- **Multi-stage build** - build + runtime separation
- **Static musl binary** - self-contained executable
- **FFmpeg statically linked** - no runtime dependencies
- **Image size** - ~200-300 MB
- **docker-compose.yml** - with jemalloc LD_PRELOAD
- **Volume mounts** - data + logs persistence
- **Multi-arch support** - linux/amd64, linux/arm64

**Winner:** MACstrom. Smaller images, multi-arch support, and static linking reduce deployment complexity.

---

### 9.2 Logging & Debugging

**MacReplayXC:**
- **Python logging** - standard library
- **DEBUG_MODE** - environment variable
- **Log files** - optional file output
- **Console output** - stdout/stderr
- **Web log viewer** - basic implementation
- **No structured logging** - plain text

**MACstrom:**
- **tracing crate** - structured logging
- **RUST_LOG** - per-module granularity (e.g., macstrom=debug,reqwest=warn)
- **Daily rolling logs** - automatic rotation, 7-day retention
- **Non-blocking writer** - never stalls async runtime
- **Web log viewer** - level filtering, freeze/resume, runtime level changes
- **Ring buffer** - 5000-entry buffer for SSE streaming
- **Structured spans** - hierarchical context

**Winner:** MACstrom. Structured logging with per-module control and non-blocking writes is far superior.

---

## 10. Security & Reliability

### 10.1 Type Safety

**MacReplayXC:**
- **Dynamic typing** - runtime type errors possible
- **No compile-time checks** - errors discovered at runtime
- **Optional type hints** - not enforced
- **Duck typing** - flexible but error-prone

**MACstrom:**
- **Static typing** - compile-time type checking
- **Ownership system** - prevents data races and memory leaks
- **No null pointers** - Option<T> for optional values
- **Pattern matching** - exhaustive case handling
- **Zero-cost abstractions** - safety without runtime overhead

**Winner:** MACstrom. Rust's type system prevents entire classes of bugs at compile time.

---

### 10.2 Error Handling

**MacReplayXC:**
- **Exception-based** - try/except blocks
- **Potential crashes** - unhandled exceptions can crash app
- **Graceful degradation** - some error paths handled
- **Logging** - errors logged but may not be caught

**MACstrom:**
- **Result<T, E>** - explicit error handling
- **No exceptions** - errors are values
- **Exhaustive matching** - compiler enforces error handling
- **Graceful degradation** - errors propagate cleanly
- **Panic = bug** - panics are rare and indicate programmer error

**Winner:** MACstrom. Explicit error handling prevents silent failures.

---

### 10.3 Authentication & Authorization

**MacReplayXC:**
- **Session-based auth** - Flask sessions
- **Login system** - username/password
- **Rate limiting** - login endpoint only (5/min)
- **Public playlist access** - optional setting
- **No API keys** - session cookies only

**MACstrom:**
- **API key authentication** - X-Api-Key header or query param
- **Auto-generated keys** - on first start
- **Regenerable** - from Settings page
- **Session lock** - heartbeat-based (60s TTL)
- **Multi-browser management** - prevents concurrent sessions
- **User management** - per-user stream limits

**Winner:** Tie. Different approaches for different use cases. MacReplayXC has traditional login, MACstrom has API keys.

---

## 11. Testing & Quality

**MacReplayXC:**
- **No unit tests** - manual testing only
- **Integration testing** - via web UI
- **No CI/CD** - manual deployment
- **Code quality** - functional but not test-driven

**MACstrom:**
- **272 unit tests** - comprehensive test coverage
- **Property-based tests** - for complex algorithms
- **Integration tests** - HTTP endpoints, FFmpeg integration
- **CI/CD ready** - Rust's cargo test
- **Benchmark suite** - performance regression detection
- **Code quality** - test-driven development

**Winner:** MACstrom. Comprehensive test suite ensures reliability.

---

## 12. Documentation

**MacReplayXC:**
- **README** - basic setup instructions
- **Wiki page** - in-app documentation
- **Code comments** - moderate coverage
- **Changelog** - version history
- **Multiple analysis docs** - extensive code review documentation

**MACstrom:**
- **Comprehensive README** - 603 lines covering all features
- **ARCHITECTURE.md** - 1200+ lines of technical details
- **PROXY_GEO_CONVERGENCE.md** - detailed algorithm documentation
- **QUALITY_MANAGEMENT.md** - QoE scoring explanation
- **Code comments** - extensive inline documentation
- **API documentation** - rustdoc for all public APIs

**Winner:** MACstrom. Far more comprehensive documentation.

---

## 13. Key Innovations

### MacReplayXC Innovations:

1. **Dual-host system** - HOST + HOST_EXTERNAL for Hairpin NAT
2. **Channel-level MAC learning** - tracks MAC-channel compatibility
3. **Soft-start scoring** - gradual confidence building for new MACs
4. **Multiple streaming modes** - FFmpeg transcode/copy, proxy, direct redirect
5. **Legacy Stalker support** - portal.php endpoints
6. **Comprehensive code analysis** - extensive documentation of issues and fixes

### MACstrom Innovations:

1. **Thompson Sampling** - ML-based MAC discovery with hierarchical block tree
2. **Persistent learning** - temporal decay and global prior
3. **Shared streaming** - N consumers share 1 upstream connection
4. **Burst buffer** - instant playback for late joiners
5. **Dynamic error frames** - H.264-encoded error messages
6. **ASN-based proxy classification** - Residential/CDN/Hosting/Infrastructure
7. **Geographic proxy convergence** - adaptive geo-aware sampling
8. **QoE-driven failover** - composite quality × reliability × stalling score
9. **Zero JavaScript** - entire frontend is Rust → WASM
10. **In-process FFmpeg** - statically linked via FFI
11. **Portal crawler** - auto-discovery from urlscan.io
12. **3-tier EPG matching** - exact + fuzzy + manual
13. **Watchdog polling** - background MAC health monitoring
14. **Split-proxy mode** - CDN redirect via proxy, stream data direct

---

## 14. Use Case Recommendations

### Choose MacReplayXC if:

- You already have MAC sources (manual import workflow)
- You need legacy Stalker portal.php support
- You prefer Python for customization
- You want simpler architecture to understand
- You need dual-host for Hairpin NAT scenarios
- You're comfortable with manual proxy configuration
- You want traditional web app with server-side rendering

### Choose MACstrom if:

- You need automatic MAC discovery (Thompson Sampling)
- You want maximum performance and efficiency
- You need to support many concurrent viewers (shared streaming)
- You want sophisticated proxy management (auto-fetch, ASN classification, geo-convergence)
- You need HDHomeRun emulation for Plex/Jellyfin
- You want modern reactive UI with type safety
- You prefer compile-time guarantees over runtime errors
- You need comprehensive testing and documentation
- You want lower resource usage (memory, CPU)

---

## 15. Feature Comparison Matrix

| Feature | MacReplayXC | MACstrom |
|---------|-------------|----------|
| **MAC Discovery** | Manual import | Thompson Sampling ✓ |
| **Automatic scanning** | ❌ | ✓ |
| **Persistent learning** | ❌ | ✓ (temporal decay) |
| **Cross-portal learning** | ❌ | ✓ (global prior) |
| **Shared streaming** | ❌ | ✓ |
| **Burst buffer** | ❌ | ✓ |
| **Dynamic error frames** | ❌ | ✓ |
| **Proxy auto-fetch** | ❌ | ✓ (9 providers) |
| **ASN classification** | ❌ | ✓ |
| **Geo-convergence** | ❌ | ✓ |
| **HDHomeRun** | ❌ | ✓ |
| **STRM files** | ❌ | ✓ |
| **Legacy Stalker** | ✓ | ❌ |
| **Dual-host** | ✓ | ❌ |
| **XC API** | ✓ | ✓ |
| **EPG fuzzy matching** | ❌ | ✓ |
| **Portal crawler** | ❌ | ✓ |
| **Unit tests** | ❌ | ✓ (272 tests) |
| **Type safety** | Runtime | Compile-time ✓ |
| **Memory safety** | Runtime | Compile-time ✓ |
| **Zero JavaScript** | ❌ | ✓ |
| **Multi-arch Docker** | ❌ | ✓ |

---

## 16. Performance Benchmarks (Estimated)

| Metric | MacReplayXC | MACstrom |
|--------|-------------|----------|
| **Startup time** | 2-5s | 1-2s |
| **Memory (base)** | 200-500 MB | 50-150 MB |
| **Memory (100 streams)** | 1-2 GB | 200-400 MB |
| **CPU (idle)** | 2-5% | <1% |
| **CPU (streaming)** | 50-80% | 20-40% |
| **Concurrent streams** | 50-100 | 500-1000+ |
| **Docker image size** | 500-800 MB | 200-300 MB |
| **Request latency** | 10-50ms | 1-10ms |

*Note: These are estimates based on architectural differences. Actual performance depends on hardware and workload.*

---

## 17. Code Complexity

| Metric | MacReplayXC | MACstrom |
|--------|-------------|----------|
| **Total LOC** | ~8,000 | ~48,000 |
| **Language** | Python | Rust |
| **Files** | ~20 | ~111 |
| **Dependencies** | ~30 | ~150 |
| **Learning curve** | Low | High |
| **Maintainability** | Good | Excellent |

---

## 18. Conclusion

Both projects are impressive achievements that solve the same problem in fundamentally different ways.

**MacReplayXC** is a pragmatic, Python-based solution that prioritizes simplicity and ease of customization. It's perfect for users who already have MAC sources and want a straightforward IPTV streaming server. The dual-host feature for Hairpin NAT and legacy Stalker support are unique advantages.

**MACstrom** is a sophisticated, Rust-based solution that pushes the boundaries of what's possible. Thompson Sampling for automatic MAC discovery, shared streaming with burst buffers, ASN-based proxy classification with geographic convergence, and zero-JavaScript WASM frontend represent significant technical innovations. The compile-time safety, comprehensive testing, and superior performance make it ideal for production deployments at scale.

### Final Verdict:

- **For hobbyists and small deployments:** MacReplayXC (simpler, easier to customize)
- **For production and large-scale deployments:** MACstrom (more efficient, more features, better reliability)
- **For learning and experimentation:** MacReplayXC (Python is more accessible)
- **For performance-critical applications:** MACstrom (native code, lock-free concurrency)

---

## 19. Potential Improvements for MacReplayXC

Based on MACstrom's innovations, here are features that could benefit MacReplayXC:

### High Priority:

1. **Shared streaming** - Implement broadcast channels to share upstream connections
2. **Burst buffer** - Cache recent data for instant playback on late joins
3. **Proxy auto-fetch** - Add automatic proxy sourcing from free lists
4. **ASN classification** - Filter proxies by type (residential/CDN/hosting)
5. **EPG fuzzy matching** - Implement Sørensen-Dice similarity for auto-matching

### Medium Priority:

6. **HDHomeRun emulation** - Add /discover.json, /lineup.json for Plex/Jellyfin
7. **STRM endpoint** - Generate .strm files for Kodi
8. **Portal crawler** - Discover portals from urlscan.io
9. **Unit tests** - Add test coverage for critical paths
10. **Structured logging** - Implement per-module log levels

### Low Priority:

11. **Thompson Sampling** - Add ML-based MAC discovery (complex, requires significant refactoring)
12. **WASM frontend** - Rewrite UI in Rust/WASM (major undertaking)
13. **In-process FFmpeg** - Replace subprocess with FFI bindings (complex)

---

## 20. Lessons Learned

### From MACstrom:

- **Shared streaming is a game-changer** - Dramatically reduces resource usage
- **Burst buffers solve the late-joiner problem** - Instant playback without waiting
- **ASN classification enables smart proxy selection** - Residential proxies work better
- **Geographic convergence is elegant** - Pool naturally adapts to portal needs
- **Dynamic error frames keep players connected** - Better UX than black screens
- **Thompson Sampling is sophisticated** - But requires significant complexity
- **Type safety prevents bugs** - Compile-time checks catch errors early
- **Comprehensive testing matters** - 272 tests ensure reliability

### From MacReplayXC:

- **Simplicity has value** - Easier to understand and customize
- **Python ecosystem is rich** - Many libraries available
- **Dual-host solves real problems** - Hairpin NAT is a common issue
- **Channel-level learning works** - Simple but effective approach
- **Multiple streaming modes offer flexibility** - Different use cases need different solutions
- **Legacy support matters** - Not all portals use modern APIs

---

**End of Comparison**

*This analysis was conducted on 2026-03-06 comparing MacReplayXC v4.2.0 with MACstrom v0.7.9.*
