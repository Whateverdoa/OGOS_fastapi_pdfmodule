import math
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import CMYKColorSep, black # black is not used, could be removed
from reportlab.lib import pagesizes

def create_stepped_dieline_pdf(
    output_filename: str,
    dieline_width_mm: float,
    dieline_height_mm: float,
    corner_radius_mm: float = 0, # Added: Corner radius in millimeters
    step_x: int = 1,             # Number of items horizontally
    step_y: int = 1,             # Number of items vertically
    space_x_mm: float = 0,       # Horizontal space between items
    space_y_mm: float = 0,       # Vertical space between items
    spot_color_name: str = "stans",
    line_thickness_pt: float = 0.5, # Default line thickness set to 0.5 pt
    margin_mm: float = 10         # Margin around the entire stepped layout
):
    """
    Creates a PDF file with a stepped rectangular dieline, potentially with rounded corners.

    Args:
        output_filename: The name of the PDF file to create (e.g., "output_dieline.pdf").
        dieline_width_mm: Width of the single dieline rectangle in millimeters.
        dieline_height_mm: Height of the single dieline rectangle in millimeters.
        corner_radius_mm: Radius of the corners in millimeters (0 for sharp corners).
        step_x: Number of repetitions horizontally.
        step_y: Number of repetitions vertically.
        space_x_mm: Space between horizontal repetitions in millimeters.
        space_y_mm: Space between vertical repetitions in millimeters.
        spot_color_name: Name of the spot color to use for the dieline.
        line_thickness_pt: The thickness of the dieline in points.
        margin_mm: Margin around the content in millimeters.
    """
    if step_x <= 0 or step_y <= 0:
        print("Error: step_x and step_y must be positive integers.")
        return
    if dieline_width_mm <= 0 or dieline_height_mm <= 0:
        print("Error: dieline dimensions must be positive.")
        return
    if corner_radius_mm < 0:
        print("Error: corner_radius_mm cannot be negative.")
        return

    # Convert dimensions to points
    width_pt = dieline_width_mm * mm
    height_pt = dieline_height_mm * mm
    radius_pt = corner_radius_mm * mm
    space_x_pt = space_x_mm * mm
    space_y_pt = space_y_mm * mm
    margin_pt = margin_mm * mm

    # Validate radius against dimensions
    max_radius_pt = min(width_pt / 2, height_pt / 2)
    if radius_pt > max_radius_pt:
        print(f"Warning: Corner radius {corner_radius_mm}mm is too large for dimensions "
              f"{dieline_width_mm}x{dieline_height_mm}mm. "
              f"Reducing radius to {max_radius_pt / mm:.2f}mm.")
        radius_pt = max_radius_pt

    # Calculate total content size
    total_content_width_pt = (step_x * width_pt) + (max(0, step_x - 1) * space_x_pt)
    total_content_height_pt = (step_y * height_pt) + (max(0, step_y - 1) * space_y_pt)

    # Calculate page size including margins
    page_width_pt = total_content_width_pt + 2 * margin_pt
    page_height_pt = total_content_height_pt + 2 * margin_pt
    page_size = (page_width_pt, page_height_pt)

    # --- Create PDF ---
    c = canvas.Canvas(output_filename, pagesize=page_size)

    # --- Define Spot Color ---
    # Using 100% Magenta as fallback/screen representation
    # Use positional arguments for CMYK fallback: cyan, magenta, yellow, black
    stans_color = CMYKColorSep(
        spotName=spot_color_name,
        density=1.0,  # Use 100% of the color
        # Corrected: Positional arguments for CMYK (0, 1, 0, 0 = Magenta)
        cyan=0,  # cyan
        magenta=1,  # magenta
        yellow=0,  # yellow
        black=0  # black
    )

    # --- Set Drawing Properties ---
    c.setStrokeColor(stans_color)
    c.setFillColorCMYK(0, 0, 0, 0, alpha=0) # Transparent fill
    c.setLineWidth(line_thickness_pt) # Set the line thickness

    # --- Draw Rectangles ---
    start_drawing_y = page_height_pt - margin_pt - height_pt

    for j in range(step_y): # Vertical loop
        current_y = start_drawing_y - j * (height_pt + space_y_pt)
        current_x = margin_pt

        for i in range(step_x): # Horizontal loop
            # Use roundRect for drawing
            # roundRect(x, y, width, height, radius, stroke=1, fill=0)
            c.roundRect(current_x, current_y, width_pt, height_pt, radius_pt, stroke=1, fill=0)

            # Move to the next horizontal position
            current_x += width_pt + space_x_pt

    # --- Save PDF ---
    try:
        c.save()
        print(f"Successfully created PDF: {output_filename}")
        print(f"  Page size: {page_width_pt / mm:.2f} mm x {page_height_pt / mm:.2f} mm")
        print(f"  Dieline: {dieline_width_mm} mm x {dieline_height_mm} mm, Radius: {corner_radius_mm} mm")
        print(f"  Steps: {step_x} x {step_y}")
        print(f"  Spacing: {space_x_mm} mm (H) x {space_y_mm} mm (V)")
        print(f"  Spot Color: '{spot_color_name}', Line Width: {line_thickness_pt} pt")
    except Exception as e:
        print(f"Error saving PDF: {e}")

# --- Example Usage ---
if __name__ == "__main__":
    # Example with rounded corners and default 0.5pt line width
    create_stepped_dieline_pdf(
        output_filename="gestepte_stanslijn_rounded.pdf",
        dieline_width_mm=70,
        dieline_height_mm=50,
        corner_radius_mm=5, # 5mm corner radius
        step_x=3,
        step_y=1,
        space_x_mm=5,
        space_y_mm=10,
        spot_color_name="stans",
        # line_thickness_pt=0.5, # Not needed, uses default 0.5
        margin_mm=10
    )

    # Example "one up" with sharp corners (radius 0) and explicit 0.5pt line width
    create_stepped_dieline_pdf(
        output_filename="enkele_stanslijn_oneup_sharp.pdf",
        dieline_width_mm=80,
        dieline_height_mm=60,
        corner_radius_mm=0, # Explicitly sharp corners
        step_x=1,
        step_y=1,
        spot_color_name="CutContour",
        line_thickness_pt=0.5, # Explicitly set 0.5 pt
        margin_mm=5
    )

    # Example with a different radius and line width
    create_stepped_dieline_pdf(
        output_filename="custom_radius_linewidth.pdf",
        dieline_width_mm=100,
        dieline_height_mm=40,
        corner_radius_mm=2.0, # 2.0mm radius
        step_x=2,
        step_y=1,
        space_x_mm=10,
        spot_color_name="stans",
        line_thickness_pt=0.75, # Example: 0.75 pt line width
        margin_mm=10
    )