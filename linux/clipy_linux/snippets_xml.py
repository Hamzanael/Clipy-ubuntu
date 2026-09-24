"""Snippet import/export in the same XML format as the macOS app.

    <folders>
      <folder>
        <title>Folder</title>
        <snippets>
          <snippet><title>Title</title><content>Body</content></snippet>
        </snippets>
      </folder>
    </folders>
"""

import xml.etree.ElementTree as ET


def export_snippets(db):
    root = ET.Element("folders")
    for folder, snippets in db.folder_details():
        folder_el = ET.SubElement(root, "folder")
        ET.SubElement(folder_el, "title").text = folder.title
        snippets_el = ET.SubElement(folder_el, "snippets")
        for snippet in snippets:
            snippet_el = ET.SubElement(snippets_el, "snippet")
            ET.SubElement(snippet_el, "title").text = snippet.title
            ET.SubElement(snippet_el, "content").text = snippet.content
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def import_snippets(db, xml_text):
    """Append the folders in `xml_text` to the database. Returns the folder count."""
    root = ET.fromstring(xml_text)
    count = 0
    for folder_el in root.findall("folder"):
        folder_id = db.add_folder(folder_el.findtext("title") or "untitled folder")
        for snippet_el in folder_el.findall("snippets/snippet"):
            db.add_snippet(
                folder_id,
                snippet_el.findtext("title") or "untitled snippet",
                snippet_el.findtext("content") or "",
            )
        count += 1
    return count
