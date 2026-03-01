import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App_Official';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  // Temporarily disable StrictMode to avoid double WebSocket connections in dev
  // <React.StrictMode>
    <App />
  // </React.StrictMode>
);
