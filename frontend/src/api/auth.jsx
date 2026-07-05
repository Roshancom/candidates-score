import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const AuthContext = createContext(null);

import { API_BASE } from '../config';



export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);

  const isAuthenticated = !!token;
  const isAdmin = user?.role === 'admin';
  const isReviewer = user?.role === 'reviewer';

  useEffect(() => {
    if (token) {
      localStorage.setItem('token', token);
      // Fetch user info
      fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((res) => {
          if (!res.ok) throw new Error('Session expired');
          return res.json();
        })
        .then((data) => {
          setUser(data);
          setLoading(false);
        })
        .catch(() => {
          localStorage.removeItem('token');
          setToken(null);
          setUser(null);
          setLoading(false);
        });
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = useCallback(async (email, password) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(err.detail || 'Login failed');
    }
    const data = await res.json().catch(() => { throw new Error('Empty response from server'); });
    setLoading(true);
    setToken(data.access_token);
    localStorage.setItem('token', data.access_token);
    setUser({ id: null, email, role: data.role });
    return data;
  }, []);

  const register = useCallback(async (email, password) => {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
      throw new Error(err.detail || 'Registration failed');
    }
    return res.json();
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    setToken(null);
    setUser(null);
  }, []);

  /** Normalize FastAPI error detail (string | object | array) into a readable string. */
  const normalizeError = (detail) => {
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => (typeof d === 'object' ? d.msg || d.message || JSON.stringify(d) : String(d))).join('; ');
    }
    if (detail && typeof detail === 'object') return detail.msg || detail.message || JSON.stringify(detail);
    return String(detail);
  };

  const apiFetch = useCallback(
    async (path, options = {}) => {
      const headers = { ...options.headers };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
      }
      const res = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
      });
      if (res.status === 204) return null;
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(normalizeError(err.detail) || 'Request failed');
      }
      return res.json();
    },
    [token]
  );

  return (
    <AuthContext.Provider
      value={{ user, token, loading, isAuthenticated, isAdmin, isReviewer, login, register, logout, apiFetch }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
