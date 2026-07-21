from __future__ import annotations

import sys
from pathlib import Path

import pypdfium2 as pdfium


source = Path(sys.argv[1]).resolve()
output_dir = Path(sys.argv[2]).resolve()
output_dir.mkdir(parents=True, exist_ok=True)
document = pdfium.PdfDocument(source)
for index in range(len(document)):
    image = document[index].render(scale=2).to_pil()
    image.save(output_dir / f"page-{index + 1}.png")
print(f"rendered_pages={len(document)}")
