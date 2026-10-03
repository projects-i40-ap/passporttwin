from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


OUTPUT_PATH = Path(
    "demo/fixtures/PassportTwin_calibration_e2e_demo.pdf"
)


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    pdf = canvas.Canvas(
        str(OUTPUT_PATH),
        pagesize=A4,
    )

    pdf.setTitle("PassportTwin Calibration E2E Demo")

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(
        72,
        780,
        "Calibration Certificate"
    )

    pdf.setFont("Helvetica", 12)

    lines = [
        "Serial: PT-DEMO-001",
        "Calibration Date: 2026-10-01",
        "Due Date: 2027-10-01",
        "Max Error: 0.06",
        "Tolerance: 0.10",
    ]

    y = 730

    for line in lines:
        pdf.drawString(
            72,
            y,
            line
        )
        y -= 30

    pdf.save()

    print(
        f"Generated: {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()