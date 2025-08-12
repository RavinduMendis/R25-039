import React from 'react';
import ModelMetricsChart from '../components/ModelMetricsChart';

function MetricsPage({ modelMetrics }) {
    if (!modelMetrics || modelMetrics.length === 0) {
        return <div className="card page-container"><h2>Model Metrics</h2><p>No data to display.</p></div>;
    }
    return (
        <div className="page-container">
            <h1>Model Metrics History</h1>
            <ModelMetricsChart data={modelMetrics} />
        </div>
    );
}

export default MetricsPage;