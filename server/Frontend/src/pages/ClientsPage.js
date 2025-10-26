import React from 'react';
import { Box, Paper } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import useApi from '../hooks/useApi';
import { fetchClientHealth } from '../api';
import PageContainer from '../components/PageContainer';
import StatusChip from '../components/StatusChip';
import { format } from 'date-fns';

const ClientsPage = () => {
  const { data: clientHealth, loading, error } = useApi(fetchClientHealth, { clients: {} });
  
  const columns = [
    { field: 'client_id', headerName: 'Client ID', flex: 1 },
    { field: 'ip_address', headerName: 'IP Address', width: 150 },
    { field: 'client_type', headerName: 'Type', width: 120 },
    { 
      field: 'status', 
      headerName: 'Status', 
      width: 120,
      renderCell: (params) => <StatusChip status={params.value} />
    },
    { 
      field: 'last_heartbeat', 
      headerName: 'Last Heartbeat', 
      flex: 1,
      valueFormatter: (params) => format(new Date(params.value * 1000), 'yyyy-MM-dd HH:mm:ss')
    },
  ];

  const rows = clientHealth ? Object.values(clientHealth.clients).map(c => ({ id: c.client_id, ...c })) : [];

  return (
    <PageContainer title="Client Management" loading={loading} error={error}>
      <Paper sx={{ height: 600, width: '100%' }}>
        <DataGrid
          rows={rows}
          columns={columns}
          pageSize={10}
          rowsPerPageOptions={[10]}
          checkboxSelection
          disableSelectionOnClick
        />
      </Paper>
    </PageContainer>
  );
};

export default ClientsPage;