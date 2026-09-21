import hashlib
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.exceptions import AppError

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SYSTEM_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_UPLOAD_DIR = SYSTEM_ROOT / "data" / "uploads"
DEFAULT_TEMP_DIR = SYSTEM_ROOT / "data" / "temp"
MIME_TYPES = {
    ".pdf": ("PDF", "application/pdf"),
    ".docx": ("DOCX", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xlsx": ("XLSX", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


@dataclass(frozen=True)
class StoredFile:
    path: Path
    file_type: str
    size: int
    checksum_sha256: str
    original_name: str


class FileStorageService:
    def __init__(self, upload_dir: Path = DEFAULT_UPLOAD_DIR, temp_dir: Path = DEFAULT_TEMP_DIR,
                 max_bytes: int = MAX_UPLOAD_BYTES):
        self.upload_dir = upload_dir.resolve()
        self.temp_dir = temp_dir.resolve()
        self.max_bytes = max_bytes
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _inside(path: Path, parent: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(parent.resolve()):
            raise AppError(500, "FILE_STORAGE_ERROR", "文件存储操作未完成")
        return resolved

    @staticmethod
    def _validate_name(name: str | None) -> tuple[str, str, str]:
        if not name or any(char in name for char in ("\x00", "\r", "\n")) or Path(name).name != name or "/" in name or "\\" in name:
            raise AppError(422, "VALIDATION_ERROR", "文件名不符合要求")
        extension = Path(name).suffix.lower()
        if extension not in MIME_TYPES:
            raise AppError(415, "UNSUPPORTED_FILE_TYPE", "仅支持 PDF、DOCX 和 XLSX 文件")
        file_type, expected_mime = MIME_TYPES[extension]
        return extension, file_type, expected_mime

    @staticmethod
    def _validate_signature(path: Path, file_type: str) -> None:
        try:
            if file_type == "PDF":
                with path.open("rb") as stream:
                    valid = stream.read(5) == b"%PDF-"
            else:
                with zipfile.ZipFile(path) as archive:
                    names = {name.replace("\\", "/").lower() for name in archive.namelist()}
                    required = {"[content_types].xml", "word/document.xml"} if file_type == "DOCX" else {
                        "[content_types].xml", "xl/workbook.xml"}
                    macro = any(name.endswith("vbaproject.bin") or "/macrosheets/" in f"/{name}" for name in names)
                    valid = required <= names and not macro
        except (OSError, zipfile.BadZipFile):
            valid = False
        if not valid:
            raise AppError(415, "UNSUPPORTED_FILE_TYPE", "文件内容与允许的文件类型不匹配")

    async def save_upload(self, upload: UploadFile) -> StoredFile:
        extension, file_type, expected_mime = self._validate_name(upload.filename)
        if upload.content_type != expected_mime:
            raise AppError(415, "UNSUPPORTED_FILE_TYPE", "文件 MIME 类型与扩展名不匹配")
        temp_path = self._inside(self.temp_dir / f"{uuid4()}.uploading", self.temp_dir)
        final_path = self._inside(self.upload_dir / f"{uuid4()}{extension}", self.upload_dir)
        size = 0
        digest = hashlib.sha256()
        try:
            with temp_path.open("xb") as stream:
                while chunk := await upload.read(64 * 1024):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise AppError(413, "FILE_TOO_LARGE", "文件大小不能超过 20 MiB")
                    stream.write(chunk)
                    digest.update(chunk)
            if size == 0:
                raise AppError(415, "UNSUPPORTED_FILE_TYPE", "文件不能为空")
            self._validate_signature(temp_path, file_type)
            os.replace(temp_path, final_path)
            return StoredFile(final_path, file_type, size, digest.hexdigest(), upload.filename)
        except AppError:
            temp_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise AppError(500, "FILE_STORAGE_ERROR", "文件存储操作未完成") from exc
        finally:
            await upload.close()

    def quarantine(self, path_value: str) -> tuple[Path, Path]:
        source = self._inside(Path(path_value), self.upload_dir)
        if not source.is_file():
            raise AppError(500, "FILE_STORAGE_ERROR", "文件存储操作未完成")
        isolated = self._inside(self.temp_dir / f"delete-{uuid4()}{source.suffix}", self.temp_dir)
        try:
            os.replace(source, isolated)
        except OSError as exc:
            raise AppError(500, "FILE_STORAGE_ERROR", "文件存储操作未完成") from exc
        return source, isolated

    @staticmethod
    def restore(source: Path, isolated: Path) -> None:
        try:
            os.replace(isolated, source)
        except OSError as exc:
            raise AppError(500, "FILE_STORAGE_ERROR", "文件存储操作未完成") from exc

    @staticmethod
    def remove_exact(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise AppError(500, "FILE_STORAGE_ERROR", "文件存储操作未完成") from exc
