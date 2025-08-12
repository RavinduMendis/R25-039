import axios from 'axios';

// Base URL for your Python backend API
// IMPORTANT: In production, this should be an environment variable or configured differently.
// For local development, assuming your Python server runs on 8080
const API_BASE_URL = 'http://127.0.0.1:8080/api'; 

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const fetchServerStatus = () => apiClient.get('/status');
export const fetchOverview = () => apiClient.get('/overview');
export const fetchModelMetrics = () => apiClient.get('/metrics');
export const fetchClientHealth = () => apiClient.get('/client_health');
export const fetchLogs = (limit = 50) => apiClient.get(`/logs?limit=${limit}`);
export const fetchModuleStatus = (moduleName) => apiClient.get(`/module_status/${moduleName}`);

// You can add more API functions here as your needs grow