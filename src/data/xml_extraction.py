import os
import re
import xml.etree.ElementTree as ET


def extract_labelled_xml(xml: os.PathLike, namespace):
    root = ET.parse(xml).getroot()

    shelfmarks = []
    titles = []
    authors = []

    text_line = f'./{namespace}TextLine/{namespace}TextEquiv/{namespace}Unicode'

    for tr in root.iter(namespace + 'TextRegion'):
        if re.search('shelfmark', tr.attrib['custom']):
            shelfmarks.append(tr.find(text_line).text)
            continue

        if re.search('title', tr.attrib['custom']):
            titles.append(tr.find(text_line).text)
            continue

        if re.search('author', tr.attrib['custom']):
            authors.append(tr.find(text_line).text)

    record = {'card_xml': xml, 'title': titles, 'author': authors, 'shelfmark': shelfmarks}

    return record