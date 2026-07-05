import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../api/auth';

export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();

  const [isRegistering, setIsRegistering] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);

    try {
      if (isRegistering) {
        await register(email, password);
      }
      // After registration or direct login, log them in and redirect based on role
      const data = await login(email, password);
      navigate(data.role === 'reviewer' ? '/candidates/review' : '/candidates');
    } catch (err) {
      setError(err.message || 'An error occurred');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: 'var(--color-page-bg)',
      padding: 'var(--space-lg)',
    }}>
      <div className="card" style={{ width: 400, maxWidth: '100%' }}>
        <div className="card-body">
          <div style={{ textAlign: 'center', marginBottom: 32 }}>
            <img
              src="/TechKraft-Logo.svg"
              alt="TechKraft Logo"
              style={{ height: 36, width: 'auto', marginBottom: 4 }}
            />
            <p style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--font-size-lg)' }}>
              Candidate Assessments
            </p>
          </div>

          {error && (
            <div className="alert alert-error" style={{ marginBottom: 16 }}>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="form-group">
              <label className="form-label" htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                className="form-input"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                className="form-input"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting}
              style={{ justifyContent: 'center', marginTop: 8 }}
            >
              {isSubmitting ? (
                <>
                  <span className="spinner" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} />
                  {isRegistering ? 'Registering...' : 'Logging in...'}
                </>
              ) : (
                isRegistering ? 'Register & Login' : 'Log in'
              )}
            </button>
          </form>

          <div style={{ marginTop: 24, textAlign: 'center', borderTop: '1px solid var(--color-border)', paddingTop: 16 }}>
            <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)', marginBottom: 8 }}>
              {isRegistering ? 'Already have an account?' : "Don't have an account?"}
            </p>
            <button
              className="btn btn-ghost"
              onClick={() => { setIsRegistering(!isRegistering); setError(''); }}
              style={{ fontSize: 'var(--font-size-sm)' }}
            >
              {isRegistering ? 'Log in instead' : 'Create account'}
            </button>
          </div>

          <div style={{ marginTop: 16, padding: 12, backgroundColor: 'var(--color-page-bg)', borderRadius: 'var(--radius-md)', fontSize: 'var(--font-size-sm)' }}>
            <p style={{ fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 4 }}>Demo accounts:</p>
            <p style={{ color: 'var(--color-text-secondary)' }}>Admin: admin@techkraft.com / admin123</p>
            <p style={{ color: 'var(--color-text-secondary)' }}>Reviewer: reviewer@techkraft.com / reviewer123</p>
          </div>
        </div>
      </div>
    </div>
  );
}
