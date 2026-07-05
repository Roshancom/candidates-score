import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../api/auth';

const ALLOWED_ROLES = [
  'Senior Frontend Engineer',
  'Backend Engineer',
  'Full Stack Developer',
  'DevOps Engineer',
  'Data Engineer',
  'Software Engineer',
  'Machine Learning Engineer',
  'Product Manager',
  'QA Engineer',
  'Mobile Developer',
  'Security Engineer',
  'Solutions Architect',
];

const MAX_CV_SIZE = 5 * 1024 * 1024; // 5 MB
const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

export default function UploadCVPage() {
  const { apiFetch } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [roleApplied, setRoleApplied] = useState('');
  const [skills, setSkills] = useState('');
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Per-field validation errors
  const [errors, setErrors] = useState({
    name: '',
    email: '',
    role_applied: '',
    skills: '',
    cv: '',
  });
  const [touched, setTouched] = useState({});

  // Client-side CV validation state
  const [cvUploadError, setCvUploadError] = useState('');

  // --- Validation helpers ---
  const validateName = (val) => {
    const trimmed = val.trim();
    if (!trimmed) return 'Name is required';
    if (trimmed.length > 100) return 'Name must be 100 characters or fewer';
    if (!/[a-zA-Z]/.test(trimmed)) return 'Name must contain at least one letter';
    return '';
  };

  const validateEmail = (val) => {
    const trimmed = val.trim();
    if (!trimmed) return 'Email is required';
    if (!EMAIL_REGEX.test(trimmed)) return 'Invalid email format';
    return '';
  };

  const validateRole = (val) => {
    if (!val) return 'Please select a role';
    if (!ALLOWED_ROLES.includes(val)) return 'Invalid role selection';
    return '';
  };

  const validateSkills = (val) => {
    const items = val.split(',').map((s) => s.trim()).filter(Boolean);
    if (items.length === 0) return 'At least one skill is required';
    if (items.length > 20) return 'Maximum 20 skills allowed';
    for (const s of items) {
      if (s.length > 50) return `Skill "${s}" exceeds 50 character limit`;
    }
    return '';
  };

  const validateCvFile = (f) => {
    if (!f) return 'CV file is required';
    const ext = f.name.split('.').pop().toLowerCase();
    if (ext !== 'pdf') return 'Only PDF files are accepted.';
    if (f.size > MAX_CV_SIZE) return 'File exceeds the maximum size of 5 MB.';
    return '';
  };

  const runFieldValidation = (field, value) => {
    let err = '';
    switch (field) {
      case 'name': err = validateName(value); break;
      case 'email': err = validateEmail(value); break;
      case 'role_applied': err = validateRole(value); break;
      case 'skills': err = validateSkills(value); break;
      case 'cv': err = validateCvFile(value); break;
    }
    setErrors((prev) => ({ ...prev, [field]: err }));
    return err;
  };

  const handleBlur = (field) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    let value;
    switch (field) {
      case 'name': value = name; break;
      case 'email': value = email; break;
      case 'role_applied': value = roleApplied; break;
      case 'skills': value = skills; break;
      case 'cv': value = file; break;
    }
    runFieldValidation(field, value);
  };

  const handleFileChange = (e) => {
    const f = e.target.files[0];
    setFile(f);
    setTouched((prev) => ({ ...prev, cv: true }));
    const err = validateCvFile(f);
    setErrors((prev) => ({ ...prev, cv: err }));
  };

  // --- Check if form is valid ---
  const isFormValid = () => {
    return (
      !validateName(name) &&
      !validateEmail(email) &&
      !validateRole(roleApplied) &&
      !validateSkills(skills) &&
      !validateCvFile(file)
    );
  };

  // --- Reviewer list ---
  const [reviewers, setReviewers] = useState([]);
  const [selectedReviewerId, setSelectedReviewerId] = useState('');
  const [loadingReviewers, setLoadingReviewers] = useState(true);

  useEffect(() => {
    apiFetch('/auth/users/reviewers')
      .then((data) => {
        setReviewers(data || []);
        setLoadingReviewers(false);
      })
      .catch(() => setLoadingReviewers(false));
  }, [apiFetch]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    // Touch all fields and run full validation
    const allTouched = { name: true, email: true, role_applied: true, skills: true, cv: true };
    setTouched(allTouched);

    const nameErr = runFieldValidation('name', name);
    const emailErr = runFieldValidation('email', email);
    const roleErr = runFieldValidation('role_applied', roleApplied);
    const skillsErr = runFieldValidation('skills', skills);
    const cvErr = runFieldValidation('cv', file);

    if (nameErr || emailErr || roleErr || skillsErr || cvErr) {
      return;
    }

    setSubmitting(true);
    setCvUploadError('');

    try {
      // Build the create payload
      const payload = {
        name: name.trim(),
        email: email.trim(),
        role_applied: roleApplied,
        skills: skills.split(',').map((s) => s.trim()).filter(Boolean),
      };
      if (selectedReviewerId) {
        payload.assigned_reviewer_id = parseInt(selectedReviewerId, 10);
      }

      // First create the candidate
      const candidate = await apiFetch('/candidates', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      // Upload the CV file via the protected endpoint
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
        const errMsg = errData.detail || 'Failed to upload CV';
        setCvUploadError(errMsg);
        throw new Error(errMsg);
      }

      setSuccess(`Candidate "${name.trim()}" created successfully!`);
      setName('');
      setEmail('');
      setRoleApplied('');
      setSkills('');
      setFile(null);
      setSelectedReviewerId('');
      setErrors({ name: '', email: '', role_applied: '', skills: '', cv: '' });
      setTouched({});
    } catch (err) {
      const msg = err.message || '';
      // Surface backend field-level Pydantic 422 errors
      if (err.detail && Array.isArray(err.detail)) {
        // FastAPI 422 validation error
        for (const e of err.detail) {
          const field = e.loc?.slice(-1)?.[0];
          if (field && ['name', 'email', 'role_applied', 'skills'].includes(field)) {
            setErrors((prev) => ({ ...prev, [field]: e.msg }));
            setTouched((prev) => ({ ...prev, [field]: true }));
          }
        }
      } else if (msg.toLowerCase().includes('email') && msg.toLowerCase().includes('already exists')) {
        setErrors((prev) => ({ ...prev, email: msg }));
      } else if (msg.toLowerCase().includes('reviewer')) {
        setErrors((prev) => ({ ...prev, role_applied: msg }));
      } else {
        setError(msg || 'Failed to create candidate');
      }
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

          {/* Backend CV upload error surfaced inline */}
          {cvUploadError && (
            <div className="alert alert-error" style={{ marginBottom: 16 }}>
              CV upload error: {cvUploadError}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Name */}
            <div className="form-group">
              <label className="form-label">Name</label>
              <input
                className={`form-input${touched.name && errors.name ? ' form-input-error' : ''}`}
                value={name}
                onChange={(e) => { setName(e.target.value); if (touched.name) runFieldValidation('name', e.target.value); }}
                onBlur={() => handleBlur('name')}
                placeholder="Candidate name"
                required
              />
              {touched.name && errors.name && (
                <p className="field-error">{errors.name}</p>
              )}
            </div>

            {/* Email */}
            <div className="form-group">
              <label className="form-label">Email</label>
              <input
                className={`form-input${touched.email && errors.email ? ' form-input-error' : ''}`}
                type="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); if (touched.email) runFieldValidation('email', e.target.value); }}
                onBlur={() => handleBlur('email')}
                placeholder="candidate@example.com"
                required
              />
              {touched.email && errors.email && (
                <p className="field-error">{errors.email}</p>
              )}
            </div>

            {/* Role Applied */}
            <div className="form-group">
              <label className="form-label">Role Applied</label>
              <select
                className={`form-select${touched.role_applied && errors.role_applied ? ' form-input-error' : ''}`}
                value={roleApplied}
                onChange={(e) => { setRoleApplied(e.target.value); if (touched.role_applied) runFieldValidation('role_applied', e.target.value); }}
                onBlur={() => handleBlur('role_applied')}
                required
              >
                <option value="">-- Select a role --</option>
                {ALLOWED_ROLES.map((role) => (
                  <option key={role} value={role}>{role}</option>
                ))}
              </select>
              {touched.role_applied && errors.role_applied && (
                <p className="field-error">{errors.role_applied}</p>
              )}
            </div>

            {/* Skills */}
            <div className="form-group">
              <label className="form-label">Skills (comma-separated)</label>
              <input
                className={`form-input${touched.skills && errors.skills ? ' form-input-error' : ''}`}
                value={skills}
                onChange={(e) => { setSkills(e.target.value); if (touched.skills) runFieldValidation('skills', e.target.value); }}
                onBlur={() => handleBlur('skills')}
                placeholder="React, TypeScript, CSS"
              />
              {touched.skills && errors.skills && (
                <p className="field-error">{errors.skills}</p>
              )}
            </div>

            {/* Assign to Reviewer */}
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

            {/* CV File */}
            <div className="form-group">
              <label className="form-label">CV File (PDF only, max 5 MB, required)</label>
              <input
                className={`form-input${touched.cv && errors.cv ? ' form-input-error' : ''}`}
                type="file"
                accept=".pdf,application/pdf"
                onChange={handleFileChange}
              />
              {touched.cv && errors.cv && (
                <p className="field-error">{errors.cv}</p>
              )}
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={submitting || !isFormValid()}
              style={{ justifyContent: 'center', marginTop: 8 }}
            >
              {submitting ? (
                <>
                  <span className="spinner" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} />
                  Creating...
                </>
              ) : (
                'Create Candidate & Upload CV'
              )}
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
