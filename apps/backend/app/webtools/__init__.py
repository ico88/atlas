"""Web tools (ROADMAP PR 15): safe search + fetch with ranking and citations.

Local-first and off by default. Every outbound request passes a URL policy that
blocks non-HTTP(S) schemes and private/loopback/link-local targets (SSRF guard),
enforces size and time caps, and honours domain allow/deny lists.
"""
