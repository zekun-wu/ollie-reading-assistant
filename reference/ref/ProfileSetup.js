import React, { useState } from 'react';
import './ProfileSetup.css';

const ProfileSetup = ({ onProfileSubmit }) => {
  const [errors, setErrors] = useState({});

  // Language selection removed; default language will be used globally

  const handleChooseMode = (mode) => {
    onProfileSubmit(mode);
  };

  return (
    <div className="profile-setup">
      <div className="profile-container">
        <div className="profile-header">
          <h1 className="profile-title">Welcome to GazeStory Lab</h1>
          <p className="profile-subtitle">Choose how you want to start</p>
        </div>

        <div className="profile-form" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <button type="button" className="submit-btn" onClick={() => handleChooseMode('child')}>Child Alone Mode</button>
          <button type="button" className="submit-btn" onClick={() => handleChooseMode('parent')}>Parent-Child Joint Mode</button>
        </div>
      </div>
    </div>
  );
};

export default ProfileSetup;
