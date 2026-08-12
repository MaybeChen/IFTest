from __future__ import annotations

from pathlib import Path
from typing import Any

from browser_ai_test.config import UploadConfig


class FileUploadError(RuntimeError):
    """A configured case attachment cannot be resolved or uploaded."""


def resolve_case_file(directory: Path, file_name: str) -> Path:
    """Resolve one case file while preventing traversal outside the upload root."""
    root = directory.expanduser().resolve()
    candidate = (root / file_name).resolve()
    if not candidate.is_relative_to(root):
        raise FileUploadError(f"文件路径不允许越过 upload.directory: {file_name!r}")
    if not candidate.is_file():
        raise FileUploadError(f"Case 文件不存在或不是普通文件: {candidate}")
    return candidate


async def upload_case_file(
    page: Any,
    file_name: str,
    config: UploadConfig,
    iframe_selector: str | None,
) -> Path:
    file_path = resolve_case_file(config.directory, file_name)
    if config.trigger_selector:
        await _upload_with_file_chooser(
            page, file_path, config, iframe_selector
        )
        return file_path
    locator = await _find_file_input(page, config, iframe_selector)
    try:
        # Upload components commonly keep several hidden inputs in the DOM.
        # Selecting one input avoids strict-mode errors and bypasses the native
        # file chooser, which otherwise blocks the following Case.
        await locator.first.set_input_files(str(file_path), timeout=config.timeout_ms)
    except Exception as exc:
        raise FileUploadError(
            f"上传文件失败 {file_path.name!r}, selector={config.input_selector!r}: {exc}"
        ) from exc
    return file_path


async def _upload_with_file_chooser(
    page: Any,
    file_path: Path,
    config: UploadConfig,
    iframe_selector: str | None,
) -> None:
    if config.target == "iframe":
        if not iframe_selector:
            raise FileUploadError("upload.target=iframe 时必须配置 system.iframe_selector")
        root = page.frame_locator(iframe_selector)
    else:
        root = page
    trigger = root.locator(config.trigger_selector)
    try:
        async with page.expect_file_chooser(timeout=config.timeout_ms) as chooser_info:
            await trigger.click(timeout=config.timeout_ms)
        chooser = await chooser_info.value
        await chooser.set_files(str(file_path))
    except Exception as exc:
        raise FileUploadError(
            f"通过文件选择器上传失败 {file_path.name!r}, trigger={config.trigger_selector!r}: {exc}"
        ) from exc


async def _find_file_input(
    page: Any, config: UploadConfig, iframe_selector: str | None
) -> Any:
    if config.target == "main":
        return page.locator(config.input_selector)
    if config.target == "iframe":
        if not iframe_selector:
            raise FileUploadError("upload.target=iframe 时必须配置 system.iframe_selector")
        return page.frame_locator(iframe_selector).locator(config.input_selector)

    main_locator = page.locator(config.input_selector)
    if await main_locator.count():
        return main_locator
    if iframe_selector:
        iframe_locator = page.frame_locator(iframe_selector).locator(config.input_selector)
        if await iframe_locator.count():
            return iframe_locator
    for frame in page.frames:
        frame_locator = frame.locator(config.input_selector)
        if await frame_locator.count():
            return frame_locator
    raise FileUploadError(f"主页面和 iframe 均未找到文件输入框: {config.input_selector!r}")
