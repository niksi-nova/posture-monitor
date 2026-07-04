import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * useWebSocket — auto-reconnecting WebSocket hook with ping-pong latency measurement.
 *
 * @param {string} url  WebSocket URL (e.g. '/ws' or 'ws://localhost:8000/ws')
 * @returns {{ data: object|null, connected: boolean, latency: number|null, lastError: string|null }}
 */
export function useWebSocket(url) {
  const [data, setData]           = useState(null);
  const [connected, setConnected] = useState(false);
  const [latency, setLatency]     = useState(null);
  const [lastError, setLastError] = useState(null);

  // Refs that live outside the render cycle
  const wsRef            = useRef(null);
  const reconnectTimer   = useRef(null);
  const pingTimer        = useRef(null);
  const pingTs           = useRef(null);
  const retryDelay       = useRef(500);       // exponential backoff start
  const unmounted        = useRef(false);

  const MAX_DELAY   = 5000;
  const MULTIPLIER  = 1.5;
  const PING_INTERVAL = 5000;

  // ── Resolve full WS URL ────────────────────────────────────────────────────
  const resolveUrl = useCallback((rawUrl) => {
    if (rawUrl.startsWith('ws://') || rawUrl.startsWith('wss://')) return rawUrl;
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${window.location.host}${rawUrl}`;
  }, []);

  // ── Ping loop ──────────────────────────────────────────────────────────────
  const startPingLoop = useCallback((ws) => {
    stopPingLoop();
    pingTimer.current = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        pingTs.current = Date.now();
        try {
          ws.send(JSON.stringify({ type: 'ping', ts: pingTs.current }));
        } catch {
          // ignore send errors; reconnect handles them
        }
      }
    }, PING_INTERVAL);
  }, []);

  const stopPingLoop = useCallback(() => {
    if (pingTimer.current) {
      clearInterval(pingTimer.current);
      pingTimer.current = null;
    }
  }, []);

  // ── Connect ────────────────────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (unmounted.current) return;

    const fullUrl = resolveUrl(url);
    let ws;

    try {
      ws = new WebSocket(fullUrl);
    } catch (err) {
      setLastError(`WebSocket constructor failed: ${err.message}`);
      scheduleReconnect();
      return;
    }

    wsRef.current = ws;

    ws.onopen = () => {
      if (unmounted.current) { ws.close(); return; }
      setConnected(true);
      setLastError(null);
      retryDelay.current = 500;   // reset backoff
      startPingLoop(ws);
    };

    ws.onmessage = (event) => {
      if (unmounted.current) return;
      let parsed;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        return; // ignore non-JSON messages
      }

      // Handle pong for latency measurement
      if (parsed?.type === 'pong' && pingTs.current !== null) {
        setLatency(Date.now() - pingTs.current);
        pingTs.current = null;
        return;
      }

      setData(parsed);
    };

    ws.onerror = (event) => {
      if (unmounted.current) return;
      setLastError('WebSocket error — check backend connection');
    };

    ws.onclose = (event) => {
      if (unmounted.current) return;
      setConnected(false);
      stopPingLoop();
      if (!event.wasClean) {
        setLastError(`Connection closed (code ${event.code})`);
      }
      scheduleReconnect();
    };
  }, [url, resolveUrl, startPingLoop, stopPingLoop]);

  // ── Reconnect with exponential backoff ─────────────────────────────────────
  const scheduleReconnect = useCallback(() => {
    if (unmounted.current) return;
    const delay = retryDelay.current;
    retryDelay.current = Math.min(delay * MULTIPLIER, MAX_DELAY);

    reconnectTimer.current = setTimeout(() => {
      if (!unmounted.current) connect();
    }, delay);
  }, [connect]);

  // ── Lifecycle ──────────────────────────────────────────────────────────────
  useEffect(() => {
    unmounted.current = false;
    connect();

    return () => {
      unmounted.current = true;
      stopPingLoop();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on intentional close
        wsRef.current.close();
      }
    };
  }, [url]); // re-run only if url changes

  return { data, connected, latency, lastError };
}
