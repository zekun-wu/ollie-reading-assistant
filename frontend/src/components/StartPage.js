import React, { useState } from 'react';
import './StartPage.css';

const StartPage = ({ onStart }) => {
  const [userNumber, setUserNumber] = useState('');

  const isValidUserNumber = () => {
    const num = parseInt(userNumber, 10);
    return !isNaN(num) && num >= 1 && num <= 100;
  };

  const handleStart = () => {
    if (isValidUserNumber()) {
      onStart('de', parseInt(userNumber, 10));
    }
  };

  return (
    <div className="start-page">
      <div className="start-container">
        {/* Welcome Section */}
        <div className="welcome-section">
          <h1 className="welcome-title">Willkommen bei EyeRead</h1>
          <p className="welcome-subtitle">
            Ein interaktives Leseerlebnis für Kinder
          </p>
        </div>

        {/* User Number Selection */}
        <div className="user-number-section">
          <label className="user-number-label">
            Teilnehmernummer
          </label>
          <input
            type="number"
            min="1"
            max="100"
            value={userNumber}
            onChange={(e) => setUserNumber(e.target.value)}
            placeholder="1-100"
            className="user-number-input"
          />
          {userNumber && !isValidUserNumber() && (
            <span className="user-number-error">
              Bitte geben Sie eine Zahl zwischen 1 und 100 ein
            </span>
          )}
        </div>

        {/* Start Button */}
        <button 
          className="btn-start"
          onClick={handleStart}
          disabled={!isValidUserNumber()}
        >
          STARTEN
        </button>
      </div>
    </div>
  );
};

export default StartPage;
