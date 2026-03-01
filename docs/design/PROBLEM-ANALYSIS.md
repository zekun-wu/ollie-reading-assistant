# Problem Analysis 
 
## The Core Issue 
Child stares at Object A for 4+ seconds  Curiosity guidance starts 
While guidance is playing, child stares at Object B  Second guidance triggers 
Result: TWO assistants appear simultaneously 
 
## Root Cause Analysis 
### Backend Issue (main.py:1123-1158) 
Problem: background_tasks.add_task() cannot be cancelled 
Multiple tasks run in parallel causing overlap 
 
### Frontend Issue (PictureBook.js:47-88) 
Problem: Multiple refs cause race conditions 
pendingGuidanceRef, nudgeGuidanceRef, activeRequestRef get out of sync 
