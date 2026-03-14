"""
Script to convert the AURA logo to Android app icon sizes
"""

import os

from PIL import Image

# Source image path
source_image = r"D:\PROJECTS\Aura_agent\image copy.png"

# Output directories and sizes
icon_sizes = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

# Base output directory
base_output_dir = r"D:\PROJECTS\Aura_agent\UI\app\src\main\res"

try:
    # Open the source image
    img = Image.open(source_image)
    print(f"✓ Loaded source image: {source_image}")
    print(f"  Original size: {img.size}")

    # Convert to RGBA if not already
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Generate icons for each density
    for density, size in icon_sizes.items():
        output_dir = os.path.join(base_output_dir, density)

        # Create directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Resize image
        resized = img.resize((size, size), Image.Resampling.LANCZOS)

        # Save as PNG for ic_launcher
        output_path = os.path.join(output_dir, "ic_launcher.png")
        resized.save(output_path, "PNG")
        print(f"✓ Created {density}/ic_launcher.png ({size}x{size})")

        # Save as PNG for ic_launcher_round (same image)
        output_path_round = os.path.join(output_dir, "ic_launcher_round.png")
        resized.save(output_path_round, "PNG")
        print(f"✓ Created {density}/ic_launcher_round.png ({size}x{size})")

    print("\n✓ All icon sizes generated successfully!")
    print("\nNote: The existing .webp files have been replaced with .png files.")
    print("You may want to delete the old .webp files manually.")

except FileNotFoundError:
    print(f"✗ Error: Source image not found at {source_image}")
except Exception as e:
    print(f"✗ Error: {str(e)}")
