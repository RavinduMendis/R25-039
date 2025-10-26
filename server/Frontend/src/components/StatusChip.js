import React from 'react';
import { Chip } from '@mui/material';

const StatusChip = ({ status }) => {
  const statusLower = status.toLowerCase();
  let color = 'default';
  if (['online', 'active', 'converged'].includes(statusLower)) {
    color = 'success';
  } else if (['offline', 'inactive'].includes(statusLower)) {
    color = 'error';
  } else if (['stale', 'training'].includes(statusLower)) {
    color = 'warning';
  }

  return <Chip label={status} color={color} size="small" />;
};

export default StatusChip;