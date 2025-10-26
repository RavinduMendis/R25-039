import React from 'react';
import { Grid } from '@mui/material';
import useApi from '../hooks/useApi';
import { fetchModuleStatus } from '../api';
import PageContainer from '../components/PageContainer';
import ModuleStatusCard from '../components/ModuleStatusCard';

const modules = ['scpm', 'mm', 'sam', 'adrm', 'ppm', 'orchestrator'];

const SystemHealthPage = () => {
  return (
    <PageContainer title="System & Module Health">
      <Grid container spacing={3}>
        {modules.map(moduleName => (
          <Grid item xs={12} md={6} lg={4} key={moduleName}>
            <ModuleLoader moduleName={moduleName} />
          </Grid>
        ))}
      </Grid>
    </PageContainer>
  );
};

// Helper component to fetch data for each module individually
const ModuleLoader = ({ moduleName }) => {
    const { data, loading } = useApi(() => fetchModuleStatus(moduleName), {});
    if (loading || !data) return <p>Loading {moduleName.toUpperCase()}...</p>;
    return <ModuleStatusCard title={`${moduleName.toUpperCase()} Status`} data={data} />;
};

export default SystemHealthPage;