import React, { useState, useMemo } from 'react';
import { Paper, Box, Typography, TextField, Select, MenuItem, FormControl, InputLabel, Grid, IconButton } from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import ClearIcon from '@mui/icons-material/Clear';

import useApi from '../hooks/useApi';
import { fetchLogs } from '../api';
import PageContainer from '../components/PageContainer';

// List of available log levels for the filter dropdown
const LOG_LEVELS = [
  'ALL', 'ERROR', 'CRITICAL', 'WARNING', 'INFO', 'DEBUG', 'GENERAL'
];

// Helper to get color for log levels
const getLogLevelColor = (level) => {
  if (!level) {
    return '#bdbdbd'; // Default grey color
  }

  const levelLower = level.toLowerCase();
  if (levelLower === 'error' || levelLower === 'critical') return '#f44336';
  if (levelLower === 'warning') return '#ffa726';
  if (levelLower === 'info') return '#29b6f6';
  return '#bdbdbd'; // Debug and other levels
};

const LogsPage = () => {
  const { data: rawLogs, loading, error } = useApi(fetchLogs, []);
  
  // State for search and filter
  const [searchTerm, setSearchTerm] = useState('');
  const [logLevel, setLogLevel] = useState('ALL');

  // --- Filtering Logic ---
  const filteredLogs = useMemo(() => {
    if (!Array.isArray(rawLogs)) return [];

    const normalizedSearchTerm = searchTerm.toLowerCase().trim();

    return rawLogs.filter(log => {
      // 1. Level Filtering
      if (logLevel !== 'ALL') {
        const logLevelName = (log.level_name || 'GENERAL').toUpperCase();
        if (logLevelName !== logLevel) {
          return false;
        }
      }

      // 2. Search Term Filtering
      if (normalizedSearchTerm === '') {
        return true;
      }

      const message = log.message ? log.message.toLowerCase() : '';
      const timestamp = log.timestamp ? log.timestamp.toLowerCase() : '';

      return message.includes(normalizedSearchTerm) || 
             timestamp.includes(normalizedSearchTerm);
    });
  }, [rawLogs, searchTerm, logLevel]);
  
  // Handle clearing the search field
  const handleClearSearch = () => setSearchTerm('');
  
  const emptyLogsMessage = loading 
    ? "Loading logs..." 
    : (searchTerm || logLevel !== 'ALL') 
      ? "No logs match your current filter or search term."
      : "No logs available from the server.";


  return (
    <PageContainer title="Server Logs" loading={loading} error={error}>
      
      {/* Search and Filter Controls */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {/* Search Input (FIXED: Using placeholder instead of floating label) */}
        <Grid item xs={12} sm={8} md={9}>
          <TextField
            fullWidth
            // REMOVED 'label' prop to prevent floating/overlap behavior
            placeholder="Search Logs (Message or Timestamp)" // Use placeholder for static hint
            variant="outlined"
            size="small"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            InputProps={{
              startAdornment: (
                <SearchIcon sx={{ color: '#bdbdbd', mr: 1 }} />
              ),
              endAdornment: searchTerm && (
                <IconButton size="small" onClick={handleClearSearch} sx={{ color: '#bdbdbd' }}>
                  <ClearIcon />
                </IconButton>
              ),
              sx: {
                color: '#fff',
                backgroundColor: '#333333',
                '& fieldset': { borderColor: '#bdbdbd !important' },
              }
            }}
            // Removed InputLabelProps as we are no longer using the floating label
          />
        </Grid>
        
        {/* Level Filter Dropdown (FIXED: Forcing label position with shrink) */}
        <Grid item xs={12} sm={4} md={3}>
          <FormControl fullWidth variant="outlined" size="small" sx={{ backgroundColor: '#333333' }}>
            {/* FIX: Add InputLabelProps={{ shrink: false }} to prevent the label from floating */}
            <InputLabel 
              id="log-level-label" 
              sx={{ color: '#bdbdbd' }} 
              shrink={false} // Prevents the label from moving/overlapping
            >
            </InputLabel>
            <Select
              labelId="log-level-label"
              value={logLevel}
              onChange={(e) => setLogLevel(e.target.value)}
              label="Log Level"
              sx={{ 
                color: '#fff',
                '.MuiSvgIcon-root': { color: '#bdbdbd' },
                '& fieldset': { borderColor: '#bdbdbd !important' },
              }}
            >
              {LOG_LEVELS.map((level) => (
                <MenuItem key={level} value={level}>
                  {level.charAt(0) + level.slice(1).toLowerCase()}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
      </Grid>

      {/* Log Display Area */}
      <Paper sx={{
        height: '75vh',
        overflowY: 'auto', 
        p: 2,
        backgroundColor: '#212121',
        color: '#fff',
        fontFamily: 'monospace',
        whiteSpace: 'pre-wrap', 
        wordWrap: 'break-word',
      }}>
        {filteredLogs.length > 0 ? (
          filteredLogs.map((log, index) => (
            <Box key={index} sx={{ display: 'flex', gap: 2, mb: 0.5 }}>
              <Typography variant="body2" component="span" sx={{ color: '#9e9e9e', flexShrink: 0 }}>
                {log.timestamp}
              </Typography>
              <Typography
                variant="body2"
                component="span"
                sx={{ color: getLogLevelColor(log.level_name), fontWeight: 'bold', flexShrink: 0 }}
              >
                [{log.level_name || 'GENERAL'}]
              </Typography>
              <Typography variant="body2" component="span" sx={{ flexGrow: 1 }}>
                {log.message}
              </Typography>
            </Box>
          ))
        ) : (
          <Typography variant="body1" sx={{ color: '#9e9e9e', textAlign: 'center', mt: 4 }}>
            {emptyLogsMessage}
          </Typography>
        )}
      </Paper>
    </PageContainer>
  );
};

export default LogsPage;