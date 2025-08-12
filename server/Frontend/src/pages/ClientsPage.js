import React from 'react';
import ClientHealthTable from '../components/ClientHealthTable';

function ClientsPage({ clientHealth }) {
    if (!clientHealth || clientHealth.length === 0) {
        return <div className="card page-container"><h2>Connected Clients</h2><p>No clients currently connected.</p></div>;
    }
    return (
        <div className="page-container">
            <h1>Connected Clients</h1>
            <ClientHealthTable clients={clientHealth} />
        </div>
    );
}

export default ClientsPage;