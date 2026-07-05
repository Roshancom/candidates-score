import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './api/auth';
import LoginPage from './pages/LoginPage';
import CandidateListPage from './pages/CandidateListPage';
import CandidateDetailPage from './pages/CandidateDetailPage';
import ReviewerCandidateListPage from './pages/ReviewerCandidateListPage';
import UploadCVPage from './pages/UploadCVPage';
import Navbar from './components/Navbar';

function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();
  if (loading) {
    return (
      <div className="loading-overlay">
        <div className="spinner spinner-lg" />
        <div className="loading-text">Loading...</div>
      </div>
    );
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

function AdminRoute({ children }) {
  const { isAuthenticated, isAdmin, isReviewer, loading } = useAuth();
  if (loading) {
    return (
      <div className="loading-overlay">
        <div className="spinner spinner-lg" />
        <div className="loading-text">Loading...</div>
      </div>
    );
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (isReviewer) return <Navigate to="/candidates/review" replace />;
  return children;
}

function ReviewerRoute({ children }) {
  const { isAuthenticated, isReviewer, isAdmin, loading } = useAuth();
  if (loading) {
    return (
      <div className="loading-overlay">
        <div className="spinner spinner-lg" />
        <div className="loading-text">Loading...</div>
      </div>
    );
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (isAdmin) return <Navigate to="/candidates" replace />;
  return children;
}

export default function App() {
  const { isAuthenticated, isAdmin, isReviewer, loading } = useAuth();

  if (loading) {
    return (
      <div className="loading-overlay">
        <div className="spinner spinner-lg" />
        <div className="loading-text">Loading...</div>
      </div>
    );
  }

  // Determine default redirect based on role
  const defaultPath = isAdmin ? '/candidates' : isReviewer ? '/candidates/review' : '/candidates';

  return (
    <div style={{ minHeight: '100vh', backgroundColor: 'var(--color-page-bg)' }}>
      {isAuthenticated && <Navbar />}
      <Routes>
        <Route path="/login" element={isAuthenticated ? <Navigate to={defaultPath} replace /> : <LoginPage />} />
        <Route
          path="/candidates"
          element={
            <AdminRoute>
              <CandidateListPage />
            </AdminRoute>
          }
        />
        <Route
          path="/candidates/review"
          element={
            <ReviewerRoute>
              <ReviewerCandidateListPage />
            </ReviewerRoute>
          }
        />
        <Route
          path="/upload-cv"
          element={
            <AdminRoute>
              <UploadCVPage />
            </AdminRoute>
          }
        />
        <Route
          path="/candidates/:id"
          element={
            <ProtectedRoute>
              <CandidateDetailPage />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<Navigate to={defaultPath} replace />} />
        <Route path="*" element={<Navigate to={defaultPath} replace />} />
      </Routes>
    </div>
  );
}
