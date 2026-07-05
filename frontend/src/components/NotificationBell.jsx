import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../api/auth';
import { getNotifications, markNotificationsRead } from '../api/client';

export default function NotificationBell() {
  const { apiFetch } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const dropdownRef = useRef(null);

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getNotifications(apiFetch);
      setNotifications(data.items || []);
      setUnreadCount(data.unread_count || 0);
    } catch {
      // Silently fail - notifications are non-critical
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  // Fetch on mount
  useEffect(() => {
    fetchNotifications();
    // Refresh every 30 seconds
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const handleToggle = () => {
    const nextOpen = !open;
    setOpen(nextOpen);
    if (nextOpen && unreadCount > 0) {
      // Optimistically mark all as read
      markNotificationsRead(apiFetch).catch(() => {});
      setUnreadCount(0);
      setNotifications((prev) =>
        prev.map((n) => ({ ...n, is_read: true }))
      );
    }
  };

  const handleNotificationClick = (notification) => {
    setOpen(false);
    if (notification.candidate_id) {
      navigate(`/candidates/${notification.candidate_id}`);
    }
  };

  const formatTime = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  const notificationTypeIcon = (type) => {
    switch (type) {
      case 'assignment':
        return '📋';
      case 'score_submitted':
        return '⭐';
      default:
        return '🔔';
    }
  };

  return (
    <div ref={dropdownRef} style={{ position: 'relative' }}>
      <button
        onClick={handleToggle}
        style={{
          background: 'none',
          border: 'none',
          color: 'rgba(255,255,255,0.7)',
          cursor: 'pointer',
          fontSize: 18,
          padding: '4px 8px',
          borderRadius: 'var(--radius-sm)',
          display: 'flex',
          alignItems: 'center',
          position: 'relative',
          transition: 'color 0.15s ease',
        }}
        title="Notifications"
        onMouseEnter={(e) => { e.currentTarget.style.color = '#fff'; }}
        onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(255,255,255,0.7)'; }}
      >
        🔔
        {unreadCount > 0 && (
          <span
            style={{
              position: 'absolute',
              top: 0,
              right: 2,
              minWidth: 16,
              height: 16,
              borderRadius: 8,
              backgroundColor: 'var(--color-danger)',
              color: '#fff',
              fontSize: 10,
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '0 4px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
              animation: unreadCount > 0 ? 'pulse 2s ease-in-out infinite' : 'none',
            }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 8px)',
            right: 0,
            width: 360,
            maxHeight: 420,
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-lg)',
            overflow: 'hidden',
            zIndex: 200,
          }}
        >
          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--color-border)',
              fontWeight: 600,
              fontSize: 'var(--font-size-base)',
              color: 'var(--color-text-primary)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <span>Notifications</span>
            {unreadCount > 0 && (
              <span className="badge badge-new" style={{ fontSize: 10 }}>
                {unreadCount} new
              </span>
            )}
          </div>

          <div style={{ overflowY: 'auto', maxHeight: 360 }}>
            {loading && notifications.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center' }}>
                <div className="spinner" style={{ margin: '0 auto' }} />
              </div>
            ) : notifications.length === 0 ? (
              <div style={{ padding: 32, textAlign: 'center', color: 'var(--color-text-secondary)' }}>
                <p style={{ fontSize: 28, marginBottom: 8 }}>🔔</p>
                <p style={{ fontSize: 'var(--font-size-sm)' }}>No notifications yet</p>
              </div>
            ) : (
              notifications.map((notif) => (
                <div
                  key={notif.id}
                  onClick={() => handleNotificationClick(notif)}
                  style={{
                    padding: '12px 16px',
                    borderBottom: '1px solid var(--color-border)',
                    cursor: notif.candidate_id ? 'pointer' : 'default',
                    backgroundColor: notif.is_read ? 'transparent' : 'rgba(59, 125, 216, 0.04)',
                    transition: 'background-color 0.12s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (notif.candidate_id) {
                      e.currentTarget.style.backgroundColor = 'rgba(59, 125, 216, 0.08)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = notif.is_read
                      ? 'transparent'
                      : 'rgba(59, 125, 216, 0.04)';
                  }}
                >
                  <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                    <span style={{ fontSize: 16, flexShrink: 0, marginTop: 2 }}>
                      {notificationTypeIcon(notif.type)}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p
                        style={{
                          fontSize: 'var(--font-size-sm)',
                          fontWeight: notif.is_read ? 400 : 600,
                          color: 'var(--color-text-primary)',
                          marginBottom: 2,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {notif.title}
                      </p>
                      <p
                        style={{
                          fontSize: 12,
                          color: 'var(--color-text-secondary)',
                          lineHeight: 1.4,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}
                      >
                        {notif.message}
                      </p>
                      <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 4 }}>
                        {formatTime(notif.created_at)}
                      </p>
                    </div>
                    {!notif.is_read && (
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          backgroundColor: 'var(--color-accent)',
                          flexShrink: 0,
                          marginTop: 6,
                        }}
                      />
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
