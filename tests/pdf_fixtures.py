"""Small synthetic PDF documents, generated without runtime PDF authoring packages."""
import zlib


def pdf_bytes(pages=None):
    pages = pages or [{"text": "Supplement zero value 0"}]
    objects = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    def add(value):
        objects.append(value)
        return len(objects)
    def stream(data, attrs=b""):
        return b"<< /Length " + str(len(data)).encode() + b" " + attrs + b" >>\nstream\n" + data + b"\nendstream"
    kids = []
    for page in pages:
        content = b""
        if page.get("text"):
            for line_index, line in enumerate(page["text"].split("\n")):
                text = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                content += f"BT /F1 10 Tf 12 {220 - line_index * 20} Td (".encode() + text.encode("ascii") + b") Tj ET\n"
        resources = b"/Font << /F1 3 0 R >>"
        if page.get("scan"):
            pixels = bytes([255, 0, 0, 0, 0, 255, 0, 255, 0, 255, 255, 0])
            image = add(stream(zlib.compress(pixels), b"/Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode"))
            resources += b" /XObject << /Im1 " + str(image).encode() + b" 0 R >>"
            content += b"q 100 0 0 100 20 20 cm /Im1 Do Q\n"
        if page.get("chart"):
            content += b"q 1 0 0 rg 20 40 30 90 re f 0 0 1 rg 70 40 30 130 re f Q\n"
        drawing = add(stream(content))
        number = add(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 180 240] /Rotate " + str(page.get("rotation", 0)).encode()
                     + b" /Resources << " + resources + b" >> /Contents " + str(drawing).encode() + b" 0 R >>")
        kids.append(str(number).encode() + b" 0 R")
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Count " + str(len(kids)).encode() + b" /Kids [" + b" ".join(kids) + b"] >>"
    document = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(document))
        document.extend(str(index).encode() + b" 0 obj\n" + value + b"\nendobj\n")
    xref = len(document)
    document.extend(b"xref\n0 " + str(len(offsets)).encode() + b"\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(b"trailer\n<< /Size " + str(len(offsets)).encode() + b" /Root 1 0 R >>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n")
    return bytes(document)


def encrypted_pdf_bytes():
    import base64
    return base64.b64decode('JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgPDg3MjAwODkyYmY+Cj4+CmVuZG9iagoyIDAgb2JqCjw8Ci9UeXBlIC9QYWdlcwovQ291bnQgMQovS2lkcyBbIDQgMCBSIF0KPj4KZW5kb2JqCjMgMCBvYmoKPDwKL1R5cGUgL0NhdGFsb2cKL1BhZ2VzIDIgMCBSCj4+CmVuZG9iago0IDAgb2JqCjw8Ci9UeXBlIC9QYWdlCi9NZWRpYUJveCBbIDAgMCAxODAgMjQwIF0KL1JvdGF0ZSAwCi9SZXNvdXJjZXMgPDwKL0ZvbnQgPDwKL0YxIDUgMCBSCj4+Cj4+Ci9Db250ZW50cyA2IDAgUgovUGFyZW50IDIgMCBSCj4+CmVuZG9iago1IDAgb2JqCjw8Ci9UeXBlIC9Gb250Ci9TdWJ0eXBlIC9UeXBlMQovQmFzZUZvbnQgL0hlbHZldGljYQo+PgplbmRvYmoKNiAwIG9iago8PAovTGVuZ3RoIDU1Cj4+CnN0cmVhbQoseus5GsJx8ZFPQmrYlIKJJN3NcyQ1H6Dwe5iRVIfA+hM1Ucz4FPSQ1s7AJrxmmOqkYDTAwVVqCmVuZHN0cmVhbQplbmRvYmoKNyAwIG9iago8PAovViAyCi9SIDMKL0xlbmd0aCAxMjgKL1AgNDI5NDk2NzI5MgovRmlsdGVyIC9TdGFuZGFyZAovTyA8OTU1YWVkMTE2OGJlNzQ3YTk0MjliMWZjMjUwNDQ5NGQyNjdiZGYzY2NhMzhhOTc4OTc5ODg5NjNiMmUyOGU2OD4KL1UgPDc4YWIxZDU4NDdjMjEzOTJjYzIwYWRhNzhhMmE3YjVjMjhiZjRlNWU0ZTc1OGE0MTY0MDA0ZTU2ZmZmYTAxMDg+Cj4+CmVuZG9iagp4cmVmCjAgOAowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMTUgMDAwMDAgbiAKMDAwMDAwMDA1OSAwMDAwMCBuIAowMDAwMDAwMTE4IDAwMDAwIG4gCjAwMDAwMDAxNjcgMDAwMDAgbiAKMDAwMDAwMDMwNSAwMDAwMCBuIAowMDAwMDAwMzc1IDAwMDAwIG4gCjAwMDAwMDA0ODAgMDAwMDAgbiAKdHJhaWxlcgo8PAovU2l6ZSA4Ci9Sb290IDMgMCBSCi9JbmZvIDEgMCBSCi9JRCBbIDw2MzM5NjQzMDM4MzQzNTM5MzIzMDM4NjQ2MjM2MzU2NTMyMzczODM3MzkzMzY1MzkzODYxMzEzNzYyMzc2NjM4PiA8NjMzOTY0MzAzODM0MzUzOTMyMzAzODY0NjIzNjM1NjUzMjM3MzgzNzM5MzM2NTM5Mzg2MTMxMzc2MjM3NjYzOD4gXQovRW5jcnlwdCA3IDAgUgo+PgpzdGFydHhyZWYKNjk1CiUlRU9GCg==')
