import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import CandidateDetailPage from '../pages/CandidateDetailPage';

// Mock the auth context
const mockUseAuth = vi.fn();
vi.mock('../api/auth', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock the API client
vi.mock('../api/client', () => ({
  getCandidate: vi.fn().mockImplementation((apiFetch, id) => {
    return Promise.resolve({
      id: Number(id),
      name: 'Test Candidate',
      email: 'test@example.com',
      role_applied: 'Engineer',
      status: 'new',
      skills: ['React', 'Python'],
      cv_file_url: null,
      is_reviewed_by_current_user: true,
      created_at: '2024-01-01T00:00:00Z',
      scores: [],
      ai_summary: null,
      ai_summary_generated_at: null,
    });
  }),
  submitScore: vi.fn(),
  updateScore: vi.fn(),
  adminUpdateScore: vi.fn(),
  generateSummary: vi.fn(),
  updateCandidate: vi.fn(),
  getNotifications: vi.fn().mockResolvedValue([]),
}));

describe('CandidateDetailPage', () => {
  it('shows AI Summary section with Generate button', async () => {
    mockUseAuth.mockReturnValue({
      apiFetch: vi.fn(),
      isAdmin: false,
      isReviewer: true,
      user: { id: 1, email: 'reviewer@test.com', role: 'reviewer' },
      token: 'mock-token',
      isAuthenticated: true,
    });

    render(
      <MemoryRouter initialEntries={['/candidates/1']}>
        <Routes>
          <Route path="/candidates/:id" element={<CandidateDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    const generateBtn = await screen.findByText('Generate Summary', {}, { timeout: 3000 });
    expect(generateBtn).toBeInTheDocument();
  });

  it('shows Regenerate button when cached AI summary exists', async () => {
    // Override mock with cached summary
    const client = await import('../api/client');
    client.getCandidate.mockResolvedValueOnce({
      id: 1,
      name: 'Test Candidate',
      email: 'test@example.com',
      role_applied: 'Engineer',
      status: 'new',
      skills: ['React'],
      cv_file_url: null,
      is_reviewed_by_current_user: true,
      created_at: '2024-01-01T00:00:00Z',
      scores: [],
      ai_summary: 'This is a cached AI-generated summary.',
      ai_summary_generated_at: '2024-06-01T00:00:00Z',
    });

    mockUseAuth.mockReturnValue({
      apiFetch: vi.fn(),
      isAdmin: false,
      isReviewer: true,
      user: { id: 1, email: 'reviewer@test.com', role: 'reviewer' },
      token: 'mock-token',
      isAuthenticated: true,
    });

    render(
      <MemoryRouter initialEntries={['/candidates/1']}>
        <Routes>
          <Route path="/candidates/:id" element={<CandidateDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    const regenerateBtn = await screen.findByText('Regenerate Summary', {}, { timeout: 3000 });
    expect(regenerateBtn).toBeInTheDocument();

    // Cached summary text should be visible
    const summaryText = await screen.findByText(/This is a cached AI-generated summary/, {}, { timeout: 3000 });
    expect(summaryText).toBeInTheDocument();
  });

  it('does not render internal notes panel for non-admin users', async () => {
    mockUseAuth.mockReturnValue({
      apiFetch: vi.fn(),
      isAdmin: false,
      isReviewer: true,
      user: { id: 1, email: 'reviewer@test.com', role: 'reviewer' },
      token: 'mock-token',
      isAuthenticated: true,
    });

    render(
      <MemoryRouter initialEntries={['/candidates/1']}>
        <Routes>
          <Route path="/candidates/:id" element={<CandidateDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    // Wait for candidate to load
    await screen.findByText('Test Candidate', {}, { timeout: 3000 });

    // Internal Notes heading should NOT be in the document for reviewers
    expect(screen.queryByText('Internal Notes')).not.toBeInTheDocument();
    expect(screen.queryByText('ADMIN ONLY')).not.toBeInTheDocument();
  });

  it('renders internal notes panel for admin users', async () => {
    mockUseAuth.mockReturnValue({
      apiFetch: vi.fn(),
      isAdmin: true,
      isReviewer: false,
      user: { id: 2, email: 'admin@test.com', role: 'admin' },
      token: 'mock-token',
      isAuthenticated: true,
    });

    render(
      <MemoryRouter initialEntries={['/candidates/1']}>
        <Routes>
          <Route path="/candidates/:id" element={<CandidateDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    // Wait for candidate to load
    await screen.findByText('Test Candidate', {}, { timeout: 3000 });

    // Internal Notes should be present for admin
    const notesHeading = screen.getByText('Internal Notes');
    expect(notesHeading).toBeInTheDocument();
  });
});
