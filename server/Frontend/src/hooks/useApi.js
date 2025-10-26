import { useState, useEffect, useCallback } from 'react';

// This hook simplifies data fetching, loading, and error handling in components
const useApi = (apiCall, initialData = null) => {
  const [data, setData] = useState(initialData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const response = await apiCall();
      // The backend wraps data in a 'data' key
      setData(response.data.data); 
    } catch (err) {
      setError(err);
      console.error("API call failed:", err);
    } finally {
      setLoading(false);
    }
  }, [apiCall]);

  useEffect(() => {
    fetchData(); // Initial fetch
    const interval = setInterval(fetchData, 5000); // Poll every 5 seconds
    return () => clearInterval(interval); // Cleanup on unmount
  }, [fetchData]);

  return { data, loading, error };
};

export default useApi;