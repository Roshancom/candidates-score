// The apiFetch function from useAuth handles all API calls.
// These are convenience helpers that wrap apiFetch.

function buildQuery(params = {}) {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  if (params.role_applied) query.set('role_applied', params.role_applied);
  if (params.skill) query.set('skill', params.skill);
  if (params.keyword) query.set('keyword', params.keyword);
  if (params.page) query.set('page', String(params.page));
  if (params.page_size) query.set('page_size', String(params.page_size));
  return query.toString();
}

export async function getCandidates(apiFetch, params = {}) {
  const qs = buildQuery(params);
  return apiFetch(`/candidates${qs ? `?${qs}` : ''}`);
}

export async function getArchivedCandidates(apiFetch, params = {}) {
  const qs = buildQuery(params);
  return apiFetch(`/candidates/archived${qs ? `?${qs}` : ''}`);
}

export async function getCandidate(apiFetch, id) {
  return apiFetch(`/candidates/${id}`);
}

export async function createCandidate(apiFetch, data) {
  return apiFetch('/candidates', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateCandidate(apiFetch, id, data) {
  return apiFetch(`/candidates/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteCandidate(apiFetch, id) {
  return apiFetch(`/candidates/${id}`, { method: 'DELETE' });
}

export async function restoreCandidate(apiFetch, id) {
  return apiFetch(`/candidates/${id}/restore`, { method: 'PATCH' });
}

export async function submitScore(apiFetch, candidateId, data) {
  return apiFetch(`/candidates/${candidateId}/scores`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateScore(apiFetch, candidateId, scoreId, data) {
  return apiFetch(`/candidates/${candidateId}/scores/${scoreId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function adminUpdateScore(apiFetch, candidateId, scoreId, data) {
  return apiFetch(`/candidates/${candidateId}/admin-score/${scoreId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function generateSummary(apiFetch, candidateId) {
  return apiFetch(`/candidates/${candidateId}/summary`, { method: 'POST' });
}

export async function getReviewCandidates(apiFetch) {
  return apiFetch('/candidates/review');
}

// -------- Admin Seed Data --------

export async function getSeedCount(apiFetch) {
  return apiFetch('/candidates/seed/count');
}

export async function seedTestCandidates(apiFetch) {
  return apiFetch('/candidates/admin/seed', {
    method: 'POST',
  });
}

export async function deleteSeedCandidates(apiFetch) {
  return apiFetch('/candidates/admin/seed', {
    method: 'DELETE',
  });
}

// -------- Notifications --------

export async function getNotifications(apiFetch) {
  return apiFetch('/notifications');
}

export async function getUnreadCount(apiFetch) {
  return apiFetch('/notifications/unread-count');
}

export async function markNotificationsRead(apiFetch, notificationIds = null) {
  let path = '/notifications/read';
  if (notificationIds && notificationIds.length > 0) {
    // Send each ID as a separate query param for FastAPI list parsing
    const params = notificationIds.map((id) => `notification_ids=${id}`).join('&');
    path += `?${params}`;
  }
  return apiFetch(path, {
    method: 'PATCH',
    body: JSON.stringify({}),
  });
}
