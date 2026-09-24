#!/usr/bin/env python3
"""
Скрипт высокоскоростной параллельной загрузки изображений каталога вин в S3-хранилище (FirstVDS / AWS S3).
Поддерживает прямую загрузку из директории или распаковку из zip-архива.
"""
import argparse
import concurrent.futures
import logging
import mimetypes
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("upload_to_s3")


def get_s3_client(endpoint_url: str, access_key: str, secret_key: str, region: str):
    """Инициализация клиента S3 с поддержкой custom endpoint (FirstVDS Ceph)."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region or "ru-central-1",
        verify=False,
        config=Config(
            signature_version="s3",
            s3={"addressing_style": "path"},
            max_pool_connections=50,
        ),
    )


def guess_content_type(file_path: Path) -> str:
    """Определение MIME-типа изображения."""
    suffix = file_path.suffix.lower()
    if suffix == ".webp":
        return "image/webp"
    if suffix in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    ct, _ = mimetypes.guess_type(str(file_path))
    return ct or "application/octet-stream"


def upload_single_file(s3_client, bucket: str, file_path: Path, s3_key: str) -> tuple[bool, str]:
    """Загрузка одного файла с указанием Content-Type."""
    try:
        content_type = guess_content_type(file_path)
        with open(file_path, "rb") as f:
            s3_client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=f,
                ContentType=content_type,
            )
        return True, s3_key
    except Exception as e:
        return False, f"{s3_key}: {e}"


def upload_images(
    source_path: str,
    endpoint_url: str,
    access_key: str,
    secret_key: str,
    bucket: str,
    region: str,
    prefix: str = "catalog",
    max_workers: int = 16,
) -> None:
    source = Path(source_path)
    if not source.exists():
        logger.error(f"Указанный путь не существует: {source}")
        sys.exit(1)

    s3_client = get_s3_client(endpoint_url, access_key, secret_key, region)

    # Проверка доступности бакета
    try:
        s3_client.head_bucket(Bucket=bucket)
        logger.info(f"Подключение к S3 успешно. Бакет '{bucket}' доступен.")
    except Exception as e:
        logger.warning(f"Проверка head_bucket вернула: {e}. Попытка продолжить...")

    # Если передан zip-архив, распаковываем во временную директорию
    temp_dir = None
    if source.is_file() and source.suffix.lower() == ".zip":
        logger.info(f"Обнаружен zip-архив: {source}. Распаковка...")
        temp_dir = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(source, "r") as zip_ref:
            zip_ref.extractall(temp_dir.name)
        images_dir = Path(temp_dir.name)
    elif source.is_dir():
        images_dir = source
    else:
        logger.error(f"Неподдерживаемый формат источника: {source}. Ожидается папка или .zip файл.")
        sys.exit(1)

    # Собираем все графические файлы
    valid_extensions = {".webp", ".jpg", ".jpeg", ".png"}
    files_to_upload: list[Path] = [
        p for p in images_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in valid_extensions and not p.name.startswith(".")
    ]

    total_files = len(files_to_upload)
    logger.info(f"Найдено {total_files} изображений для загрузки в s3://{bucket}/{prefix}/")

    if total_files == 0:
        logger.warning("Нет изображений для загрузки.")
        if temp_dir:
            temp_dir.cleanup()
        return

    clean_prefix = prefix.strip("/")
    success_count = 0
    fail_count = 0

    logger.info(f"Старт многопоточной загрузки ({max_workers} воркеров)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for file_path in files_to_upload:
            s3_key = f"{clean_prefix}/{file_path.name}"
            fut = executor.submit(upload_single_file, s3_client, bucket, file_path, s3_key)
            futures[fut] = s3_key

        for idx, fut in enumerate(concurrent.futures.as_completed(futures), start=1):
            ok, msg = fut.result()
            if ok:
                success_count += 1
            else:
                fail_count += 1
                logger.error(f"Ошибка загрузки: {msg}")

            if idx % 100 == 0 or idx == total_files:
                logger.info(f"Прогресс: {idx}/{total_files} (Успешно: {success_count}, Ошибок: {fail_count})")

    logger.info(f"Загрузка завершена! Всего: {total_files}, успешно: {success_count}, ошибок: {fail_count}.")

    if temp_dir:
        temp_dir.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Загрузка фотографий вин в S3 хранилище")
    parser.add_argument(
        "--source",
        required=True,
        help="Путь к папке с фотографиями или к .zip архиву",
    )
    parser.add_argument(
        "--prefix",
        default="catalog",
        help="Префикс/папка в S3 (по умолчанию 'catalog')",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Количество параллельных потоков (по умолчанию 16)",
    )
    parser.add_argument(
        "--endpoint-url",
        default=os.getenv("S3_ENDPOINT_URL", "https://s3.firstvds.ru:443"),
        help="URL эндпоинта S3",
    )
    parser.add_argument(
        "--access-key",
        default=os.getenv("S3_AWS_ACCESS_KEY_ID") or os.getenv("S3_ACCESS_KEY", ""),
        help="AWS Access Key ID",
    )
    parser.add_argument(
        "--secret-key",
        default=os.getenv("S3_AWS_SECRET_ACCESS_KEY") or os.getenv("S3_SECRET_KEY", ""),
        help="AWS Secret Access Key",
    )
    parser.add_argument(
        "--bucket",
        default=os.getenv("S3_BUCKET_NAME", "wine-hack"),
        help="Название S3 бакета",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("S3_REGION_NAME", "ru-central-1"),
        help="Регион S3",
    )

    args = parser.parse_args()

    if not args.access_key or not args.secret_key:
        logger.error("Не указаны S3_AWS_ACCESS_KEY_ID и/или S3_AWS_SECRET_ACCESS_KEY (в аргументах или .env)!")
        sys.exit(1)

    upload_images(
        source_path=args.source,
        endpoint_url=args.endpoint_url,
        access_key=args.access_key,
        secret_key=args.secret_key,
        bucket=args.bucket,
        region=args.region,
        prefix=args.prefix,
        max_workers=args.workers,
    )


if __name__ == "__main__":
    main()
