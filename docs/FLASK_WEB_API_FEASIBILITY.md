# Flask Web API Feasibility Analysis

## Overview

This document evaluates the feasibility of converting `mbank-cli` into a Flask web application with REST API endpoints. The proposed solution would expose banking operations via HTTP endpoints, enabling web-based and programmatic access to mBank account data.

## Proposed Architecture

### Endpoints

| Endpoint | Method | Description | Expected Response Time |
|----------|--------|-------------|------------------------|
| `/balances` | GET | Returns list of accounts with balances | Up to 20 seconds |
| `/history` | GET | Returns transaction history | Up to 20 seconds |

### Request Parameters

**`/balances`**
- No required parameters
- Optional: Query parameters for filtering

**`/history`**
- `from` (optional): Start date in YYYY-MM-DD format
- `to` (optional): End date in YYYY-MM-DD format
- `all` (optional): Include external account history (Accounts Aggregation)

## Technical Feasibility Assessment

### ✅ Feasible Aspects

1. **Core Logic Reuse**: The existing `mbank-cli.py` contains well-structured functions for:
   - Authentication and session management
   - Account listing (`list` command)
   - Transaction history retrieval (`history` command)
   - Cookie jar management for session persistence

2. **Python Ecosystem**: Flask integrates naturally with the existing Python codebase.

3. **Response Formats**: Current implementation already uses JSON internally, which maps directly to REST API responses.

### ⚠️ Considerations

#### 1. Long Response Times (Up to 20 seconds)

The banking operations can take up to 20 seconds due to:
- Two-factor authentication flows
- Multiple HTTP requests to mBank servers
- Session establishment delays

**Recommended Solutions:**
- Configure proper timeout values in Flask/Gunicorn
- Use async workers (e.g., gevent, eventlet)
- Implement request timeouts and proper error handling
- Consider WebSocket or Server-Sent Events for progress updates
- Add loading indicators on client side

```python
# Example timeout configuration (NOT FOR IMPLEMENTATION)
# 60 seconds provides 3x headroom over the 20-second max response time
# gunicorn --timeout 60 --workers 2 app:app
```

#### 2. Authentication & Security

**Challenges:**
- mBank credentials must be stored/provided securely
- Session cookies need proper management
- Multi-user scenarios require session isolation

**Recommendations:**
- Store credentials in environment variables or secure vault
- Implement HTTPS only (no HTTP)
- Consider API token authentication for the Flask layer
- Rate limiting to prevent abuse
- IP whitelisting for production use

#### 3. Session State Management

The CLI uses cookie jars for session persistence. The web API would need:
- Per-user session isolation
- Concurrent request handling
- Session cleanup and timeout handling

#### 4. Deployment Architecture

```
[Client] → [NGINX/Reverse Proxy] → [Gunicorn] → [Flask App] → [mBank API]
              (HTTPS)              (timeout=60s)
```

## Implementation Effort Estimate

| Component | Effort | Complexity |
|-----------|--------|------------|
| Flask app skeleton | Low | Simple |
| Endpoint integration | Medium | Moderate |
| Authentication layer | Medium | Moderate |
| Error handling | Medium | Moderate |
| Long-request handling | Medium | Moderate |
| Security hardening | High | Complex |
| Production deployment | Medium | Moderate |

**Total Estimated Effort**: 2-4 days for basic implementation, additional time for security hardening and production readiness.

## Pros and Cons

### Pros
- ✅ Enables web/mobile clients to access banking data
- ✅ Can integrate with automation tools (cron, monitoring)
- ✅ Reuses existing, tested CLI logic
- ✅ Python/Flask is a mature, well-documented stack
- ✅ Easy to containerize (Docker)

### Cons
- ⚠️ Security concerns with exposing banking credentials via web API
- ⚠️ Long response times may cause UX issues
- ⚠️ Requires proper session management
- ⚠️ mBank may rate-limit or block API-like access
- ⚠️ Maintenance burden for security updates

## Prerequisites for Implementation

1. **Dependencies**: `flask`, `gunicorn`, optionally `gevent`
2. **Configuration**: Environment-based config for credentials
3. **Infrastructure**: HTTPS-enabled server, firewall rules
4. **Testing**: Offline mock server (already exists in test suite)

## Conclusion

Converting `mbank-cli` to a Flask web API is **technically feasible**. The existing codebase already contains the core logic needed for account listing and history retrieval. The main challenges are:

1. Handling long response times gracefully
2. Implementing proper security measures
3. Managing authentication and sessions in a web context

The Flask framework is well-suited for this use case, and with proper timeout configuration (gunicorn `--timeout 60`), the 20-second response time can be accommodated.

---

*This is a feasibility analysis document. No implementation has been done per the stakeholder's request.*
