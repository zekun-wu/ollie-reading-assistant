# Project Structure 
 
## Repository Organization 
Ollie/ 
��� README.md                    # Project overview and links 
��� backend/ 
�   ��� src/                     # New implementation 
�   �   ��� main.py             # FastAPI app with state machine 
�   �   ��� state_machine.py    # Core state management 
�   �   ��� guidance_service.py # Guidance generation service 
�   �   ��� websocket_handler.py # Real-time communication 
�   ��� tests/                   # Comprehensive test suite 
�   ��� requirements.txt         # Python dependencies 
��� frontend/ 
�   ��� src/ 
�   �   ��� hooks/              # Custom React hooks 
�   �   ��� components/         # React components 
�   ��� package.json             # Node.js dependencies 
��� docs/                        # All documentation 
��� reference/                   # Original files for reference 
��� tools/                       # Migration and testing tools 
