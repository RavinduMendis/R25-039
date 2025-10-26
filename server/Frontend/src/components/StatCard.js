import React from 'react';
import { Card, CardContent, Typography, Box } from '@mui/material';

const StatCard = ({ title, value, icon, color = '#1976d2' }) => {
  return (
    <Card elevation={3} sx={{ display: 'flex', alignItems: 'center', p: 2 }}>
      <Box sx={{
        mr: 2,
        backgroundColor: color,
        color: 'white',
        borderRadius: '50%',
        p: 1.5,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        {icon}
      </Box>
      <Box>
        <Typography color="text.secondary" gutterBottom>
          {title}
        </Typography>
        <Typography variant="h5" component="div" sx={{ fontWeight: 'bold' }}>
          {value}
        </Typography>
      </Box>
    </Card>
  );
};

export default StatCard;