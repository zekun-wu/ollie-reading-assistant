import React from 'react';
import './CompletionPage.css';

const CompletionPage = ({ onCompleted, childName }) => {
  return (
    <div className="completion-page">
      <div className="completion-card">
        <div className="completion-content">
          <h1 className="completion-title">🎉 Great Job{childName ? `, ${childName}` : ''}!</h1>
          <p className="completion-description">
            You've finished all the reading activities! Thank you for participating in our reading adventure.
          </p>
          <button 
            className="completion-button"
            onClick={onCompleted}
          >
            Completed
          </button>
        </div>
      </div>
    </div>
  );
};

export default CompletionPage;

