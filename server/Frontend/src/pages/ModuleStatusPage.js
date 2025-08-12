import React from 'react';
import ModuleStatusCard from '../components/ModuleStatusCard';

function ModuleStatusPage({ moduleStatuses }) {
    return (
        <div className="page-container">
            <h1>Module Statuses</h1>
            <div className="grid-container module-status-group"> 
                <ModuleStatusCard title="SCPM Status" data={moduleStatuses.scpm} type="scpm" />
                <ModuleStatusCard title="Model Manager (MM) Status" data={moduleStatuses.mm} type="mm" />
                <ModuleStatusCard title="Secure Aggregation (SAM) Status" data={moduleStatuses.sam} type="sam" />
                <ModuleStatusCard title="Attack Detection (ADRM) Status" data={moduleStatuses.adrm} type="adrm" />
                <ModuleStatusCard title="Privacy Preservation (PPM) Status" data={moduleStatuses.ppm} type="ppm" />
            </div>
        </div>
    );
}

export default ModuleStatusPage;