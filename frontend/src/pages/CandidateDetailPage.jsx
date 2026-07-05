import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../api/auth';
import { getCandidate, submitScore, updateScore, adminUpdateScore, generateSummary, updateCandidate, getNotifications } from '../api/client';
import StatusBadge from '../components/StatusBadge';

const SCORE_CATEGORIES = [
  'Technical Skills',
  'Communication',
  'Problem Solving',
  'Leadership',
  'Cultural Fit',
  'Experience',
];

export default function CandidateDetailPage() {
  const { id } = useParams();
  const { apiFetch, isAdmin, user } = useAuth();
  const currentUserId = user?.id;
  const navigate = useNavigate();

  const [candidate, setCandidate] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Score form
  // Compute categories the current reviewer has already scored (scores are filtered by reviewer on the backend)
  const scoredCategories = new Set((candidate?.scores || []).map((s) => s.category));
  const availableCategories = SCORE_CATEGORIES.filter((cat) => !scoredCategories.has(cat));
  const allCategoriesScored = availableCategories.length === 0;

  const [scoreCategory, setScoreCategory] = useState(
    availableCategories.length > 0 ? availableCategories[0] : SCORE_CATEGORIES[0]
  );
  const [scoreValue, setScoreValue] = useState(3);
  const [scoreNote, setScoreNote] = useState('');
  const [submittingScore, setSubmittingScore] = useState(false);
  const [editingScoreId, setEditingScoreId] = useState(null);

  // Find the score being edited (if any) to pre-fill the form
  const editingScore = editingScoreId != null
    ? (candidate?.scores || []).find((s) => s.id === editingScoreId)
    : null;
  const isEditing = editingScoreId != null;

  // Reset score category if the current one was just scored (removed from dropdown)
  useEffect(() => {
    if (availableCategories.length > 0 && !availableCategories.includes(scoreCategory)) {
      setScoreCategory(availableCategories[0]);
    }
  }, [candidate?.scores]);

  // AI Summary — initialize from cached data if present
  const [summary, setSummary] = useState('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState('');
  const [hasCachedSummary, setHasCachedSummary] = useState(false);

  // When candidate data loads, check for existing cached summary
  useEffect(() => {
    if (candidate?.ai_summary) {
      setSummary(candidate.ai_summary);
      setHasCachedSummary(true);
    } else {
      setSummary('');
      setHasCachedSummary(false);
    }
  }, [candidate?.ai_summary]);

  // Internal notes (admin only)
  const [internalNotes, setInternalNotes] = useState('');
  const [savingNotes, setSavingNotes] = useState(false);

  // CV file
  const cvFileUrl = candidate?.cv_file_url;
  const cvContentType = candidate?.cv_content_type || 'application/pdf';
  const cvFileName = cvFileUrl || 'resume.pdf';
  const isImageType = cvContentType.startsWith('image/');

  // CV modal — uses protected endpoint /api/candidates/{id}/cv
  const cvApiEndpoint = `/api/candidates/${id}/cv`;
  const [cvModalOpen, setCvModalOpen] = useState(false);
  const [cvLoading, setCvLoading] = useState(false);
  const [cvError, setCvError] = useState('');
  const [cvBlobUrl, setCvBlobUrl] = useState(null);

  // Fetch the CV via protected endpoint when modal opens
  const loadCv = useCallback(async () => {
    if (!candidate?.cv_file_url) return;
    setCvLoading(true);
    setCvError('');
    setCvBlobUrl(null);

    const token = localStorage.getItem('token');
    try {
      const res = await fetch(cvApiEndpoint, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to load CV');
      }
      const blob = await res.blob();
      setCvBlobUrl(URL.createObjectURL(blob));
    } catch (err) {
      setCvError(err.message);
    } finally {
      setCvLoading(false);
    }
  }, [candidate?.cv_file_url, cvApiEndpoint]);

  useEffect(() => {
    if (cvModalOpen && candidate?.cv_file_url) {
      loadCv();
    }
  }, [cvModalOpen]);

  // Lock body scroll when modal is open, close on Escape
  useEffect(() => {
    if (cvModalOpen) {
      document.body.style.overflow = 'hidden';
      const handleKey = (e) => {
        if (e.key === 'Escape') handleCloseCv();
      };
      document.addEventListener('keydown', handleKey);
      return () => {
        document.body.style.overflow = '';
        document.removeEventListener('keydown', handleKey);
      };
    }
  }, [cvModalOpen]);

  const handleCloseCv = () => {
    setCvModalOpen(false);
    if (cvBlobUrl) {
      URL.revokeObjectURL(cvBlobUrl);
      setCvBlobUrl(null);
    }
    setCvError('');
  };

  // Not reviewed state
  const notReviewed = !candidate?.is_reviewed_by_current_user && !isAdmin;

  // Determine where the back button should go based on role
  const backPath = isAdmin ? '/candidates' : '/candidates/review';


  const fetchCandidate = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getCandidate(apiFetch, id);
      setCandidate(data);
      setInternalNotes(data.internal_notes || '');
    } catch (err) {
      setError(err.message || 'Failed to load candidate');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCandidate();
  }, [id]);

  const handleStartEdit = (score) => {
    setEditingScoreId(score.id);
    setScoreCategory(score.category);
    setScoreValue(score.score);
    setScoreNote(score.note || '');
  };

  const handleCancelEdit = () => {
    setEditingScoreId(null);
    setScoreCategory(
      availableCategories.length > 0 ? availableCategories[0] : SCORE_CATEGORIES[0]
    );
    setScoreValue(3);
    setScoreNote('');
  };

  const handleSubmitScore = async (e) => {
    e.preventDefault();
    setSubmittingScore(true);
    try {
      if (isEditing && editingScore) {
        if (isAdmin) {
          // Admin: only update numeric score, preserve reviewer's note
          await adminUpdateScore(apiFetch, id, editingScore.id, {
            score: scoreValue,
          });
        } else {
          // Reviewer: update score and note
          await updateScore(apiFetch, id, editingScore.id, {
            score: scoreValue,
            note: scoreNote,
          });
        }
        setEditingScoreId(null);
      } else {
        // Create new score
        await submitScore(apiFetch, id, {
          category: scoreCategory,
          score: scoreValue,
          note: scoreNote,
        });
        setScoreNote('');
      }
      setScoreValue(3);
      await fetchCandidate();
      // Refresh notifications on create only (first score notif)
      if (!isEditing) {
        getNotifications(apiFetch).catch(() => {});
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmittingScore(false);
    }
  };

  const handleGenerateSummary = async () => {
    setSummaryLoading(true);
    setSummaryError('');
    setSummary('');
    try {
      const data = await generateSummary(apiFetch, id);
      setSummary(data.summary);
      setHasCachedSummary(true);
    } catch (err) {
      setSummaryError(err.message || 'Failed to generate summary');
    } finally {
      setSummaryLoading(false);
    }
  };

  const handleSaveNotes = async () => {
    setSavingNotes(true);
    try {
      await updateCandidate(apiFetch, id, { internal_notes: internalNotes });
      await fetchCandidate();
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingNotes(false);
    }
  };

  // StatusBadge component used instead of inline statusBadgeClass

  if (loading) {
    return (
      <div className="page-container">
        <div className="loading-overlay">
          <div className="spinner spinner-lg" />
          <div className="loading-text">Loading candidate...</div>
        </div>
      </div>
    );
  }

  if (error && !candidate) {
    return (
      <div className="page-container">
        <div className="alert alert-error">{error}</div>
        <button className="btn btn-accent mt-md" onClick={() => navigate(isAdmin ? '/candidates' : '/candidates/review')}>
          ← Back to {isAdmin ? 'candidates' : 'review list'}
        </button>
      </div>
    );
  }

  if (!candidate) return null;

  // Group scores by reviewer for admin view
  const scoresByReviewer = {};
  if (candidate.scores) {
    candidate.scores.forEach((s) => {
      if (!scoresByReviewer[s.reviewer_id]) {
        scoresByReviewer[s.reviewer_id] = [];
      }
      scoresByReviewer[s.reviewer_id].push(s);
    });
  }

  return (
    <div className="page-container">
      {/* Back button — navigates to correct origin based on role */}
      <button className="btn btn-ghost mb-md" onClick={() => navigate(backPath)} style={{ marginBottom: 16 }}>
        ← Back to {isAdmin ? 'candidates' : 'review list'}
      </button>

      {error && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* Left column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {/* Profile info */}
          <div className="card">
            <div className="card-header">
              <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: 600, color: 'var(--color-primary)' }}>
                {candidate.name}
              </h2>
              <StatusBadge status={candidate.status} />
            </div>
            <div className="card-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <span className="form-label">Email</span>
                <p style={{ marginTop: 2 }}>{candidate.email}</p>
              </div>
              <div>
                <span className="form-label">Role Applied</span>
                <p style={{ marginTop: 2, fontWeight: 500 }}>{candidate.role_applied}</p>
              </div>
              <div>
                <span className="form-label">Skills</span>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                  {(candidate.skills || []).map((skill) => (
                    <span
                      key={skill}
                      style={{
                        padding: '3px 10px',
                        fontSize: 'var(--font-size-sm)',
                        backgroundColor: 'var(--color-accent)',
                        color: '#fff',
                        borderRadius: 999,
                        fontWeight: 500,
                      }}
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <span className="form-label">Created</span>
                <p style={{ marginTop: 2, color: 'var(--color-text-secondary)' }}>
                  {new Date(candidate.created_at).toLocaleString()}
                </p>
              </div>
            </div>

            {/* CV File Section */}
            <div style={{
              borderTop: '1px solid var(--color-border)',
              padding: 'var(--space-md) var(--space-lg)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 20 }}>📄</span>
                <div>
                  <p style={{ fontSize: 'var(--font-size-sm)', fontWeight: 500 }}>
                    {cvFileUrl ? cvFileName : 'No CV uploaded'}
                  </p>
                  <p style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>
                    {cvFileUrl ? 'Resume / CV' : 'Candidate has no CV file'}
                  </p>
                </div>
              </div>
              {cvFileUrl ? (
                <button
                  onClick={() => setCvModalOpen(true)}
                  className="btn btn-outline"
                  style={{ fontSize: 'var(--font-size-sm)', padding: '4px 12px' }}
                >
                  View CV
                </button>
              ) : (
                <span
                  className="badge badge-archived"
                  style={{ fontSize: 11, opacity: 0.7 }}
                >
                  No CV
                </span>
              )}
            </div>
          </div>

          {/* AI Summary */}
          <div className="card">
            <div className="card-header">
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, color: 'var(--color-primary)' }}>
                AI Summary
              </h3>
            </div>
            <div className="card-body">
              <button
                className="btn btn-accent"
                onClick={handleGenerateSummary}
                disabled={summaryLoading}
              >
                {summaryLoading ? (
                  <>
                    <span className="spinner" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} />
                    Generating...
                  </>
                ) : (
                  hasCachedSummary ? 'Regenerate Summary' : 'Generate Summary'
                )}
              </button>

              {hasCachedSummary && !summaryLoading && (
                <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 8 }}>
                  Summary was previously generated{candidate?.ai_summary_generated_at
                    ? ` on ${new Date(candidate.ai_summary_generated_at).toLocaleDateString()}`
                    : ''}. Click <strong>Regenerate</strong> to create a new one.
                </p>
              )}

              {summaryLoading && (
                <div style={{ marginTop: 16 }}>
                  <div className="skeleton" style={{ height: 16, width: '100%', marginBottom: 8 }} />
                  <div className="skeleton" style={{ height: 16, width: '80%', marginBottom: 8 }} />
                  <div className="skeleton" style={{ height: 16, width: '60%' }} />
                </div>
              )}

              {summaryError && (
                <div className="alert alert-error" style={{ marginTop: 16 }}>
                  {summaryError}
                </div>
              )}

              {summary && !summaryLoading && (
                <div style={{
                  marginTop: 16,
                  padding: 16,
                  backgroundColor: 'var(--color-page-bg)',
                  borderRadius: 'var(--radius-md)',
                  lineHeight: 1.7,
                  color: 'var(--color-text-primary)',
                }}>
                  {summary}
                </div>
              )}
            </div>
          </div>

          {/* Internal Notes (admin only) */}
          {isAdmin && (
            <div className="card">
              <div className="card-header">
                <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, color: 'var(--color-primary)' }}>
                  Internal Notes
                </h3>
                <span className="badge badge-new" style={{ fontSize: 10 }}>ADMIN ONLY</span>
              </div>
              <div className="card-body">
                <textarea
                  className="form-textarea"
                  value={internalNotes}
                  onChange={(e) => setInternalNotes(e.target.value)}
                  placeholder="Add internal notes about this candidate..."
                  rows={4}
                  style={{ width: '100%' }}
                />
                <button
                  className="btn btn-accent mt-sm"
                  onClick={handleSaveNotes}
                  disabled={savingNotes}
                  style={{ marginTop: 8 }}
                >
                  {savingNotes ? 'Saving...' : 'Save Notes'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {/* Scores */}
          <div className="card">
            <div className="card-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, color: 'var(--color-primary)' }}>
                  Scores
                </h3>
                {notReviewed && (
                  <span
                    className="badge badge-new"
                    style={{
                      fontSize: 11,
                      padding: '2px 8px',
                      animation: 'pulse 2s ease-in-out infinite',
                    }}
                  >
                    ⚠ Not Reviewed Yet
                  </span>
                )}
              </div>
              <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
                {candidate.scores?.length || 0} total
              </span>
            </div>
            <div className="card-body">
              {isAdmin ? (
                // Admin view: grouped by reviewer
                Object.keys(scoresByReviewer).length === 0 ? (
                  <p style={{ color: 'var(--color-text-secondary)', textAlign: 'center', padding: 16 }}>
                    No scores yet
                  </p>
                ) : (
                  Object.entries(scoresByReviewer).map(([reviewerId, scores]) => (
                    <div key={reviewerId} style={{ marginBottom: 16 }}>
                      <p style={{ fontWeight: 600, fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)', marginBottom: 8 }}>
                        Reviewer #{reviewerId}
                      </p>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {scores.map((score) => (
                          <div
                            key={score.id}
                            style={{
                              padding: '8px 12px',
                              backgroundColor: 'var(--color-page-bg)',
                              borderRadius: 'var(--radius-md)',
                              borderLeft: '3px solid var(--color-accent)',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <span style={{ fontWeight: 500, fontSize: 'var(--font-size-sm)' }}>{score.category}</span>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <span style={{
                                  fontWeight: 700,
                                  color: score.score >= 4 ? 'var(--color-success)' : score.score >= 3 ? 'var(--color-warning)' : 'var(--color-danger)',
                                }}>
                                  {score.score}/5
                                </span>
                                <button
                                  onClick={(e) => { e.stopPropagation(); handleStartEdit(score); }}
                                  className="btn btn-outline"
                                  style={{
                                    fontSize: 11,
                                    padding: '2px 10px',
                                    flexShrink: 0,
                                  }}
                                >
                                  Edit
                                </button>
                              </div>
                            </div>
                            {score.note && (
                              <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)', marginTop: 4 }}>
                                {score.note}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                )
              ) : (
                // Reviewer view: only their own scores — all rows show Edit button
                candidate.scores?.length === 0 && notReviewed ? (
                  <div style={{ textAlign: 'center', padding: 24 }}>
                    <p style={{ fontSize: 32, marginBottom: 8 }}>📝</p>
                    <p style={{ color: 'var(--color-text-secondary)' }}>
                      You haven't submitted any scores yet for this candidate.
                    </p>
                    <p style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--font-size-sm)', marginTop: 4 }}>
                      Use the form below to submit your first score.
                    </p>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {candidate.scores.map((score) => (
                      <div
                        key={score.id}
                        style={{
                          padding: '8px 12px',
                          backgroundColor: 'var(--color-page-bg)',
                          borderRadius: 'var(--radius-md)',
                          borderLeft: '3px solid var(--color-accent)',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                              <span style={{ fontWeight: 500, fontSize: 'var(--font-size-sm)' }}>{score.category}</span>
                              <span style={{
                                fontWeight: 700,
                                color: score.score >= 4 ? 'var(--color-success)' : score.score >= 3 ? 'var(--color-warning)' : 'var(--color-danger)',
                              }}>
                                {score.score}/5
                              </span>
                            </div>
                            {score.note && (
                              <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
                                {score.note}
                              </p>
                            )}
                          </div>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleStartEdit(score); }}
                            className="btn btn-outline"
                            style={{
                              fontSize: 11,
                              padding: '2px 10px',
                              flexShrink: 0,
                              marginLeft: 8,
                            }}
                          >
                            Edit
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              )}
            </div>
          </div>

          {/* Score Form — Create mode (hidden when all categories scored) / Edit mode (always available via Edit button) */}
          <div className="card">
            <div className="card-header">
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, color: 'var(--color-primary)' }}>
                {isEditing ? 'Edit Score' : 'Submit Score'}
              </h3>
            </div>
            <div className="card-body">
              {!isEditing && allCategoriesScored ? (
                <div style={{ textAlign: 'center', padding: 16 }}>
                  <p style={{ fontSize: 32, marginBottom: 8 }}>✅</p>
                  <p style={{ color: 'var(--color-text-secondary)' }}>
                    You've scored all categories for this candidate.
                  </p>
                  {candidate.scores?.length > 0 && (
                    <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-accent)', marginTop: 8 }}>
                      Click the <strong>Edit</strong> button on a score above to edit it.
                    </p>
                  )}
                </div>
              ) : (
                <form onSubmit={handleSubmitScore} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div className="form-group">
                    <label className="form-label">Category</label>
                    {isEditing ? (
                      <div style={{
                        padding: '8px 12px',
                        backgroundColor: 'var(--color-page-bg)',
                        borderRadius: 'var(--radius-md)',
                        color: 'var(--color-text-secondary)',
                        fontWeight: 500,
                        fontSize: 'var(--font-size-sm)',
                      }}>
                        {scoreCategory}
                      </div>
                    ) : (
                      <>
                        <select
                          className="form-select"
                          value={scoreCategory}
                          onChange={(e) => setScoreCategory(e.target.value)}
                        >
                          {availableCategories.map((cat) => (
                            <option key={cat} value={cat}>{cat}</option>
                          ))}
                        </select>
                        {availableCategories.length < SCORE_CATEGORIES.length && (
                          <p style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginTop: 4 }}>
                            {SCORE_CATEGORIES.length - availableCategories.length} of {SCORE_CATEGORIES.length} categories scored.
                          </p>
                        )}
                      </>
                    )}
                  </div>

                  <div className="form-group">
                    <label className="form-label">Score (1-5)</label>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <input
                        type="range"
                        min="1"
                        max="5"
                        step="0.5"
                        value={scoreValue}
                        onChange={(e) => setScoreValue(parseFloat(e.target.value))}
                        style={{ flex: 1, accentColor: 'var(--color-accent)' }}
                      />
                      <span style={{
                        fontWeight: 700,
                        fontSize: 18,
                        minWidth: 36,
                        textAlign: 'center',
                        color: scoreValue >= 4 ? 'var(--color-success)' : scoreValue >= 3 ? 'var(--color-warning)' : 'var(--color-danger)',
                      }}>
                        {scoreValue}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--color-text-secondary)', padding: '0 2px' }}>
                      <span>1 (Poor)</span>
                      <span>5 (Excellent)</span>
                    </div>
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      {isEditing && isAdmin ? "Reviewer's Note (read-only)" : 'Note (optional)'}
                    </label>
                    {isEditing && isAdmin ? (
                      <div style={{
                        padding: '8px 12px',
                        backgroundColor: 'var(--color-page-bg)',
                        borderRadius: 'var(--radius-md)',
                        color: 'var(--color-text-secondary)',
                        fontSize: 'var(--font-size-sm)',
                        lineHeight: 1.6,
                        minHeight: 48,
                      }}>
                        {scoreNote || 'No note provided by reviewer.'}
                      </div>
                    ) : (
                      <textarea
                        className="form-textarea"
                        value={scoreNote}
                        onChange={(e) => setScoreNote(e.target.value)}
                        placeholder="Add notes about this score..."
                        rows={3}
                      />
                    )}
                  </div>

                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      type="submit"
                      className="btn btn-primary"
                      disabled={submittingScore}
                      style={{ justifyContent: 'center', flex: 1 }}
                    >
                      {submittingScore ? (
                        <>
                          <span className="spinner" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} />
                          {isEditing ? 'Updating...' : 'Submitting...'}
                        </>
                      ) : (
                        isEditing ? 'Update Score' : 'Submit Score'
                      )}
                    </button>
                    {isEditing && (
                      <button
                        type="button"
                        className="btn btn-outline"
                        onClick={handleCancelEdit}
                        style={{ justifyContent: 'center' }}
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* CV Modal */}
      {cvModalOpen && cvFileUrl && (
        <div className="modal-overlay" onClick={handleCloseCv}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 18 }}>📄</span>
                <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, color: 'var(--color-primary)' }}>
                  {cvFileName}
                </h3>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {cvBlobUrl && (
                  <a
                    href={cvApiEndpoint}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-outline"
                    style={{ fontSize: 'var(--font-size-sm)', padding: '4px 10px' }}
                  >
                    Open in new tab
                  </a>
                )}
                <button
                  className="modal-close-btn"
                  onClick={handleCloseCv}
                  title="Close"
                >
                  ✕
                </button>
              </div>
            </div>
            <div className="modal-body">
              {/* Loading state */}
              {cvLoading && (
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%',
                  gap: 16,
                  color: 'var(--color-text-secondary)',
                }}>
                  <div className="spinner spinner-lg" />
                  <p>Loading CV...</p>
                </div>
              )}

              {/* Error state */}
              {cvError && !cvLoading && (
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%',
                  gap: 12,
                  color: 'var(--color-text-secondary)',
                  padding: 'var(--space-lg)',
                  textAlign: 'center',
                }}>
                  <p style={{ fontSize: 48 }}>⚠️</p>
                  <p style={{ fontWeight: 500, color: 'var(--color-danger)' }}>
                    Failed to load CV
                  </p>
                  <p style={{ fontSize: 'var(--font-size-sm)' }}>
                    {cvError}
                  </p>
                  <button
                    className="btn btn-accent"
                    onClick={loadCv}
                  >
                    Retry
                  </button>
                </div>
              )}

              {/* PDF: render in iframe */}
              {cvBlobUrl && !cvLoading && !cvError && !isImageType && (
                <iframe
                  src={cvBlobUrl}
                  title="CV Preview"
                  style={{
                    width: '100%',
                    height: '100%',
                    border: 'none',
                    borderRadius: 'var(--radius-md)',
                  }}
                />
              )}

              {/* Image: render as img */}
              {cvBlobUrl && !cvLoading && !cvError && isImageType && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%',
                  padding: 'var(--space-md)',
                  overflow: 'auto',
                }}>
                  <img
                    src={cvBlobUrl}
                    alt="CV Preview"
                    style={{
                      maxWidth: '100%',
                      maxHeight: '100%',
                      objectFit: 'contain',
                      borderRadius: 'var(--radius-sm)',
                      boxShadow: 'var(--shadow-sm)',
                    }}
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
