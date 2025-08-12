import React from 'react';
import './Overview.css'; 

function Overview({ data }) {
  if (!data) return null;
  return (
    <div className="card overview-card">
      <h2>Overview</h2>
      <p>Server Status: <span className={data.server_status.class}>{data.server_status.text}</span></p>
      <p>Current Round: {data.current_round}</p>
      <p>Connected Clients: {data.connected_clients}</p>
      <p>Updates in Queue: {data.updates_in_queue}</p>
      <p>Last Aggregation: {data.last_aggregation_time}</p>
    </div>
  );
}

export default Overview;