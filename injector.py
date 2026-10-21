import sys, requests, json, os, re, shutil, base64

if len(sys.argv) < 2:
    print("Error: No Gist ID provided.")
    sys.exit(1)

GIST_ID = sys.argv[1]
print(f"Fetching Gist: {GIST_ID}")
response = requests.get(f"https://api.github.com/gists/{GIST_ID}")
if response.status_code != 200:
    print(f"Error fetching Gist: HTTP {response.status_code}")
    sys.exit(1)

files = response.json().get("files", {})

config = {
    "appName": "App",
    "packageId": "com.factory.app",
    "versionCode": 1,
    "orientation": "portrait",
    "minSdk": 24,
    "filament": False,
    "extraDependencies": []
}
if "config.json" in files:
    try:
        config.update(json.loads(files["config.json"]["content"]))
    except Exception as e:
        print(f"Warning: Failed to parse config.json: {e}")

pkg_id = config["packageId"]
app_name = config["appName"]
v_code = str(config.get("versionCode", 1))
orientation = config.get("orientation", "portrait")
min_sdk = str(config.get("minSdk", 24))

env_file = os.getenv("GITHUB_ENV")
if env_file:
    with open(env_file, "a") as f:
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "", app_name.replace(" ", ""))
        if not safe_name:
            safe_name = "App"
        f.write(f"APP_NAME={safe_name}\n")

print(f"Injecting App: {app_name} ({pkg_id}) v{v_code} [Orientation: {orientation}]")

# Auto-detect Filament usage or CMake native code
use_filament = bool(config.get("filament", False))
has_cmake = "CMakeLists.txt" in files
for fname, fdata in files.items():
    content_str = fdata.get("content", "")
    if (fname.endswith(".kt") or fname.endswith(".java")) and "com.google.android.filament" in content_str:
        use_filament = True

# 1. Tune gradle.properties for fast parallel 3D builds
with open("gradle.properties", "w") as gp:
    gp.write("org.gradle.jvmargs=-Xmx4096m -Dfile.encoding=UTF-8\n")
    gp.write("org.gradle.parallel=true\n")
    gp.write("org.gradle.caching=true\n")
    gp.write("android.useAndroidX=true\n")
    gp.write("android.nonTransitiveRClass=true\n")

# 2. Update Gradle config
app_gradle_path = "app/build.gradle.kts"
with open(app_gradle_path, "r") as f:
    gradle = f.read()

gradle = re.sub(r'applicationId\s*=\s*".*"', f'applicationId = "{pkg_id}"', gradle)
gradle = re.sub(r'namespace\s*=\s*".*"', f'namespace = "{pkg_id}"', gradle)
gradle = re.sub(r'versionCode\s*=\s*\d+', f'versionCode = {v_code}', gradle)
gradle = re.sub(r'versionName\s*=\s*".*"', f'versionName = "1.0.{v_code}"', gradle)
gradle = re.sub(r'minSdk\s*=\s*\d+', f'minSdk = {min_sdk}', gradle)

extra_deps_lines = []
if use_filament:
    print("-> Injecting Google Filament PBR Engine dependencies (v1.56.0)")
    extra_deps_lines.extend([
        '    implementation("com.google.android.filament:filament-android:1.56.0")',
        '    implementation("com.google.android.filament:gltfio-android:1.56.0")',
        '    implementation("com.google.android.filament:filament-utils-android:1.56.0")',
        '    implementation("com.google.android.filament:filamat-android:1.56.0")'
    ])

for dep in config.get("extraDependencies", []):
    extra_deps_lines.append(f'    implementation("{dep}")')

if extra_deps_lines:
    deps_block = "\n".join(extra_deps_lines)
    if "// EXTRA_DEPS_MARKER" in gradle:
        gradle = gradle.replace("// EXTRA_DEPS_MARKER", deps_block + "\n    // EXTRA_DEPS_MARKER")
    else:
        gradle = re.sub(r'(dependencies\s*\{)', r'\1\n' + deps_block, gradle, count=1)

if has_cmake and "externalNativeBuild" not in gradle:
    cmake_block = """
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
        }
    }
"""
    gradle = re.sub(r'(defaultConfig\s*\{)', cmake_block + r'\n    \1', gradle, count=1)

with open(app_gradle_path, "w") as f:
    f.write(gradle)

# 3. Update AndroidManifest.xml orientation
manifest_path = "app/src/main/AndroidManifest.xml"
if os.path.exists(manifest_path):
    with open(manifest_path, "r") as f:
        manifest = f.read()
    manifest = re.sub(r'android:screenOrientation="[^"]*"', f'android:screenOrientation="{orientation}"', manifest)
    with open(manifest_path, "w") as f:
        f.write(manifest)

# 4. Update Strings XML
strings_path = "app/src/main/res/values/strings.xml"
os.makedirs(os.path.dirname(strings_path), exist_ok=True)
with open(strings_path, "w") as f:
    f.write(f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <string name="app_name">{app_name}</string>\n</resources>')

# 5. Clean stale Java/Kotlin, Assets & C++ directories
java_root = "app/src/main/java"
if os.path.exists(java_root):
    shutil.rmtree(java_root)

assets_root = "app/src/main/assets"
if os.path.exists(assets_root):
    shutil.rmtree(assets_root)
os.makedirs(assets_root, exist_ok=True)

cpp_root = "app/src/main/cpp"
if os.path.exists(cpp_root):
    shutil.rmtree(cpp_root)

pkg_path = os.path.join(java_root, pkg_id.replace(".", "/"))
os.makedirs(pkg_path, exist_ok=True)

ASSET_EXTENSIONS = (
    ".glsl", ".vert", ".frag", ".comp", ".shader", ".wgsl",
    ".obj", ".mtl", ".gltf", ".ply", ".txt", ".csv", ".cfg", ".lua", ".ini"
)

def safe_b64decode(raw_str):
    cleaned = raw_str.strip().replace("\n", "").replace("\r", "").replace(" ", "")
    pad = len(cleaned) % 4
    if pad:
        cleaned += "=" * (4 - pad)
    return base64.b64decode(cleaned)

# 6. Inject Source Files, 3D Shaders, Meshes, Binary Assets, C++ JNI & Icons
for filename, file_data in files.items():
    if filename == "config.json":
        continue
    content = file_data.get("content", "")

    if filename == "app_icon.xml":
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

    elif filename.endswith(".kt") or filename.endswith(".java"):
        rel_parts = filename.split("__")
        target_dir = os.path.join(pkg_path, *rel_parts[:-1]) if len(rel_parts) > 1 else pkg_path
        os.makedirs(target_dir, exist_ok=True)
        with open(os.path.join(target_dir, rel_parts[-1]), "w") as f:
            f.write(content)

    elif filename == "CMakeLists.txt" or filename.endswith((".cpp", ".c", ".h", ".hpp")):
        os.makedirs(cpp_root, exist_ok=True)
        with open(os.path.join(cpp_root, filename), "w") as f:
            f.write(content)

    elif filename.startswith("res_raw_"):
        raw_dir = "app/src/main/res/raw"
        os.makedirs(raw_dir, exist_ok=True)
        raw_name = filename[len("res_raw_"):]
        if raw_name.endswith(".b64"):
            raw_name = raw_name[:-4]
            with open(os.path.join(raw_dir, raw_name), "wb") as f:
                f.write(safe_b64decode(content))
        else:
            with open(os.path.join(raw_dir, raw_name), "w") as f:
                f.write(content)

    elif filename.startswith("res_layout_") and filename.endswith(".xml"):
        layout_dir = "app/src/main/res/layout"
        os.makedirs(layout_dir, exist_ok=True)
        with open(os.path.join(layout_dir, filename[len("res_layout_"):]), "w") as f:
            f.write(content)

    elif filename.startswith("res_drawable_") and filename.endswith(".xml"):
        drawable_dir = "app/src/main/res/drawable"
        os.makedirs(drawable_dir, exist_ok=True)
        with open(os.path.join(drawable_dir, filename[len("res_drawable_"):]), "w") as f:
            f.write(content)

    elif filename.endswith(".b64"):
        asset_rel = filename[:-4].replace("__", "/")
        asset_path = os.path.join(assets_root, asset_rel)
        os.makedirs(os.path.dirname(asset_path), exist_ok=True)
        with open(asset_path, "wb") as f:
            f.write(safe_b64decode(content))
        print(f"-> Decoded binary 3D asset: assets/{asset_rel}")

    elif filename.endswith(ASSET_EXTENSIONS) or (filename.endswith(".json") and filename != "config.json"):
        asset_rel = filename.replace("__", "/")
        asset_path = os.path.join(assets_root, asset_rel)
        os.makedirs(os.path.dirname(asset_path), exist_ok=True)
        with open(asset_path, "w") as f:
            f.write(content)
        print(f"-> Injected 3D shader/asset: assets/{asset_rel}")

print("Injection Complete!")
