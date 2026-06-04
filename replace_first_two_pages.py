from __future__ import annotations

from pathlib import Path
import shutil

import win32com.client


SOURCE = Path.home() / "OneDrive" / "Desktop" / "АБД курсовая работа.docx"
TARGET = Path.home() / "OneDrive" / "Desktop" / "Курсовая работа клиент Translazia FDO.docx"
BACKUP = Path.home() / "OneDrive" / "Desktop" / "Курсовая работа клиент Translazia FDO.backup-before-front-pages.docx"
PDF = Path.home() / "OneDrive" / "Desktop" / "Курсовая работа клиент Translazia FDO.pdf"

WD_GOTO_PAGE = 1
WD_GOTO_ABSOLUTE = 1
WD_EXPORT_PDF = 17
WD_STATISTIC_PAGES = 2
WD_FORMAT_ORIGINAL_FORMATTING = 16
WD_FORMAT_XML_DOCUMENT = 16


def page_range(document, first_page: int, after_last_page: int):
    start = document.GoTo(What=WD_GOTO_PAGE, Which=WD_GOTO_ABSOLUTE, Count=first_page).Start
    if after_last_page <= document.ComputeStatistics(WD_STATISTIC_PAGES):
        end = document.GoTo(What=WD_GOTO_PAGE, Which=WD_GOTO_ABSOLUTE, Count=after_last_page).Start
    else:
        end = document.Content.End
    return document.Range(Start=start, End=end)


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(SOURCE)
    if not TARGET.exists():
        raise FileNotFoundError(TARGET)

    shutil.copyfile(TARGET, BACKUP)

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        source_doc = word.Documents.Open(str(SOURCE), ReadOnly=True)
        target_doc = word.Documents.Open(str(TARGET), ReadOnly=False)

        source_first_two = page_range(source_doc, 1, 3)
        target_first_two = page_range(target_doc, 1, 3)

        source_first_two.Copy()
        target_first_two.Select()
        word.Selection.PasteAndFormat(WD_FORMAT_ORIGINAL_FORMATTING)

        target_doc.SaveAs2(str(TARGET), FileFormat=WD_FORMAT_XML_DOCUMENT)
        pages = target_doc.ComputeStatistics(WD_STATISTIC_PAGES)
        target_doc.ExportAsFixedFormat(str(PDF), WD_EXPORT_PDF)
        print(f"saved={TARGET}")
        print(f"backup={BACKUP}")
        print(f"pdf={PDF}")
        print(f"pages={pages}")

        target_doc.Close(False)
        source_doc.Close(False)
    finally:
        word.Quit()


if __name__ == "__main__":
    main()
