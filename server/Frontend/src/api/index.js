import axios from 'axios';

// The proxy in package.json handles the base URL
const apiClient = axios.create();

export const fetchOverview = () => apiClient.get('/api/overview');

export const fetchMetricsHistory = () => apiClient.get('/api/metrics_history');

// ADDED: This function was missing
export const fetchMetricsDetails = () => apiClient.get('/api/model/metrics_details');

export const fetchClientHealth = () => apiClient.get('/api/client_health');

export const fetchLogs = (limit = 100) => apiClient.get(`/api/logs?limit=${limit}`);

// A single function for all module statuses
export const fetchModuleStatus = (moduleName) => apiClient.get(`/api/module_status/${moduleName}`);