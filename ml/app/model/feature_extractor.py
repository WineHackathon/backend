import io
import logging
from PIL import Image
import numpy as np
import torch
import torchvision.transforms as T
import torchvision.models as models

logger = logging.getLogger(__name__)


class VisionFeatureExtractor:
    """Extracts normalized visual embeddings from wine bottle photographs."""

    def __init__(self) -> None:
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")

        logger.info(f"Initializing feature extractor on device: {self.device}")

        # Lightweight, high-accuracy vision backbone (MobileNetV3 / ResNet)
        try:
            weights = models.MobileNet_V3_Small_Weights.DEFAULT
            self.model = models.mobilenet_v3_small(weights=weights)
        except Exception:
            # Offline initialization fallback
            self.model = models.mobilenet_v3_small()

        # Remove final classifier to output raw embedding representation
        self.model.classifier = torch.nn.Identity()
        self.model.eval()
        self.model.to(self.device)

        self.transform = T.Compose([
            T.Resize(256),
            T.CenterCrop(224),
            T.ToTensor(),
            T.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])

    def extract_from_bytes(self, image_bytes: bytes) -> np.ndarray:
        """Process image bytes and return unit-normalized embedding vector."""
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = self.transform(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            embedding = self.model(tensor).cpu().numpy().flatten()

        # L2 unit normalization for exact cosine similarity via dot product
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding
