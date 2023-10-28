import os
import re
import json
from pdfminer.high_level import extract_text
from flask import render_template, Flask, request, jsonify, send_from_directory
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'

def clean_number(value):
    # Convert commas to dots
    value = value.replace(',', '.')

    # Remove other unwanted punctuation characters
    cleaned = re.sub(r'[-]', '', value)

    # Handle possible floating-point values to remove leading zeros after the conversion
    if '.' in cleaned:
        integer_part, decimal_part = cleaned.split('.')
        return f"{int(integer_part)}.{decimal_part}"
    else:
        # Remove leading zeros and return for integer values
        return str(int(cleaned))
def extract_pickup_address(pdf_path):
    text = extract_text(pdf_path)

    # List of potential labels for the pick-up address
    labels = ["Pick-up\s+address:", "Collect\s+From:", "Departure\s+:"]

    # Iterate over the labels to find a match
    for label in labels:
        pattern = rf'{label}(.*?)(?:VAT:|Contact:|UST-ID:|Recipient:)'
        match = re.search(pattern, text, re.DOTALL)

        if match:
            pick_up_address = match.group(1).strip()
            return pick_up_address

    return "Pick-up address not found!"
def extract_delivery_address(pdf_path):
    """
    Extracts the delivery address from the given PDF file.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        str: Extracted delivery address or a message if not found.
    """
    text = extract_text(pdf_path)

    # List of potential labels for the delivery address
    labels = ["Delivery\s+address:", "Deliver\s+To:", "Recipient:"]

    # Iterate over the labels to find a match
    for label in labels:
        # The pattern is designed to stop capturing at known terminators.
        pattern = rf'{label}(.*?)(?:Tel\.|Contact:|VAT\s+NO:|Shipper:|Tel:|Fax:|Email:|Flight|Versender)'
        match = re.search(pattern, text, re.DOTALL)

        if match:
            delivery_address = match.group(1).strip()
            return delivery_address

    return "Delivery address not found!"
def extract_shipper_from_pdf(pdf_path):
    text = extract_text(pdf_path)
    # Pattern to extract the shipper details based on "Versender:" label
    pattern_versender = r"(Versender\s?:\s?)([^\n]+)"
    match = re.search(pattern_versender, text)

    if match:
        return match.group(2).strip()

    # Pattern to extract the shipper details based on "Collect From:" label
    collect_pattern = r"Collect\s*From\s*:\s*\n\n([^\n]+)"
    match_collect = re.search(collect_pattern, text)

    # If found, return
    if match_collect:
        return match_collect.group(1).strip()

    # Pattern to extract the shipper details based on "Pick-up address:" label
    shipper_pattern = r"Pick-up\s*address\s*:\s*\n\n([^\n]+)"
    match_shipper = re.search(shipper_pattern, text)

    # If found, return
    if match_shipper:
        return match_shipper.group(1).strip()

    return "Shipper details not found!"
def extract_weight_from_pdf(pdf_path):
    text = extract_text(pdf_path)

    # Pattern to extract weight details
    weight_pattern = r'(\d+[,.\d]*)\s*(kgs?|KGS?)'

    match = re.search(weight_pattern, text)

    if match:
        weight_details = clean_number(match.group(1)) + " " + match.group(2).upper()
        return weight_details

    return "Weight details not found!"
def extract_volume_from_pdf(pdf_path):
    text = extract_text(pdf_path)

    # Pattern to extract volume details directly
    volume_pattern = r'(\d+[,.\d]*)\s*CBM'

    match = re.search(volume_pattern, text)

    if match:
        volume_details = clean_number(match.group(1)) + " CBM"
        return volume_details

    # Pattern to extract dimensions and calculate volume
    dims_pattern = r'Dims:\s*(\d+)\s*x\s*(\d+)\s*x\s*(\d+)\s*cm'

    match = re.search(dims_pattern, text)

    if match:
        length = int(match.group(1))
        width = int(match.group(2))
        height = int(match.group(3))

        # Calculate volume in cm^3
        volume = length * width * height

        # Convert volume to m^3
        volume_CBM = volume / 1000000

        # Convert to CBM for the final output
        volume_cbm = f"{volume_CBM:.6f} CBM"

        return volume_cbm

    return "Volume details not found!"
def extract_quantity_from_pdf(pdf_path):
    text = extract_text(pdf_path)

    # Patterns to check for
    patterns = [
        r'(\d+)\s*PCS',
        r'(\d+)\s*PIECES',
        r'Koli\s*:\s*(\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_number(match.group(1))

    return "Quantity details not found!"
def extract_remarks_from_pdf(pdf_path):
    text = extract_text(pdf_path)
    # Pattern to check for
    pattern = r'Remarks:\s*(.*?)(\n{2,}|$)'

    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return "Remarks details not found!"
def extract_instructions_from_pdf(pdf_path):
    text = extract_text(pdf_path)
    # Pattern to check for
    patterns = [
        r'Instructions:\s*(.*?)(\n{2,}|$)',
        r'The\s+instruction:\s*(.*?)(\n{2,}|$)'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return "Instructions details not found!"
def extract_description_of_goods_from_pdf(pdf_path):
    text = extract_text(pdf_path)

    patterns = [
        r"(?:Description\s*of\s*goods:)([^:]+?)(?:\n|$)",
        r"(?:Inhalt\s*:)([^:]+?)(?:\n|$)",
        r"(?:Description\s*of\s*goods:)([\s\S]+?)(?:Number\s*of\s*packages|Dangerous\s*goods:|Security\s*Status:|END)",
        r"(?:Description\s*of\s*goods:)([\s\S]+?)(?=\n)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Clean the matched text to remove unwanted lines and spaces
            cleaned = ' '.join([line.strip() for line in match.group(1).strip().split('\n') if line.strip()])
            if cleaned:
                return cleaned
    return "Description of goods details not found!"
def extract_dimensions_from_pdf(pdf_path):
    text = extract_text(pdf_path)

    # Pattern to match dimensions
    pattern = r"(\d+(\.\d+)?[xX]\d+(\.\d+)?[xX]\d+(\.\d+)?)(?:cm|CM|m|M)?"
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    return "Dimensions details not found!"
def extract_mawb_from_pdf(pdf_path):

    text = extract_text(pdf_path)

    pattern = r"MAWB[^\n\d]*([\d\s\-]+)?"
    matches = re.findall(pattern, text)

    for match in matches:
        if match and match.strip():  # check if match is not just whitespace
            return match.strip()
    return "MAWB details not found!"
def extract_hawb_from_pdf(pdf_path):
    text = extract_text(pdf_path)

    pattern = r"HAWB[^\n\d]*([\d\s\-]+)?"
    matches = re.findall(pattern, text)

    for match in matches:
        if match and match.strip():  # check if match is not just whitespace
            return match.strip()
    value = None

    if value is None:
        lines = text.split('\n')

        # Find the starting index of the search
        try:
            start_idx = lines.index("HAWB:")
        except ValueError:
            return "HAWB details not found!"

        # Start searching from the line after HAWB:
        for i in range(start_idx + 1, min(start_idx + 100, len(lines))):
            line = lines[i].strip()

            # Check for a numeric value
            if line.isdigit():
                return line

            # Check for an alphanumeric value starting with AFRAA
            if re.match(r"^AFRAA[A-Za-z0-9]+$", line):
                return line

    return "HAWB details not found!"
def extract_data_from_pdf(pdf_path):
    """
    Extract all relevant details from the PDF.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        dict: Dictionary containing all extracted details.
    """
    data = {}
    data['pickup_address'] = extract_pickup_address(pdf_path)
    data['delivery_address'] = extract_delivery_address(pdf_path)
    data['shipper'] = extract_shipper_from_pdf(pdf_path)
    data['weight'] = extract_weight_from_pdf(pdf_path)
    data['volume'] = extract_volume_from_pdf(pdf_path)
    data['quantity'] = extract_quantity_from_pdf(pdf_path)
    data['remarks'] = extract_remarks_from_pdf(pdf_path)
    data['instructions'] = extract_instructions_from_pdf(pdf_path)
    data['description_of_goods'] = extract_description_of_goods_from_pdf(pdf_path)
    data['dimensions'] = extract_dimensions_from_pdf(pdf_path)
    data['mawb'] = extract_mawb_from_pdf(pdf_path)
    data['hawb'] = extract_hawb_from_pdf(pdf_path)

    return data
def save_data_as_json(data, json_file):
    """
    Save extracted data to a JSON file.

    Args:
        data (dict): Dictionary containing extracted data.
        json_file (str): Path to save the JSON file.
    """
    with open(json_file, 'w') as f:
        json.dump(data, f, indent=4)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_pdf():
    # Check if the post request has the file part
    if 'file' not in request.files:
        return jsonify(error='No file part'), 400

    file = request.files['file']

    # Check if the user does not select file
    if file.filename == '':
        return jsonify(error='No selected file'), 400

    if file:
        filename = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filename)

        extracted_data = extract_data_from_pdf(filename)
        json_path = os.path.join(UPLOAD_FOLDER, file.filename + '.json')

        save_data_as_json(extracted_data, json_path)

        return send_from_directory(UPLOAD_FOLDER, file.filename + '.json', as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True)


