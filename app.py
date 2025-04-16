from flask import Flask, request, send_file, render_template_string
import os
import csv
from fpdf import FPDF
from datetime import datetime
import io
import zipfile
import tempfile


# ----- Original PDF logic adapted into functions -----

class PDF(FPDF):
    """
    Simple subclass of FPDF to add a header and footer.
    """

    def header(self):
        self.set_font("DejaVu", "", 10)
        with open("nastaveni/hlavicka.txt", "r", encoding="utf-8") as file:
            header_text = file.read()
        self.multi_cell(0, 8, header_text, align="L")

        # Add a line between header and content
        y_after_text = self.get_y()  # Get the current y position after the text
        self.line(10, y_after_text + 2, 200, y_after_text + 2)  # Draw the line slightly below the text
        self.ln(5)

        self.set_font("DejaVu", "", 16)
        self.cell(0, 10, "Potvrzení o přijaté platbě", ln=True, align="C")
        self.ln(5)


def generate_payment_pdf(row: dict) -> bytes:
    """
    Generates a single-page PDF (in memory) confirming payment information,
    based on the dictionary row from CSV. Returns PDF data as bytes.
    """

    pdf = PDF()
    pdf.add_font("DejaVu", "", "dejavu-sans/DejaVuSans.ttf", uni=True)
    pdf.add_page()
    pdf.set_font("DejaVu", "", 12)

    NOT_SPECIFIED = "neuvedeno"

    # Replace empty fields with NOT_SPECIFIED
    for key in row:
        if row[key] == "":
            row[key] = NOT_SPECIFIED

    # Extract fields from CSV row
    datum_zauctovani = row.get("Datum zaúčtování", NOT_SPECIFIED)
    nazev_protiuctu = row.get("Název protiúčtu", NOT_SPECIFIED)
    iban = row.get("IBAN", NOT_SPECIFIED)
    bic = row.get("BIC", NOT_SPECIFIED)
    protiucet = row.get("Protiúčet", NOT_SPECIFIED)
    bankovni_kod = row.get("Bankovní kód protiúčtu", NOT_SPECIFIED)
    jmeno_a_oddil = row.get("Zpráva pro příjemce", NOT_SPECIFIED)
    castka = row.get("Částka", NOT_SPECIFIED)
    mena = row.get("Měna", NOT_SPECIFIED)
    var_symbol = row.get("Variabilní symbol", NOT_SPECIFIED)

    pdf.multi_cell(0, 10,
                   "Potvrzujeme přijetí platby ve prospěch naší jednoty za níže uvedeného člena\n a pohybovou aktivitu.",
                   align="L"
                   )

    pdf.cell(0, 10, f"Jméno a pohybová aktivita: {jmeno_a_oddil}", ln=True)
    pdf.cell(0, 10, f"Rodné číslo (var. symbol): {var_symbol}", ln=True)

    pdf.ln(5)

    pdf.cell(0, 10, "Detail platby:", ln=True)
    pdf.cell(0, 10, f"Přijato dne: {datum_zauctovani}", ln=True)
    pdf.cell(0, 10, f"Částka: {castka} {mena}", ln=True)
    pdf.cell(0, 10, "Příjemce: Tělocvičná jednota Sokol Brno – Jundrov, IČO: 44995989", ln=True)

    # put the date and signature at the bottom of the page
    pdf.set_y(-40)
    current_y = pdf.get_y()
    # get the current date
    today = datetime.today().strftime('%d.%m.%Y')
    pdf.cell(0, 10, f"Datum vystavení: {today}", ln=True)

    # signature image
    pdf.image("nastaveni/podpis.jpg", x=150, y=current_y, w=40)

    # Return PDF as bytes
    return pdf.output(dest='S').encode('latin-1')


# ----- Flask Application -----

app = Flask(__name__)

# Simple upload form template
UPLOAD_FORM_TEMPLATE = """
<!doctype html>
<html>
<head>
    <title>CSV to PDFs</title>
</head>
<body>
    <h1>Upload CSV to Generate PDFs</h1>
    <form method="POST" action="/" enctype="multipart/form-data">
        <input type="file" name="csv_file" accept=".csv" required />
        <button type="submit">Convert to PDFs</button>
    </form>
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        # Show the upload form
        return render_template_string(UPLOAD_FORM_TEMPLATE)

    if request.method == "POST":
        # Handle the CSV upload
        uploaded_file = request.files.get("csv_file")
        if not uploaded_file:
            return "No file uploaded.", 400

        # We'll parse the CSV using the same assumptions (UTF-16, comma delimiter)
        csv_data = uploaded_file.read()

        # Create a temporary folder to store individual PDFs
        with tempfile.TemporaryDirectory() as temp_dir:
            # Convert the CSV data into rows
            # Because it's UTF-16, we decode first:
            decoded_csv = csv_data.decode("utf-16", errors="replace")
            reader = csv.DictReader(decoded_csv.splitlines(), delimiter=",")

            pdf_file_paths = []
            row_number = 0

            for row in reader:
                # Skip rows where the amount is negative
                amount = row.get("Částka", "")
                if amount.startswith('-'):
                    continue

                row_number += 1
                # Generate the PDF in memory
                pdf_bytes = generate_payment_pdf(row)

                # Build a filename based on row data
                datum_zauctovani = row.get("Datum zaúčtování", "").replace('.', '-')
                pdf_filename = f"row{row_number}_{datum_zauctovani}.pdf"

                # Write to temp folder
                output_path = os.path.join(temp_dir, pdf_filename)
                with open(output_path, 'wb') as f:
                    f.write(pdf_bytes)

                pdf_file_paths.append(output_path)

            # Now, zip all PDFs in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w') as zf:
                for pdf_path in pdf_file_paths:
                    arcname = os.path.basename(pdf_path)
                    zf.write(pdf_path, arcname=arcname)

            zip_buffer.seek(0)

            # Send the ZIP file back as a downloadable response
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name="pdf_confirmations.zip"
            )


if __name__ == "__main__":
    app.run(debug=True)
