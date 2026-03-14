from PIL import Image
import os

# Source image
src = r'd:\PROJECTS\Aura_agent - Phase 2\UI\download.png'
base_path = r'd:\PROJECTS\Aura_agent - Phase 2\UI\app\src\main\res'

# Android mipmap sizes (launcher icon)
sizes = {
    'mipmap-mdpi': 48,
    'mipmap-hdpi': 72,
    'mipmap-xhdpi': 96,
    'mipmap-xxhdpi': 144,
    'mipmap-xxxhdpi': 192,
}

# Open and convert to RGBA
img = Image.open(src).convert('RGBA')

for folder, size in sizes.items():
    folder_path = os.path.join(base_path, folder)
    os.makedirs(folder_path, exist_ok=True)
    
    # Resize with high quality
    resized = img.resize((size, size), Image.LANCZOS)
    
    # Save both regular and round icons
    resized.save(os.path.join(folder_path, 'ic_launcher.png'), 'PNG')
    resized.save(os.path.join(folder_path, 'ic_launcher_round.png'), 'PNG')
    print(f'Created {size}x{size} icons in {folder}')

print('Done!')
