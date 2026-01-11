# Agent0 SDK v0.2.2 Release Notes

## What's New

### Fixed Agent Search by Owner/Operator ([#2](https://github.com/agent0lab/agent0-py/pull/2))
Fixed `owners` and `operators` filters in `searchAgents()` that were not being correctly applied.

### Reduced Installation Footprint ([#5](https://github.com/agent0lab/agent0-py/pull/5))
- Made `sentence-transformers` optional (moved to `[project.optional-dependencies]`)
- Removed unused `numpy` and `scikit-learn` dependencies
- **Result:** Significantly reduced default installation size (removes PyTorch stack)

### Additional Improvements ([#4](https://github.com/agent0lab/agent0-py/pull/4))
Various improvements and enhancements related to A2A cards and A2A skills.

## Migration

**No breaking changes.**
```

## Installation

```bash
pip install --upgrade agent0-sdk
```

---

**Contributors:** [@ptrus](https://github.com/ptrus), [@rickycambrian](https://github.com/rickycambrian)  
**Full Changelog:** [v0.2.1...v0.2.2](https://github.com/agent0lab/agent0-py/compare/v0.2.1...v0.2.2)

