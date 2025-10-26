import React, { useMemo } from 'react';
import { Grid, Paper, Typography, Box, Divider, List, ListItem, ListItemText, Chip, CircularProgress } from '@mui/material';
import { AreaChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import useApi from '../hooks/useApi';
import { fetchOverview, fetchMetricsHistory, fetchClientHealth, fetchLogs } from '../api';
import PageContainer from '../components/PageContainer';
import StatCard from '../components/StatCard';

// Icon Imports
import ShowChartIcon from '@mui/icons-material/ShowChart';
import PeopleIcon from '@mui/icons-material/People';
import DnsIcon from '@mui/icons-material/Dns';
import PlaylistAddCheckIcon from '@mui/icons-material/PlaylistAddCheck';

// Helper to get color for log levels
const getLogLevelColor = (level = '') => {
  const levelLower = level.toLowerCase();
  if (levelLower === 'error' || levelLower === 'critical') return 'error';
  if (levelLower === 'warning') return 'warning';
  if (levelLower === 'info') return 'info';
  return 'default';
};

/**
 * Converts a large number of hours into a human-readable format (Y, M, D, H).
 * Example: 489292h ago => 55 years, 10 months, 29 days, 4 hours ago
 * @param {number | string} totalHours The total number of hours from the API.
 * @returns {string} Formatted time string.
 */
const formatHoursToReadableTime = (totalHours) => {
  // Try to parse the value as a number. If it fails, return the original string.
  const hours = parseInt(totalHours, 10);
  if (isNaN(hours) || hours <= 0) {
    return totalHours || 'N/A';
  }

  const result = [];

  const hoursInYear = 8760; // 365 days * 24 hours
  const hoursInMonth = 730.5; // Average month: 30.4375 days * 24 hours
  const hoursInDay = 24;
  
  // NOTE: This large number strongly suggests the time is a Unix epoch timestamp 
  // mistakenly being displayed as hours. However, based on the prompt 
  // showing 'h ago', we format it as hours.
  
  let remainingHours = hours;

  // Years
  const years = Math.floor(remainingHours / hoursInYear);
  if (years > 0) {
    result.push(`${years}y`);
    remainingHours %= hoursInYear;
  }

  // Months
  const months = Math.floor(remainingHours / hoursInMonth);
  if (months > 0) {
    result.push(`${months}mo`);
    remainingHours %= hoursInMonth;
  }

  // Days
  const days = Math.floor(remainingHours / hoursInDay);
  if (days > 0) {
    result.push(`${days}d`);
    remainingHours %= hoursInDay;
  }

  // Hours (remaining)
  if (remainingHours > 0 || result.length === 0) {
    result.push(`${Math.round(remainingHours)}h`);
  }
  
  return result.length > 0 ? `${result.join(', ')} ago` : 'just now';
};


const DashboardPage = () => {
  const { data: overview } = useApi(fetchOverview, {});
  const { data: metricsHistory } = useApi(fetchMetricsHistory, { metrics_history: [] });
  const { data: clientHealth } = useApi(fetchClientHealth, { clients: {} });
  const { data: logs } = useApi(fetchLogs, []);

  // --- Data Processing ---
  const flattenedMetrics = useMemo(() => 
    (metricsHistory?.metrics_history || []).map(item => ({
      round: item.round,
      accuracy: item.metrics?.accuracy,
      loss: item.metrics?.loss,
    })), [metricsHistory]);

  const clientStatusCounts = useMemo(() => {
    const clients = Object.values(clientHealth?.clients || {});
    return clients.reduce((acc, client) => {
      const status = client.status || 'unknown';
      acc[status] = (acc[status] || 0) + 1;
      return acc;
    }, {});
  }, [clientHealth]);

  const progress = overview?.training_progress?.percentage || 0;
  const currentRound = overview?.current_round || 0;
  const totalRounds = overview?.total_rounds || 0;
  const recentLogs = logs?.slice(0, 5) || [];
  
  // NEW: Process the raw time value for display
  const lastAggregationTime = useMemo(() => {
    // Check if the raw data is the large hour count (e.g., "489292h ago")
    const rawTime = overview?.time_since_last_aggregation_formatted;

    if (rawTime && rawTime.endsWith('h ago')) {
      const hours = rawTime.replace('h ago', '');
      return formatHoursToReadableTime(hours);
    }
    // If it's already a good format or N/A, use it directly
    return rawTime || 'N/A';

  }, [overview?.time_since_last_aggregation_formatted]);


  return (
    <PageContainer title="Dashboard Overview" loading={!overview}>
      <Grid container spacing={3}>
        {/* Main Stats and Progress */}
        <Grid item xs={12} md={8}>
          <Grid container spacing={3}>
            <Grid item xs={12} sm={6}>
              <StatCard title="Server Status" value={overview?.server_status?.text || '...'} icon={<DnsIcon />} color="#2e7d32" />
            </Grid>
            <Grid item xs={12} sm={6}>
              <StatCard title="Connected Clients" value={overview?.connected_clients || '...'} icon={<PeopleIcon />} color="#1976d2" />
            </Grid>
            <Grid item xs={12} sm={6}>
               <StatCard title="Updates in Queue" value={overview?.updates_in_queue || '...'} icon={<PlaylistAddCheckIcon />} color="#673ab7" />
            </Grid>
             <Grid item xs={12} sm={6}>
               {/* MODIFIED: Use the newly processed value */}
               <StatCard title="Last Aggregation" value={lastAggregationTime} icon={<ShowChartIcon />} color="#ed6c02" />
            </Grid>
          </Grid>
        </Grid>

        {/* Training Progress Donut */}
        <Grid item xs={12} md={4}>
          <Paper sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <Typography variant="h6" gutterBottom>Training Progress</Typography>
            <Box sx={{ position: 'relative', display: 'inline-flex' }}>
              <CircularProgress
                variant="determinate"
                value={100}
                size="7rem"
                thickness={4}
                sx={{ color: '#e0e0e0' }}
              />
              <CircularProgress
                variant="determinate"
                value={progress}
                size="7rem"
                thickness={4}
                sx={{
                  position: 'absolute',
                  left: 0,
                  color: '#1976d2',
                  '& .MuiCircularProgress-circle': {
                    strokeLinecap: 'round',
                  },
                }}
              />
              <Box
                sx={{
                  top: 0, left: 0, bottom: 0, right: 0,
                  position: 'absolute',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Typography variant="h5" component="div" color="text.secondary" sx={{ fontWeight: 'bold' }}>
                  {`${Math.round(progress)}%`}
                </Typography>
                 <Typography variant="body2">{`${currentRound} / ${totalRounds}`}</Typography>
              </Box>
            </Box>
          </Paper>
        </Grid>
        
        {/* Combined Metrics Chart */}
        <Grid item xs={12}>
          <Paper sx={{ p: 2, height: 350 }}>
            <Typography variant="h6">Model Performance: Accuracy vs. Loss</Typography>
            <ResponsiveContainer width="100%" height="90%">
              <AreaChart data={flattenedMetrics} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="round" />
                <YAxis yAxisId="left" orientation="left" stroke="#4caf50" label={{ value: 'Accuracy (%)', angle: -90, position: 'insideLeft' }} domain={[0, 100]} />
                <YAxis yAxisId="right" orientation="right" stroke="#f44336" label={{ value: 'Loss', angle: 90, position: 'insideRight' }} />
                <Tooltip />
                <Legend />
                <Area yAxisId="left" type="monotone" dataKey="accuracy" stroke="#4caf50" fill="#4caf50" fillOpacity={0.2} name="Accuracy" />
                <Line yAxisId="right" type="monotone" dataKey="loss" stroke="#f44336" strokeWidth={2} name="Loss" />
              </AreaChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        {/* Client Status & Recent Logs */}
        <Grid item xs={12} md={6}>
           <Paper sx={{ p: 2, height: '100%' }}>
            <Typography variant="h6" gutterBottom>Client Status Breakdown</Typography>
            <Divider sx={{ mb: 2 }} />
            <Box>
              {Object.entries(clientStatusCounts).length > 0 ? Object.entries(clientStatusCounts).map(([status, count]) => (
                <Box key={status} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography>{status.charAt(0).toUpperCase() + status.slice(1)}</Typography>
                  <Chip label={count} color="primary" size="small" />
                </Box>
              )) : <Typography color="text.secondary">No client data available.</Typography>}
            </Box>
           </Paper>
        </Grid>
        <Grid item xs={12} md={6}>
            <Paper sx={{ p: 2, height: '100%' }}>
              <Typography variant="h6" gutterBottom>Recent Activity</Typography>
              <Divider sx={{ mb: 1 }} />
              <List dense>
                {recentLogs.length > 0 ? recentLogs.map((log, index) => (
                  <ListItem key={index} disableGutters>
                    <Chip label={log.level_name} color={getLogLevelColor(log.level_name)} size="small" sx={{ mr: 1.5, minWidth: 70 }} />
                    <ListItemText 
                      primary={log.message}
                      secondary={log.timestamp}
                      primaryTypographyProps={{ style: { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } }}
                    />
                  </ListItem>
                )) : <Typography color="text.secondary">No recent logs to display.</Typography>}
              </List>
            </Paper>
        </Grid>

      </Grid>
    </PageContainer>
  );
};

export default DashboardPage;