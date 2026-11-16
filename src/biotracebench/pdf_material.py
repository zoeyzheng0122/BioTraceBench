"""Complete, page-addressable text and PNG representations of PDF attachments."""
import importlib.metadata
from contextlib import closing
from .common import Stop, sha

RENDERING = {"dpi": 200, "format": "PNG", "color_mode": "RGB", "pages": "all",
             "additional_crop": [0, 0, 0, 0], "annotations": True, "forms": True}


def versions():
    try:
        import pypdfium2 as pdfium
    except ImportError:
        raise Stop("blocked_dependency", "pypdfium2==5.14.0 is required for PDF attachments") from None
    return {"parser": "pypdfium2", "parser_version": importlib.metadata.version("pypdfium2"),
            "pdfium_version": str(pdfium.version.PDFIUM_INFO)}


def prepare_pdf(source, folder, origin):
    identity = versions()
    import pypdfium2 as pdfium
    source_hash = sha(source)
    pages, images = [], []
    offset = 0
    try:
        with pdfium.PdfDocument(str(source)) as document:
            if pdfium.raw.FPDF_GetSecurityHandlerRevision(document) != -1:
                raise Stop("blocked_pdf", "Encrypted PDF attachment requires an unencrypted source")
            if len(document) < 1:
                raise Stop("blocked_pdf", "PDF attachment has no pages")
            document.init_forms()
            with (folder / "content.txt").open("w", encoding="utf-8", newline="") as text_file:
                for index in range(len(document)):
                    with closing(document[index]) as page:
                        with closing(page.get_textpage()) as text_page:
                            text = text_page.get_text_bounded(errors="strict")
                        marker = f"\n=== PDF page {index + 1} ===\n"
                        text_file.write(marker)
                        start = offset + len(marker)
                        text_file.write(text)
                        offset = start + len(text)
                        target = folder / f"page-{index + 1:05d}.png"
                        with closing(page.render(scale=RENDERING["dpi"] / 72, fill_color=(255, 255, 255, 255),
                                                 draw_annots=True, may_draw_forms=True)) as bitmap:
                            picture = bitmap.to_pil().convert("RGB")
                            try:
                                picture.save(target, format="PNG")
                                width, height = picture.size
                            finally:
                                picture.close()
                        images.append({"path": target.name, "origin": origin, "page": index + 1,
                                       "source_sha256": source_hash, "sha256": sha(target),
                                       "width": width, "height": height, "bytes": target.stat().st_size,
                                       "mime": "image/png"})
                        pages.append({"page": index + 1, "image_index": index, "text_start": start,
                                      "text_end": offset, "text_characters": len(text),
                                      "size_points": list(page.get_size()), "rotation": page.get_rotation()})
    except Stop:
        raise
    except Exception as exc:
        raise Stop("blocked_pdf", "PDF attachment could not be completely read: " + str(exc)) from exc
    return {"images": images, "pdf": {**identity, "rendering": RENDERING.copy(),
            "source_sha256": source_hash, "page_count": len(pages), "pages": pages}}


def validate_pdf(entry, folder):
    """Check complete page/image coverage without reparsing or uploading the PDF."""
    metadata = entry.get("pdf", {})
    pages, images = metadata.get("pages", []), entry.get("images", [])
    count = metadata.get("page_count")
    if (type(count) is not int or count < 1 or count != len(pages) or count != len(images)
            or metadata.get("rendering") != RENDERING or metadata.get("source_sha256") != entry.get("sha256")):
        raise Stop("blocked_materials", "Incomplete or incompatible PDF representation")
    # Path.read_text normalizes CRLF; explicit newline preserves PDF text offsets.
    with (folder / "content.txt").open(encoding="utf-8", newline="") as stream:
        content = stream.read()
    previous = 0
    for index, page in enumerate(pages):
        image = images[index]
        start, end = page.get("text_start"), page.get("text_end")
        if (page.get("page") != index + 1 or page.get("image_index") != index or image.get("page") != index + 1
                or type(start) is not int or type(end) is not int or not previous <= start <= end <= len(content)
                or page.get("text_characters") != end - start or not (folder / image["path"]).is_file()):
            raise Stop("blocked_materials", "Missing or invalid PDF page representation")
        previous = end
    if previous != len(content):
        raise Stop("blocked_materials", "PDF text coverage is incomplete")
