import React, { useState, useEffect, useRef } from 'react';
import './PictureBook.css'; // Use the same CSS as PictureBook

const BaselineBook = ({ activity, isParentMode = false, onBackToModeSelect }) => {
  const [currentPage, setCurrentPage] = useState(0);
  const [isFullscreenMode, setIsFullscreenMode] = useState(false);
  const fullscreenImageRef = useRef(null);

  // Choose images based on activity
  const allImages = activity === 'storytelling' ? [
    'http://localhost:8001/storytelling-pictures/1.png',
    'http://localhost:8001/storytelling-pictures/2.png'
  ] : [
    'http://localhost:8001/pictures/1.jpg',
    'http://localhost:8001/pictures/2.jpg',
    'http://localhost:8001/pictures/3.jpg',
    'http://localhost:8001/pictures/4.jpg',
    'http://localhost:8001/pictures/5.jpg'
  ];

  const totalPages = allImages.length;

  // Get current page image
  const getCurrentPageImage = () => {
    return allImages[currentPage];
  };

  // Navigation functions
  const handleNextPage = () => {
    if (currentPage < totalPages - 1) {
      setCurrentPage(currentPage + 1);
    }
  };

  const handlePrevPage = () => {
    if (currentPage > 0) {
      setCurrentPage(currentPage - 1);
    }
  };

  // Fullscreen functions
  const handleImageClick = () => {
    setIsFullscreenMode(true);
  };

  const handleExitFullscreen = () => {
    setIsFullscreenMode(false);
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (isFullscreenMode) {
        if (event.key === 'Escape') {
          handleExitFullscreen();
        } else if (event.key === 'ArrowRight') {
          handleNextPage();
        } else if (event.key === 'ArrowLeft') {
          handlePrevPage();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isFullscreenMode, currentPage]);

  // Fullscreen mode - matches PictureBook structure
  if (isFullscreenMode) {
    return (
      <div className="fullscreen-eye-tracking">
        <img
          src={getCurrentPageImage()}
          alt={`${activity} page ${currentPage + 1}`}
          className="fullscreen-image"
          ref={fullscreenImageRef}
        />

        {/* Eye tracking status - simplified for baseline */}
        <div className="eye-tracking-status">
          <div className="status-indicator inactive">
            {activity === 'storytelling' ? '📚' : '❓'} Baseline Mode
          </div>
          <div className="status-text">
            Press ESC to exit fullscreen
          </div>
        </div>

        {/* Fullscreen instructions */}
        <div className="fullscreen-instructions">
          <div className="instruction-item">
            <span className="instruction-key">ESC</span>
            <span>Exit fullscreen</span>
          </div>
          <div className="instruction-item">
            <span className="instruction-key">← →</span>
            <span>Navigate pages</span>
          </div>
        </div>
      </div>
    );
  }

  // Main layout - matches PictureBook structure exactly
  return (
    <div className="picture-book">
      {/* Compact header with back button and navigation */}
      <div className="compact-header">
        <button
          className="back-button"
          onClick={onBackToModeSelect}
        >
          ← Back to Mode Selection
        </button>

        <div className="top-navigation">
          <button
            onClick={handlePrevPage}
            disabled={currentPage === 0}
            className="nav-button prev-button"
          >
            ← Previous
          </button>

          <div className="page-info">
            <span className="page-counter">
              Page {currentPage + 1} of {totalPages}
            </span>
          </div>

          <button
            onClick={handleNextPage}
            disabled={currentPage === totalPages - 1}
            className="nav-button next-button"
          >
            Next →
          </button>
        </div>

        {/* Simple viewing mode */}
      </div>

      {/* Main image area - takes most of the space */}
      <div className="main-image-area">
          <div className={`image-card`}>
            <img
              src={getCurrentPageImage()}
              alt={`${activity} page ${currentPage + 1}`}
              className="book-image"
              onDoubleClick={handleImageClick}
            />
          </div>
        </div>
    </div>
  );
};

export default BaselineBook;
