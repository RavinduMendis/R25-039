// App.js

import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'; 

// Import layout components
import Header from './components/Header';
import SideNavigation from './components/SideNavigation'; 

// Import page components from the new 'pages' directory
import DashboardPage from './pages/DashboardPage';
import MetricsPage from './pages/MetricsPage.js';
import ClientsPage from './pages/ClientsPage';
import LogsPage from './pages/LogsPage';
import ModuleStatusPage from './pages/ModuleStatusPage';

// Import API functions
import { 
  fetchServerStatus, 
  fetchOverview, 
  fetchModelMetrics, 
  fetchClientHealth, 
  fetchLogs,
  fetchModuleStatus 
} from './api';

// Import global CSS
import './App.css'; 

function App() {
  // All top-level state for global data remains here,
  // as multiple pages might need access to it.
  const [serverStatus, setServerStatus] = useState(null);
  const [overviewData, setOverviewData] = useState(null);
  const [modelMetrics, setModelMetrics] = useState([]);
  const [clientHealth, setClientHealth] = useState(null); // Keep as null initially to represent the full object
  const [logs, setLogs] = useState([]);
  const [moduleStatuses, setModuleStatuses] = useState({
    mm: null,
    sam: null,
    adrm: null,
    ppm: null,
    scpm: null, // SCPM status combined from serverStatus and overviewData
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true); 
    setError(null);
    try {
      const [
        statusRes, 
        overviewRes, 
        metricsRes, 
        clientRes, 
        logsRes,
        mmStatusRes,
        samStatusRes,
        adrmStatusRes,
        ppmStatusRes
      ] = await Promise.all([
        fetchServerStatus(),
        fetchOverview(),
        fetchModelMetrics(),
        fetchClientHealth(),
        fetchLogs(),
        fetchModuleStatus('mm'),
        fetchModuleStatus('sam'),
        fetchModuleStatus('adrm'),
        fetchModuleStatus('ppm')
      ]);

      setServerStatus(statusRes.data.data);
      setOverviewData(overviewRes.data.data);
      setModelMetrics(metricsRes.data.data);
      // CORRECTED: Extract the clients object and pass it to the state
      setClientHealth(clientRes.data.data);
      setLogs(logsRes.data.data);
      setModuleStatuses(prev => ({
        ...prev,
        mm: mmStatusRes.data.data,
        sam: samStatusRes.data.data,
        adrm: adrmStatusRes.data.data,
        ppm: ppmStatusRes.data.data,
        // SCPM status is derived from general server status and overview
        scpm: { 
          server_status_text: statusRes.data.data.server_status,
          connected_clients: statusRes.data.data.connected_clients,
          server_ready: statusRes.data.data.server_ready,
          current_round: overviewRes.data.data.current_round,
          updates_in_queue: overviewRes.data.data.updates_in_queue,
          last_aggregation_time: overviewRes.data.data.last_aggregation_time
        }
      }));
    } catch (err) {
      setError("Failed to fetch dashboard data: " + err.message);
      console.error("Dashboard fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Poll for updates every 5 seconds
    const interval = setInterval(fetchData, 5000); 
    return () => clearInterval(interval); 
  }, [fetchData]);

  // Conditional rendering for loading and error states
  if (loading) return <div className="dashboard-loading">Loading Dashboard...</div>;
  if (error) return <div className="dashboard-error">{error}</div>;

  return (
    <Router>
      <div className="dashboard-container"> 
        <Header /> 
        <div className="content-wrapper"> {/* New wrapper for side-nav and main-content */}
          <SideNavigation /> 
          <main className="main-content">
            <Routes>
              <Route 
                path="/" 
                element={
                  <DashboardPage 
                    serverStatus={serverStatus} 
                    overviewData={overviewData} 
                    modelMetrics={modelMetrics} 
                    clientHealth={clientHealth} // Pass the full object here
                    logs={logs} 
                    moduleStatuses={moduleStatuses} 
                  />
                } 
              />
              <Route path="/metrics" element={<MetricsPage modelMetrics={modelMetrics} />} />
              <Route path="/clients" element={<ClientsPage clientHealth={clientHealth} />} /> // Pass the full object here
              <Route path="/logs" element={<LogsPage logs={logs} />} />
              <Route path="/modules" element={<ModuleStatusPage moduleStatuses={moduleStatuses} />} />
            </Routes>
          </main>
        </div> {/* End content-wrapper */}
      </div>
    </Router>
  );
}

export default App;