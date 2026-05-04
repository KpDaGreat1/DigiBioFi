from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.storage import storage


def _upload_path_from_url(value: str) -> Path | None:
    return storage.resolve_url(value)


def collect_user_file_paths(user) -> list[Path]:
    paths: set[Path] = set()
    profile = user.profile

    if profile:
        for attr in (
            "profile_image",
            "resume_pdf",
            "profile_image_2",
            "profile_image_3",
            "custom_background_url",
            "custom_header_url",
        ):
            path = _upload_path_from_url(getattr(profile, attr, ""))
            if path:
                paths.add(path)

        for education in getattr(profile, "educations", []):
            path = _upload_path_from_url(education.certificate_url)
            if path:
                paths.add(path)

        for project in getattr(profile, "projects", []):
            path = _upload_path_from_url(project.thumbnail_url)
            if path:
                paths.add(path)

        if profile.slug:
            paths.add(settings.upload_path / "qr_codes" / f"{profile.slug}.png")

        if getattr(profile, "qr_code", None) and profile.qr_code.image_path:
            paths.add(settings.upload_path / profile.qr_code.image_path)

    for pattern in (
        f"profile_images/profile_{user.id}_*",
        f"resumes/resume_{user.id}_*",
        f"resume_previews/resume_preview_{user.id}.png",
        f"project_thumbnails/project_{user.id}_*",
        f"certificates/cert_{user.id}_*",
    ):
        paths.update(Path(settings.upload_dir).glob(pattern))

    return sorted(paths)


def delete_user_and_assets(user, db: Session) -> None:
    file_paths = collect_user_file_paths(user)
    db.delete(user)
    db.commit()

    for path in file_paths:
        if path.exists() and path.is_file():
            path.unlink()
