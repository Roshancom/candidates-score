import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../api/auth';
import { getReviewCandidates } from '../api/client';

export default function ReviewerCandidateListPage() {
  const { apiFetch, user } = useAuth();
  const navigate = useNavigate();

  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const currentUserId = user?.id;

  // Wait for user data to load so we have an accurate currentUserId for split logic
  if (!currentUserId) {
    return (
      <div className="page-container">
        <div className="loading-overlay">
          <div className="spinner spinner-lg" />
          <div className="loading-text">Loading...</div>
        </div>
      </div>
    );
  }

  const fetchCandidates = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getReviewCandidates(apiFetch);
      setCandidates(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => {
    fetchCandidates();
  }, [fetchCandidates]);

  // Not Reviewed Yet: candidates assigned to this reviewer that have no scores from anyone
  const notReviewedYet = candidates.filter(
    (c) => c.assigned_reviewer_id === currentUserId && !c.is_reviewed_by_anyone
  );

  // Reviewed: all candidates that have been reviewed by anyone (system-wide)
  const reviewed = candidates.filter((c) => c.is_reviewed_by_anyone);

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Review Candidates</h1>
        <p className="page-subtitle">Candidates assigned to you for review</p>
      </div>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* Not Reviewed Yet section — always renders */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, color: 'var(--color-primary)' }}>
            Not Reviewed Yet
          </h3>
          <span className="badge badge-new">{notReviewedYet.length}</span>
        </div>
        <div className="card-body" style={{ padding: notReviewedYet.length === 0 ? 'var(--space-lg)' : 0 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <div className="spinner spinner-lg" style={{ margin: '0 auto' }} />
            </div>
          ) : notReviewedYet.length === 0 ? (
            <p style={{ color: 'var(--color-text-secondary)', textAlign: 'center' }}>
              All assigned candidates have been reviewed!
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {notReviewedYet.map((candidate) => (
                <ReviewCandidateCard
                  key={candidate.id}
                  candidate={candidate}
                  onClick={() => navigate(`/candidates/${candidate.id}`)}
                  notReviewed
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Reviewed section — always renders */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, color: 'var(--color-primary)' }}>
            Reviewed
          </h3>
          <span className="badge badge-reviewed">{reviewed.length}</span>
        </div>
        <div className="card-body" style={{ padding: reviewed.length === 0 ? 'var(--space-lg)' : 0 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <div className="spinner spinner-lg" style={{ margin: '0 auto' }} />
            </div>
          ) : reviewed.length === 0 ? (
            <p style={{ color: 'var(--color-text-secondary)', textAlign: 'center' }}>
              No candidates have been reviewed yet.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {reviewed.map((candidate) => {
                const isAssignedToMe = candidate.assigned_reviewer_id === currentUserId;
                return (
                  <ReviewCandidateCard
                    key={candidate.id}
                    candidate={candidate}
                    onClick={isAssignedToMe ? () => navigate(`/candidates/${candidate.id}`) : null}
                    disabled={!isAssignedToMe}
                  />
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Empty state — only when there are no candidates at all */}
      {!loading && candidates.length === 0 && !error && (
        <div className="card">
          <div className="card-body" style={{ textAlign: 'center', padding: 'var(--space-2xl)' }}>
            <p style={{ fontSize: 48, marginBottom: 16 }}>📋</p>
            <p style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--font-size-lg)' }}>
              No candidates assigned to you yet.
            </p>
            <p style={{ color: 'var(--color-text-secondary)', marginTop: 8 }}>
              When an admin assigns candidates, they'll appear here.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewCandidateCard({ candidate, onClick, notReviewed, disabled }) {
  const isClickable = !!onClick;
  const isAssigned = !disabled;
  // Show average score only if assigned to the current reviewer
  const showScore = isAssigned && candidate.average_score != null;
  const showNotScored = isAssigned && candidate.average_score == null && candidate.is_reviewed_by_current_user === false;
  const scoreColor = candidate.average_score >= 4 ? 'var(--color-success)'
    : candidate.average_score >= 3 ? 'var(--color-warning)'
    : 'var(--color-danger)';
  return (
    <div
      onClick={disabled ? undefined : onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-md) var(--space-lg)',
        borderBottom: '1px solid var(--color-border)',
        cursor: isClickable ? 'pointer' : 'default',
        opacity: disabled ? 0.55 : 1,
        transition: 'background-color 0.12s ease, opacity 0.12s ease',
        pointerEvents: disabled ? 'none' : 'auto',
      }}
      onMouseEnter={(e) => {
        if (isClickable) e.currentTarget.style.backgroundColor = 'rgba(59,125,216,0.04)';
      }}
      onMouseLeave={(e) => {
        if (isClickable) e.currentTarget.style.backgroundColor = '';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flex: 1 }}>
        <div style={{
          width: 36,
          height: 36,
          borderRadius: '50%',
          backgroundColor: disabled ? 'var(--color-border)' : 'var(--color-page-bg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 600,
          fontSize: 'var(--font-size-sm)',
          color: disabled ? 'var(--color-text-secondary)' : 'var(--color-accent)',
          flexShrink: 0,
        }}>
          {candidate.name.charAt(0).toUpperCase()}
        </div>
        <div>
          <p style={{ fontWeight: 500 }}>{candidate.name}</p>
          <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
            {candidate.role_applied}
          </p>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {candidate.assigned_date && (
          <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
            Assigned {new Date(candidate.assigned_date).toLocaleDateString()}
          </span>
        )}
        {/* Average score — only shown for assigned reviewers */}
        {isAssigned && candidate.average_score != null && (
          <span style={{
            fontWeight: 700,
            fontSize: 'var(--font-size-sm)',
            color: scoreColor,
            padding: '2px 8px',
            borderRadius: 4,
            backgroundColor: 'var(--color-page-bg)',
            border: '1px solid var(--color-border)',
          }}>
            {candidate.average_score.toFixed(2)}
          </span>
        )}
        {showNotScored && (
          <span style={{
            fontSize: 11,
            color: 'var(--color-text-secondary)',
            whiteSpace: 'nowrap',
          }}>
            Not scored yet
          </span>
        )}
        {notReviewed ? (
          <span className="badge badge-new">Not Reviewed</span>
        ) : (
          <span className="badge badge-reviewed">Reviewed</span>
        )}
        {isClickable ? (
          <span style={{ color: 'var(--color-text-secondary)', fontSize: 18 }}>→</span>
        ) : disabled && (
          <span style={{ color: 'var(--color-text-secondary)', fontSize: 14, opacity: 0.4 }}>🔒</span>
        )}
      </div>
    </div>
  );
}
