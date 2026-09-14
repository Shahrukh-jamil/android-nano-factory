import sys
import requests
import json
import os

if len(sys.argv) < 2:
    print("Error: No Gist ID provided.")
    sys.exit(1)

GIST_ID = sys.argv[1]
print(f"Fetching Gist: {GIST_ID}")

response = requests.get(f"https://api.github.com/gists/{GIST_ID}")
if response.status_code != 200:
    print(f"Failed to fetch Gist: {response.text}")
    sys.exit(1)

files = response.json().get('files', {})

config = {"appName": "My App", "packageId": "com.factory.app", "versionCode": 1}
if "config.json" in files:
    config.update(json.loads(files["config.json"]["content"]))

pkg_id = config["packageId"]
app_name = config["appName"]
v_code = str(config.get("versionCode", 1))

print(f"Injecting App: {app_name} ({pkg_id}) v{v_code}")

app_gradle_path = "app/build.gradle.kts"
with open(app_gradle_path, "r") as f:
    gradle_content = f.read()
gradle_content = gradle_content.replace("com.factory.placeholder", pkg_id)
gradle_content = gradle_content.replace("versionCode = 1", f"versionCode = {v_code}")
gradle_content = gradle_content.replace('versionName = "1.0"', f'versionName = "1.0.{v_code}"')
with open(app_gradle_path, "w") as f:
    f.write(gradle_content)

strings_path = "app/src/main/res/values/strings.xml"
os.makedirs(os.path.dirname(strings_path), exist_ok=True)
with open(strings_path, "w") as f:
    f.write(f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <string name="app_name">{app_name}</string>\n</resources>')

pkg_path = f"app/src/main/java/{pkg_id.replace('.', '/')}"
os.makedirs(pkg_path, exist_ok=True)

if "MainActivity.kt" in files:
    with open(f"{pkg_path}/MainActivity.kt", "w") as f:
        f.write(files["MainActivity.kt"]["content"])

if "GameView.kt" in files:
    with open(f"{pkg_path}/GameView.kt", "w") as f:
        f.write(files["GameView.kt"]["content"])

if "app_icon.xml" in files:
    icon_dir = "app/src/main/res/drawable"
    os.makedirs(icon_dir, exist_ok=True)
    with open(f"{icon_dir}/ic_launcher_foreground.xml", "w") as f:
        f.write(files["app_icon.xml"]["content"])

print("Injection Complete!")