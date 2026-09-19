import json
import logging
import signal
import sys
import threading
import time
import boto3
from botocore.client import Config
import redis

from app.config import settings
from app.model.feature_extractor import VisionFeatureExtractor
from app.model.vector_index import VectorIndex

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [MLWorker] %(message)s",
)
logger = logging.getLogger("ml_worker")


class MLRecognitionWorker:
    """Redis Stream consumer worker performing wine label image recognition."""

    def __init__(self) -> None:
        self.running = True
        self.in_flight_message_id: str | None = None
        self.is_processing = threading.Event()
        self.shutdown_event = threading.Event()
        logger.info(f"Initializing ML worker (Consumer: {settings.consumer_name})...")

        # 1. Connect to Redis
        self.redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            decode_responses=True,
        )

        # 2. Connect to MinIO S3
        self.s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4"),
        )

        # 3. Initialize Vision Model and Vector Index
        self.extractor = VisionFeatureExtractor()
        self.index = VectorIndex()

        # Try loading precomputed vector index
        loaded = self.index.load(settings.index_cache_file)
        if not loaded or self.index.is_empty():
            logger.warning(
                f"No precomputed index at {settings.index_cache_file}. "
                "Will bootstrap index from catalog service or synthesize initial anchors."
            )
            self._bootstrap_minimal_index()

        self._init_stream_group()

    def _init_stream_group(self) -> None:
        """Create consumer group on stream if not already existing."""
        try:
            self.redis.xgroup_create(
                settings.tasks_stream,
                settings.consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info(f"Created consumer group '{settings.consumer_group}' on '{settings.tasks_stream}'")
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Consumer group '{settings.consumer_group}' already exists")
            else:
                logger.error(f"Error creating consumer group: {e}")

    def _bootstrap_minimal_index(self) -> None:
        """
        Safely initialize vector index.
        Does NOT fabricate fake pseudo-noise vectors. Real embeddings are indexed
        via scripts/build_index.py or dynamically synchronized from catalog S3 images.
        """
        logger.info("Vector index is currently empty. Awaiting index build or dynamic image synchronization.")
        self.index = VectorIndex()

    def run(self) -> None:
        """Main consumer loop polling Redis Stream for tasks."""
        logger.info(f"ML Recognition Worker ready, polling stream: {settings.tasks_stream}")
        last_heartbeat_time = 0.0

        while self.running and not self.shutdown_event.is_set():
            now = time.time()
            if now - last_heartbeat_time >= 5.0:
                try:
                    self.redis.setex(
                        f"ml:worker:heartbeat:{settings.consumer_name}",
                        15,
                        str(now),
                    )
                    last_heartbeat_time = now
                except Exception as exc:
                    logger.debug(f"Failed to update worker heartbeat: {exc}")

            try:
                # Read 1 task from stream with 2s block timeout
                response = self.redis.xreadgroup(
                    groupname=settings.consumer_group,
                    consumername=settings.consumer_name,
                    streams={settings.tasks_stream: ">"},
                    count=1,
                    block=2000,
                )

                if not response:
                    continue

                for stream_name, messages in response:
                    for message_id, data in messages:
                        self._process_message(message_id, data)

            except Exception as e:
                if not self.running or self.shutdown_event.is_set():
                    break
                logger.error(f"Unexpected error in consumer loop: {e}", exc_info=True)
                time.sleep(1)

        self.stop(timeout=25.0)

    def _process_message(self, message_id: str, data: dict) -> None:
        self.is_processing.set()
        self.in_flight_message_id = message_id
        try:
            request_id = data.get("request_id")
            image_id = data.get("image_id")
            s3_key = data.get("s3_key")

            if not request_id or not s3_key:
                logger.warning(f"Malformed task message {message_id}: {data}")
                self.redis.xack(settings.tasks_stream, settings.consumer_group, message_id)
                return

            start_time = time.perf_counter()
            logger.info(f"Processing task {request_id} for image {image_id}...")

            predicted_slug = None
            confidence = 0.0

            try:
                # 1. Download image from MinIO S3
                s3_response = self.s3.get_object(
                    Bucket=settings.s3_scans_bucket,
                    Key=s3_key,
                )
                image_bytes = s3_response["Body"].read()

                # 2. Extract visual feature embedding
                embedding = self.extractor.extract_from_bytes(image_bytes)

                # 3. Vector search Top-1 match
                predicted_slug, confidence = self.index.search_top1(embedding)
                inference_ms = int((time.perf_counter() - start_time) * 1000)
                logger.info(f"Prediction: slug='{predicted_slug}' (conf={confidence:.3f}) in {inference_ms}ms")

            except Exception as e:
                logger.error(f"Inference error for task {request_id}: {e}", exc_info=True)
                predicted_slug = None

            # 4. Publish result to response channel
            response_payload = {
                "request_id": request_id,
                "image_id": image_id,
                "slug": predicted_slug,
                "confidence": confidence,
            }
            response_channel = f"{settings.response_channel_prefix}{request_id}"
            self.redis.publish(response_channel, json.dumps(response_payload))

            # 5. Acknowledge task in Redis Stream
            self.redis.xack(settings.tasks_stream, settings.consumer_group, message_id)
        finally:
            self.in_flight_message_id = None
            self.is_processing.clear()

    def stop(self, timeout: float = 25.0) -> None:
        """
        Graceful shutdown sequence:
        1. Signals consumer loop to stop accepting new tasks.
        2. Waits up to timeout seconds for any active in-flight task to finish inference,
           publish its result, and acknowledge (XACK) to Redis.
        3. Cleans up Redis connections and exits cleanly.
        """
        if not self.running and self.shutdown_event.is_set():
            return

        logger.info(f"Shutdown sequence initiated. Current in-flight task: {self.in_flight_message_id}")
        self.running = False
        self.shutdown_event.set()

        if self.is_processing.is_set():
            logger.info(
                f"Waiting up to {timeout}s for in-flight task {self.in_flight_message_id} to finish..."
            )
            deadline = time.time() + timeout
            while self.is_processing.is_set() and time.time() < deadline:
                time.sleep(0.02)

            if self.is_processing.is_set():
                logger.warning(
                    f"In-flight task {self.in_flight_message_id} did not finish within {timeout}s timeout!"
                )
            else:
                logger.info("In-flight task completed successfully prior to shutdown.")

        try:
            self.redis.close()
        except Exception:
            pass
        logger.info("ML Recognition Worker stopped cleanly.")


def main():
    worker = MLRecognitionWorker()

    def handle_signal(signum, frame):
        logger.info(f"Received termination signal ({signum}). Initiating graceful shutdown...")
        worker.stop(timeout=25.0)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    worker.run()


if __name__ == "__main__":
    main()
