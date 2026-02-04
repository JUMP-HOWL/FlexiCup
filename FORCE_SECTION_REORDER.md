# Force Characterization Section Reordering

## Change Made
Moved "Sensor-Based Force Characterization" to be the first subsection in System Characterization.

## New Order in System Characterization

1. **Force Characterization** ← Moved to first position
2. **Wafer Pick-up Comparison** 
3. **Dynamic Performance**

## Rationale
- Force characterization provides fundamental quantitative validation
- Establishes baseline performance metrics before specific applications
- Logical flow: Basic force → Specific validation → Dynamic performance

## Navigation Updated
Side navigation now reflects new order:
```
System Characterization
├─ Force Characterization
├─ Wafer Pick-up  
└─ Dynamic Performance
```

## Files Modified
- `FlexiCup_website/index.html` - Reordered sections and updated navigation

## Testing
Refresh http://localhost:8080/index.html to verify:
- ✅ Force Characterization appears first in System Characterization
- ✅ Navigation links work correctly
- ✅ Content flows logically
- ✅ No duplicate content