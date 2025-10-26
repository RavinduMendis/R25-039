import React from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';

const PageContainer = ({ title, loading, error, children }) => {
  return (
    <Box>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 'bold', color: '#1a237e' }}>
        {title}
      </Typography>
      {loading && <CircularProgress />}
      {error && <Typography color="error">Failed to load data. Please try again later.</Typography>}
      {!loading && !error && children}
    </Box>
  );
};

export default PageContainer;