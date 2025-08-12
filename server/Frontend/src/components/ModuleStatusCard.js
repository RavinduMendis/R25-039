import React from 'react';
import './ModuleStatusCard.css'; 

function ModuleStatusCard({ title, data, type }) {
  if (!data) return null;

  // Custom rendering for SCPM specific data
  if (type === 'scpm') {
    return (
      <div className="card module-status-card scpm-card">
        <h3>{title}</h3>
        <p>Server Status: <span className={data.server_ready ? 'status-online' : 'status-offline'}>{data.server_ready ? 'Online' : 'Offline'}</span></p>
        <p>Connected Clients: {data.connected_clients}</p>
        <p>Current Round: {data.current_round}</p>
        <p>Updates in Queue: {data.updates_in_queue}</p>
        <p>Last Aggregation: {data.last_aggregation_time}</p>
      </div>
    );
  }

  // Generic rendering for other modules
  return (
    <div className="card module-status-card">
      <h3>{title}</h3>
      {Object.entries(data).map(([key, value]) => (
        <p key={key}>
          <strong>{key.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase())}:</strong> {String(value)}
        </p>
      ))}
    </div>
  );
}

export default ModuleStatusCard;