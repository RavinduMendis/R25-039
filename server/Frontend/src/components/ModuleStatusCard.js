import React from 'react';
import { Card, CardContent, Typography, Box, Divider, CircularProgress } from '@mui/material';

const ModuleStatusCard = ({ title, data }) => {
  // ADDED: This guard clause prevents the component from crashing.
  // If data is null or undefined, it renders nothing.
  if (!data) {
    return (
        <Card elevation={2}>
            <CardContent>
                <Typography variant="h6" gutterBottom>{title}</Typography>
                <Divider sx={{ mb: 2 }} />
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 100 }}>
                    <CircularProgress size={24} />
                </Box>
            </CardContent>
        </Card>
    );
  }

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>{title}</Typography>
        <Divider sx={{ mb: 2 }} />
        {Object.entries(data).map(([key, value]) => (
          <Box key={key} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
              {String(value)}
            </Typography>
          </Box>
        ))}
      </CardContent>
    </Card>
  );
};

export default ModuleStatusCard;