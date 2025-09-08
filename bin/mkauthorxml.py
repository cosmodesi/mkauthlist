#!/usr/bin/env python3

"""
python script to create the author.xml file for a paper written by a large 
collaboration for an APS journal

The author.xml format is described here:
  https://github.com/inspirehep/author.xml
"""

import re
import sys
import os
from datetime import date
import xml.etree.ElementTree as ET
from xml.dom import minidom
from collections import OrderedDict
import argparse

def parse_name(full_name):
    """
    Splits a full name into given and family names, handling LaTeX 
    non-breaking spaces, multi-word family names (e.g., "de la Soul"),
    and formatting for initials.
    """
    # 1. Pre-process the name to handle LaTeX formatting
    # Replace non-breaking spaces (~) with standard spaces for splitting
    cleaned_name = full_name.replace('~', ' ')
    parts = cleaned_name.strip().split()

    if not parts:
        return "", ""
    if len(parts) == 1:
        return "", parts[0]

    # 2. Identify the family name by working backwards from the end
    family_name_parts = []
    split_index = len(parts)
    # Iterate backwards from the last word
    for i in range(len(parts) - 1, -1, -1):
        word = parts[i]
        # The last word is always part of the family name.
        # Preceding lowercase words (like 'de', 'la', 'von') are also part of it.
        if i == len(parts) - 1 or word.islower():
            family_name_parts.insert(0, word)
            split_index = i
        else:
            # We've reached the given names, so stop
            break
    
    # 3. Separate the given name parts from the family name parts
    given_name_parts = parts[:split_index]
    family_name = " ".join(family_name_parts)
    
    # 4. Format the given name (e.g., combine initials like "A. P." into "A.P.")
    given_name = "".join(given_name_parts)
    
    return given_name, family_name


def pretty_print_xml(elem):
    """
    Return a nicely formatted XML string for the Element.
    """

    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    # Return the XML part, without the <?xml...> declaration
    return reparsed.toprettyxml(indent="  ").splitlines(True)[1:]


def generate_collaboration_xml(latex_file, output_filename, publication_reference, collab_name, collab_id):
    """
    Parses a revtex LaTeX file to generate INSPIRE-HEP compliant 
    collaboration XML.
    """
    try:
        with open(latex_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: The file '{latex_file}' was not found.")
        sys.exit(1)

    ET.register_namespace('foaf', "http://xmlns.com/foaf/0.1/")
    ET.register_namespace('cal', "http://inspirehep.net/info/HepNames/tools/authors_xml/")
    
    lines = content.splitlines()
    authors_data = []
    
    unique_affiliations = OrderedDict()
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith(r'\affiliation{'):
            start_index = line.find(r'\affiliation{') + len(r'\affiliation{')
            brace_level = 1
            end_index = -1
            for j in range(start_index, len(line)):
                if line[j] == '{':
                    brace_level += 1
                elif line[j] == '}':
                    brace_level -= 1
                    if brace_level == 0:
                        end_index = j
                        break
            if end_index == -1: continue
            affiliation_text = line[start_index:end_index].strip()
            if affiliation_text not in unique_affiliations:
                unique_affiliations[affiliation_text] = f"aff{len(unique_affiliations) + 1}"

    current_author_group = []
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        if stripped_line.startswith(r'\author{'):
            start_index = line.find(r'\author{') + len(r'\author{')
            brace_level = 1
            end_index = -1
            for j in range(start_index, len(line)):
                if line[j] == '{':
                    brace_level += 1
                elif line[j] == '}':
                    brace_level -= 1
                    if brace_level == 0:
                        end_index = j
                        break
            if end_index == -1: continue
            full_content = line[start_index:end_index]
            name = full_content.strip()
            orcid = None
            orcid_match = re.search(r'\\orcidlink\{(.*?)\}', full_content)
            if orcid_match:
                orcid = orcid_match.group(1)
                name = full_content[:orcid_match.start()].strip()
            author_info = {'name': name, 'orcid': orcid, 'affiliations': []}
            authors_data.append(author_info)
            current_author_group.append(author_info)
        elif stripped_line.startswith(r'\affiliation{'):
            start_index = line.find(r'\affiliation{') + len(r'\affiliation{')
            brace_level = 1
            end_index = -1
            for j in range(start_index, len(line)):
                if line[j] == '{':
                    brace_level += 1
                elif line[j] == '}':
                    brace_level -= 1
                    if brace_level == 0:
                        end_index = j
                        break
            if end_index == -1: continue
            affiliation_text = line[start_index:end_index].strip()
            aff_id = unique_affiliations.get(affiliation_text)
            if aff_id:
                for author in current_author_group:
                    if aff_id not in author['affiliations']:
                        author['affiliations'].append(aff_id)
            next_line_is_affil = False
            for j in range(i + 1, len(lines)):
                future_line = lines[j].strip()
                if not future_line: continue
                if future_line.startswith(r'\affiliation{'):
                    next_line_is_affil = True
                break
            if not next_line_is_affil:
                 current_author_group = []

    # --- Build the XML structure ---
    ns = {'foaf': 'http://xmlns.com/foaf/0.1/', 'cal': 'http://inspirehep.net/info/HepNames/tools/authors_xml/'}
    root = ET.Element('collaborationauthorlist')

    ET.SubElement(root, f"{{{ns['cal']}}}creationDate").text = date.today().isoformat()
    ET.SubElement(root, f"{{{ns['cal']}}}publicationReference").text = publication_reference
    collaborations = ET.SubElement(root, f"{{{ns['cal']}}}collaborations")
    collaboration = ET.SubElement(collaborations, f"{{{ns['cal']}}}collaboration", {'id': collab_id})
    ET.SubElement(collaboration, f"{{{ns['foaf']}}}name").text = collab_name
    organizations = ET.SubElement(root, f"{{{ns['cal']}}}organizations")
    for text, org_id in unique_affiliations.items():
        org = ET.SubElement(organizations, f"{{{ns['foaf']}}}Organization", {'id': org_id})
        ET.SubElement(org, f"{{{ns['foaf']}}}name").text = text
    authors_xml = ET.SubElement(root, f"{{{ns['cal']}}}authors")
    
    # --- START OF XML GENERATION FIX ---
    # Reordered this loop to match the DTD specification
    for data in authors_data:
        person = ET.SubElement(authors_xml, f"{{{ns['foaf']}}}Person")
        
        # Parse full name into given and family names
        given_name, family_name = parse_name(data['name'])

        # Create elements in the order specified by author.dtd
        if given_name:
            ET.SubElement(person, f"{{{ns['foaf']}}}givenName").text = given_name
        
        # foaf:familyName is a required element
        ET.SubElement(person, f"{{{ns['foaf']}}}familyName").text = family_name
        
        # cal:authorNamePaper is a required element
        ET.SubElement(person, f"{{{ns['cal']}}}authorNamePaper").text = data['name']
        
        # Add affiliations if they exist
        if data['affiliations']:
            affs = ET.SubElement(person, f"{{{ns['cal']}}}authorAffiliations")
            for aff_id in data['affiliations']:
                ET.SubElement(affs, f"{{{ns['cal']}}}authorAffiliation", {'organizationid': aff_id, 'connection': ''})
        
        # Add ORCID if it exists
        if data['orcid']:
            ids = ET.SubElement(person, f"{{{ns['cal']}}}authorids")
            ET.SubElement(ids, f"{{{ns['cal']}}}authorid", {'source': 'ORCID'}).text = data['orcid']
    # --- END OF XML GENERATION FIX ---

    xml_header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    doctype_header = '<!DOCTYPE collaborationauthorlist SYSTEM "author.dtd">\n\n'
    xml_content_lines = pretty_print_xml(root)

    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(xml_header)
        f.write(doctype_header)
        f.writelines(xml_content_lines)

    print(f"Successfully created '{output_filename}'!")



def main():
    parser = argparse.ArgumentParser(description="Generate INSPIRE-HEP compliant author XML from a revtex LaTeX file.")
    
    parser.add_argument("latex_file", help="Path to the input LaTeX file (.tex).")
    parser.add_argument("-o", "--output", help="Path to the output XML file. Defaults to the input filename with a .xml extension.")
    parser.add_argument("-r", "--ref", default="https://arxiv.org/abs/2503.14739", help="The publication reference URL (e.g., arXiv link).")
    parser.add_argument("--collab-name", default="DESI", help="The name of the collaboration.")
    parser.add_argument("--collab-id", default="c1", help="The ID for the collaboration (e.g., c1).")
    
    args = parser.parse_args()

    if args.output:
        output_filename = args.output
    else:
        base_name = os.path.splitext(args.latex_file)[0]
        output_filename = f"{base_name}.xml"
        
    generate_collaboration_xml(
        latex_file=args.latex_file,
        output_filename=output_filename,
        publication_reference=args.ref,
        collab_name=args.collab_name,
        collab_id=args.collab_id
    )

if __name__ == "__main__":
    main()
