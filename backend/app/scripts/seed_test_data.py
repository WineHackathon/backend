"""
Скрипт генерации тестовых данных для ручного и интеграционного тестирования API:
1. Тестовый пользователь (test@wine.ru / password123).
2. Администратор (admin@wine.ru / adminpassword123).
3. Позиции в винном погребе (in_cellar, wishlist, tasted).
4. История сканирований пользователя и гостя (для проверки связывания).
5. История диалогов и предпочтений сомелье.

Запуск:
    python -m backend.app.scripts.seed_test_data
"""
import asyncio
import logging
import uuid
from sqlalchemy import select

from application.adapters.database.db_session import create_session, close_db
from application.adapters.database.models.user import User, UserRole
from application.adapters.database.models.wine import Wine
from application.adapters.database.models.cellar import UserCellar
from application.adapters.database.models.scan_history import UserScanHistory, ScanStatus
from application.adapters.database.models.preference_history import UserPreferenceHistory
from application.entities.user_modes import CellarStatus
from application.services.security import hash_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_test_data")


async def seed_test_data() -> None:
    """Генерация тестовых данных с полной гарантией идемпотентности."""
    try:
        async with create_session() as session:
            # 1. Получаем реальные вина из каталога
            wines_stmt = select(Wine).limit(10)
            res = await session.execute(wines_stmt)
            wines = res.scalars().all()
            if not wines:
                logger.error(
                    "В каталоге нет вин! Сначала загрузите каталог: "
                    "python -m infrastructure.scripts.seed_wines"
                )
                return

            # 2. Создаем или обновляем тестового пользователя
            test_email = "test@wine.ru"
            user = await session.scalar(select(User).where(User.email == test_email))
            if not user:
                user = User(
                    id=uuid.uuid4(),
                    email=test_email,
                    password_hash=hash_password("password123"),
                    first_name="Иван",
                    last_name="Виноделов",
                    role=UserRole.USER,
                    is_admin=False,
                    taste_profile={
                        "preferred_categories": ["Красное", "Белое"],
                        "sweetness_pref": 1.2,
                        "body_pref": 4.2,
                        "acidity_pref": 3.5,
                        "oak_pref": 4.0,
                        "favorite_aromas": ["спелая вишня", "дуб", "черная смородина"],
                        "disliked_aromas": ["табак", "кожа"],
                    },
                )
                session.add(user)
                await session.flush()
                logger.info("Создан тестовый пользователь: %s / password123", test_email)
            else:
                user.password_hash = hash_password("password123")
                if not user.taste_profile:
                    user.taste_profile = {
                        "preferred_categories": ["Красное", "Белое"],
                        "sweetness_pref": 1.2,
                        "body_pref": 4.2,
                        "acidity_pref": 3.5,
                        "oak_pref": 4.0,
                        "favorite_aromas": ["спелая вишня", "дуб", "черная смородина"],
                        "disliked_aromas": ["табак", "кожа"],
                    }
                await session.flush()
                logger.info("Обновлен пароль тестового пользователя: %s / password123", test_email)

            # 3. Создаем или обновляем администратора
            admin_email = "admin@wine.ru"
            admin = await session.scalar(select(User).where(User.email == admin_email))
            if not admin:
                admin = User(
                    id=uuid.uuid4(),
                    email=admin_email,
                    password_hash=hash_password("adminpassword123"),
                    first_name="Админ",
                    last_name="Системный",
                    role=UserRole.ADMIN,
                    is_admin=True,
                    taste_profile={},
                )
                session.add(admin)
                await session.flush()
                logger.info("Создан администратор: %s / adminpassword123", admin_email)
            else:
                admin.password_hash = hash_password("adminpassword123")
                admin.role = UserRole.ADMIN
                admin.is_admin = True
                await session.flush()
                logger.info("Обновлены права администратора: %s / adminpassword123", admin_email)

            # 4. Наполняем личный погреб для test@wine.ru
            cellar_count = 0
            for idx, wine in enumerate(wines[:5]):
                status = (
                    CellarStatus.IN_CELLAR
                    if idx < 2
                    else (CellarStatus.WISHLIST if idx < 4 else CellarStatus.TASTED)
                )
                existing_cellar = await session.scalar(
                    select(UserCellar).where(
                        UserCellar.user_id == user.id,
                        UserCellar.wine_id == wine.id,
                        UserCellar.status == status,
                    )
                )
                if not existing_cellar:
                    cellar_item = UserCellar(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        wine_id=wine.id,
                        status=status,
                        bottles_count=2 if status == CellarStatus.IN_CELLAR else 1,
                        personal_rating=5 if idx == 0 else 4,
                        tasting_notes=(
                            f"Отличный образец российского виноделия ({wine.name}). "
                            "Прекрасный баланс и долгое послевкусие."
                        ),
                    )
                    session.add(cellar_item)
                    cellar_count += 1
            if cellar_count > 0:
                logger.info("Добавлено %d позиций в погреб пользователя %s", cellar_count, test_email)

            # 5. Создаем историю сканирований пользователя (идемпотентно)
            user_scans_exist = await session.scalar(
                select(UserScanHistory.id).where(UserScanHistory.user_id == user.id)
            )
            if not user_scans_exist:
                for idx, wine in enumerate(wines[:3]):
                    scan = UserScanHistory(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        image_id=str(uuid.uuid4()),
                        image_s3_key=f"scans/test_scan_{idx}.jpg",
                        predicted_slug=wine.slug,
                        confidence=0.96 - idx * 0.05,
                        latency_ms=120 + idx * 30,
                        device_fingerprint="fp_test_device_registered",
                        ip_address="127.0.0.1",
                        status=ScanStatus.SUCCESS,
                    )
                    session.add(scan)
                logger.info("Создана история сканирований для пользователя %s", test_email)

            # 6. Создаем гостевые сканы для демо-фингерпринта fp_guest_demo_123 (user_id = NULL)
            demo_fp = "fp_guest_demo_123"
            guest_scans_exist = await session.scalar(
                select(UserScanHistory.id).where(UserScanHistory.device_fingerprint == demo_fp)
            )
            if not guest_scans_exist and len(wines) >= 2:
                session.add(
                    UserScanHistory(
                        id=uuid.uuid4(),
                        user_id=None,
                        image_id=str(uuid.uuid4()),
                        image_s3_key="scans/guest_scan_1.jpg",
                        predicted_slug=wines[0].slug,
                        confidence=0.92,
                        latency_ms=140,
                        device_fingerprint=demo_fp,
                        ip_address="127.0.0.1",
                        status=ScanStatus.SUCCESS,
                    )
                )
                session.add(
                    UserScanHistory(
                        id=uuid.uuid4(),
                        user_id=None,
                        image_id=str(uuid.uuid4()),
                        image_s3_key="scans/guest_scan_2.jpg",
                        predicted_slug=wines[1].slug,
                        confidence=0.89,
                        latency_ms=155,
                        device_fingerprint=demo_fp,
                        ip_address="127.0.0.1",
                        status=ScanStatus.SUCCESS,
                    )
                )
                logger.info("Созданы гостевые сканы для фингерпринта %s", demo_fp)

            # 7. Создаем историю предпочтений сомелье (идемпотентно)
            pref_exist = await session.scalar(
                select(UserPreferenceHistory.id).where(UserPreferenceHistory.user_id == user.id)
            )
            if not pref_exist:
                pref = UserPreferenceHistory(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    session_id=str(uuid.uuid4()),
                    raw_answers={
                        "category": "Красное",
                        "sweetness": "Сухое",
                        "body_oak": "Мощное, с благородным дубом и танинами",
                        "acidity": "Больше мягкости",
                        "aromas": "Спелые ягоды и вишня",
                    },
                    recommended_slugs=[w.slug for w in wines[:3]],
                )
                session.add(pref)
                logger.info("Создана история диалогов с сомелье для %s", test_email)

            await session.commit()
            logger.info("Тестовые данные успешно проверены и синхронизированы с БД!")
    finally:
        await close_db()


if __name__ == "__main__":
    asyncio.run(seed_test_data())
