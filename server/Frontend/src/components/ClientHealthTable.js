// components/ClientHealthTable.js

import React from 'react';

// The clients prop is now the entire clientHealth object from the API
function ClientHealthTable({ clients }) {
    // We now have to check if clients is an object and if it contains the nested clients key
    if (!clients || !clients.clients || Object.keys(clients.clients).length === 0) {
        return <p>No clients currently connected.</p>;
    }
    
    // Convert the nested clients object into an array of its values for mapping
    const clientArray = Object.values(clients.clients);

    return (
        <div className="card">
            <h3>Connected Clients ({clients.connected_clients})</h3>
            <div className="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>Client ID</th>
                            <th>IP Address</th>
                            <th>Type</th>
                            <th>Status</th>
                            <th>Last Heartbeat</th>
                        </tr>
                    </thead>
                    <tbody>
                        {clientArray.map(client => (
                            <tr key={client.client_id}>
                                <td>{client.client_id}</td>
                                <td>{client.ip_address}</td>
                                <td>{client.client_type}</td>
                                <td><span className={`status-dot ${client.status}`}></span> {client.status}</td>
                                <td>{new Date(client.last_heartbeat * 1000).toLocaleString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

export default ClientHealthTable;