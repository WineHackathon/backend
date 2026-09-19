import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

try:
    from app.config import settings
except ImportError:
    settings = None

logger = logging.getLogger(__name__)


class VectorIndex:
    """
    In-memory cosine similarity vector index over wine catalog embeddings.
    Features cryptographic HMAC-SHA256 integrity verification, versioning and tamper resistance (HIGH-04).
    """

    VERSION = "1.0.0"

    def __init__(self, hmac_secret: str | None = None) -> None:
        self.slugs: list[str] = []
        self.embeddings: np.ndarray | None = None  # Shape (N, D)
        self.version: str = self.VERSION
        self.created_at: str | None = None
        self.hmac_secret: str = (
            hmac_secret
            or (getattr(settings, "index_hmac_secret", None) if settings else None)
            or "wine_ml_index_integrity_secret_key_v1"
        )

    def is_empty(self) -> bool:
        return self.embeddings is None or len(self.slugs) == 0

    def add(self, slug: str, embedding: np.ndarray) -> None:
        """Add single wine embedding vector to index."""
        self.slugs.append(slug)
        embedding = embedding.reshape(1, -1)
        if self.embeddings is None:
            self.embeddings = embedding
        else:
            self.embeddings = np.vstack([self.embeddings, embedding])

    def search_top1(self, query_embedding: np.ndarray) -> tuple[str | None, float]:
        """
        Query index with normalized vector via dot product.
        Returns (top_1_slug, confidence_score).
        """
        if self.is_empty():
            logger.warning("Search called on empty vector index")
            return None, 0.0

        # Cosine similarity via inner product on L2-normalized vectors
        scores = np.dot(self.embeddings, query_embedding)  # Shape (N,)
        best_idx = int(np.argmax(scores))
        confidence = float(scores[best_idx])
        return self.slugs[best_idx], confidence

    def _compute_hmac(self) -> str:
        """Calculate HMAC-SHA256 digest of embeddings, slugs, and version using secret key."""
        mac = hmac.new(self.hmac_secret.encode("utf-8"), digestmod=hashlib.sha256)
        mac.update(self.VERSION.encode("utf-8"))
        if self.embeddings is not None:
            mac.update(self.embeddings.tobytes())
        mac.update("".join(self.slugs).encode("utf-8"))
        return mac.hexdigest()

    def save(self, filepath: str) -> None:
        """Persist index matrix, slugs, version and cryptographic HMAC signature to compressed .npz archive."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.embeddings is not None:
            signature = self._compute_hmac()
            now_iso = datetime.now(timezone.utc).isoformat()
            np.savez_compressed(
                filepath,
                slugs=np.array(self.slugs),
                embeddings=self.embeddings,
                version=np.array(self.VERSION),
                created_at=np.array(now_iso),
                signature=np.array(signature),
            )
            # Write HMAC sidecar file for external verification
            sidecar = path.with_suffix(".npz.sig")
            sidecar.write_text(signature, encoding="utf-8")
            logger.info(f"Saved vector index with {len(self.slugs)} entries (sig: {signature[:12]}...) to {filepath}")

    def load(self, filepath: str, verify_checksum: bool = True) -> bool:
        """Load and cryptographically verify persisted index from .npz file."""
        path = Path(filepath)
        if not path.exists():
            return False
        try:
            data = np.load(filepath, allow_pickle=True)
            loaded_version = str(data["version"]) if "version" in data else "unknown"

            # Version matching validation
            if loaded_version != self.VERSION:
                logger.error(
                    f"Index version mismatch! Worker expected {self.VERSION}, but index has {loaded_version}."
                )
                return False

            self.slugs = list(data["slugs"])
            self.embeddings = data["embeddings"]
            self.version = loaded_version
            self.created_at = str(data["created_at"]) if "created_at" in data else None

            if verify_checksum:
                # Support both "signature" (HMAC) and legacy "checksum" (SHA-256)
                if "signature" in data:
                    stored_sig = str(data["signature"])
                    calculated_sig = self._compute_hmac()
                    if not hmac.compare_digest(stored_sig, calculated_sig):
                        logger.error("HMAC signature verification failed! Possible tamper detected.")
                        self.slugs = []
                        self.embeddings = None
                        return False
                elif "checksum" in data:
                    hasher = hashlib.sha256()
                    if self.embeddings is not None:
                        hasher.update(self.embeddings.tobytes())
                    hasher.update("".join(self.slugs).encode("utf-8"))
                    if not hmac.compare_digest(str(data["checksum"]), hasher.hexdigest()):
                        logger.error("Legacy checksum verification failed!")
                        self.slugs = []
                        self.embeddings = None
                        return False

            logger.info(
                f"Successfully loaded and verified vector index with {len(self.slugs)} wines (v{self.version}) from {filepath}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to load vector index from {filepath}: {e}")
            return False
