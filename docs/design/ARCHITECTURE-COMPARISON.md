# Architecture Comparison: Original vs Ollie 
 
## Original architecture 
### Backend 
- FastAPI with background_tasks 
- Manual freeze flags (_aoi_freeze dict) 
- No task cancellation mechanism 
- Race conditions in guidance generation 
 
### Frontend 
- 15+ useRef hooks for state management 
- Manual synchronization between refs 
- Complex timer management 
- No centralized state machine 
 
## Ollie architecture 
### Backend 
- Explicit state machine with valid transitions 
- Proper async task management with cancellation 
- WebSocket for real-time state updates 
- Impossible to have race conditions 
 
### Frontend 
- Single useGuidanceStateMachine hook 
- WebSocket-driven state updates 
- Event-driven architecture 
- Predictable state transitions 
