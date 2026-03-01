import React from 'react';
import './IntroPage.css';

const ChildAssistanceSetup = ({ onContinue, onBack }) => {
  const [selectedActivity, setSelectedActivity] = React.useState('');
  const [needsAssistance, setNeedsAssistance] = React.useState('');
  const [needsEyeTracking, setNeedsEyeTracking] = React.useState('');

  const submit = (e) => {
    e.preventDefault();
    onContinue && onContinue(selectedActivity || 'qa', needsAssistance || 'no', needsEyeTracking || 'no');
  };

  return (
    <div className="intro-page">
      <div className="intro-upload-top">
        <button className="intro-upload-btn" onClick={onBack}>← Back</button>
      </div>
      <div className="intro-card">
        <div className="assistant-stage">
          <img src="http://localhost:8001/assistant/hi.png" alt="assistant says hi" className="intro-assistant" />
          <div className="chat-bubble" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <span className="typed-text">Hi there! Let's set up your reading adventure.</span>
            <form onSubmit={submit} className="intro-form">
              <div className="parent-form-section">
                <div className="form-section-title">Choose reading activity</div>
                <div className="radio-options-container">
                  <label className="radio-option-label">
                    <input
                      type="radio"
                      name="activity"
                      value="qa"
                      checked={selectedActivity === 'qa'}
                      onChange={(e) => setSelectedActivity(e.target.value)}
                    />
                    <span className="radio-option-text">Question-and-Answer Reading</span>
                  </label>
                  <label className="radio-option-label">
                    <input
                      type="radio"
                      name="activity"
                      value="storytelling"
                      checked={selectedActivity === 'storytelling'}
                      onChange={(e) => setSelectedActivity(e.target.value)}
                    />
                    <span className="radio-option-text">Busy Picture Book Reading</span>
                  </label>
                </div>
              </div>
              <div className="parent-form-section">
                <div className="form-section-title">Do you want assistance?</div>
                <div className="radio-options-container">
                  <label className="radio-option-label">
                    <input
                      type="radio"
                      name="assistance"
                      value="yes"
                      checked={needsAssistance === 'yes'}
                      onChange={(e) => setNeedsAssistance(e.target.value)}
                    />
                    <span className="radio-option-text">Yes, provide AI assistance and guidance</span>
                  </label>
                  <label className="radio-option-label">
                    <input
                      type="radio"
                      name="assistance"
                      value="no"
                      checked={needsAssistance === 'no'}
                      onChange={(e) => setNeedsAssistance(e.target.value)}
                    />
                    <span className="radio-option-text">No, just simple viewing experience</span>
                  </label>
                </div>
              </div>
              {needsAssistance === 'yes' && (
                <div className="parent-form-section">
                  <div className="form-section-title">Enable eye-tracking for enhanced guidance?</div>
                  <div className="radio-options-container">
                    <label className="radio-option-label">
                      <input
                        type="radio"
                        name="eyeTracking"
                        value="yes"
                        checked={needsEyeTracking === 'yes'}
                        onChange={(e) => setNeedsEyeTracking(e.target.value)}
                      />
                      <span className="radio-option-text">Yes, enable gaze tracking for enhanced guidance</span>
                    </label>
                    <label className="radio-option-label">
                      <input
                        type="radio"
                        name="eyeTracking"
                        value="no"
                        checked={needsEyeTracking === 'no'}
                        onChange={(e) => setNeedsEyeTracking(e.target.value)}
                      />
                      <span className="radio-option-text">No, provide assistance without eye-tracking</span>
                    </label>
                  </div>
                </div>
              )}
              <button 
                className="intro-confirm" 
                type="submit" 
                disabled={!selectedActivity || !needsAssistance || (needsAssistance === 'yes' && !needsEyeTracking)}
              >
                Continue
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChildAssistanceSetup;
