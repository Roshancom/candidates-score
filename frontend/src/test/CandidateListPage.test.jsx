import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import CandidateListPage from '../pages/CandidateListPage';

// Hoisted shared state — this is the correct Vitest pattern for per-test mock data
const mockState = vi.hoisted(() => ({
  candidates: { data: [], pagination: { page: 1, page_size: 20, total_count: 0, total_pages: 0 } },
}));

vi.mock('../api/auth', () => ({
  useAuth: () => ({
    apiFetch: vi.fn(),
    isAdmin: false,
    isReviewer: true,
    user: { id: 1, email: 'test@test.com', role: 'reviewer' },
    token: 'mock-token',
    isAuthenticated: true,
  }),
}));

vi.mock('../api/client', () => ({
  getCandidates: vi.fn(() => Promise.resolve(mockState.candidates)),
  getArchivedCandidates: vi.fn().mockResolvedValue({ data: [], pagination: { page: 1, page_size: 20, total_count: 0, total_pages: 0 } }),
  getSeedCount: vi.fn().mockResolvedValue({ count: 0 }),
  seedTestCandidates: vi.fn(),
  deleteSeedCandidates: vi.fn(),
  deleteCandidate: vi.fn(),
  restoreCandidate: vi.fn(),
}));

describe('CandidateListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders pagination footer when there are multiple pages', async () => {
    mockState.candidates = {
      data: Array.from({ length: 25 }, (_, i) => ({
        id: i + 1,
        name: `Candidate ${i + 1}`,
        email: `candidate${i + 1}@test.com`,
        role_applied: 'Engineer',
        status: 'new',
        skills: ['React'],
        created_at: '2024-01-01T00:00:00Z',
        average_score: null,
        score_count: null,
      })),
      pagination: { page: 1, page_size: 20, total_count: 25, total_pages: 2 },
    };

    render(
      <MemoryRouter initialEntries={['/candidates']}>
        <Routes>
          <Route path="/candidates" element={<CandidateListPage />} />
        </Routes>
      </MemoryRouter>
    );

    const paginationText = await screen.findByText(/Page 1 of 2/i, {}, { timeout: 3000 });
    expect(paginationText).toBeInTheDocument();
  });

  it('hides pagination footer when all results fit on one page', async () => {
    mockState.candidates = {
      data: [{
        id: 1,
        name: 'Single Candidate',
        email: 'single@test.com',
        role_applied: 'Engineer',
        status: 'new',
        skills: [],
        created_at: '2024-01-01T00:00:00Z',
        average_score: null,
        score_count: null,
      }],
      pagination: { page: 1, page_size: 20, total_count: 1, total_pages: 0 },
    };

    render(
      <MemoryRouter initialEntries={['/candidates']}>
        <Routes>
          <Route path="/candidates" element={<CandidateListPage />} />
        </Routes>
      </MemoryRouter>
    );

    const candidateName = await screen.findByText('Single Candidate', {}, { timeout: 3000 });
    expect(candidateName).toBeInTheDocument();

    expect(screen.queryByText(/Page 1 of/i)).not.toBeInTheDocument();
  });
});
