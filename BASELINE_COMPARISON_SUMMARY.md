# BC-RNN Baseline Comparison Addition Summary

## Overview
Added BC-RNN baseline comparison to address reviewer concerns about non-diffusion learning baselines.

## Location in Website
- Section: Applications → End-to-End Contact-Aware Manipulation
- Position: After the two main task demonstrations
- Added as subsection with separator line

## Content Structure

### 1. Introduction
Explains the BC-RNN baseline implementation using same multimodal observations and training data.

### 2. Key Finding
BC-RNN consistently failed both tasks, getting stuck near target objects without progressing to successful manipulation.

### 3. Two-Column Video Comparison
**Left Column - BC-RNN: Inclined Transport (Failed)**
- Video: `baseline1.mp4` (565KB, optimized from 9.5MB)
- Shows BC-RNN failure on inclined transport task

**Right Column - BC-RNN: Orange Extraction (Failed)**
- Video: `baseline2.mp4` (429KB, optimized from 9.0MB)  
- Shows BC-RNN failure on orange extraction task

### 4. Conclusion
Validates diffusion policy choice for complex contact-aware manipulation tasks.

## Reviewer Response Addressed

**Original Concern**: "I also recommend including variations in object pose, surface properties, harder task variations as well as comparisons with non-diffusion learning baselines to better support the learning-based approach."

**Response Elements**:
1. ✅ **Non-diffusion baseline**: Implemented BC-RNN (Behavioral Cloning with RNN)
2. ✅ **Same conditions**: Used identical multimodal observations and training data
3. ✅ **Clear comparison**: Both tasks show BC-RNN failures vs. diffusion policy success
4. ✅ **Validation**: Demonstrates advantage of diffusion policies for contact-aware manipulation

## Technical Details

### Video Optimization Results
- baseline1.mp4: 9.5MB → 565KB (94.0% reduction)
- baseline2.mp4: 9.0MB → 429KB (95.2% reduction)

### Baseline Implementation
- **Method**: BC-RNN (Behavioral Cloning with RNN)
- **Input**: Same multimodal observations (workspace + dual-zone suction cameras)
- **Training Data**: Identical demonstration data used for diffusion policy
- **Architecture**: RNN-based policy network for sequential decision making

### Failure Modes Observed
1. **Inclined Transport**: Gets stuck near object, unable to establish proper contact
2. **Orange Extraction**: Fails to progress beyond initial approach phase
3. **Common Pattern**: Cannot handle complex contact-aware manipulation sequences

## Key Messages

### For Reviewers
- Demonstrates that the task complexity requires advanced policy learning
- Shows diffusion policy advantage over traditional behavioral cloning
- Validates the choice of diffusion-based approach for multimodal manipulation

### Technical Insights
- Contact-aware manipulation requires sophisticated policy representation
- Sequential decision-making benefits from diffusion policy's iterative refinement
- Multimodal sensory fusion is better handled by diffusion architectures

## Comparison Summary

| Method | Inclined Transport | Orange Extraction | Key Characteristics |
|--------|-------------------|-------------------|-------------------|
| **Diffusion Policy** | 73.3% success | 66.7% success | Handles contact-aware manipulation |
| **BC-RNN Baseline** | 0% success | 0% success | Gets stuck near objects |

## Files Modified
- `FlexiCup_website/index.html` - Added baseline comparison section

## Files Added
- `FlexiCup_website/static/video/optimized/baseline1.mp4`
- `FlexiCup_website/static/video/optimized/baseline2.mp4`

## Testing
Local server: http://localhost:8080/index.html

Verify:
1. ✅ Baseline comparison appears after main task demonstrations
2. ✅ Both baseline videos load and autoplay correctly
3. ✅ Content flows naturally with existing sections
4. ✅ Styling is consistent with other video comparisons
5. ✅ Captions clearly indicate failure modes

## Impact
This addition:
- Directly addresses reviewer concern about non-diffusion baselines
- Provides concrete evidence of diffusion policy advantages
- Strengthens the experimental validation of the learning approach
- Shows the complexity of contact-aware manipulation tasks
- Validates the technical approach without requiring extensive additional experiments