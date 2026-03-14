# OmniParser Models

This directory contains pre-trained models for the OmniParser hybrid perception pipeline.

## Model Structure

```
models/
└── omniparser/
    ├── icon_detect/
    │   └── best.pt          # YOLOv8 weights for UI element detection
    └── icon_caption_florence/  # (Optional) Florence-2 for icon captioning
```

## Automatic Download

Models are automatically downloaded from HuggingFace on first use:

```python
from perception.omniparser_detector import OmniParserDetector

# Model will be downloaded automatically if not present
detector = OmniParserDetector()
detections = detector.detect(screenshot)
```

## Manual Download

To pre-download models:

```bash
pip install huggingface-hub

python -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='microsoft/OmniParser-v2.0',
    local_dir='./models/omniparser',
    allow_patterns=['icon_detect/*']
)
"
```

## Model Source

- **Repository:** https://huggingface.co/microsoft/OmniParser-v2.0
- **Paper:** OmniParser v2 (Microsoft, 2025)
- **License:** See HuggingFace repository for license terms

## Performance

| Device | Inference Time | Notes |
|--------|---------------|-------|
| CUDA GPU | 200-400ms | Recommended |
| Apple MPS | 300-500ms | M1/M2 Macs |
| CPU | 2-3s | Fallback only |

## Troubleshooting

### Model not loading
```bash
# Verify model file exists
ls models/omniparser/icon_detect/best.pt

# If not, re-download
python -c "from perception.omniparser_detector import OmniParserDetector; OmniParserDetector()"
```

### GPU not detected
```python
# Check CUDA availability
import torch
print(f"CUDA: {torch.cuda.is_available()}")
print(f"MPS: {torch.backends.mps.is_available()}")
```
