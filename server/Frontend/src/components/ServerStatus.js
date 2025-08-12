// Example of a corrected ServerStatus.js component
import React from 'react';

function ServerStatus({ status }) {
  // Check if status data is available before rendering
  if (!status) {
    return (
      <div className="card">
        <h3>Server Status</h3>
        <p>Loading server status...</p>
      </div>
    );
  }

  // Destructure the properties for easier access
  const { 
    status: serverStatusText, 
    uptime_seconds, 
    connected_clients, 
    log_file_size_kb 
  } = status;

  return (
    <div className="card">
      <h3>Server Status</h3>
      <p><strong>Status:</strong> {serverStatusText}</p>
      <p><strong>Connected Clients:</strong> {connected_clients}</p>
      <p><strong>Uptime:</strong> {uptime_seconds} seconds</p>
      <p><strong>Log File Size:</strong> {log_file_size_kb} KB</p>
    </div>
  );
}

export default ServerStatus;