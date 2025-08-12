import React, { useState } from 'react';
import ServerStatus from '../components/ServerStatus';
import Overview from '../components/Overview';
import ModelMetricsChart from '../components/ModelMetricsChart';
import ClientHealthTable from '../components/ClientHealthTable';
import LogsDisplay from '../components/LogsDisplay';
import ModuleStatusCard from '../components/ModuleStatusCard'; // Still imported

function DashboardPage({ 
  serverStatus, overviewData, modelMetrics, clientHealth, logs, moduleStatuses 
}) {
  const [introCollapsed, setIntroCollapsed] = useState(false); 

  return (
    <>
      {/* Introduction Section (collapsible) */}
      <section className="collapsible-section card">
        <div className="collapsible-header" onClick={() => setIntroCollapsed(!introCollapsed)}>
          <h2>Introduction</h2>
          <span className="collapse-icon">{introCollapsed ? '-' : '+'}</span>
        </div>
        <div className={`collapsible-content ${introCollapsed ? 'collapsed' : ''}`}>
          <p>This dashboard provides a comprehensive and transparent view of the Federated Learning process, enhancing operational control and security.</p>
          <p>Visit our project website: <a href="https://k0k1s.github.io/r25-039" target="_blank" rel="noopener noreferrer">Click here</a></p>
        </div>
      </section>

      <div className="grid-container"> 
        <ServerStatus status={serverStatus} />
        <Overview data={overviewData} />
        <ModelMetricsChart data={modelMetrics} /> 
        <ClientHealthTable clients={clientHealth} />
        {/* Showing only a snippet of logs on the dashboard overview */}
        <LogsDisplay logs={logs.slice(0, 5)} title="Recent Logs" /> 
        
        {/* UNCOMMENTED: Display SCPM status on the dashboard overview */}
        <ModuleStatusCard title="SCPM Status" data={moduleStatuses.scpm} type="scpm" /> 
      </div>
    </>
  );
}

export default DashboardPage;