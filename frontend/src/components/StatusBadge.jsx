import React from 'react';

const STATUS_CLASS_MAP = {
  new: 'badge-new',
  reviewed: 'badge-reviewed',
  hired: 'badge-hired',
  rejected: 'badge-rejected',
  archived: 'badge-archived',
};

/**
 * Renders a badge for a candidate status with the correct color.
 * Accepts any extra className and props to pass through.
 */
export default function StatusBadge({ status, className = '', ...props }) {
  const badgeClass = `badge ${STATUS_CLASS_MAP[status] || 'badge-new'} ${className}`;
  return (
    <span className={badgeClass.trim()} {...props}>
      {status}
    </span>
  );
}
