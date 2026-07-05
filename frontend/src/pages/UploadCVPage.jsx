import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../api/auth';

export default function UploadCVPage() {
  const { apiFetch } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [roleApplied, setRoleApplied] = useState('Senior Frontend Engineer');
  const [skills, setSkills] = useState('');
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Reviewer assignment
  const [reviewers, setReviewers] = useState([]);
  const [selectedReviewerId, setSelectedReviewerId] = useState('');
  const [loadingReviewers, setLoadingReviewers] = useState(true);

  useEffect(() => {
    // Fetch available reviewers for assignment
    apiFetch('/auth/users/reviewers')
      .then((data) => {
        setReviewers(data || []);
        setLoadingReviewers(false);
      })
      .catch(() => setLoadingReviewers(false));
  }, [apiFetch]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSubmitting(true);

    try {
      // Build the create payload
      const payload = {
        name,
        email,
        role_applied: roleApplied,
        skills: skills.split(',').map((s) => s.trim()).filter(Boolean),
      };
      // Assign reviewer if selected
      if (selectedReviewerId) {
        payload.assigned_reviewer_id = parseInt(selectedReviewerId, 10);
      }

      // First create the candidate
      const candidate = await apiFetch('/candidates', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      // Upload the CV file via the protected endpoint
      if (file) {
        const formData = new FormData();
        formData.append('file', file);

        const uploadRes = await fetch(`/api/candidates/${candidate.id}/cv`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${localStorage.getItem('token')}`,
          },
          body: formData,
        });

        if (!uploadRes.ok) {
          const errData = await uploadRes.json().catch(() => ({}));
          throw new Error(errData.detail || 'Failed to upload CV');
        }
      }

      setSuccess(`Candidate "${name}" created successfully!`);
      setName('');
      setEmail('');
      setRoleApplied('Senior Frontend Engineer');
      setSkills('');
      setFile(null);
      setSelectedReviewerId('');
    } catch (err) {
      setError(err.message || 'Failed to create candidate');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="page-container">
      <div className="page-header">
        <h1 className="page-title">Upload CV</h1>
        <p className="page-subtitle">Add a new candidate with their CV file</p>
      </div>

      <div className="card" style={{ maxWidth: 600 }}>
        <div className="card-body">
          {error && (
            <div className="alert alert-error" style={{ marginBottom: 16 }}>
              {error}
            </div>
          )}
          {success && (
            <div className="alert alert-success" style={{ marginBottom: 16 }}>
              {success}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div className="form-group">
              <label className="form-label">Name</label>
              <input
                className="form-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Candidate name"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Email</label>
              <input
                className="form-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="candidate@example.com"
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">Role Applied</label>
              <select
                className="form-select"
                value={roleApplied}
                onChange={(e) => setRoleApplied(e.target.value)}
                required
              >
                <option value="Senior Frontend Engineer">Senior Frontend Engineer</option>
                <option value="Full Stack Developer">Full Stack Developer</option>
                <option value="Backend Engineer">Backend Engineer</option>
                <option value="DevOps Engineer">DevOps Engineer</option>
                <option value="Data Engineer">Data Engineer</option>
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Skills (comma-separated)</label>
              <input
                className="form-input"
                value={skills}
                onChange={(e) => setSkills(e.target.value)}
                placeholder="React, TypeScript, CSS"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Assign to Reviewer</label>
              <select
                className="form-select"
                value={selectedReviewerId}
                onChange={(e) => setSelectedReviewerId(e.target.value)}
                disabled={loadingReviewers}
              >
                <option value="">-- Not assigned --</option>
                {reviewers.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.email}
                  </option>
                ))}
              </select>
              {loadingReviewers && (
                <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-secondary)', marginTop: 4 }}>
                  Loading reviewers...
                </p>
              )}
            </div>

            <div className="form-group">
              <label className="form-label">CV File (PDF, PNG, JPG)</label>
              <input
                className="form-input"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={(e) => setFile(e.target.files[0])}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting}
              style={{ justifyContent: 'center', marginTop: 8 }}
            >
              {submitting ? 'Creating...' : 'Create Candidate & Upload CV'}
            </button>
          </form>

          <div style={{ marginTop: 16, padding: 12, backgroundColor: 'var(--color-page-bg)', borderRadius: 'var(--radius-md)', fontSize: 'var(--font-size-sm)' }}>
            <p style={{ color: 'var(--color-text-secondary)' }}>
              Select a reviewer to assign the candidate during creation. The reviewer will then be able to view the CV.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
