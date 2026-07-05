import React from 'react';

/**
 * Pagination footer component. Renders Previous/Next controls and page info.
 * Hidden when totalPages <= 1.
 *
 * @param {Object} props
 * @param {number} props.page - Current page number
 * @param {number} props.totalPages - Total number of pages
 * @param {number} props.totalCount - Total number of items
 * @param {boolean} props.loading - Whether data is being fetched
 * @param {(page: number) => void} props.onPageChange - Callback when page changes
 */
export default function PaginationFooter({ page, totalPages, totalCount, loading, onPageChange }) {
  if (totalPages <= 1) return null;

  return (
    <div className="pagination">
      <button
        className="btn btn-ghost"
        disabled={page <= 1 || loading}
        onClick={() => onPageChange(page - 1)}
      >
        ← Previous
      </button>
      <span className="pagination-info">
        Page {page} of {totalPages}
        {totalCount > 0 && ` (${totalCount} total)`}
      </span>
      <button
        className="btn btn-ghost"
        disabled={page >= totalPages || loading || totalPages === 0}
        onClick={() => onPageChange(page + 1)}
      >
        Next →
      </button>
    </div>
  );
}
