import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../api/auth';
import NotificationBell from './NotificationBell';

export default function Navbar() {
  const { user, isAdmin, isReviewer, logout } = useAuth();
  const location = useLocation();

  const isActive = (path) => location.pathname.startsWith(path);

  const navLinkStyle = (path) => ({
    color: isActive(path) ? '#fff' : 'rgba(255,255,255,0.7)',
    textDecoration: 'none',
    fontSize: 'var(--font-size-base)',
    fontWeight: 500,
    borderBottom: isActive(path) ? '2px solid #fff' : '2px solid transparent',
    paddingBottom: 2,
    transition: 'color 0.15s ease, border-color 0.15s ease',
  });

  return (
    <nav style={{
      backgroundColor: 'var(--color-primary)',
      color: '#fff',
      padding: '0 var(--space-lg)',
      height: 56,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0,
      zIndex: 100,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
        <Link to={isAdmin ? '/candidates' : '/candidates/review'} style={{
          display: 'flex',
          alignItems: 'center',
          textDecoration: 'none',
        }}>
          <img
            src="/TechKraft-Logo.svg"
            alt="TechKraft Logo"
            style={{ height: 32, width: 'auto' }}
          />
        </Link>

        {/* Admin nav: Candidates, Upload CV */}
        {isAdmin && (
          <>
            <Link to="/candidates" style={navLinkStyle('/candidates')}>
              Candidates
            </Link>
            <Link to="/upload-cv" style={navLinkStyle('/upload-cv')}>
              Upload CV
            </Link>
            <NotificationBell />
          </>
        )}

        {/* Reviewer nav: Review Candidates, notification bell */}
        {isReviewer && (
          <>
            <Link to="/candidates/review" style={navLinkStyle('/candidates/review')}>
              Review Candidates
            </Link>
            <NotificationBell />
          </>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <span style={{ fontSize: 'var(--font-size-sm)', opacity: 0.8 }}>
          {user?.email}
          {isAdmin && <span style={{ marginLeft: 8, padding: '1px 6px', borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.2)', fontSize: 11 }}>ADMIN</span>}
          {isReviewer && <span style={{ marginLeft: 8, padding: '1px 6px', borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.15)', fontSize: 11 }}>REVIEWER</span>}
        </span>
        <button onClick={logout} className="btn btn-ghost" style={{ color: 'rgba(255,255,255,0.8)', borderColor: 'rgba(255,255,255,0.3)' }}>
          Log out
        </button>
      </div>
    </nav>
  );
}
