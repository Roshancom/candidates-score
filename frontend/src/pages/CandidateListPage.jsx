import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../api/auth';
import { getCandidates, getArchivedCandidates, deleteCandidate, restoreCandidate, getSeedCount, seedTestCandidates, deleteSeedCandidates } from '../api/client';
import StatusBadge from '../components/StatusBadge';
import PaginationFooter from '../components/PaginationFooter';

const STATUS_OPTIONS = ['', 'new', 'reviewed', 'hired', 'rejected', 'archived'];
const PAGE_SIZE_OPTIONS = [20, 50];
const TAB_ACTIVE = 'active';
const TAB_ARCHIVED = 'archived';

export default function CandidateListPage() {
  const { apiFetch, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Read all filter/pagination state from URL query params
  // Clamp pageSize to valid values to handle manual URL manipulation
  const rawPageSize = parseInt(searchParams.get('page_size') || '20', 10);
  const pageSize = Math.min(50, Math.max(1, rawPageSize || 20));
  const tab = searchParams.get('tab') || TAB_ACTIVE;
  const page = parseInt(searchParams.get('page') || '1', 10);
  const statusFilter = searchParams.get('status') || '';
  const roleFilter = searchParams.get('role_applied') || '';
  const skillFilter = searchParams.get('skill') || '';
  const keywordFilter = searchParams.get('keyword') || '';

  const [candidates, setCandidates] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, page_size: 20, total_count: 0, total_pages: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Seed data state
  const [seedCount, setSeedCount] = useState(0);
  const [seeding, setSeeding] = useState(false);
  const [removingSeed, setRemovingSeed] = useState(false);
  const [confirmSeedRemove, setConfirmSeedRemove] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  // Confirmation dialog state
  const [confirmCandidate, setConfirmCandidate] = useState(null);
  const [confirmAction, setConfirmAction] = useState(null);
  const [confirming, setConfirming] = useState(false);

  // Unique roles for filter dropdown
  const [roles, setRoles] = useState([]);

  const isArchived = tab === TAB_ARCHIVED;
  const { total_count: totalCount, total_pages: totalPages } = pagination;

  /** Update URL params — resets page to 1 when filters change. */
  const updateParams = useCallback((updates) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      // If any filter (not page/page_size) changed, reset page to 1
      const filterKeys = ['status', 'role_applied', 'skill', 'keyword', 'tab'];
      const isFilterChange = Object.keys(updates).some((k) => filterKeys.includes(k));

      for (const [key, value] of Object.entries(updates)) {
        if (value === '' || value === null || value === undefined) {
          next.delete(key);
        } else {
          next.set(key, String(value));
        }
      }

      if (isFilterChange) {
        next.delete('page');
      }

      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const setTab = (t) => updateParams({ tab: t });
  const setPage = (p) => updateParams({ page: p });
  const setPageSize = (ps) => updateParams({ page_size: ps });
  const setStatusFilter = (v) => updateParams({ status: v, page_size: pageSize });
  const setRoleFilter = (v) => updateParams({ role_applied: v, page_size: pageSize });
  const setSkillFilter = (v) => updateParams({ skill: v, page_size: pageSize });
  const setKeywordFilter = (v) => updateParams({ keyword: v, page_size: pageSize });

  const fetchCandidates = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const fetcher = isArchived ? getArchivedCandidates : getCandidates;
      const data = await fetcher(apiFetch, {
        status: statusFilter || undefined,
        role_applied: roleFilter || undefined,
        skill: skillFilter || undefined,
        keyword: keywordFilter || undefined,
        page,
        page_size: pageSize,
      });
      setCandidates(data.data);
      setPagination(data.pagination);

      // Collect unique roles from returned data
      if (data.data.length > 0) {
        const uniqueRoles = [...new Set(data.data.map((c) => c.role_applied))];
        setRoles((prev) => {
          const all = new Set([...prev, ...uniqueRoles]);
          return [...all].sort();
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [apiFetch, isArchived, statusFilter, roleFilter, skillFilter, keywordFilter, page, pageSize]);

  // Fetch on mount and when deps change
  useEffect(() => {
    fetchCandidates();
  }, [fetchCandidates]);

  const fetchSeedCount = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const data = await getSeedCount(apiFetch);
      setSeedCount(data.count || 0);
    } catch {
      // Silently fail
    }
  }, [apiFetch, isAdmin]);

  useEffect(() => {
    fetchSeedCount();
  }, [fetchSeedCount]);

  // Button state helpers: mutually exclusive based on seed data existence
  const seedExists = seedCount > 0;
  const anySeedOperationInFlight = seeding || removingSeed;
  const injectDisabled = anySeedOperationInFlight || seedExists;
  const removeDisabled = anySeedOperationInFlight || !seedExists;

  const handleInjectSeed = async () => {
    setSeeding(true);
    setError('');
    setSuccessMessage('');
    try {
      const data = await seedTestCandidates(apiFetch);
      setSuccessMessage(data.message || `Inserted ${data.inserted} test candidates`);
      setSeedCount(data.inserted || 80);
      updateParams({ page: 1 });
      await fetchCandidates();
    } catch (err) {
      setError(err.message);
      fetchSeedCount();
    } finally {
      setSeeding(false);
    }
  };

  const handleRemoveSeed = async () => {
    setRemovingSeed(true);
    setError('');
    setSuccessMessage('');
    try {
      const data = await deleteSeedCandidates(apiFetch);
      setSuccessMessage(data.message || `Removed ${data.deleted} test candidate(s)`);
      setSeedCount(0);
      setConfirmSeedRemove(false);
      updateParams({ page: 1 });
      await fetchCandidates();
    } catch (err) {
      setError(err.message);
      fetchSeedCount();
    } finally {
      setRemovingSeed(false);
    }
  };

  // Auto-dismiss success message after 4 seconds
  useEffect(() => {
    if (!successMessage) return;
    const timer = setTimeout(() => setSuccessMessage(''), 4000);
    return () => clearTimeout(timer);
  }, [successMessage]);

  // StatusBadge is used instead of inline statusBadgeClass

  const handleDelete = async () => {
    if (!confirmCandidate) return;
    setConfirming(true);
    try {
      await deleteCandidate(apiFetch, confirmCandidate.id);
      setConfirmCandidate(null);
      setConfirmAction(null);
      await fetchCandidates();
    } catch (err) {
      setError(err.message);
    } finally {
      setConfirming(false);
    }
  };

  const handleRestore = async () => {
    if (!confirmCandidate) return;
    setConfirming(true);
    try {
      await restoreCandidate(apiFetch, confirmCandidate.id);
      setConfirmCandidate(null);
      setConfirmAction(null);
      await fetchCandidates();
    } catch (err) {
      setError(err.message);
    } finally {
      setConfirming(false);
    }
  };

  const openConfirm = (candidate, action) => {
    setConfirmCandidate(candidate);
    setConfirmAction(action);
  };

  const closeConfirm = () => {
    setConfirmCandidate(null);
    setConfirmAction(null);
  };

  const colSpan = isAdmin ? 8 : 7;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Candidates</h1>
        <p className="page-subtitle">Review and score candidate applications</p>

        {/* Admin seed data controls — testing-only tools */}
        {isAdmin && (<>
          <div role="note" aria-label="Testing tools information"
            style={{ marginTop: 16, padding: '10px 14px', borderRadius: 'var(--radius-md)',
              backgroundColor: 'rgba(59, 125, 216, 0.06)', border: '1px solid rgba(59, 125, 216, 0.15)',
              fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)', lineHeight: 1.5 }}>
            ℹ️ These controls are for testing purposes only. Use <strong>Inject 80 Test Candidates</strong> to
            generate sample data for validating pagination, filtering, and search behavior. Injected records are
            tagged as test data and can be fully removed with <strong>Remove Test Candidates</strong> without
            affecting real candidates.
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button
              className="btn btn-outline"
              onClick={handleInjectSeed}
              disabled={injectDisabled}
              title={seedExists ? 'Remove existing test data first' : 'Inject 80 test candidates'}
              style={{ fontSize: 13 }}
            >
              {seeding ? (
                <>
                  <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                  Injecting...
                </>
              ) : (
                'Inject 80 Test Candidates'
              )}
            </button>
            <button
              className="btn btn-outline"
              onClick={() => setConfirmSeedRemove(true)}
              disabled={removeDisabled}
              title={!seedExists ? 'No test data to remove' : 'Remove all test candidates'}
              style={{
                fontSize: 13,
                color: seedExists ? 'var(--color-danger)' : 'var(--color-text-secondary)',
                borderColor: seedExists ? 'var(--color-danger)' : 'var(--color-border)',
              }}
            >
              {removingSeed ? (
                <>
                  <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                  Removing...
                </>
              ) : (
                `Remove Test Candidates${seedExists ? ` (${seedCount})` : ''}`
              )}
            </button>
          </div>
        </>)}
      </div>

      {/* Tabs */}
      {isAdmin && (
        <div style={{ display: 'flex', gap: 0, marginBottom: 24, borderBottom: '2px solid var(--color-border)' }}>
          <button onClick={() => setTab(TAB_ACTIVE)}
            style={{
              padding: '10px 24px', border: 'none', background: 'none', cursor: 'pointer',
              fontWeight: tab === TAB_ACTIVE ? 600 : 400,
              color: tab === TAB_ACTIVE ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              borderBottom: tab === TAB_ACTIVE ? '2px solid var(--color-accent)' : '2px solid transparent',
              marginBottom: -2, transition: 'color 0.12s, border-color 0.12s', fontSize: 'var(--font-size-sm)',
            }}
          >Active</button>
          <button onClick={() => setTab(TAB_ARCHIVED)}
            style={{
              padding: '10px 24px', border: 'none', background: 'none', cursor: 'pointer',
              fontWeight: tab === TAB_ARCHIVED ? 600 : 400,
              color: tab === TAB_ARCHIVED ? 'var(--color-accent)' : 'var(--color-text-secondary)',
              borderBottom: tab === TAB_ARCHIVED ? '2px solid var(--color-accent)' : '2px solid transparent',
              marginBottom: -2, transition: 'color 0.12s, border-color 0.12s', fontSize: 'var(--font-size-sm)',
            }}
          >Archived</button>
        </div>
      )}

      {/* Filters */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-body">
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div className="form-group" style={{ minWidth: 160 }}>
              <label className="form-label">Status</label>
              <select className="form-select" value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">All Statuses</option>
                {STATUS_OPTIONS.filter(Boolean).map((s) => (
                  <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
                ))}
              </select>
            </div>

            <div className="form-group" style={{ minWidth: 160 }}>
              <label className="form-label">Role</label>
              <select className="form-select" value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}>
                <option value="">All Roles</option>
                {roles.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>

            <div className="form-group" style={{ minWidth: 140 }}>
              <label className="form-label">Skill</label>
              <input className="form-input" placeholder="e.g. React"
                value={skillFilter}
                onChange={(e) => setSkillFilter(e.target.value)} />
            </div>

            <div className="form-group" style={{ minWidth: 180, flex: 1 }}>
              <label className="form-label">Search</label>
              <input className="form-input" placeholder="Name or email..."
                value={keywordFilter}
                onChange={(e) => setKeywordFilter(e.target.value)} />
            </div>

            <button className="btn btn-accent" onClick={fetchCandidates} style={{ height: 36 }}>
              Search
            </button>
          </div>
        </div>
      </div>

      {/* Success message */}
      {successMessage && (
        <div className="alert alert-success" style={{ marginBottom: 16 }}>{successMessage}</div>
      )}
      {/* Error */}
      {error && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>
      )}

      {/* Results summary */}
      {!loading && (
        <div style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)', marginBottom: 8 }}>
          {totalCount} candidate{totalCount !== 1 ? 's' : ''} found
          {isArchived ? ' (archived)' : ''}
        </div>
      )}

      {/* Table */}
      <div className="card">
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Skills</th><th>Score</th><th>Created</th>
                {isAdmin && <th style={{ width: 100 }}>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={colSpan} style={{ textAlign: 'center', padding: 40 }}>
                    <div className="spinner spinner-lg" style={{ margin: '0 auto' }} />
                  </td>
                </tr>
              ) : candidates.length === 0 ? (
                <tr>
                  <td colSpan={colSpan} style={{ textAlign: 'center', padding: 40, color: 'var(--color-text-secondary)' }}>
                    {isArchived ? 'No archived candidates found' : 'No candidates found'}
                  </td>
                </tr>
              ) : (
                candidates.map((candidate) => (
                  <tr key={candidate.id} className={isArchived ? '' : 'clickable'}
                    onClick={() => { if (!isArchived) navigate(`/candidates/${candidate.id}`); }}>
                    <td style={{ fontWeight: 500 }}>{candidate.name}</td>
                    <td style={{ color: 'var(--color-text-secondary)' }}>{candidate.email}</td>
                    <td>{candidate.role_applied}</td>
                    <td><StatusBadge status={candidate.status} /></td>
                    <td>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {(candidate.skills || []).map((skill) => (
                          <span key={skill} style={{
                            padding: '1px 8px', fontSize: 'var(--font-size-sm)',
                            backgroundColor: 'var(--color-page-bg)', borderRadius: 'var(--radius-sm)',
                            color: 'var(--color-text-secondary)',
                          }}>{skill}</span>
                        ))}
                      </div>
                    </td>
                    <td>
                      {candidate.average_score != null ? (
                        <span title={`${candidate.score_count} score${candidate.score_count !== 1 ? 's' : ''} across all reviewers`}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 6, fontWeight: 600,
                            fontSize: 'var(--font-size-sm)',
                            color: candidate.average_score >= 4 ? 'var(--color-success, #16a34a)'
                              : candidate.average_score >= 3 ? 'var(--color-warning, #f59e0b)'
                              : 'var(--color-danger, #dc2626)',
                          }}>
                          {candidate.average_score}/5
                          <span style={{ fontWeight: 400, fontSize: 11, color: 'var(--color-text-secondary)' }}>
                            ({candidate.score_count})
                          </span>
                        </span>
                      ) : (
                        <span style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)', opacity: 0.6 }}>—</span>
                      )}
                    </td>
                    <td style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)' }}>
                      {new Date(candidate.created_at).toLocaleDateString()}
                    </td>
                    {isAdmin && (
                      <td>
                        {isArchived ? (
                          <button className="btn btn-accent"
                            style={{ fontSize: 11, padding: '3px 10px' }}
                            onClick={(e) => { e.stopPropagation(); openConfirm(candidate, 'restore'); }}>Restore</button>
                        ) : (
                          <button className="btn btn-outline"
                            style={{ fontSize: 11, padding: '3px 10px',
                              color: 'var(--color-danger)', borderColor: 'var(--color-danger)' }}
                            onClick={(e) => { e.stopPropagation(); openConfirm(candidate, 'delete'); }}>Delete</button>
                        )}
                      </td>
                    )}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination + page-size selector — only show when multiple pages */}
        {totalPages > 1 && (
        <div className="pagination">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <label className="form-label" style={{ margin: 0, whiteSpace: 'nowrap' }}>Per page</label>
            <select className="form-select" value={pageSize}
              onChange={(e) => setPageSize(parseInt(e.target.value, 10))}
              style={{ width: 70, padding: '4px 8px', fontSize: 'var(--font-size-sm)' }}>
              {PAGE_SIZE_OPTIONS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <PaginationFooter
            page={page}
            totalPages={totalPages}
            totalCount={totalCount}
            loading={loading}
            onPageChange={setPage}
          />
        </div>
        )}
      </div>

      {/* Confirmation Dialog */}
      {confirmCandidate && (
        <div
          className="modal-overlay"
          onClick={closeConfirm}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <div
            className="card"
            style={{ maxWidth: 420, width: '90%', position: 'relative' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-body" style={{ textAlign: 'center', padding: 'var(--space-lg)' }}>
              <p style={{ fontSize: 36, marginBottom: 12 }}>
                {confirmAction === 'delete' ? '🗑️' : '♻️'}
              </p>
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 8 }}>
                {confirmAction === 'delete' ? 'Archive candidate?' : 'Restore candidate?'}
              </h3>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: 20 }}>
                {confirmAction === 'delete'
                  ? `Are you sure you want to archive "${confirmCandidate.name}"? It can be restored later from the Archived tab.`
                  : `Are you sure you want to restore "${confirmCandidate.name}"? It will reappear in the Active list.`}
              </p>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                <button
                  className="btn btn-outline"
                  onClick={closeConfirm}
                  disabled={confirming}
                >
                  Cancel
                </button>
                <button
                  className={confirmAction === 'delete' ? 'btn btn-danger' : 'btn btn-accent'}
                  onClick={confirmAction === 'delete' ? handleDelete : handleRestore}
                  disabled={confirming}
                  style={{ justifyContent: 'center', minWidth: 100 }}
                >
                  {confirming ? (
                    <>
                      <span className="spinner" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} />
                      {confirmAction === 'delete' ? 'Archiving...' : 'Restoring...'}
                    </>
                  ) : (
                    confirmAction === 'delete' ? 'Archive' : 'Restore'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Seed Remove Confirmation Dialog */}
      {confirmSeedRemove && (
        <div
          className="modal-overlay"
          onClick={() => { if (!removingSeed) setConfirmSeedRemove(false); }}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}
        >
          <div
            className="card"
            style={{ maxWidth: 420, width: '90%', position: 'relative' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-body" style={{ textAlign: 'center', padding: 'var(--space-lg)' }}>
              <p style={{ fontSize: 36, marginBottom: 12 }}>🧹</p>
              <h3 style={{ fontSize: 'var(--font-size-lg)', fontWeight: 600, marginBottom: 8 }}>
                Remove Test Candidates?
              </h3>
              <p style={{ color: 'var(--color-text-secondary)', marginBottom: 20 }}>
                This will remove <strong>{seedCount}</strong> test candidate{seedCount !== 1 ? 's' : ''} permanently. 
                Real candidate records will not be affected.
              </p>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                <button
                  className="btn btn-outline"
                  onClick={() => setConfirmSeedRemove(false)}
                  disabled={removingSeed}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-danger"
                  onClick={handleRemoveSeed}
                  disabled={removingSeed}
                  style={{ justifyContent: 'center', minWidth: 100 }}
                >
                  {removingSeed ? (
                    <>
                      <span className="spinner" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} />
                      Removing...
                    </>
                  ) : (
                    `Remove ${seedCount} Test Candidate${seedCount !== 1 ? 's' : ''}`
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
