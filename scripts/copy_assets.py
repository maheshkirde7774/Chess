import os
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
icon_src = os.path.join(BASE_DIR, "frontend", "assets", "icon.png")
splash_src = os.path.join(BASE_DIR, "frontend", "assets", "splash.png")

res_dir = os.path.join(BASE_DIR, "android", "app", "src", "main", "res")

mipmaps = ["mipmap-hdpi", "mipmap-mdpi", "mipmap-xhdpi", "mipmap-xxhdpi", "mipmap-xxxhdpi"]
for m in mipmaps:
    target_dir = os.path.join(res_dir, m)
    if os.path.exists(target_dir):
        shutil.copyfile(icon_src, os.path.join(target_dir, "ic_launcher.png"))
        shutil.copyfile(icon_src, os.path.join(target_dir, "ic_launcher_round.png"))
        shutil.copyfile(icon_src, os.path.join(target_dir, "ic_launcher_foreground.png"))
        print(f"Updated {m} icons")

splash_dirs = [
    "drawable-port-hdpi", "drawable-port-mdpi", "drawable-port-xhdpi", "drawable-port-xxhdpi", "drawable-port-xxxhdpi",
    "drawable-land-hdpi", "drawable-land-mdpi", "drawable-land-xhdpi", "drawable-land-xxhdpi", "drawable-land-xxxhdpi"
]
for sd in splash_dirs:
    target_dir = os.path.join(res_dir, sd)
    if os.path.exists(target_dir):
        shutil.copyfile(splash_src, os.path.join(target_dir, "splash.png"))
        print(f"Updated {sd} splash")

print("All Android assets successfully configured!")
