import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import PaginationFooter from '../components/PaginationFooter';

/**
 * Hook for pagination state synced with URL search params.
 *
 * @param {Object} options
 * @param {number} options.defaultPageSize - Items per page (default 20)
 * @param {number} options.maxPageSize - Max items per page (default 50)
 * @returns {Object} { page, pageSize, PaginationFooter, setPage, setPageSize }
 *
 * `PaginationFooter` is the component — pass it { totalPages, totalCount, loading, onPageChange } props.
 *   onPageChange defaults to setPage, so you can omit it.
 */
export default function usePagination({ defaultPageSize = 20, maxPageSize = 50 } = {}) {
  const [searchParams, setSearchParams] = useSearchParams();

  const rawPage = parseInt(searchParams.get('page') || '1', 10);
  const rawPageSize = parseInt(searchParams.get('page_size') || String(defaultPageSize), 10);
  const page = Math.max(1, rawPage || 1);
  const pageSize = Math.min(maxPageSize, Math.max(1, rawPageSize || defaultPageSize));

  const updateParams = useCallback((updates) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      for (const [key, value] of Object.entries(updates)) {
        if (value === '' || value === null || value === undefined) {
          next.delete(key);
        } else {
          next.set(key, String(value));
        }
      }
      return next;
    }, { replace: true });
  }, [setSearchParams]);

  const setPage = useCallback((p) => updateParams({ page: p }), [updateParams]);
  const setPageSize = useCallback((ps) => updateParams({ page_size: ps, page: 1 }), [updateParams]);

  return { page, pageSize, setPage, setPageSize, PaginationFooter };
}
