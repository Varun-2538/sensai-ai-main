# MediaPipe Proctoring System Setup Guide

This guide explains how to set up and test the MediaPipe-based proctoring system for SensAI.

## Overview

The system combines:
- **MediaPipe**: Advanced face detection, pose estimation, and gaze tracking
- **Native Browser APIs**: Tab switching, window blur, and copy/paste detection
- **Backend Integration**: Event logging, analysis, and integrity scoring
- **Real-time Processing**: Event batching, throttling, and live monitoring

## Backend Setup

### 1. Database Tables
The system automatically creates three new tables:
- `integrity_sessions`: Monitoring sessions
- `proctor_events`: Individual monitoring events
- `integrity_flags`: Generated integrity flags

### 2. API Endpoints
New endpoints available at `/integrity/`:
- `POST /sessions` - Create monitoring session
- `GET /sessions/{uuid}` - Get session details
- `POST /events` - Log single event
- `POST /events/batch` - Log multiple events
- `GET /sessions/{uuid}/analysis` - Get session analysis
- `GET /cohorts/{id}/integrity-overview` - Cohort overview

### 3. Environment Variables
```bash
# Optional configuration
INTEGRITY_MONITORING_ENABLED=true
MAX_CONCURRENT_SESSIONS=100
EVENT_BATCH_SIZE=10
```

## Frontend Setup

### 1. Install Dependencies
```bash
cd sensai-frontend
npm install @mediapipe/tasks-vision
```

### 2. Components Added
- `MediaPipeProctor.tsx` - Core MediaPipe integration
- `IntegratedProctorSystem.tsx` - Complete proctoring system
- `integrity-api.ts` - Backend API client
- `ui/alert.tsx` & `ui/badge.tsx` - UI components

### 3. Demo Page
Visit `/integrity-demo` to test the system

## How It Works

### MediaPipe Features
1. **Face Detection**: Detects if face is present/absent
2. **Multiple Face Detection**: Identifies when multiple people are present
3. **Gaze Tracking**: Monitors eye direction and head position
4. **Head Movement**: Tracks significant head movements
5. **Pose Detection**: Monitors body position changes

### Native Browser Features
1. **Tab Switching**: Detects when user switches tabs
2. **Window Blur**: Monitors when window loses focus
3. **Copy/Paste**: Detects clipboard operations
4. **Context Menu**: Prevents right-click menu

### Event Processing
- **Throttling**: Prevents spam events
- **Batching**: Groups events for efficient transmission
- **Severity Scoring**: Automatic event classification
- **Flagging**: Auto-generates integrity flags

## Testing the System

### 1. Start Backend
```bash
cd sensai-ai
python -m uvicorn src.api.main:app --reload
```

### 2. Start Frontend
```bash
cd sensai-frontend
npm run dev
```

### 3. Access Demo
Navigate to `http://localhost:3000/integrity-demo`

### 4. Test Scenarios
- **Face Detection**: Move out of camera view
- **Multiple Faces**: Have someone else join the camera
- **Gaze Tracking**: Look away from the camera
- **Tab Switching**: Switch to another tab
- **Copy/Paste**: Try copying text

## Integration with Existing Platform

### 1. Assessment Integration
```tsx
import IntegratedProctorSystem from '@/components/IntegratedProctorSystem';

// In your assessment component
<IntegratedProctorSystem
  userId={currentUser.id}
  cohortId={cohort.id}
  taskId={task.id}
  onSessionEnd={(uuid, analysis) => {
    // Handle session completion
    console.log('Integrity Score:', analysis.integrity_score);
  }}
  sensitivity="medium"
  autoStart={true}
/>
```

### 2. Admin Dashboard
```tsx
// Get cohort integrity overview
const overview = await integrityAPI.getCohortOverview(cohortId, true);

// Review pending flags
const pendingFlags = await integrityAPI.getPendingFlags();

// Update flag decisions
await integrityAPI.updateFlagDecision(flagId, 'resolved');
```

## Security Considerations

### 1. Permissions
- Camera access required for MediaPipe
- Events tied to authenticated users
- Session validation on all endpoints

### 2. Privacy
- Video processing happens locally (on-device)
- Only landmarks and events sent to server
- No video recording or storage

### 3. Data Retention
- Events and flags stored with timestamps
- Configurable retention policies
- GDPR-compliant data handling

## Performance

### 1. MediaPipe Optimization
- GPU acceleration enabled
- 30 FPS processing limit
- Efficient landmark extraction

### 2. Event Optimization
- Event throttling (1-5 second cooldowns)
- Batch processing (5-10 events per batch)
- Automatic severity classification

### 3. Network Optimization
- Compressed event data
- Batch API calls
- Connection pooling

## Troubleshooting

### Camera Issues
- Check browser permissions
- Ensure HTTPS (required for camera access)
- Test camera in other applications

### MediaPipe Loading
- Check network connectivity
- Verify CDN access to MediaPipe scripts
- Check browser console for errors

### Backend Connection
- Verify API endpoint accessibility
- Check authentication tokens
- Monitor network requests in DevTools

## Production Deployment

### 1. Database Migration
Tables will auto-create on first startup, or run manually:
```sql
-- Run in production database
CREATE TABLE integrity_sessions (...);
CREATE TABLE proctor_events (...);
CREATE TABLE integrity_flags (...);
```

### 2. Environment Configuration
```bash
# Production settings
INTEGRITY_MONITORING_ENABLED=true
MAX_CONCURRENT_SESSIONS=1000
EVENT_BATCH_SIZE=50
DATABASE_POOL_SIZE=20
```

### 3. Monitoring
- Set up alerts for high event volumes
- Monitor integrity scores and flag rates
- Track system performance metrics

## Future Enhancements

### Planned Features
1. **Audio Monitoring**: Voice pattern analysis
2. **Screen Recording**: Optional video capture
3. **Advanced ML**: Custom behavior models
4. **Mobile Support**: Responsive design improvements
5. **Real-time Alerts**: Live admin notifications

### Integration Opportunities
1. **LMS Integration**: Canvas, Moodle, etc.
2. **Video Conferencing**: Zoom, Teams integration
3. **Identity Verification**: Document verification
4. **Biometric Authentication**: Fingerprint, face ID

## Support

For issues or questions:
1. Check browser console for JavaScript errors
2. Review backend logs for API errors
3. Test with the demo page first
4. Verify camera and network connectivity
