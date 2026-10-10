import sys, requests, json, os, re, shutil

if len(sys.argv) < 2:
    print("Error: No Gist ID provided.")
    sys.exit(1)

GIST_ID = sys.argv[1]
print(f"Fetching Gist: {GIST_ID}")
response = requests.get(f"https://api.github.com/gists/{GIST_ID}")
files = response.json().get('files', {})

config = {"appName": "App", "packageId": "com.factory.app", "versionCode": 1}
if "config.json" in files:
    config.update(json.loads(files["config.json"]["content"]))

pkg_id = config["packageId"]
app_name = config["appName"]
v_code = str(config.get("versionCode", 1))

env_file = os.getenv('GITHUB_ENV')
if env_file:
    with open(env_file, 'a') as f:
        safe_name = app_name.replace(' ', '')
        f.write(f"APP_NAME={safe_name}\n")

print(f"Injecting App: {app_name} ({pkg_id}) v{v_code}")

# 1. Update Gradle config
app_gradle_path = "app/build.gradle.kts"
with open(app_gradle_path, "r") as f:
    gradle = f.read()
gradle = re.sub(r'applicationId\s*=\s*".*"', f'applicationId = "{pkg_id}"', gradle)
gradle = re.sub(r'namespace\s*=\s*".*"', f'namespace = "{pkg_id}"', gradle)
gradle = re.sub(r'versionCode\s*=\s*\d+', f'versionCode = {v_code}', gradle)
gradle = re.sub(r'versionName\s*=\s*".*"', f'versionName = "1.0.{v_code}"', gradle)
with open(app_gradle_path, "w") as f:
    f.write(gradle)

# 2. Update Strings XML
strings_path = "app/src/main/res/values/strings.xml"
os.makedirs(os.path.dirname(strings_path), exist_ok=True)
with open(strings_path, "w") as f:
    f.write(f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <string name="app_name">{app_name}</string>\n</resources>')

# 3. Clean stale Java/Kotlin files
java_root = "app/src/main/java"
if os.path.exists(java_root):
    shutil.rmtree(java_root)

pkg_path = os.path.join(java_root, pkg_id.replace('.', '/'))
os.makedirs(pkg_path, exist_ok=True)

# 4. Inject Source Files & Icons
for filename, file_data in files.items():
    content = file_data["content"]
    
    if filename.endswith(".kt") or filename.endswith(".java"):
        with open(os.path.join(pkg_path, filename), "w") as f:
            f.write(content)
            
    elif filename == "app_icon.xml":
        drawable_dir = "app/src/main/res/drawable"
        os.makedirs(drawable_dir, exist_ok=True)
        with open(os.path.join(drawable_dir, "ic_launcher_foreground.xml"), "w") as f:
            f.write(content)
        with open(os.path.join(drawable_dir, "ic_launcher.xml"), "w") as f:
            f.write(content)
            
        mipmap_dir = "app/src/main/res/mipmap-anydpi-v26"
        os.makedirs(mipmap_dir, exist_ok=True)
        adaptive_xml = '<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n    <background android:drawable="@color/ic_launcher_background"/>\n    <foreground android:drawable="@drawable/ic_launcher_foreground"/>\n</adaptive-icon>'
        with open(os.path.join(mipmap_dir, "ic_launcher.xml"), "w") as f:
            f.write(adaptive_xml)
        with open(os.path.join(mipmap_dir, "ic_launcher_round.xml"), "w") as f:
            f.write(adaptive_xml)
            
        values_dir = "app/src/main/res/values"
        os.makedirs(values_dir, exist_ok=True)
        with open(os.path.join(values_dir, "colors.xml"), "w") as f:
            f.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#0A0E14</color>\n</resources>')

print("Injection Complete!")
