import React from 'react';
import { Grid, Paper, Typography, Box } from '@mui/material';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { DataGrid } from '@mui/x-data-grid';
import useApi from '../hooks/useApi';
import { fetchMetricsHistory, fetchMetricsDetails } from '../api';
import PageContainer from '../components/PageContainer';
import StatCard from '../components/StatCard';

import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import AutorenewIcon from '@mui/icons-material/Autorenew';
import UpdateIcon from '@mui/icons-material/Update';
import NumbersIcon from '@mui/icons-material/Numbers';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';

// A helper component to show when there's no data
const EmptyState = ({ message }) => (
  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'text.secondary' }}>
    <InfoOutlinedIcon sx={{ mr: 1 }} />
    <Typography>{message}</Typography>
  </Box>
);

const PerformancePage = () => {
  const { data: historyData, loading: historyLoading, error: historyError } = useApi(fetchMetricsHistory, { metrics_history: [] });
  const { data: detailsData, loading: detailsLoading, error: detailsError } = useApi(fetchMetricsDetails, {});

  // MODIFIED: Flatten the nested data from the API
  const flattenedMetrics = (historyData?.metrics_history || []).map(item => ({
    round: item.round,
    accuracy: item.metrics?.accuracy,
    loss: item.metrics?.loss,
    precision: item.metrics?.precision,
    recall: item.metrics?.recall,
  }));

  const hasChartData = flattenedMetrics.length > 0 && flattenedMetrics.some(m => typeof m.accuracy === 'number');

  const columns = [
    { field: 'round', headerName: 'Round', width: 100 },
    // MODIFIED: Corrected accuracy formatting (no longer multiplying by 100)
    { 
      field: 'accuracy', 
      headerName: 'Accuracy', 
      width: 150, 
      valueFormatter: (params) => typeof params.value === 'number' ? `${params.value.toFixed(2)}%` : 'N/A'
    },
    { 
      field: 'loss', 
      headerName: 'Loss', 
      width: 150, 
      valueFormatter: (params) => typeof params.value === 'number' ? params.value.toFixed(4) : 'N/A' 
    },
    { 
      field: 'precision', 
      headerName: 'Precision', 
      width: 150, 
      valueFormatter: (params) => typeof params.value === 'number' ? params.value.toFixed(3) : 'N/A' 
    },
    { 
      field: 'recall', 
      headerName: 'Recall', 
      width: 150, 
      valueFormatter: (params) => typeof params.value === 'number' ? params.value.toFixed(3) : 'N/A' 
    },
  ];

  const rows = flattenedMetrics.map((row, index) => ({ id: row.round || index, ...row }));
  const isConverged = detailsData?.convergence_status === 'Converged';

  return (
    <PageContainer title="Model Performance" loading={historyLoading || detailsLoading} error={historyError || detailsError}>
      <Grid container spacing={3}>
        {/* Stat Cards */}
        <Grid item xs={12} sm={6} md={3}>
            <StatCard 
                title="Convergence Status" 
                value={detailsData?.convergence_status || '...'} 
                icon={isConverged ? <CheckCircleOutlineIcon /> : <AutorenewIcon />}
                color={isConverged ? '#2e7d32' : '#ed6c02'}
            />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
            <StatCard title="Model Version" value={detailsData?.model_version || '...'} icon={<NumbersIcon />} />
        </Grid>
        <Grid item xs={12} sm={6} md={6}>
            <StatCard title="Last Model Update" value={detailsData?.last_model_update || '...'} icon={<UpdateIcon />} />
        </Grid>
        
        {/* Charts - Now use 'flattenedMetrics' */}
        <Grid item xs={12} lg={6}>
          <Paper sx={{ p: 2, height: 300 }}>
            <Typography variant="h6">Accuracy Over Rounds</Typography>
            {hasChartData ? (
              <ResponsiveContainer width="100%" height="90%">
                <AreaChart data={flattenedMetrics}>
                  <defs>
                    <linearGradient id="colorAccuracy" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#4caf50" stopOpacity={0.8}/>
                      <stop offset="95%" stopColor="#4caf50" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="round" />
                  <YAxis domain={[0, 100]} tickFormatter={(tick) => `${tick}%`}/>
                  <Tooltip formatter={(value) => `${value.toFixed(2)}%`}/>
                  <Legend />
                  <Area type="monotone" dataKey="accuracy" stroke="#4caf50" fillOpacity={1} fill="url(#colorAccuracy)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState message="Waiting for first model evaluation..." />
            )}
          </Paper>
        </Grid>

        <Grid item xs={12} lg={6}>
          <Paper sx={{ p: 2, height: 300 }}>
            <Typography variant="h6">Loss Over Rounds</Typography>
            {hasChartData ? (
              <ResponsiveContainer width="100%" height="90%">
                 <AreaChart data={flattenedMetrics}>
                  <defs>
                    <linearGradient id="colorLoss" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f44336" stopOpacity={0.8}/>
                      <stop offset="95%" stopColor="#f44336" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="round" />
                  <YAxis />
                  <Tooltip formatter={(value) => typeof value === 'number' ? value.toFixed(4) : 'N/A'}/>
                  <Legend />
                  <Area type="monotone" dataKey="loss" stroke="#f44336" fillOpacity={1} fill="url(#colorLoss)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState message="Waiting for first model evaluation..." />
            )}
          </Paper>
        </Grid>
        
        {/* Data Table - Now uses 'rows' derived from flattenedMetrics */}
        <Grid item xs={12}>
            <Paper sx={{ height: 400, width: '100%' }}>
                <DataGrid
                    rows={rows}
                    columns={columns}
                    pageSize={5}
                    rowsPerPageOptions={[5]}
                    density="compact"
                    localeText={{ noRowsLabel: 'No metrics data to display' }}
                />
            </Paper>
        </Grid>
      </Grid>
    </PageContainer>
  );
};

export default PerformancePage;