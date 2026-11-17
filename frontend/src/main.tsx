import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

function App() {
  const [status, setStatus] = useState('Checking backend connection…');
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/health', { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error('API unavailable'); return response.json(); })
      .then(data => setStatus(data.status === 'ok' ? 'Backend connected' : 'Backend not ready'))
      .catch(error => { if (error.name !== 'AbortError') setStatus('Backend unavailable — start the API on port 8000'); });
    return () => controller.abort();
  }, []);
  return <main><p>TIME AND ATTENDANCE</p><h1>Resolva</h1>
    <p>AI drafts. Rules verify. The manager decides.</p>
    <section><h2>Development workspace</h2><p role="status">{status}</p>
    <p>The application structure is ready. Exception handling and manager workflows are pending implementation.</p></section></main>;
}

createRoot(document.getElementById('root')!).render(<App />);
